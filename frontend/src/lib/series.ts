import type { SeriesPoint } from "../api/types";

/**
 * Presentation helpers for monthly series. Nothing here creates measurements:
 * months the backend did not return become explicit null points so charts
 * show a gap instead of drawing a line across missing periods.
 */
export type MonthState = "valid" | "withheld" | "not_returned";

export interface MonthRow {
  month: string; // YYYY-MM
  value: number | null;
  state: MonthState;
  status?: string;
  /** A valid month whose neighbours are both gaps: needs a visible dot, a line alone would be invisible. */
  isolated: boolean;
}

const pad = (m: number) => String(m).padStart(2, "0");

function parseMonth(s: string): [number, number] | null {
  const m = /^(\d{4})-(\d{2})/.exec(s);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

export function calendarSeries(series: SeriesPoint[], start?: string | null, endExclusive?: string | null): MonthRow[] {
  const byMonth = new Map<string, SeriesPoint>();
  for (const p of series) byMonth.set(p.date.slice(0, 7), p);
  const keys = [...byMonth.keys()].sort();
  const first = keys[0];
  const last = keys[keys.length - 1];
  if (!first || !last) return [];

  let from = parseMonth(start ?? first) ?? parseMonth(first)!;
  if (`${from[0]}-${pad(from[1])}` > first) from = parseMonth(first)!;
  // Period end is exclusive; the last month to show is the month before it, unless observations go further.
  const to = parseMonth(endExclusive ?? "");
  let toInclusive: [number, number];
  if (to) {
    toInclusive = to[1] === 1 ? [to[0] - 1, 12] : [to[0], to[1] - 1];
    if (`${toInclusive[0]}-${pad(toInclusive[1])}` < last) toInclusive = parseMonth(last)!;
  } else {
    toInclusive = parseMonth(last)!;
  }

  const rows: MonthRow[] = [];
  let [y, m] = from;
  // Guard against malformed periods producing runaway loops (max 200 years).
  for (let guard = 0; guard < 2400; guard++) {
    if (y > toInclusive[0] || (y === toInclusive[0] && m > toInclusive[1])) break;
    const key = `${y}-${pad(m)}`;
    const p = byMonth.get(key);
    if (!p) rows.push({ month: key, value: null, state: "not_returned", isolated: false });
    else if (p.usable === false || p.value === null || p.value === undefined || !Number.isFinite(p.value))
      rows.push({ month: key, value: null, state: "withheld", status: p.status, isolated: false });
    else rows.push({ month: key, value: p.value, state: "valid", status: p.status, isolated: false });
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]!;
    if (r.state !== "valid") continue;
    const prev = rows[i - 1];
    const next = rows[i + 1];
    r.isolated = (!prev || prev.state !== "valid") && (!next || next.state !== "valid");
  }
  return rows;
}

export interface GapRun {
  from: string;
  to: string;
  months: number;
}

/** Consecutive runs of months without a usable value. */
export function gapRuns(rows: MonthRow[]): GapRun[] {
  const runs: GapRun[] = [];
  let cur: GapRun | null = null;
  for (const r of rows) {
    if (r.state === "valid") {
      cur = null;
      continue;
    }
    if (cur) {
      cur.to = r.month;
      cur.months += 1;
    } else {
      cur = { from: r.month, to: r.month, months: 1 };
      runs.push(cur);
    }
  }
  return runs;
}

export function monthLabel(key: string): string {
  const p = parseMonth(key);
  if (!p) return key;
  return new Date(Date.UTC(p[0], p[1] - 1, 1)).toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

export interface SeasonalPoint {
  month: number; // 1–12
  mean: number | null;
  n: number;
}

/**
 * Average of valid monthly values for each calendar month (descriptive).
 * Months with no valid value stay null; nothing is filled.
 */
export function seasonalCycle(rows: MonthRow[]): SeasonalPoint[] {
  const sums = Array.from({ length: 12 }, () => ({ s: 0, n: 0 }));
  for (const r of rows) {
    if (r.state !== "valid" || r.value === null) continue;
    const m = Number(r.month.slice(5, 7));
    const b = sums[m - 1];
    if (!b) continue;
    b.s += r.value;
    b.n += 1;
  }
  return sums.map((b, i) => ({ month: i + 1, mean: b.n ? b.s / b.n : null, n: b.n }));
}
