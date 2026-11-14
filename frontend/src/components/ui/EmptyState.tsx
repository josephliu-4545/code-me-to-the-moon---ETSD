import type { ReactNode } from "react";

export default function EmptyState({ title, children, action, art }: { title: string; children?: ReactNode; action?: ReactNode; art?: ReactNode }) {
  return (
    <div className="empty-state">
      {art && <div className="empty-art" aria-hidden>{art}</div>}
      <div>
        <h2 className="empty-title">{title}</h2>
        {children && <div className="empty-body">{children}</div>}
        {action && <div className="empty-action">{action}</div>}
      </div>
    </div>
  );
}
