import { useId, useMemo, useState } from "react";
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, XAxis, YAxis } from "recharts";
import { fmt, signed } from "../../lib/format";
import { ols, theilSen } from "../../lib/robustStats";
import { CHART, tickStyle } from "../science/chartTheme";
import { OLS_COLOR } from "./MethodComparisonChart";

/** Deterministic SIMULATED data: a straight line (slope 0.5) plus fixed small wiggles. Not NASA data. */
export const SIM_STEPS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const WIGGLE = [0.3, -0.2, 0.1, -0.4, 0.2, 0, -0.1, 0.3, -0.3, 0.2, -0.2, 0.1];
export const SIM_BASE = SIM_STEPS.map((x, i) => 10 + 0.5 * x + WIGGLE[i]!);

export function simulate(outlierStep: number, offset: number) {
  const y = SIM_BASE.map((v, i) => (SIM_STEPS[i] === outlierStep ? v + offset : v));
  return { y, ols: ols(SIM_STEPS, y)!, theilSen: theilSen(SIM_STEPS, y)! };
}

export default function OutlierExperiment() {
  const id = useId();
  const [step, setStep] = useState(12);
  const [offset, setOffset] = useState(6);
  const base = useMemo(() => simulate(step, 0), [step]);
  const run = useMemo(() => simulate(step, offset), [step, offset]);
  const rows = SIM_STEPS.map((x, i) => ({
    x,
    sim: SIM_STEPS[i] === step ? null : run.y[i]!,
    outlier: SIM_STEPS[i] === step ? run.y[i]! : null,
    ols: run.ols.intercept + run.ols.slope * x,
    ts: run.theilSen.intercept + run.theilSen.slope * x,
  }));
  return (
    <div className="sim-panel" data-testid="outlier-simulation">
      <p className="sim-badge" role="note"><strong>Simulation</strong> — synthetic numbers for learning only. Not NASA data, not saved, and not part of your investigation.</p>
      <div className="sim-controls">
        <label className="field-label" htmlFor={`${id}-step`}>
          Outlier position (simulated step)
          <select id={`${id}-step`} value={step} onChange={(e) => setStep(Number(e.target.value))}>
            {SIM_STEPS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="field-label" htmlFor={`${id}-off`}>
          Outlier size: <strong className="mono">{signed(offset, 1)}</strong>
          <input id={`${id}-off`} type="range" min={-10} max={10} step={0.5} value={offset} onChange={(e) => setOffset(Number(e.target.value))} />
        </label>
      </div>
      <figure className="lab-figure" aria-label="Simulated data with one adjustable outlier and the OLS and Theil–Sen lines">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
            <XAxis dataKey="x" type="number" domain={[1, 12]} allowDecimals={false} tick={tickStyle} stroke={CHART.axis} label={{ value: "simulated step", position: "insideBottomRight", offset: -2, fill: CHART.tick, fontSize: 11 }} />
            <YAxis domain={["auto", "auto"]} tick={tickStyle} stroke={CHART.axis} width={48} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Scatter name="Simulated point" dataKey="sim" fill={CHART.obs} isAnimationActive={false} />
            <Scatter name="Simulated outlier" dataKey="outlier" fill="var(--warning)" isAnimationActive={false} />
            <Line name="Theil–Sen" dataKey="ts" stroke={CHART.trend} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Line name="OLS" dataKey="ols" stroke={OLS_COLOR} strokeWidth={2} strokeDasharray="7 4" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
      <div className="table-wrap">
        <table className="table" aria-live="polite">
          <thead><tr><th>Estimator (simulation)</th><th>Slope without outlier</th><th>Slope with outlier</th><th>Change</th></tr></thead>
          <tbody>
            <tr><td>OLS</td><td className="mono">{fmt(base.ols.slope, 4)}</td><td className="mono" data-testid="sim-ols">{fmt(run.ols.slope, 4)}</td><td className="mono">{signed(run.ols.slope - base.ols.slope, 4)}</td></tr>
            <tr><td>Theil–Sen</td><td className="mono">{fmt(base.theilSen.slope, 4)}</td><td className="mono" data-testid="sim-ts">{fmt(run.theilSen.slope, 4)}</td><td className="mono">{signed(run.theilSen.slope - base.theilSen.slope, 4)}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="note">
        OLS minimises squared distances, so one large deviation pulls the whole line; Theil–Sen takes the median of pairwise slopes, so one point changes it only a little.
        Points near the ends of the record have the most leverage. This illustrates estimator behaviour — it says nothing about any real place or about climate change.
      </p>
    </div>
  );
}
