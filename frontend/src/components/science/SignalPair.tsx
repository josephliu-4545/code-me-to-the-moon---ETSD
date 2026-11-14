import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { RelationshipsResponse } from "../../api/types";
import { fmt } from "../../lib/format";
import { CHART, tickStyle } from "./chartTheme";

/**
 * Two annual signals as small multiples on a shared year axis (never a dual-axis chart).
 * Bands mark the years eligible for both variables — the only years that are paired.
 */
export default function SignalPair({ data, name }: { data: RelationshipsResponse; name: (id: string) => string }) {
  const [va, vb] = data.variables;
  const ra = data.results[va];
  const rb = data.results[vb];
  if (!ra || !rb) return null;
  const years = [...new Set([...ra.annual.map((y) => y.year), ...rb.annual.map((y) => y.year)])].sort((x, y) => x - y);
  if (!years.length) return null;
  const shared = new Set(data.common_eligible_years);
  const rows = (r: typeof ra) => years.map((year) => {
    const y = r.annual.find((p) => p.year === year);
    return { year, value: y && y.eligible ? y.value : null };
  });
  const panels = [
    { id: va, r: ra, color: CHART.obs, letter: "A" },
    { id: vb, r: rb, color: CHART.trend, letter: "B" },
  ];
  const lo = years[0]!;
  const hi = years[years.length - 1]!;
  return (
    <figure className="signal-pair" aria-label={`Annual ${name(va)} and ${name(vb)} on a shared year axis; ${shared.size} shared eligible years highlighted.`}>
      {panels.map((p, idx) => (
        <div key={p.id} className="sp-panel">
          <p className="sp-label"><span className={`sp-letter sp-${p.letter}`} aria-hidden>{p.letter}</span>{name(p.id)} <span className="mono sp-units">({p.r.units.annual_value})</span></p>
          <div aria-hidden>
            <ResponsiveContainer width="100%" height={idx === 1 ? 128 : 108}>
              <LineChart data={rows(p.r)} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                {[...shared].map((y) => <ReferenceArea key={y} x1={y - 0.45} x2={y + 0.45} fill={CHART.band} fillOpacity={1} ifOverflow="hidden" />)}
                <XAxis dataKey="year" type="number" domain={[lo - 0.5, hi + 0.5]} ticks={years} allowDecimals={false} tick={idx === 1 ? tickStyle : false} height={idx === 1 ? 24 : 4} stroke={CHART.axis} tickLine={false} />
                <YAxis domain={["auto", "auto"]} tick={tickStyle} axisLine={false} tickLine={false} width={52} tickCount={3} tickFormatter={(v: number) => fmt(v, 1)} />
                <Line dataKey="value" stroke={p.color} strokeWidth={2} connectNulls={false} dot={{ r: 3.5, fill: p.color, stroke: CHART.surface, strokeWidth: 1.5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
      <figcaption className="chart-caption">
        Each panel has its own scale and units. Shaded columns are the {shared.size} years eligible for both variables; only these are paired. Gaps are years not eligible for that variable.
      </figcaption>
    </figure>
  );
}
