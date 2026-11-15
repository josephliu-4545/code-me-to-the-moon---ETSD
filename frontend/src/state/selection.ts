import { useCallback, useEffect, useState } from "react";
import type { AnalysisRequest, Mode, VariableId } from "../api/types";

export interface Selection {
  latitude: number;
  longitude: number;
  placeName: string;
  variable: VariableId;
  startYear: number;
  endYearInclusive: number;
  mode: Mode;
  radiusKm: number;
  boxSpan: number;
  bbox?: [number, number, number, number];
  dataset: string;
}

export const DEFAULT_SELECTION: Selection = {
  latitude: 16.8661,
  longitude: 96.1951,
  placeName: "Yangon, Myanmar",
  variable: "temperature",
  startYear: 2015,
  endYearInclusive: 2024,
  mode: "point",
  radiusKm: 5,
  boxSpan: 1,
  dataset: "gldas_2_1_noah_0_10cm",
};

const VARIABLES: VariableId[] = ["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"];

function num(v: string | null, fallback: number, min: number, max: number): number {
  const n = v === null ? NaN : Number(v);
  return Number.isFinite(n) && n >= min && n <= max ? n : fallback;
}

export function parseSelection(search: string): Selection {
  const p = new URLSearchParams(search);
  const d = DEFAULT_SELECTION;
  const variable = p.get("v") as VariableId | null;
  const mode = p.get("mode");
  return {
    latitude: num(p.get("lat"), d.latitude, -90, 90),
    longitude: num(p.get("lon"), d.longitude, -180, 180),
    placeName: p.get("place") ?? (p.has("lat") ? "" : d.placeName),
    variable: variable && VARIABLES.includes(variable) ? variable : d.variable,
    startYear: Math.round(num(p.get("from"), d.startYear, 1981, 2100)),
    endYearInclusive: Math.round(num(p.get("to"), d.endYearInclusive, 1981, 2100)),
    mode: mode === "region" ? "region" : "point",
    radiusKm: num(p.get("r"), d.radiusKm, Number.MIN_VALUE, Number.MAX_SAFE_INTEGER),
    boxSpan: num(p.get("box"), d.boxSpan, Number.MIN_VALUE, 360),
    bbox: parseBounds(p.get("bbox")),
    dataset: p.get("ds") ?? d.dataset,
  };
}

export function serializeSelection(s: Selection): string {
  const p = new URLSearchParams({
    lat: s.latitude.toFixed(4),
    lon: s.longitude.toFixed(4),
    v: s.variable,
    from: String(s.startYear),
    to: String(s.endYearInclusive),
    mode: s.mode,
  });
  if (s.placeName) p.set("place", s.placeName);
  if (s.variable === "ndvi" && s.mode === "region") p.set("r", String(s.radiusKm));
  if (s.variable === "soil_moisture") p.set("ds", s.dataset);
  if (s.variable === "precipitation" && s.mode === "region") {
    p.set("box", String(s.boxSpan));
    if (s.bbox) p.set("bbox", s.bbox.join(","));
  }
  return p.toString();
}

export function toRequest(s: Selection): AnalysisRequest {
  return {
    variable: s.variable,
    latitude: Number(s.latitude.toFixed(4)),
    longitude: Number(s.longitude.toFixed(4)),
    startYear: s.startYear,
    endYear: s.endYearInclusive + 1,
    mode: s.mode,
    radiusKm: s.variable === "ndvi" && s.mode === "region" ? s.radiusKm : undefined,
    dataset: s.variable === "soil_moisture" ? s.dataset : undefined,
    bbox: s.variable === "precipitation" && s.mode === "region" ? selectionBox(s) : undefined,
  };
}

export function requestIdentity(r: AnalysisRequest | null): string {
  if (!r) return "none";
  return JSON.stringify([r.variable, r.variable === "soil_moisture" ? r.dataset : null,
    r.latitude, r.longitude, r.mode, r.variable === "ndvi" && r.mode === "region" ? r.radiusKm : null,
    r.variable === "precipitation" && r.mode === "region" ? r.bbox : null, r.startYear, r.endYear]);
}

/** Latitude-longitude box of side boxSpan degrees centred on the selected point. Invalid edge boxes are rejected by validation, never clipped. */
export function selectionBox(s: Selection): [number, number, number, number] {
  if (s.bbox) return s.bbox;
  const h = s.boxSpan / 2;
  const r = (v: number) => Number(v.toFixed(4));
  return [r(s.longitude - h), r(s.latitude - h), r(s.longitude + h), r(s.latitude + h)];
}

function parseBounds(value: string | null): Selection["bbox"] {
  if (!value) return undefined;
  const values = value.split(",").map(Number);
  return values.length === 4 && values.every(Number.isFinite) ? values as NonNullable<Selection["bbox"]> : undefined;
}

/** Moving the location starts a new centered selection; explicit bounds stay authoritative. */
export function patchSelection(s: Selection, patch: Partial<Selection>): Selection {
  const reset = patch.bbox === undefined && (patch.latitude !== undefined || patch.longitude !== undefined || patch.boxSpan !== undefined);
  return { ...s, ...(reset ? { bbox: undefined } : {}), ...patch };
}

/** Selection kept in sync with the URL query string so investigations are shareable. */
export function useSelection(): [Selection, (patch: Partial<Selection>) => void] {
  const [selection, setSelection] = useState<Selection>(() => parseSelection(window.location.search));

  useEffect(() => {
    const query = serializeSelection(selection);
    const url = `${window.location.pathname}?${query}${window.location.hash}`;
    window.history.replaceState(null, "", url);
  }, [selection]);

  const update = useCallback((patch: Partial<Selection>) => setSelection((s) => patchSelection(s, patch)), []);
  return [selection, update];
}
