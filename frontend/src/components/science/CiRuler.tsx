import { signed } from "../../lib/format";

/**
 * Slope and its 95% interval on a ruler centred on zero (no change).
 * Shows only values the backend returned; if the interval is unavailable it says why.
 */
export default function CiRuler({ slope, ci, units, unavailableReason, compact = false }: {
  slope: number | null;
  ci: [number, number] | null;
  units: string;
  unavailableReason?: string | null;
  compact?: boolean;
}) {
  if (slope === null) return <p className="ruler-empty">Slope not estimated.</p>;
  const extent = Math.max(Math.abs(slope), Math.abs(ci?.[0] ?? 0), Math.abs(ci?.[1] ?? 0)) * 1.25 || 1;
  const pos = (v: number) => `${((v + extent) / (2 * extent)) * 100}%`;
  const crossesZero = ci ? ci[0] <= 0 && ci[1] >= 0 : null;
  const label = ci
    ? `Slope ${signed(slope, 4)} ${units}; 95% interval ${signed(ci[0], 4)} to ${signed(ci[1], 4)}${crossesZero ? ", which includes zero" : ", which excludes zero"}.`
    : `Slope ${signed(slope, 4)} ${units}; interval not reported.`;
  return (
    <figure className={`ruler ${compact ? "ruler-compact" : ""}`}>
      <div className="ruler-track" role="img" aria-label={label}>
        <span className="ruler-zero" style={{ left: pos(0) }}><span className="ruler-zero-label">0</span></span>
        {ci && <span className={`ruler-band ${crossesZero ? "crosses" : ""}`} style={{ left: pos(ci[0]), width: `calc(${pos(ci[1])} - ${pos(ci[0])})` }} />}
        <span className="ruler-dot" style={{ left: pos(slope) }} />
      </div>
      {!compact && (
        <figcaption className="ruler-caption">
          {ci ? (
            <>
              <span className="mono">{signed(ci[0], 4)}</span>
              <span>95% interval{crossesZero ? " · includes zero" : " · excludes zero"}</span>
              <span className="mono">{signed(ci[1], 4)}</span>
            </>
          ) : (
            <span>Interval not reported{unavailableReason ? `: ${unavailableReason}` : ""}</span>
          )}
        </figcaption>
      )}
    </figure>
  );
}
