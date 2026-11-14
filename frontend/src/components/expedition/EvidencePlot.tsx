import type { Analysis } from "../../api/types";
import { fmt } from "../../lib/format";
import { buildRows } from "../TrendChart";

/**
 * Real annual values and the backend's fitted line, with a focus year.
 * Rows come from the same builder as the main trend chart, so no statistic is recomputed here.
 */
export default function EvidencePlot({ analysis, focusYear, onSelectYear, emphasis = "all" }: {
  analysis: Analysis;
  focusYear: number | null;
  onSelectYear?: (year: number) => void;
  emphasis?: "all" | "trend";
}) {
  const rows = buildRows(analysis);
  const vals = rows.flatMap((r) => [r.eligible, r.excluded, r.trend]).filter((v): v is number => v !== null);
  if (rows.length < 1 || !vals.length) return <p className="evidence-empty">No annual values were returned, so there is nothing to plot.</p>;
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo || Math.abs(hi) || 1) * 0.12;
  const y0 = rows[0]!.year, y1 = rows[rows.length - 1]!.year;
  const W = 560, H = 190, L = 46, R = 14, T = 14, B = 26;
  const x = (yr: number) => L + ((yr - y0) / Math.max(1, y1 - y0)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - (lo - pad)) / (hi - lo + 2 * pad || 1)) * (H - T - B);
  const fitted = rows.filter((r) => r.trend !== null);
  const ticks = [lo, (lo + hi) / 2, hi];
  return (
    <svg className={`evidence-plot emphasis-${emphasis}`} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Annual values; select a year to inspect it">
      {ticks.map((t) => (
        <g key={t} aria-hidden="true">
          <path d={`M${L} ${y(t)}H${W - R}`} className="ep-grid" />
          <text x={L - 6} y={y(t) + 4} textAnchor="end" className="ep-tick">{fmt(t, 2)}</text>
        </g>
      ))}
      {focusYear !== null && rows.some((r) => r.year === focusYear) && (
        <g aria-hidden="true">
          <rect x={x(focusYear) - 11} y={T - 4} width="22" height={H - T - B + 8} rx="11" className="ep-focus" />
        </g>
      )}
      {fitted.length > 1 && <path aria-hidden="true" className="ep-trend" d={`M${x(fitted[0]!.year)} ${y(fitted[0]!.trend!)}L${x(fitted[fitted.length - 1]!.year)} ${y(fitted[fitted.length - 1]!.trend!)}`} />}
      {rows.map((r) => {
        const v = r.eligible ?? r.excluded;
        const label = `${r.year}: ${v === null ? "no annual value" : `${fmt(v, 3)} ${analysis.units.annual_value}`}, ${r.eligible !== null ? "eligible" : "not used in the trend"}`;
        return (
          <g key={r.year}>
            {v !== null
              ? <circle cx={x(r.year)} cy={y(v)} r={r.year === focusYear ? 7 : 5} className={r.eligible !== null ? "ep-dot" : "ep-ring"} aria-hidden="true" />
              : <path d={`M${x(r.year)} ${H - B - 8}v8`} className="ep-gap" aria-hidden="true" />}
            {onSelectYear && (
              <rect
                x={x(r.year) - 12} y={T} width="24" height={H - T - B} className="ep-hit" tabIndex={-1}
                onClick={() => onSelectYear(r.year)} aria-label={label}
              />
            )}
            {(rows.length <= 16 || r.year % 5 === 0 || r.year === y0 || r.year === y1) && (
              <text x={x(r.year)} y={H - 8} textAnchor="middle" className={`ep-year ${r.year === focusYear ? "is-focus" : ""}`} aria-hidden="true">{String(r.year).slice(rows.length > 12 ? 2 : 0)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
