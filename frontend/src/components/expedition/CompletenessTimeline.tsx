import type { Analysis } from "../../api/types";
import { fmt, reasonLabel } from "../../lib/format";
import { MONTH_ABBR, MONTH_NAMES, plainYearReason, yearRecords, type MonthCell } from "../../lib/evidence";

const CELL_WORD: Record<MonthCell, string> = { valid: "data", missing: "missing", unknown: "not reported" };

/**
 * B2: every requested year as a selectable capsule of twelve months.
 * Missing months are shown as missing; months the backend did not describe are "not reported", never zero.
 */
export default function CompletenessTimeline({ analysis, focusYear, onSelectYear }: { analysis: Analysis; focusYear: number | null; onSelectYear: (year: number) => void }) {
  const records = yearRecords(analysis);
  const selected = records.find((r) => r.year === focusYear) ?? null;
  const anyMonths = records.some((r) => r.monthSource !== "none");
  return (
    <div className="xp-timeline">
      <ul className="xp-timeline-legend" aria-label="Legend">
        <li><span className="tl-key tl-eligible" />Used in the trend</li>
        <li><span className="tl-key tl-excluded" />Set aside</li>
        {anyMonths && <><li><span className="tl-pip pip-valid" />Month with data</li><li><span className="tl-pip pip-missing" />Missing month</li><li><span className="tl-pip pip-unknown" />Not reported</li></>}
      </ul>
      <ol className="xp-timeline-track" aria-label="Years in this investigation">
        {records.map((r) => {
          const valid = r.months.filter((m) => m === "valid").length;
          const label = `${r.year}: ${r.status === "eligible" ? "used in the trend" : r.status === "empty" ? "no annual value" : "set aside"}${r.monthSource !== "none" ? `, ${valid} of 12 months with data` : ""}`;
          return (
            <li key={r.year}>
              <button type="button" className={`tl-year tl-${r.status} ${r.year === focusYear ? "is-selected" : ""}`} aria-pressed={r.year === focusYear} aria-label={label} onClick={() => onSelectYear(r.year)}>
                {r.monthSource !== "none" ? <span className="tl-pips" aria-hidden="true">{r.months.map((m, i) => <i key={i} className={`tl-pip pip-${m}`} />)}</span> : <span className={`tl-orb orb-${r.status}`} aria-hidden="true" />}
                <span className="tl-label" aria-hidden="true">{r.year}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="xp-timeline-detail" aria-live="polite">
        {!selected ? (
          <p className="xp-timeline-hint">Select a year to see which months it contains and why it was used or set aside.</p>
        ) : (
          <article className={`year-card year-${selected.status}`} aria-label={`Year ${selected.year} details`}>
            <header className="year-card-head">
              <span className="year-card-year mono">{selected.year}</span>
              <span className={`year-chip chip-${selected.status}`}>{selected.status === "eligible" ? "Used in the trend" : selected.status === "empty" ? "No annual value" : "Set aside"}</span>
              <span className="year-card-value">
                {selected.value === null ? "No annual value returned" : <><span className="mono">{fmt(selected.value, 3)}</span> {analysis.units.annual_value}</>}
              </span>
            </header>
            {selected.monthSource === "none" ? (
              <p className="year-note">This product reports annual values only; no month-by-month detail was returned{selected.coverage !== null ? `. Reported temporal coverage: ${fmt(selected.coverage, 1)}%` : ""}.</p>
            ) : (
              <>
                <ol className="month-row" aria-label={`Months in ${selected.year}`}>
                  {selected.months.map((m, i) => (
                    <li key={i} className={`month month-${m}`}>
                      <span aria-hidden="true">{MONTH_ABBR[i]}</span>
                      <span className="sr-only">{MONTH_NAMES[i]}: {CELL_WORD[m]}</span>
                      {selected.monthValues[i] !== null && <small className="mono" aria-hidden="true">{fmt(selected.monthValues[i], 2)}</small>}
                    </li>
                  ))}
                </ol>
                <dl className="year-facts">
                  <div><dt>Months with data</dt><dd>{selected.months.filter((m) => m === "valid").length} of 12</dd></div>
                  <div><dt>Missing</dt><dd>{selected.months.map((m, i) => (m === "missing" ? MONTH_ABBR[i] : null)).filter(Boolean).join(", ") || "none"}</dd></div>
                  {selected.months.includes("unknown") && <div><dt>Not reported</dt><dd>{selected.months.map((m, i) => (m === "unknown" ? MONTH_ABBR[i] : null)).filter(Boolean).join(", ")}</dd></div>}
                  {selected.coverage !== null && <div><dt>Temporal coverage</dt><dd>{fmt(selected.coverage, 1)}%</dd></div>}
                </dl>
              </>
            )}
            {selected.reasons.length > 0 ? (
              <div className="year-reasons">
                <span className="trace-label">Why it was set aside</span>
                <ul>{selected.reasons.map((code) => <li key={code}>{plainYearReason(code)} <code className="reason-code" title={reasonLabel(code)}>{code}</code></li>)}</ul>
              </div>
            ) : selected.status === "eligible" ? (
              <p className="year-note">Passed every completeness rule for this product.</p>
            ) : (
              <p className="year-note">The backend did not report a reason for this year.</p>
            )}
            {selected.facts.length > 0 && (
              <dl className="year-facts year-extra">
                {selected.facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="mono">{v}</dd></div>)}
              </dl>
            )}
          </article>
        )}
      </div>
    </div>
  );
}
