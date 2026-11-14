import { useState } from "react";
import type { Analysis } from "../../api/types";
import { fmt } from "../../lib/format";
import { plainDependence } from "../../lib/evidence";
import { testName } from "../../lib/verdict";

/** Fixed, deterministic schematic noise (no randomness, so the illustration never changes). */
const NOISE = [0.6, -1.1, 0.9, -0.4, -1.3, 1.2, 0.2, -0.8, 1.4, -0.2, -1.0, 0.7, 0.3, -1.4, 1.1, -0.6, 0.5, -0.3, 1.0, -0.9];

export function schematicSeries(memory: number): number[] {
  const out: number[] = [];
  let prev = 0;
  for (const e of NOISE) {
    prev = memory * prev + e;
    out.push(prev);
  }
  return out;
}

function Spark({ values, label }: { values: number[]; label: string }) {
  const W = 220, H = 80;
  const lo = Math.min(...values), hi = Math.max(...values);
  const x = (i: number) => 8 + (i / (values.length - 1)) * (W - 16);
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo || 1)) * (H - 16);
  const runs = values.map((v, i) => (i > 0 && Math.sign(v) === Math.sign(values[i - 1]!) ? i : -1)).filter((i) => i > 0);
  return (
    <figure className="memory-spark">
      <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true" focusable="false">
        <path d={`M8 ${y(0)}H${W - 8}`} className="ms-zero" />
        {runs.map((i) => <path key={i} d={`M${x(i - 1)} ${y(values[i - 1]!)}L${x(i)} ${y(values[i]!)}`} className="ms-run" />)}
        <path d={values.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join("")} className="ms-line" />
        {values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="2.4" className="ms-dot" />)}
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

/** B4: why related neighbouring years make a significance test over-confident. */
export default function MemoryLab({ analysis }: { analysis: Analysis }) {
  const [memory, setMemory] = useState(0.75);
  const t = analysis.trend;
  const sd = t?.serial_dependence ?? null;
  const plain = plainDependence(sd);
  const rho = sd?.lag1_spearman_rho ?? null;
  const policy = (analysis.methodology.source as { trend_policy?: { material_lag1_rho?: number } } | null)?.trend_policy?.material_lag1_rho;
  const tested = !!t?.mann_kendall;
  return (
    <div className="xp-lab lab-memory">
      <div className="lab-stage">
        <p className="lab-badge">Educational example · invented series, not NASA data</p>
        <div className="memory-pair">
          <Spark values={schematicSeries(0)} label="Independent years: each year starts fresh." />
          <Spark values={schematicSeries(memory)} label="Years with memory: highs follow highs." />
        </div>
        <label className="memory-slider">
          <span>Year-to-year memory</span>
          <input type="range" min={0} max={0.95} step={0.05} value={memory} onChange={(e) => setMemory(Number(e.target.value))} aria-valuetext={`${Math.round(memory * 100)}% carried over`} />
          <span className="mono">{Math.round(memory * 100)}%</span>
        </label>
        <p className="lab-insight">Long runs above or below zero can look like a trend even when none exists. That is why a significance test needs care when years are related.</p>
      </div>
      <div className="lab-controls">
        <p className="lab-title">Why significance needs care</p>
        <div className={`memory-verdict tone-${plain.tone}`}>
          <span className="trace-label">In your result</span>
          <p className="memory-headline">{plain.headline}</p>
          <p className="memory-detail">{plain.detail}</p>
        </div>
        <div className="memory-scale" role="img" aria-label={rho === null ? "Lag-1 correlation not reported" : `Lag-1 residual correlation ${fmt(rho, 2)} on a scale from −1 to +1${policy !== undefined ? `; the screen flags values above ${policy}` : ""}`}>
          <span className="msc-track" />
          {policy !== undefined && <span className="msc-threshold" style={{ left: `${((policy + 1) / 2) * 100}%` }}><small>screen {policy}</small></span>}
          {rho !== null && <span className="msc-dot" style={{ left: `${((rho + 1) / 2) * 100}%` }}><small className="mono">ρ {fmt(rho, 2)}</small></span>}
          <span className="msc-ticks" aria-hidden="true"><i>−1</i><i>0</i><i>+1</i></span>
        </div>
        <dl className="lab-readout">
          <div><dt>Significance test</dt><dd>{tested ? `${testName(analysis)} reported` : "Not evaluated / reported"}</dd></div>
          {!tested && t?.significance_unavailable_reason && <div><dt>Reason (technical)</dt><dd>{t.significance_unavailable_reason}</dd></div>}
        </dl>
        {!tested && <p className="lab-real">Not evaluated is different from “not significant”: it means the test was not run, so it says nothing either way.</p>}
        {sd?.caveat && <p className="lab-footnote">{sd.caveat}</p>}
      </div>
    </div>
  );
}
