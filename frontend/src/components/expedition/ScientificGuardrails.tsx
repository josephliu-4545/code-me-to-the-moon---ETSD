import { useId, useState } from "react";
import type { Analysis } from "../../api/types";
import { guardrails, type StageId } from "../../lib/evidence";
import { GuardGlyph } from "./Glyphs";

/**
 * Experience C: scientific boundaries as visual, selectable explanations.
 * Only limitations relevant to this dataset and result are rendered, and each backend
 * limitation or caveat is attached to exactly one boundary.
 */
export default function ScientificGuardrails({ analysis, onShowEvidence }: { analysis: Analysis; onShowEvidence?: (stage: StageId) => void }) {
  const items = guardrails(analysis);
  const [open, setOpen] = useState<string | null>(null);
  const base = useId();
  const current = items.find((i) => i.id === open) ?? null;
  return (
    <section className="guardrails" aria-labelledby={`${base}-title`}>
      <div className="guard-horizon" aria-hidden="true">
        <svg viewBox="0 0 1200 140" preserveAspectRatio="none"><path d="M0 140C260 40 940 40 1200 140" /><path d="M0 140C260 60 940 60 1200 140" className="guard-horizon-glow" /></svg>
      </div>
      <header className="guard-head">
        <p className="kicker">Scientific guardrails</p>
        <h3 id={`${base}-title`} className="guard-title">What can we <em>not</em> conclude?</h3>
        <p className="guard-sub">{items.length} boundaries apply to this result. Select one to see why it matters here.</p>
      </header>
      <ul className="guard-grid">
        {items.map((g) => {
          const selected = open === g.id;
          return (
            <li key={g.id} className={`guard ${selected ? "is-open" : ""}`}>
              <button
                type="button"
                className="guard-card"
                aria-expanded={selected}
                aria-controls={`${base}-detail`}
                onClick={() => {
                  setOpen(selected ? null : g.id);
                  if (!selected && window.innerWidth <= 900) {
                    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
                    requestAnimationFrame(() => document.getElementById(`${base}-detail`)?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "nearest" }));
                  }
                }}
              >
                <GuardGlyph visual={g.visual} />
                <strong className="guard-name">{g.title}</strong>
                <span className="guard-line">{g.line}</span>
                <span className="guard-more" aria-hidden="true">{selected ? "Close" : "Explore"}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <div id={`${base}-detail`} className="guard-detail-slot" aria-live="polite">
        {current && (
          <article className={`guard-detail visual-${current.visual}`} aria-label={current.title}>
            <div className="guard-detail-art"><GuardGlyph visual={current.visual} /></div>
            <div className="guard-detail-copy">
              <p className="guard-detail-title">{current.title}</p>
              <p>{current.detail}</p>
              <p className="guard-relevance"><span className="trace-label">In this investigation</span>{current.relevance}</p>
              {current.notes.length > 0 && (
                <div className="guard-notes">
                  <span className="trace-label">From the backend, verbatim</span>
                  <ul>{current.notes.map((n) => <li key={n}>{n}</li>)}</ul>
                </div>
              )}
              {current.stage && onShowEvidence && (
                <button type="button" className="btn btn-ghost guard-evidence" onClick={() => onShowEvidence(current.stage!)}>See the supporting evidence →</button>
              )}
            </div>
          </article>
        )}
      </div>
    </section>
  );
}
