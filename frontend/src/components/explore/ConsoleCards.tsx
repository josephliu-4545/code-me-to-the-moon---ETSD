import type { Analysis } from "../../api/types";
import { fmt, pText, signed } from "../../lib/format";
import { periodLabel } from "../../lib/verdict";
import VariableGlyph from "../ui/VariableGlyph";

/** Annual sparkline. Missing years break the line; values are never interpolated. */
function Spark({ analysis }: { analysis: Analysis }) {
  const points = analysis.annual.filter((point) => point.value != null && Number.isFinite(point.value));
  if (points.length < 2) return <p className="console-empty">Not enough annual values to draw.</p>;
  const years = analysis.annual.map((point) => point.year);
  const firstYear = Math.min(...years);
  const lastYear = Math.max(...years);
  const values = points.map((point) => point.value as number);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const x = (year: number) => 8 + ((year - firstYear) / Math.max(1, lastYear - firstYear)) * 204;
  const y = (value: number) => 62 - ((value - low) / (high - low || 1)) * 50;
  const segments: string[] = [];
  let run: string[] = [];

  for (let year = firstYear; year <= lastYear; year += 1) {
    const point = points.find((candidate) => candidate.year === year);
    if (point) run.push(`${x(year).toFixed(1)},${y(point.value as number).toFixed(1)}`);
    else {
      if (run.length > 1) segments.push(run.join(" "));
      run = [];
    }
  }
  if (run.length > 1) segments.push(run.join(" "));

  return (
    <svg className="console-spark" viewBox="0 0 220 72" role="img" aria-label={`Annual values, ${firstYear} to ${lastYear}; gaps are years without a usable value`}>
      {segments.map((segment) => <polyline key={segment} points={segment} />)}
      {points.map((point) => <circle key={point.year} cx={x(point.year)} cy={y(point.value as number)} r={point.eligible ? 2.6 : 2} className={point.eligible ? "" : "is-excluded"} />)}
    </svg>
  );
}

/** At-a-glance console. Every displayed value comes from the returned analysis. */
export default function ConsoleCards({ analysis }: { analysis: Analysis }) {
  const trend = analysis.trend;
  const valuesAvailable = analysis.annual.filter((point) => point.value != null).length;
  const eligible = trend?.eligible_years.length ?? analysis.coverage.eligible_years;
  const requested = analysis.coverage.years_requested;
  const tested = trend?.result_level === "statistical_inference" && Boolean(trend.mann_kendall);
  const steps = [
    { name: "Observations retrieved", detail: `${valuesAvailable} annual values`, done: valuesAvailable > 0 },
    { name: "Quality screening", detail: `${eligible} of ${requested} years eligible`, done: eligible > 0 },
    { name: "Trend estimated", detail: trend?.slope != null ? `${signed(trend.slope, 3)} ${trend.slope_units ?? analysis.units.slope}` : "No slope available", done: trend?.slope != null },
    { name: "Significance test", detail: tested ? pText(trend!.mann_kendall!.p_value) : "Not reported", done: tested },
  ];
  const coveragePercent = requested > 0 ? Math.round((eligible / requested) * 100) : 0;

  return (
    <section className="console-row" aria-label="Investigation console">
      <article className="console-card">
        <header><span>Signal</span><span className="console-tag">{analysis.dataset.source}</span></header>
        <div className="console-glyph"><VariableGlyph id={analysis.variable.id} size={64} /></div>
        <p className="console-name">{analysis.variable.name}</p>
        <p className="console-sub">{analysis.dataset.id}</p>
      </article>
      <article className="console-card">
        <header><span>Record</span><span className="console-tag mono">{periodLabel(analysis)}</span></header>
        <Spark analysis={analysis} />
        <p className="console-sub">Annual values <span aria-hidden>·</span> {analysis.units.annual_value}</p>
      </article>
      <article className="console-card">
        <header><span>Coverage</span><span className="console-tag mono">{eligible}/{requested}</span></header>
        <p className="console-big mono">{fmt(coveragePercent, 0)}%</p>
        <div className="console-meter" aria-hidden><span style={{ width: `${Math.min(100, coveragePercent)}%` }} /></div>
        <p className="console-sub">Requested years eligible for the trend</p>
      </article>
      <article className="console-card console-card-wide">
        <header><span>Evidence chain</span><span className="console-tag">{steps.filter((step) => step.done).length}/{steps.length}</span></header>
        <ol className="console-steps">
          {steps.map((step) => <li key={step.name} className={step.done ? "is-done" : "is-missing"}><span className="console-step-name">{step.name}</span><span className="console-step-detail mono">{step.detail}</span></li>)}
        </ol>
      </article>
    </section>
  );
}
