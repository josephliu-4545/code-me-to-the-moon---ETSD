import type { ReactNode } from "react";

/** Native <details> disclosure with consistent styling; keyboard and screen-reader accessible by default. */
export default function Disclosure({ summary, meta, children, defaultOpen, className = "" }: {
  summary: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <details className={`disclosure ${className}`} open={defaultOpen}>
      <summary>
        <span className="disclosure-label">{summary}</span>
        {meta !== undefined && <span className="disclosure-meta">{meta}</span>}
        <span className="disclosure-chevron" aria-hidden />
      </summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}
