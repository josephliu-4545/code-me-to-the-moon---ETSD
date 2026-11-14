/**
 * Visual summary of the chosen period inside the dataset's available record.
 * Decorative companion to the year selectors (which remain the accessible control);
 * designed to grow into a historical playback timeline later.
 */
export default function PeriodTimeline({ min, max, start, end, maxYears }: { min: number; max: number; start: number; end: number; maxYears: number }) {
  const span = Math.max(1, max - min + 1);
  const left = ((Math.max(start, min) - min) / span) * 100;
  const width = ((Math.min(end, max) - Math.max(start, min) + 1) / span) * 100;
  const n = end - start + 1;
  const over = n > maxYears || start > end;
  return (
    <div className="timeline" aria-hidden>
      <div className="timeline-track">
        {width > 0 && <span className={`timeline-range ${over ? "is-over" : ""}`} style={{ left: `${left}%`, width: `${width}%` }} />}
      </div>
      <div className="timeline-ends mono">
        <span>{min}</span>
        <span className="timeline-count">{start > end ? "—" : `${n} yr${n === 1 ? "" : "s"}`} · max {maxYears}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
