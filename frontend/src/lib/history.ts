import type { Analysis } from "../api/types";
import { calendarSeries } from "./series";
import { reasonLabel } from "./format";

export interface HistoricalObservation {
  date: string;
  value: number | null;
  status: string;
  eligible: boolean;
}

/** Presentation of returned records only. Missing calendar slots never become measurements. */
function serverRow(p: NonNullable<Analysis["discovery"]>["history"]["annual"][number]): HistoricalObservation {
  const label = p.status === "eligible" ? "Eligible annual summary" : p.status === "valid" ? "Valid monthly observation" :
    p.status === "excluded" ? "Excluded from annual trend" : p.status === "withheld" ? "Withheld" : "No observation returned";
  return { date: p.date, value: p.value, eligible: p.eligible,
    status: label + (p.reasons.length ? `: ${p.reasons.map(reasonLabel).join("; ")}` : "") };
}

export function annualHistory(a: Analysis): HistoricalObservation[] {
  if (a.discovery) return a.discovery.history.annual.map(serverRow);
  const byYear = new Map(a.annual.map((p) => [p.year, p]));
  const rows: HistoricalObservation[] = [];
  const start = Number(a.period.start.slice(0, 4));
  const endDate = new Date(a.period.end_exclusive + "T00:00:00Z");
  endDate.setUTCDate(endDate.getUTCDate() - 1);
  const end = endDate.getUTCFullYear();
  for (let year = start; year <= end && rows.length < 200; year++) {
    const p = byYear.get(year);
    const value = p?.value != null && Number.isFinite(p.value) ? p.value : null;
    rows.push({ date: String(year), value, eligible: value !== null && !!p?.eligible,
      status: !p || value === null ? "No annual value" : p.eligible ? "Eligible annual summary" :
        `Excluded from annual trend: ${p.reasons.map(reasonLabel).join("; ") || "Eligibility rules not met"}` });
  }
  return rows;
}

export function monthlyHistory(a: Analysis): HistoricalObservation[] {
  if (a.discovery) return a.discovery.history.monthly.map(serverRow);
  return calendarSeries(a.series, a.period.start, a.period.end_exclusive).map((p) => ({
    date: p.month, value: p.value, eligible: p.state === "valid",
    status: p.state === "valid" ? `Valid monthly observation${p.status ? ` (${reasonLabel(p.status)})` : ""}` :
      p.state === "not_returned" ? "No observation returned" : `Withheld: ${p.status ? reasonLabel(p.status) : "No usable value"}`,
  }));
}

/** A difference between two observations, never a trend estimate or significance test. */
export function observationDifference(a?: HistoricalObservation, b?: HistoricalObservation): number | null {
  return a?.value != null && b?.value != null ? b.value - a.value : null;
}
