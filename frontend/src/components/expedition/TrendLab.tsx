import { useMemo, useState } from "react";
import type { Analysis } from "../../api/types";
import { signed } from "../../lib/format";
import { slopeName } from "../../lib/verdict";

/**
 * B3: an educational Theil–Sen demonstration on a small, invented dataset.
 * The arithmetic here runs only on these schematic points; the real result always comes from the backend.
 */
export const SCHEMATIC = [2.0, 2.6, 2.3, 3.1, 2.9, 3.6, 3.3, 4.0];
const OUTLIER_INDEX = 6;
const OUTLIER_VALUE = 9.2;

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

export function schematicFits(ys: number[]) {
  const pairs: { i: number; j: number; slope: number }[] = [];
  for (let i = 0; i < ys.length; i++) for (let j = i + 1; j < ys.length; j++) pairs.push({ i, j, slope: (ys[j]! - ys[i]!) / (j - i) });
  const robust = median(pairs.map((p) => p.slope));
  const robustIntercept = median(ys.map((y, x) => y - robust * x));
  const n = ys.length, mx = (n - 1) / 2, my = ys.reduce((a, b) => a + b, 0) / n;
  const ols = ys.reduce((acc, y, x) => acc + (x - mx) * (y - my), 0) / ys.reduce((acc, _, x) => acc + (x - mx) ** 2, 0);
  return { pairs, robust, robustIntercept, ols, olsIntercept: my - ols * mx };
}

export default function TrendLab({ analysis }: { analysis: Analysis }) {
  const [outlier, setOutlier] = useState(false);
  const [showPairs, setShowPairs] = useState(true);
  const [focus, setFocus] = useState<number | null>(null);
  const ys = useMemo(() => SCHEMATIC.map((v, i) => (outlier && i === OUTLIER_INDEX ? OUTLIER_VALUE : v)), [outlier]);
  const fit = useMemo(() => schematicFits(ys), [ys]);
  const W = 420, H = 230, L = 26, R = 12, T = 14, B = 24;
  const yMax = 10, yMin = 0;
  const x = (i: number) => L + (i / (ys.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
  const lineAt = (m: number, b: number) => `M${x(0)} ${y(b)}L${x(ys.length - 1)} ${y(b + m * (ys.length - 1))}`;
  const slopes = fit.pairs.map((p) => p.slope);
  const sMin = Math.min(-0.5, ...slopes), sMax = Math.max(1.5, ...slopes);
  const sx = (s: number) => 12 + ((s - sMin) / (sMax - sMin)) * (W - 24);
  const t = analysis.trend;
  return (
    <div className="xp-lab lab-trend">
      <div className="lab-stage">
        <p className="lab-badge">Educational example · invented points, not NASA data</p>
        <svg viewBox={`0 0 ${W} ${H}`} className="lab-plot" role="img" aria-label={`Schematic: ${fit.pairs.length} pairwise slopes. Robust median slope ${signed(fit.robust, 2)} per step; ordinary straight-line fit ${signed(fit.ols, 2)} per step${outlier ? ", with one outlier added" : ""}.`}>
          <path d={`M${L} ${H - B}H${W - R}`} className="lab-axis" />
          {showPairs && fit.pairs.map((p) => (
            <path key={`${p.i}-${p.j}`} d={`M${x(p.i)} ${y(ys[p.i]!)}L${x(p.j)} ${y(ys[p.j]!)}`} className={`lab-pair ${focus !== null && (p.i === focus || p.j === focus) ? "is-focus" : ""}`} />
          ))}
          <path d={lineAt(fit.ols, fit.olsIntercept)} className="lab-ols" />
          <path d={lineAt(fit.robust, fit.robustIntercept)} className="lab-robust" />
          {ys.map((v, i) => (
            <circle
              key={i} cx={x(i)} cy={y(v)} r={focus === i ? 7 : 5.5}
              className={`lab-point ${outlier && i === OUTLIER_INDEX ? "is-outlier" : ""}`}
              onMouseEnter={() => setFocus(i)} onMouseLeave={() => setFocus(null)}
            />
          ))}
        </svg>
        <div className="lab-strip" aria-hidden="true">
          <svg viewBox={`0 0 ${W} 46`}>
            <path d={`M12 26H${W - 12}`} className="lab-axis" />
            {slopes.map((s, k) => <circle key={k} cx={sx(s)} cy={26 + ((k % 3) - 1) * 6} r="3" className="lab-slope-dot" />)}
            <path d={`M${sx(fit.robust)} 8v36`} className="lab-robust" />
            <path d={`M${sx(fit.ols)} 8v36`} className="lab-ols" />
          </svg>
          <span>Each dot is the slope between one pair of points. The bright marker is their median.</span>
        </div>
      </div>
      <div className="lab-controls">
        <p className="lab-title">How a robust trend line is found</p>
        <ol className="lab-steps">
          <li><strong>Connect every pair.</strong> {fit.pairs.length} pairs from {ys.length} points.</li>
          <li><strong>Measure each slope.</strong> Some are steep, some are flat.</li>
          <li><strong>Take the middle one.</strong> That median is the {slopeName(analysis)}.</li>
        </ol>
        <div className="lab-toggles">
          <button type="button" className={`lab-toggle ${outlier ? "is-on" : ""}`} aria-pressed={outlier} onClick={() => setOutlier((o) => !o)}>{outlier ? "Remove the outlier" : "Add an outlier year"}</button>
          <button type="button" className={`lab-toggle ${showPairs ? "is-on" : ""}`} aria-pressed={showPairs} onClick={() => setShowPairs((p) => !p)}>Pairwise slopes</button>
        </div>
        <dl className="lab-readout" aria-live="polite">
          <div className="lr-robust"><dt>Robust median slope</dt><dd className="mono">{signed(fit.robust, 2)}</dd></div>
          <div className="lr-ols"><dt>Ordinary straight-line fit</dt><dd className="mono">{signed(fit.ols, 2)}</dd></div>
        </dl>
        <p className="lab-insight">{outlier ? "One extreme year pulls the ordinary line upward, while the median moves far less." : "Try adding an outlier: watch which line gets dragged."}</p>
        <p className="lab-real">
          <span className="trace-label">Your real result</span>
          {t?.slope != null ? `The backend’s ${slopeName(analysis)} for this investigation is ${signed(t.slope, 4)} ${t.slope_units ?? analysis.units.slope}. An ordinary fit was not computed on the real data.` : "No slope was estimated for this investigation, so there is no real line to compare."}
        </p>
      </div>
    </div>
  );
}
