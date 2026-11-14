import { SECTION_TITLES, STATUS_LABELS, type Answer } from "../../detective/answers";
import { safeHref } from "../../detective/safety";

/** Renders an answer as plain React text — never as HTML — with its evidence sources. */
export default function AnswerCard({ answer, headingId }: { answer: Answer; headingId: string }) {
  return (
    <article className={`dt-answer status-${answer.status}`} aria-labelledby={headingId}>
      <header className="dt-answer-head">
        <h3 id={headingId} className="dt-topic">{answer.topic}</h3>
        <span className="dt-status" data-testid="answer-status">{STATUS_LABELS[answer.status]}</span>
      </header>
      {answer.sections.map((s, i) => {
        const bullets = s.lines.filter((l) => l.startsWith("• "));
        const prose = s.lines.filter((l) => !l.startsWith("• "));
        return (
          <section key={i} className={`dt-section dt-${s.kind}`} data-kind={s.kind}>
            <h4 className="dt-section-title">{SECTION_TITLES[s.kind]}</h4>
            {prose.map((l, j) => <p key={j}>{l}</p>)}
            {bullets.length > 0 && <ul>{bullets.map((l, j) => <li key={j}>{l.slice(2)}</li>)}</ul>}
          </section>
        );
      })}
      {answer.sources.length > 0 && (
        <details className="dt-sources">
          <summary>Evidence used ({answer.sources.length})</summary>
          <ul>
            {answer.sources.map((src, i) => {
              const href = safeHref(src.href);
              const external = href?.startsWith("https://");
              return (
                <li key={i}>
                  {href ? <a href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>{src.label}</a> : <strong>{src.label}</strong>}
                  <span className="dt-source-detail">{src.detail}</span>
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </article>
  );
}
