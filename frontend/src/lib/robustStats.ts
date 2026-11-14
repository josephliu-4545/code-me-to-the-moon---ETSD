/**
 * Browser-side OLS and Theil–Sen used ONLY by the clearly labelled outlier simulation in the
 * Statistical Methods Lab. Real NASA trends are always computed by the backend.
 * Verified against NumPy polyfit and SciPy theilslopes (method="separate") reference values.
 */

export interface Line {
  slope: number;
  intercept: number;
}

export function ols(x: number[], y: number[]): Line | null {
  const n = x.length;
  if (n < 2 || n !== y.length) return null;
  const xm = x.reduce((s, v) => s + v, 0) / n;
  const ym = y.reduce((s, v) => s + v, 0) / n;
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < n; i++) {
    sxx += (x[i]! - xm) ** 2;
    sxy += (x[i]! - xm) * (y[i]! - ym);
  }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  return { slope, intercept: ym - slope * xm };
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

/** Median pairwise slope; intercept = median(y) − slope·median(x), as in SciPy. */
export function theilSen(x: number[], y: number[]): Line | null {
  const n = x.length;
  if (n < 2 || n !== y.length) return null;
  const slopes: number[] = [];
  for (let i = 0; i < n - 1; i++)
    for (let j = i + 1; j < n; j++) if (x[j] !== x[i]) slopes.push((y[j]! - y[i]!) / (x[j]! - x[i]!));
  if (!slopes.length) return null;
  const slope = median(slopes);
  return { slope, intercept: median(y) - slope * median(x) };
}
