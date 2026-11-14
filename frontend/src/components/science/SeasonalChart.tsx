import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Analysis } from "../../api/types";
import { fmt } from "../../lib/format";
import { calendarSeries, seasonalCycle, type SeasonalPoint } from "../../lib/series";
import { isSeasonal, monthsUsed } from "../../lib/verdict";
import Disclosure from "../ui/Disclosure";
import { CHART, tickStyle } from "./chartTheme";

const NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function TooltipBody({ active, payload, units }: { active?: boolean; payload?: Array<{ payload: SeasonalPoint }>; units: string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0]!.payload;
  return (
    <div className="chart-tooltip">
      <strong>{NAMES[p.month - 1]}</strong>
      {p.mean === null ? <div className="tt-muted">No valid months</div> : <div><span className="mono">{fmt(p.mean, 3)}</span> {units}</div>}
      <div className="tt-muted">Average of {p.n} valid month{p.n === 1 ? "" : "s"}</div>
    </div>
  );
}

/** Average seasonal cycle from valid months only. Descriptive context, not part of the trend test. */
export default function SeasonalChart({ analysis }: { analysis: Analysis }) {
  if (!analysis.series.length || !analysis.series_definition) return null;
  const rows = calendarSeries(analysis.series, analysis.period.start, analysis.period.end_exclusive);
  const cycle = seasonalCycle(rows);
  const covered = cycle.filter((c) => c.n > 0).length;
  if (covered < 6) return null; // too sparse to describe a cycle honestly
  const units = analysis.series_definition.match(/\(([^)]+)\)\s*$/)?.[1] ?? analysis.units.annual_value;
  const data = cycle.map((c) => ({ ...c, label: NAMES[c.month - 1] }));
  const minN = Math.min(...cycle.filter((c) => c.n > 0).map((c) => c.n));
  const maxN = Math.max(...cycle.map((c) => c.n));
  return (
    <figure className="chart chart-compact" aria-labelledby="season-title">
      <div className="chart-head">
        <div>
          <h3 id="season-title" className="chart-title">Average seasonal cycle</h3>
          <p className="chart-sub">Mean of valid monthly values per calendar month · {units}</p>
        </div>
      </div>
      <div className="chart-plot" aria-hidden>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="22%">
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="label" tick={tickStyle} stroke={CHART.axis} tickLine={false} interval={0} />
            <YAxis tick={tickStyle} axisLine={false} tickLine={false} width={58} tickFormatter={(v: number) => fmt(v, 2)} domain={[(min: number) => Math.min(0, min), "auto"]} />
            <Tooltip content={<TooltipBody units={units} />} cursor={{ fill: CHART.band }} />
            <Bar dataKey="mean" fill={CHART.obs} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-caption">
        {isSeasonal(analysis) && analysis.trend?.slope != null
          ? `The trend test uses these monthly values, comparing each of ${monthsUsed(analysis)} only with the same month in other years. `
          : "Descriptive context only; not used in the trend test. "}
        Each bar averages {minN === maxN ? `${minN}` : `${minN}–${maxN}`} valid months. Months without valid data have no bar.
      </figcaption>
      <Disclosure summary="Seasonal data table" meta="12 months" className="chart-table">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Month</th><th scope="col">Mean ({units})</th><th scope="col">Valid months</th></tr></thead>
            <tbody>{data.map((d) => <tr key={d.month}><th scope="row">{d.label}</th><td className="mono">{fmt(d.mean, 3)}</td><td className="mono">{d.n}</td></tr>)}</tbody>
          </table>
        </div>
      </Disclosure>
    </figure>
  );
}
