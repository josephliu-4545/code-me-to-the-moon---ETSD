import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useState, useId } from "react";
import type { VariableId, VariableInfo } from "../api/types";
import { selectionBox, type Selection } from "../state/selection";
import { boxProblem, circleProblem, regionLimits } from "../lib/region";
import RegionBounds from "./explore/RegionBounds";
import type { LaunchPhase } from "../state/launch";

import PeriodTimeline from "./explore/PeriodTimeline";
import VariableGlyph from "./ui/VariableGlyph";

export const SOIL_DATASETS: { key: string; label: string; first: number; last?: number }[] = [
  { key: "gldas_2_1_noah_0_10cm", label: "GLDAS-2.1 Noah · 0–10 cm model layer (kg m⁻²)", first: 2000 },
  { key: "smap_l3e_v006_am", label: "SMAP L3 Enhanced V006 · ≈0–5 cm satellite (m³ m⁻³)", first: 2015 },
  { key: "smap_l3e_v005_am", label: "SMAP L3 Enhanced V005 · ≈0–5 cm satellite (m³ m⁻³)", first: 2015, last: 2023 },
];

const CURRENT_YEAR = new Date().getFullYear();

export function yearLimits(info: VariableInfo | undefined, s: Selection): { min: number; max: number; maxYears: number } {
  let min = info ? Number(info.available_from.slice(0, 4)) : 1981;
  const knownLast = info?.availability?.latest_observation ?? info?.availability?.documented_last;
  let max = knownLast ? Math.min(CURRENT_YEAR, Number(knownLast.slice(0, 4))) : CURRENT_YEAR;
  if (s.variable === "soil_moisture") {
    const product = info?.products?.find((d) => d.key === s.dataset);
    if (product) {
      min = Number(product.availability.documented_first.slice(0, 4));
      const last = product.availability.latest_observation ?? product.availability.documented_last;
      if (last) max = Math.min(max, Number(last.slice(0, 4)));
    }
    const ds = !product ? SOIL_DATASETS.find((d) => d.key === s.dataset) : undefined;
    if (ds) {
      min = Math.max(min, ds.first);
      if (ds.last) max = ds.last;
    }
  }
  return { min, max, maxYears: info?.max_years ?? 10 };
}

export function validateSelection(info: VariableInfo | undefined, s: Selection): string | null {
  const { min, max, maxYears } = yearLimits(info, s);
  if (!info) return "The signal catalog is unavailable.";
  if (s.variable === "soil_moisture" && !(info.products ?? SOIL_DATASETS).some((d) => d.key === s.dataset)) return "Choose a supported soil moisture product.";
  if (s.startYear > s.endYearInclusive) return "The start year must not be after the end year.";
  if (s.startYear < min || s.endYearInclusive > max) return `This dataset covers ${min}–${max}.`;
  if (s.endYearInclusive - s.startYear + 1 > maxYears) return `At most ${maxYears} years can be analysed at once for this variable.`;
  if (s.mode === "region" && info && !info.modes.region) return info.region_unsupported_reason ?? "Region analysis is not supported for this variable.";
  if (s.mode === "region" && info.region_shape === "bbox") {
    const limits = regionLimits(info);
    if (!limits) return "Region limits are unavailable. Reload the catalog.";
    return boxProblem(selectionBox(s), limits);
  }
  if (s.variable === "ndvi" && s.mode === "region") return circleProblem(s.latitude, s.radiusKm, info.max_radius_km ?? 0);
  return null;
}

interface Props {
  variables: VariableInfo[];
  selection: Selection;
  onChange: (patch: Partial<Selection>) => void;
  onAnalyze: () => void;
  busy: boolean;
  /** Compact live status (e.g. result summary) shown with the sticky action. */
  status?: React.ReactNode;
  phase?: LaunchPhase;
  launchRef?: React.RefObject<HTMLButtonElement | null>;
}

export default function AnalysisControls({ variables, selection, onChange, onAnalyze, busy, status, phase = "idle", launchRef }: Props) {
  const id = useId();
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(false);
  const [availabilityError, setAvailabilityError] = useState("");
  async function verifyAvailability() {
    setChecking(true); setAvailabilityError("");
    try { queryClient.setQueryData(["variables"], await api.variables(undefined, true)); }
    catch (error) { setAvailabilityError(error instanceof Error ? error.message : "Catalog verification failed."); }
    finally { setChecking(false); }
  }
  const info = variables.find((v) => v.id === selection.variable);
  const { min, max, maxYears } = yearLimits(info, selection);
  const years: number[] = [];
  for (let y = max; y >= min; y--) years.push(y);
  const problem = validateSelection(info, selection);
  const regionAllowed = info?.modes.region ?? false;

  return (
    <>
      <section className="step" aria-labelledby={`${id}-sig`}>
        <h2 id={`${id}-sig`} className="step-title"><span className="step-num" aria-hidden>02</span>Choose an Earth signal</h2>
        <div className="variable-grid" role="radiogroup" aria-label="Environmental variable">
          {variables.map((v) => {
            const active = v.id === selection.variable;
            return (
              <button
                key={v.id}
                type="button"
                role="radio"
                aria-checked={active}
                tabIndex={active ? 0 : -1}
                className={`variable-chip ${active ? "active" : ""}`}
                onClick={() => onChange({ variable: v.id as VariableId, mode: v.modes.region ? selection.mode : "point" })}
                onKeyDown={(e) => {
                  const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"];
                  if (!keys.includes(e.key)) return;
                  e.preventDefault();
                  const idx = variables.findIndex((x) => x.id === v.id);
                  const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
                  const next = variables[(idx + step + variables.length) % variables.length]!;
                  onChange({ variable: next.id as VariableId, mode: next.modes.region ? selection.mode : "point" });
                  const group = e.currentTarget.parentElement;
                  requestAnimationFrame(() => (group?.querySelector('[aria-checked="true"]') as HTMLElement | null)?.focus());
                }}
                title={v.description}
              >
                <VariableGlyph id={v.id as VariableId} />
                <span className="chip-name">{v.short_name}</span>
                <span className="chip-source">{v.dataset.source}</span>
              </button>
            );
          })}
        </div>
        {info && <p className="step-note">{info.description}</p>}
      </section>

      <section className="step" aria-labelledby={`${id}-per`}>
        <h2 id={`${id}-per`} className="step-title"><span className="step-num" aria-hidden>03</span>Set the investigation window</h2>
        <div className="years">
          <label className="field">
            <span className="field-label">From</span>
            <select value={selection.startYear} onChange={(e) => onChange({ startYear: Number(e.target.value) })}>
              {!years.includes(selection.startYear) && <option value={selection.startYear}>{selection.startYear} · outside record</option>}
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="field-label">To (inclusive)</span>
            <select value={selection.endYearInclusive} onChange={(e) => onChange({ endYearInclusive: Number(e.target.value) })}>
              {!years.includes(selection.endYearInclusive) && <option value={selection.endYearInclusive}>{selection.endYearInclusive} · outside record</option>}
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </div>
        <p className="step-note" role="note">{(selection.variable === "soil_moisture" ? info?.products?.find((d) => d.key === selection.dataset)?.availability : info?.availability)?.verification === "live_catalog_cached" ? "Catalog observation dates verified; local quality and completeness are checked after retrieval." : "Documented record. Latest usable observations are verified during retrieval; current and boundary years may be incomplete."}</p>
        <PeriodTimeline min={min} max={max} start={selection.startYear} end={selection.endYearInclusive} maxYears={maxYears} />

        {selection.variable === "soil_moisture" && (
          <label className="field">
            <span className="field-label">Dataset (analysed separately; never merged)</span>
            <select value={selection.dataset} onChange={(e) => onChange({ dataset: e.target.value })}>
              {(info?.products?.map((d) => ({ key: d.key, label: `${d.title} (${d.native_units})` })) ?? SOIL_DATASETS).map((d) => (
                <option key={d.key} value={d.key}>{d.label}</option>
              ))}
            </select>
          </label>
        )}

        {selection.variable === "soil_moisture" && <><button type="button" className="btn btn-ghost" disabled={checking} onClick={() => void verifyAvailability()}>{checking ? "Checking NASA catalog…" : "Verify latest product dates"}</button><p role="status" className="step-note">{availabilityError}</p></>}
        <fieldset className="field fieldset">
          <legend className="field-label">Spatial mode</legend>
          <div className="segmented">
            <button type="button" aria-pressed={selection.mode === "point"} className={selection.mode === "point" ? "active" : ""} onClick={() => onChange({ mode: "point" })}>
              Point
            </button>
            <button
              type="button"
              aria-pressed={selection.mode === "region"}
              className={selection.mode === "region" ? "active" : ""}
              disabled={!regionAllowed}
              onClick={() => onChange({ mode: "region" })}
            >
              Region
            </button>
          </div>
          {!regionAllowed && info?.region_unsupported_reason && <p className="step-note">Region: {info.region_unsupported_reason}</p>}
          {selection.mode === "region" && info?.region_shape === "bbox" && (
            <>
              <RegionBounds selection={selection} info={info} onChange={onChange} />
              {info.region_description && <p className="step-note">{info.region_description}</p>}
            </>
          )}
          {selection.mode === "region" && selection.variable === "ndvi" && (
            <label className="field">
              <span className="field-label">Radius: <strong className="mono">{selection.radiusKm} km</strong></span>
              <input
                type="number"
                min={0.001}
                max={info?.max_radius_km ?? 100}
                step="any"
                value={selection.radiusKm}
                onChange={(e) => onChange({ radiusKm: Number(e.target.value) })}
              />
            </label>
          )}
        </fieldset>
        {info?.geographic_limitations?.map((note) => <p className="step-note" key={note}>{note}</p>)}
        {info && <p className="step-note mono-note">Available from {info.available_from.slice(0, 4)} · up to {info.max_years} years per request · {info.spatial_resolution}</p>}
      </section>

      <div className="step step-go">
        {status}
        {problem && <p className="error-text" role="alert">{problem}</p>}
        <div className="launch-pad">
          <button ref={launchRef} type="button" className={`btn btn-primary btn-investigate ${phase === "ignition" ? "is-launching" : ""}`} onClick={onAnalyze} disabled={!!problem || busy}>
            <span className="step-num" aria-hidden>04</span>
            <span>{phase === "ignition" ? "Launching…" : busy ? "Analysis running…" : "Launch investigation"}</span>
            <svg className="launch-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M5 19c1.2-3.6 3.4-6.2 6-7.8M13.5 4.5c3.2-.9 5.4-.6 6 0 .6.6.9 2.8 0 6-1 3.6-4.6 7-8 8.5l-3-3-3-3c1.5-3.4 4.9-7 8-8.5z" />
              <circle cx="15.5" cy="8.5" r="1.4" />
              <path d="M4 20l2-.4" />
            </svg>
          </button>
        </div>
        <p className="launch-hint">{selection.variable === "ndvi" ? "Seasonal Sen slope and Seasonal Kendall test on quality-filtered MODIS observations." : "Theil–Sen slope on NASA data; significance is reported only when supported."}</p>
      </div>
    </>
  );
}
