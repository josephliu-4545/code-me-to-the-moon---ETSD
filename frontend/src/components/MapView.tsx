import { useEffect, useRef, useState } from "react";
import { Map as MLMap, Marker, NavigationControl, setWorkerUrl, type GeoJSONSource, type MapMouseEvent, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection } from "geojson";
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
}

interface Props {
  latitude: number;
  longitude: number;
  footprint: Footprint | null;
  onSelect: (lat: number, lon: number) => void;
  theme?: "dark" | "light";
}

const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
const STYLE: StyleSpecification = {
  version: 8,
  projection: { type: "globe" },
  sources: {
    bluemarble: {
      type: "raster",
      tiles: [`${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`],
      tileSize: 256,
      maxzoom: 8,
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
    { id: "background", type: "background", paint: { "background-color": "#13233D" } },
    { id: "bluemarble", type: "raster", source: "bluemarble", paint: { "raster-brightness-max": 0.9, "raster-saturation": -0.12, "raster-contrast": 0.05 } },
    { id: "features", type: "raster", source: "features", paint: { "raster-opacity": 0.5 } },
  ],
};

/** Theme treatments for the same NASA imagery: Orbit (night-side atmosphere) and Mission Briefing (daylit, paper space). */
const THEMES = {
  dark: {
    background: "#0a1826",
    brightnessMax: 1,
    saturation: 0.08,
    features: 0.18,
    sky: { "sky-color": "#02050a", "horizon-color": "#4899db", "fog-color": "#02050a", "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.9, 5, 0.45, 7, 0] },
  },
  light: {
    background: "#C9D4DE",
    brightnessMax: 1,
    saturation: 0,
    features: 0.75,
    sky: { "sky-color": "#E4E8EC", "horizon-color": "#9fc2df", "fog-color": "#F7F4EC", "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.75, 5, 0.35, 7, 0] },
  },
} as const;

function applyMapTheme(m: MLMap, theme: "dark" | "light") {
  const t = THEMES[theme];
  m.setPaintProperty("background", "background-color", t.background);
  m.setPaintProperty("bluemarble", "raster-brightness-max", t.brightnessMax);
  m.setPaintProperty("bluemarble", "raster-saturation", t.saturation);
  m.setPaintProperty("features", "raster-opacity", t.features);
  m.setSky(t.sky as unknown as Parameters<MLMap["setSky"]>[0]);
  m.setPaintProperty("footprint-line", "line-color", theme === "dark" ? "#F0C38A" : "#99612E");
  m.setPaintProperty("footprint-fill", "fill-color", theme === "dark" ? "#E7AE68" : "#99612E");
}

export function circlePolygon(lat: number, lon: number, radiusKm: number, steps = 72): [number, number][] {
  const coords: [number, number][] = [];
  const R = 6371.0088;
  const d = radiusKm / R;
  const φ1 = (lat * Math.PI) / 180;
  const λ1 = (lon * Math.PI) / 180;
  for (let i = 0; i <= steps; i++) {
    const θ = (2 * Math.PI * i) / steps;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(d) + Math.cos(φ1) * Math.sin(d) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(Math.sin(θ) * Math.sin(d) * Math.cos(φ1), Math.cos(d) - Math.sin(φ1) * Math.sin(φ2));
    coords.push([(((λ2 * 180) / Math.PI + 540) % 360) - 180, (φ2 * 180) / Math.PI]);
  }
  return coords;
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
    features: ring.length ? [{ type: "Feature", properties: { approximate: f.approximate ? 1 : 0 }, geometry: { type: "Polygon", coordinates: [ring] } }] : [],
  };
}

/** Map padding so the selected point sits in the visible area beside the floating dossier on wide screens. */
function mapPadding(el: HTMLElement | null) {
  const wide = !!el && el.clientWidth >= 960;
  return { top: wide ? 160 : 10, bottom: wide ? 40 : 10, right: wide ? 380 : 10, left: wide ? 190 : 10 };
}

function markerElement(): HTMLElement {
  const el = document.createElement("div");
  el.className = "atlas-marker";
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = '<span class="atlas-marker-pulse"></span><span class="atlas-marker-core"></span>';
  return el;
}

export default function MapView({ latitude, longitude, footprint, onSelect, theme = "dark" }: Props) {
  const themeRef = useRef(theme);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const marker = useRef<Marker | null>(null);
  const onSelectRef = useRef(onSelect);
  const footprintRef = useRef(footprint);
  const [failed, setFailed] = useState(false);
  const [projection, setProjection] = useState<"globe" | "mercator">("globe");

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
        zoom: container.current.clientWidth < 640 ? 0.85 : 1.65,
        attributionControl: { compact: true },
      });
    } catch {
      // WebGL unavailable: coordinates and place search in the dossier still work.
      queueMicrotask(() => setFailed(true));
      return;
    }
    m.addControl(new NavigationControl({ visualizePitch: false }), "bottom-right");
    // "style.load" fires once the style is parsed; "load" also waits for every initial tile,
    // which may never finish when imagery is slow or blocked — overlays must not depend on it.
    // Start with the compact attribution collapsed (still one tap away) so it does not cover small maps.
    const collapseAttribution = () => container.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
    m.once("load", collapseAttribution);
    m.once("idle", collapseAttribution);
    window.setTimeout(collapseAttribution, 900);
    m.once("style.load", () => {
      collapseAttribution();
      m.setPadding(mapPadding(container.current));
      m.jumpTo({ center: [longitude, latitude] });
      m.addSource("footprint", { type: "geojson", data: footprintGeoJSON(footprintRef.current) });
      m.addLayer({ id: "footprint-fill", type: "fill", source: "footprint", paint: { "fill-color": "#E7AE68", "fill-opacity": 0.14 } });
      m.addLayer({
        id: "footprint-line",
        type: "line",
        source: "footprint",
        paint: { "line-color": "#F0C38A", "line-width": 1.75, "line-dasharray": ["case", ["==", ["get", "approximate"], 1], ["literal", [2, 2]], ["literal", [1, 0]]] },
      });
      applyMapTheme(m, themeRef.current);
    });
    m.on("click", (e: MapMouseEvent) => onSelectRef.current(Number(e.lngLat.lat.toFixed(4)), Number(e.lngLat.wrap().lng.toFixed(4))));
    const onResize = () => m.setPadding(mapPadding(container.current));
    m.on("resize", onResize);
    marker.current = new Marker({ element: markerElement() }).setLngLat([longitude, latitude]).addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
    // The map is created once; later position changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const firstPosition = useRef(true);
  useEffect(() => {
    marker.current?.setLngLat([longitude, latitude]);
    // The initial position is applied when the style loads; only animate later selections.
    if (firstPosition.current) {
      firstPosition.current = false;
      return;
    }
    const m = map.current;
    if (m) {
      const zoom = m.getZoom();
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
    src?.setData(footprintGeoJSON(footprint));
  }, [footprint]);

  function changeProjection(type: "globe" | "mercator") {
    const m = map.current;
    if (!m?.isStyleLoaded()) return;
    m.setProjection({ type });
    setProjection(type);
  }

  if (failed) return <MapUnavailable />;

  return (
    <div className="map-wrap">
      <div ref={container} className="map" role="application" aria-label="World map. Click anywhere to choose a location. Coordinates can also be entered in the investigation panel." />
      <div className="earth-view-switch" role="group" aria-label="Earth view"><button type="button" aria-pressed={projection === "globe"} onClick={() => changeProjection("globe")}>3D Earth</button><button type="button" aria-pressed={projection === "mercator"} onClick={() => changeProjection("mercator")}>2D Map</button></div>
      <p className="map-hint">
        <span>Click or tap anywhere on Earth to choose a location.</span>
        {footprint && <span className="map-hint-fp"><span className="fp-key" aria-hidden /> {footprint.label}</span>}
      </p>
    </div>
  );
}
