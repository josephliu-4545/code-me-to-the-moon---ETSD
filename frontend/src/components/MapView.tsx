import { useEffect, useRef, useState } from "react";
import { Map as MLMap, Marker, NavigationControl, setWorkerUrl, type GeoJSONSource, type MapMouseEvent, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection } from "geojson";
import { createImageryStatus } from "../lib/imageryStatus";
import { attachRegionHandles, type EditableRegion } from "../lib/regionInteraction";
import { boxFromCorners, boxProblem, distanceKm } from "../lib/region";
import { circlePolygon, splitAtDateline } from "../lib/geometry";
import type { Bounds } from "../api/types";
import { MapUnavailable } from "./explore/MapBoundary";

setWorkerUrl(workerUrl);

export interface Footprint {
  kind: "cell" | "circle";
  bounds?: Bounds;
  center?: [number, number];
  radiusKm?: number;
  approximate?: boolean;
  label: string;
  confirmed?: boolean;
}

interface Props {
  latitude: number;
  longitude: number;
  footprint: Footprint | null;
  onSelect: (lat: number, lon: number) => void;
  theme?: "dark" | "light";
  region?: EditableRegion | null;
  onRegionChange?: (region: EditableRegion) => void;
}

const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
export const STYLE: StyleSpecification = {
  version: 8,
  projection: { type: "globe" },
  sources: {
    bluemarble: {
      type: "raster",
      tiles: [`${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`],
      tileSize: 256,
      maxzoom: 8,
      scheme: "xyz",
      attribution: "Imagery: NASA Blue Marble via NASA GIBS",
    },
    features: {
      type: "raster",
      tiles: [`${GIBS}/Reference_Features_15m/default/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`],
      tileSize: 256,
      maxzoom: 13,
      attribution: "Coastlines and borders: NASA GIBS (© OpenStreetMap contributors)",
    },
  },
  layers: [
    // Globe surface shown before (or without) imagery; space around the globe stays transparent so the starfield shows.
    { id: "background", type: "background", paint: { "background-color": "#082A46" } },
    { id: "bluemarble", type: "raster", source: "bluemarble", paint: { "raster-opacity": 1, "raster-fade-duration": 0, "raster-brightness-max": 1, "raster-saturation": 0, "raster-contrast": 0 } },
    { id: "features", type: "raster", source: "features", minzoom: 5, paint: { "raster-opacity": 0.5, "raster-fade-duration": 0 } },
  ],
};

/** Keep source radiometry identical in both midnight viewing modes. */
const THEMES = {
  dark: {
    background: "#082A46",
    brightnessMax: 1,
    saturation: 0,
    features: 0.5,
    sky: { "sky-color": "#121826", "horizon-color": "#41577A", "fog-color": "#010102", "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.25, 5, 0.15, 7, 0] },
  },
  light: {
    background: "#082A46",
    brightnessMax: 1,
    saturation: 0,
    features: 0.75,
    sky: { "sky-color": "#121826", "horizon-color": "#5878A7", "fog-color": "#090B12", "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.25, 5, 0.15, 7, 0] },
  },
} as const;

function applyMapTheme(m: MLMap, theme: "dark" | "light") {
  const t = THEMES[theme];
  m.setPaintProperty("background", "background-color", t.background);
  m.setPaintProperty("bluemarble", "raster-brightness-max", t.brightnessMax);
  m.setPaintProperty("bluemarble", "raster-saturation", t.saturation);
  m.setPaintProperty("features", "raster-opacity", t.features);
  m.setSky(t.sky as unknown as Parameters<MLMap["setSky"]>[0]);
  m.setPaintProperty("footprint-line", "line-color", theme === "dark" ? "#CDD5E1" : "#90A1BA");
  m.setPaintProperty("footprint-fill", "fill-color", theme === "dark" ? "#5878A7" : "#90A1BA");
}


function footprintGeoJSON(f: Footprint | null): FeatureCollection {
  if (!f) return { type: "FeatureCollection", features: [] };
  let ring: [number, number][] = [];
  if (f.kind === "cell" && f.bounds) {
    const b = f.bounds;
    ring = [[b.west, b.south], [b.east, b.south], [b.east, b.north], [b.west, b.north], [b.west, b.south]];
  } else if (f.kind === "circle" && f.center && f.radiusKm) {
    ring = circlePolygon(f.center[0], f.center[1], f.radiusKm);
  }
  return {
    type: "FeatureCollection",
    features: ring.length ? [{ type: "Feature", properties: { approximate: !f.confirmed || f.approximate ? 1 : 0 }, geometry: { type: "MultiPolygon", coordinates: splitAtDateline(ring).map((part) => [part]) } }] : [],
  };
}

/** Map padding so the selected point sits in the visible area beside the floating dossier on wide screens. */
function mapPadding(el: HTMLElement | null) {
  const wide = !!el && el.clientWidth >= 960;
  return { top: wide ? 40 : 10, bottom: wide ? 40 : 10, right: wide ? 40 : 10, left: wide ? Math.min(460, el!.clientWidth * 0.36) : 10 };
}

function markerElement(): HTMLElement {
  const el = document.createElement("div");
  el.className = "atlas-marker";
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = '<span class="atlas-target-halo"></span><span class="atlas-marker-pulse"></span><span class="atlas-target-ring"></span><span class="atlas-target-crosshair"></span><span class="atlas-marker-core"></span>';
  return el;
}

export default function MapView({ latitude, longitude, footprint, onSelect, theme = "dark", region = null, onRegionChange }: Props) {
  const themeRef = useRef(theme);
  const regionRef = useRef(region);
  const changeRegionRef = useRef(onRegionChange);
  const handles = useRef<ReturnType<typeof attachRegionHandles> | null>(null);
  const skipCamera = useRef<[number, number] | null>(null);
  const drawing = useRef(false);
  const firstCorner = useRef<[number, number] | null>(null);
  const [drawingBox, setDrawingBox] = useState(false);
  const [regionMessage, setRegionMessage] = useState("");
  const [ready, setReady] = useState(0);
  useEffect(() => { changeRegionRef.current = onRegionChange; }, [onRegionChange]);
  function changeRegion(next: EditableRegion) {
    skipCamera.current = next.kind === "circle" ? next.center : [(next.bounds[0]+next.bounds[2])/2, (next.bounds[1]+next.bounds[3])/2];
    regionRef.current = next;
    changeRegionRef.current?.(next);
  }
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const marker = useRef<Marker | null>(null);
  const onSelectRef = useRef(onSelect);
  const footprintRef = useRef(footprint);
  const [failed, setFailed] = useState(false);
  const [imageryError, setImageryError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!container.current) return;
    let m: MLMap;
    try {
      m = new MLMap({
        container: container.current,
        style: STYLE,
        center: [longitude, latitude],
        zoom: container.current.clientWidth < 640 ? 0.9 : 1.65,
        attributionControl: { compact: true },
      });
    } catch {
      // WebGL unavailable: coordinates and place search in the dossier still work.
      queueMicrotask(() => setFailed(true));
      return;
    }
    const onContextLost = () => setFailed(true);
    m.getCanvas().addEventListener("webglcontextlost", onContextLost);
    const imagery = createImageryStatus(setImageryError);
    m.on("error", (event) => {
      // MapLibre propagates sourceId from tile errors; unrelated map errors are not imagery outages.
      const sourceId = (event as typeof event & { sourceId?: string }).sourceId;
      if (sourceId === "bluemarble") imagery.failed();
    });
    m.on("sourcedata", (event) => {
      if (event.sourceId === "bluemarble" && event.tile?.state === "loaded") imagery.loaded();
    });
    m.addControl(new NavigationControl({ visualizePitch: false }), "bottom-right");
    // "style.load" fires once the style is parsed; "load" also waits for every initial tile,
    // which may never finish when imagery is slow or blocked — overlays must not depend on it.
    // Start with the compact attribution collapsed (still one tap away) so it does not cover small maps.
    const collapseAttribution = () => container.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
    m.once("load", collapseAttribution);
    m.once("idle", collapseAttribution);
    const attributionTimer = window.setTimeout(collapseAttribution, 900);
    m.once("style.load", () => {
      collapseAttribution();
      m.setPadding(mapPadding(container.current));
      m.jumpTo({ center: [longitude, latitude] });
      m.addSource("footprint", { type: "geojson", data: footprintGeoJSON(regionRef.current && !footprintRef.current?.confirmed ? null : footprintRef.current) });
      m.addLayer({ id: "footprint-fill", type: "fill", source: "footprint", paint: { "fill-color": "#5878A7", "fill-opacity": 0.14 } });
      m.addLayer({
        id: "footprint-line",
        type: "line",
        source: "footprint",
        paint: { "line-color": "#CDD5E1", "line-width": 1.75, "line-dasharray": ["case", ["==", ["get", "approximate"], 1], ["literal", [2, 2]], ["literal", [1, 0]]] },
      });
      m.addSource("selection", { type: "geojson", data: footprintGeoJSON(regionFootprint(regionRef.current)) });
      m.addLayer({ id: "selection-fill", type: "fill", source: "selection", paint: { "fill-color": "#5878A7", "fill-opacity": 0.22 } });
      m.addLayer({ id: "selection-line", type: "line", source: "selection", paint: { "line-color": "#EFF2F7", "line-width": 2 } });
      applyMapTheme(m, themeRef.current);
      setReady(n => n + 1);
    });
    m.on("click", (e: MapMouseEvent) => {
      if ((e.originalEvent.target as HTMLElement)?.closest(".region-handle")) return;
      const current = regionRef.current;
      if (drawing.current && current?.kind === "box") {
        const p: [number, number] = [e.lngLat.wrap().lng, e.lngLat.lat];
        if (!firstCorner.current) { firstCorner.current = p; setRegionMessage("Choose the opposite corner. Escape cancels."); return; }
        const bounds = boxFromCorners(firstCorner.current, p), problem = boxProblem(bounds, current.limits);
        if (problem) { setRegionMessage(problem); return; }
        changeRegion({ ...current, bounds }); firstCorner.current = null; drawing.current = false; setDrawingBox(false); setRegionMessage("Rectangle selected.");
        return;
      }
      onSelectRef.current(Number(e.lngLat.lat.toFixed(4)), Number(e.lngLat.wrap().lng.toFixed(4)));
    });
    const onResize = () => m.setPadding(mapPadding(container.current));
    m.on("resize", onResize);
    marker.current = new Marker({ element: markerElement() }).setLngLat([longitude, latitude]).addTo(m);
    map.current = m;
    return () => {
      handles.current?.dispose(); handles.current = null;
      window.clearTimeout(attributionTimer);
      imagery.dispose();
      m.getCanvas().removeEventListener("webglcontextlost", onContextLost);
      m.remove();
      map.current = null;
    };
    // The map is created once; later position changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const firstPosition = useRef(true);
  useEffect(() => {
    marker.current?.setLngLat([longitude, latitude]);
    const target = marker.current?.getElement();
    target?.setAttribute("title", `Selected coordinate ${latitude.toFixed(4)}, ${longitude.toFixed(4)}; not a measurement footprint`);
    if (target && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) target.animate?.([{opacity:0.35},{opacity:1}],{duration:350});
    const skip = skipCamera.current;
    skipCamera.current = null;
    if (skip?.[0] === longitude && skip[1] === latitude) return;
    // The initial position is applied when the style loads; only animate later selections.
    if (firstPosition.current) {
      firstPosition.current = false;
      return;
    }
    const m = map.current;
    if (m) {
      const zoom = Math.max(m.getZoom(), 3.2);
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      m.easeTo({ center: [longitude, latitude], zoom, duration: reduce ? 0 : 1100, padding: mapPadding(container.current) });
    }
  }, [latitude, longitude]);

  useEffect(() => {
    themeRef.current = theme;
    const m = map.current;
    if (m?.isStyleLoaded() && m.getLayer("footprint-line")) applyMapTheme(m, theme);
  }, [theme]);

  useEffect(() => {
    footprintRef.current = footprint;
    const src = map.current?.getSource("footprint") as GeoJSONSource | undefined;
    src?.setData(footprintGeoJSON(region && !footprint?.confirmed ? null : footprint));
  }, [footprint, region]);

  useEffect(() => {
    regionRef.current = region;
    (map.current?.getSource("selection") as GeoJSONSource | undefined)?.setData(footprintGeoJSON(regionFootprint(region)));
    if (region && handles.current) handles.current.sync(region);
  }, [region]);

  const regionKind = region?.kind;
  useEffect(() => {
    const m = map.current;
    drawing.current = false; firstCorner.current = null;
    queueMicrotask(() => { setDrawingBox(false); setRegionMessage(""); });
    if (!m || !regionRef.current || !m.getSource("selection")) return;
    handles.current = attachRegionHandles(m, regionRef.current, changeRegion, setRegionMessage, () => {});
    return () => { handles.current?.dispose(); handles.current = null; };
    // Rebuild only on spatial-mode changes, never on drag frames.
  }, [regionKind, ready]);

  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") { drawing.current = false; firstCorner.current = null; setDrawingBox(false); setRegionMessage("Drawing cancelled."); }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  if (failed) return <MapUnavailable onRetry={() => { setFailed(false); setImageryError(false); setAttempt((n) => n + 1); }} />;

  return (
    <div className="map-wrap">
      <div ref={container} className="map" role="application" aria-label="World map. Click anywhere to choose a location. Coordinates can also be entered in the investigation panel." />
      {imageryError && <div className="imagery-error" role="status"><span>NASA imagery unavailable</span><button type="button" onClick={() => { setImageryError(false); setAttempt((n) => n + 1); }}>Retry</button></div>}
      {region && <div className="region-tools">
        <button type="button" className="btn btn-ghost" onClick={() => {
          const points = region.kind === "box" ? [[region.bounds[0],region.bounds[1]], [region.bounds[2],region.bounds[3]]] : circlePolygon(region.center[1],region.center[0],region.radiusKm).map(([x,y]) => [x + 360*Math.round((region.center[0]-x)/360), y]);
          const xs = points.map(p => p[0]!), ys = points.map(p => p[1]!);
          map.current?.fitBounds([[Math.min(...xs),Math.min(...ys)],[Math.max(...xs),Math.max(...ys)]], { padding: mapPadding(container.current), maxZoom: 10, duration: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : 600 });
        }}>Frame selection</button>
        {region.kind === "box" && <button type="button" className="btn btn-ghost" aria-pressed={drawingBox} onClick={() => {
          drawing.current = !drawing.current; firstCorner.current = null; setDrawingBox(drawing.current);
          setRegionMessage(drawing.current ? "Choose the first corner, then the opposite corner. Escape cancels." : "Drawing cancelled.");
        }}>{drawingBox ? "Cancel drawing" : "Draw rectangle"}</button>}
        <span>{region.kind === "circle" ? `${region.radiusKm.toFixed(2)} km radius · valid pixels only` : boxLabel(region.bounds)}</span>
        <span className="region-status" role="status">{regionMessage || "Drag handles or edit numerical controls."}</span>
      </div>}
      <p className="map-hint">
        <span>NASA Blue Marble · reference imagery, not live measurements. Click or tap to select.</span>
        {footprint && <span className="map-hint-fp"><span className="fp-key" aria-hidden /> {footprint.confirmed ? "Confirmed analytical support" : "Requested sampling area"} · {footprint.label}</span>}
      </p>
    </div>
  );
}

function regionFootprint(r: EditableRegion | null): Footprint | null {
  if (!r) return null;
  if (r.kind === "box") { const [west,south,east,north] = r.bounds; return { kind: "cell", bounds: { west,south,east,north }, confirmed: true, label: "Requested region" }; }
  return { kind: "circle", center: [r.center[1], r.center[0]], radiusKm: r.radiusKm, confirmed: true, label: "Requested circle" };
}
function boxLabel([w,s,e,n]: [number,number,number,number]) {
  const lat = (s+n)/2;
  return `${(e-w).toFixed(3)}° × ${(n-s).toFixed(3)}° · ≈${distanceKm([w,lat],[e,lat]).toFixed(1)} × ${distanceKm([w,s],[w,n]).toFixed(1)} km`;
}
