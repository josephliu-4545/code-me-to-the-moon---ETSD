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
    radiusKm: num(p.get("r"), d.radiusKm, 0.5, 100),
    boxSpan: num(p.get("box"), d.boxSpan, 0.2, 5),
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
  if (s.variable === "precipitation" && s.mode === "region") p.set("box", String(s.boxSpan));
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
    radiusKm: s.radiusKm,
    dataset: s.dataset,
    bbox: s.variable === "precipitation" && s.mode === "region" ? selectionBox(s) : undefined,
  };
}

/** Latitude-longitude box of side boxSpan degrees centred on the selected point (clipped to valid ranges). */
export function selectionBox(s: Selection): [number, number, number, number] {
  const h = s.boxSpan / 2;
  const r = (v: number) => Number(v.toFixed(4));
  return [r(Math.max(-180, s.longitude - h)), r(Math.max(-90, s.latitude - h)), r(Math.min(180, s.longitude + h)), r(Math.min(90, s.latitude + h))];
}

/** Selection kept in sync with the URL query string so investigations are shareable. */
export function useSelection(): [Selection, (patch: Partial<Selection>) => void] {
  const [selection, setSelection] = useState<Selection>(() => parseSelection(window.location.search));

  useEffect(() => {
    const query = serializeSelection(selection);
    const url = `${window.location.pathname}?${query}${window.location.hash}`;
    window.history.replaceState(null, "", url);
  }, [selection]);

  const update = useCallback((patch: Partial<Selection>) => setSelection((s) => ({ ...s, ...patch })), []);
  return [selection, update];
}
