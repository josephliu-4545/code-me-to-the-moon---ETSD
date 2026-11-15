import { useId, useState } from "react";
import type { Analysis } from "../../api/types";
import { methodTopics, type TopicId } from "../../lib/evidence";
import Disclosure from "../ui/Disclosure";

const TOPIC_ICON: Record<TopicId, string> = {
  derived: "M4 20h16M6 20V9l6-5 6 5v11M10 20v-6h4v6",
  selected: "M3 5h18l-7 8v6l-4 2v-8z",
  trend: "M3 20V4M3 20h18M6 16l5-5 3 3 6-7",
  uncertainty: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v6M12 16v.5",
  caveats: "M12 3l9 17H3zM12 10v4M12 17v.5",
};

/**
 * B5: the backend's methodology notes grouped into five approachable topics.
 * Level 2 shows a plain sentence and key facts; Level 3 shows every note verbatim.
 */
export default function MethodExplorer({ analysis }: { analysis: Analysis }) {
  const topics = methodTopics(analysis);
  const [active, setActive] = useState<TopicId>(topics[0]?.id ?? "trend");
  const base = useId();
  const topic = topics.find((t) => t.id === active) ?? topics[0];
  const total = topics.reduce((n, t) => n + t.notes.length, 0);
  if (!topic) return null;
  return (
    <div className="methods">
      <div className="methods-head">
        <p className="lab-title">Methodology explorer</p>
        <p className="methods-count mono">{total} backend notes · {topics.length} topics</p>
      </div>
      <div className="methods-tabs" role="tablist" aria-label="Methodology topics">
        {topics.map((t) => (
          <button
            key={t.id} type="button" role="tab" id={`${base}-tab-${t.id}`}
            aria-selected={t.id === topic.id} aria-controls={`${base}-panel`} tabIndex={t.id === topic.id ? 0 : -1}
            className={`methods-tab ${t.id === topic.id ? "is-active" : ""}`}
            onClick={() => setActive(t.id)}
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              const i = topics.findIndex((x) => x.id === t.id);
              const next = topics[(i + (e.key === "ArrowRight" ? 1 : topics.length - 1)) % topics.length]!;
              setActive(next.id);
              document.getElementById(`${base}-tab-${next.id}`)?.focus();
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d={TOPIC_ICON[t.id]} /></svg>
            <span>{t.title}</span>
            <small className="mono">{t.notes.length}</small>
          </button>
        ))}
      </div>
      <div className="methods-panel" role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-tab-${topic.id}`}>
        <p className="methods-plain">{topic.plain}</p>
        {topic.facts.length > 0 && <ul className="methods-facts">{topic.facts.map((f) => <li key={f} className="mono">{f}</li>)}</ul>}
        {topic.notes.length > 0 ? (
          <Disclosure summary="Technical details" meta={`${topic.notes.length} note${topic.notes.length === 1 ? "" : "s"}`} className="methods-technical">
            <dl className="method-grid">
              {topic.notes.map((n) => (
                <div className="method-item" key={n.key}>
                  <dt>{n.origin === "caveat" ? "Scientific note" : n.label}</dt>
                  <dd>{n.value}</dd>
                </div>
              ))}
            </dl>
          </Disclosure>
        ) : (
          <p className="methods-none">The backend did not report technical notes for this topic.</p>
        )}
      </div>
    </div>
  );
}
