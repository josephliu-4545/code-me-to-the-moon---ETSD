import { CartesianGrid, Line, LineChart, ReferenceLine, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Analysis } from "../api/types";
import { fmt, reasonLabel } from "../lib/format";
import { calendarSeries, gapRuns, monthLabel, type MonthRow } from "../lib/series";
import Disclosure from "./ui/Disclosure";
import { CHART, tickStyle } from "./science/chartTheme";

type Indexed = MonthRow & { i: number };

function stateText(r: MonthRow): string {
  if (r.state === "valid") return "Valid";
  if (r.state === "not_returned") return "No value returned for this month";
  return `Withheld${r.status ? ` (${reasonLabel(r.status)})` : ""}`;
}

function TooltipBody({ active, payload, units }: { active?: boolean; payload?: Array<{ payload: Indexed }>; units: string }) {
  if (!active || !payload?.length) return null;
  const r = payload[0]!.payload;
  return (
    <div className="chart-tooltip">
      <strong>{monthLabel(r.month)}</strong>
      {r.value !== null ? <div><span className="mono">{fmt(r.value, 3)}</span> {units}</div> : <div className="tt-muted">{stateText(r)}</div>}
    </div>
  );
}

const IsolatedDot = (p: unknown) => {
  const { cx, cy, payload, index } = p as { cx?: number; cy?: number; payload?: Indexed; index?: number };
  if (!payload?.isolated || cx === undefined || cy === undefined) return <g key={`n${index}`} />;
  return <circle key={`d${index}`} cx={cx} cy={cy} r={3.5} fill={CHART.series} stroke={CHART.surface} strokeWidth={1.5} />;
};

export default function SeriesChart({ analysis, onSelect, selectedDate }: { analysis: Analysis; onSelect?: (date: string) => void; selectedDate?: string }) {
  if (!analysis.series.length || !analysis.series_definition) return null;
  const rows: Indexed[] = calendarSeries(analysis.series, analysis.period.start, analysis.period.end_exclusive).map((r, i) => ({ ...r, i }));
  if (!rows.length) return null;
  const withheld = rows.filter((r) => r.state === "withheld").length;
  const notReturned = rows.filter((r) => r.state === "not_returned").length;
  const runs = gapRuns(rows);
  const index = new Map(rows.map((r) => [r.month, r.i]));
  const ticks = rows.filter((r) => r.month.endsWith("-01")).map((r) => r.i);
  const yearStep = Math.max(1, Math.ceil(ticks.length / 8));
  const shownTicks = ticks.filter((_, k) => k % yearStep === 0);
  const units = analysis.series_definition.match(/\(([^)]+)\)\s*$/)?.[1] ?? analysis.units.annual_value;
  return (
    <figure className="chart" aria-labelledby="series-chart-title">
      <div className="chart-head">
        <div>
          <h3 id="series-chart-title" className="chart-title">Monthly record</h3>
          <p className="chart-sub">{analysis.series_definition}</p>
        </div>
        <ul className="legend" aria-label="Legend">
          <li><span className="key key-line" style={{ background: CHART.series }} />Monthly value</li>
          {runs.length > 0 && <li><span className="key key-gap" />Gap: missing or unusable month</li>}
        </ul>
      </div>
      <div className="chart-plot" aria-hidden>
        <ResponsiveContainer width="100%" height={210}>
          <LineChart onClick={(state) => { const label = (state as unknown as { activeLabel?: string | number }).activeLabel; const row = label == null ? undefined : rows[Number(label)]; if (row) onSelect?.(row.month); }} data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <defs>
              <pattern id="gap-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill="var(--chart-gap)" />
                <line x1="0" y1="0" x2="0" y2="6" stroke="var(--chart-gap-line)" strokeWidth="2" />
              </pattern>
            </defs>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            {selectedDate && index.has(selectedDate) && <ReferenceLine x={index.get(selectedDate)} stroke={CHART.obs} strokeDasharray="2 4" />}
            {runs.map((g) => (
              <ReferenceArea key={g.from} x1={index.get(g.from)! - 0.5} x2={index.get(g.to)! + 0.5} fill="url(#gap-hatch)" fillOpacity={1} ifOverflow="hidden" />
            ))}
            <XAxis dataKey="i" type="number" domain={[-0.5, rows.length - 0.5]} ticks={shownTicks} tickFormatter={(i: number) => rows[i]?.month.slice(0, 4) ?? ""} tick={tickStyle} stroke={CHART.axis} tickLine={false} />
            <YAxis domain={["auto", "auto"]} tick={tickStyle} axisLine={false} tickLine={false} width={58} tickFormatter={(v: number) => fmt(v, 2)} />
            <Tooltip content={<TooltipBody units={units} />} cursor={{ stroke: CHART.axis, strokeDasharray: "2 3" }} />
            <Line dataKey="value" stroke={CHART.series} strokeWidth={1.75} dot={IsolatedDot} activeDot={{ r: 4, fill: CHART.series, stroke: CHART.surface, strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-caption">
        Gaps are missing or unusable months; they are never interpolated.
        {withheld ? ` ${withheld} month(s) withheld (insufficient support, provisional, or no valid data).` : ""}
        {notReturned ? ` ${notReturned} month(s) had no value returned by the service.` : ""}
      </figcaption>
      <Disclosure summary="Monthly data table" meta={`${rows.length} months`} className="chart-table">
        <div className="table-wrap table-tall">
          <table className="table">
            <caption className="sr-only">Monthly values: {analysis.series_definition}</caption>
            <thead><tr><th scope="col">Month</th><th scope="col">Value</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.month} className={r.state === "valid" ? "" : "row-excluded"}>
                  <th scope="row" className="mono">{onSelect ? <button type="button" className="history-date" onClick={() => onSelect(r.month)}>{r.month}</button> : r.month}</th>
                  <td className="mono">{fmt(r.value, 3)}</td>
                  <td>{stateText(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
    </figure>
  );
}
