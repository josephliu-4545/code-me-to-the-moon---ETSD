import { useEffect, useId, useState } from "react";
import type { Theme } from "../../state/theme";
import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";

export interface NavItem {
  id: string;
  label: string;
  short: string;
  /** Planned destinations are shown but not navigable. */
  planned?: boolean;
}

/** Mission rail navigation. Hash links keep the existing routing and deep links working. */
export default function SiteHeader({ items, current, theme, onToggleTheme }: { items: readonly NavItem[]; current: string; theme: Theme; onToggleTheme: () => void }) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const activeIndex = items.findIndex((t) => t.id === current);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className={`topbar ${open ? "menu-open" : ""}`}>
      <a className="brand" href="#explore" aria-label="EarthLens by Code Me to the Moon — Explore Earth">
        <Logo size={34} />
        <span className="brand-text" aria-hidden>
          <span className="brand-name">EarthLens</span>
          <span className="brand-team">Code Me to the Moon · NASA Space Apps 2026</span>
        </span>
      </a>
      <button type="button" className="menu-button" aria-expanded={open} aria-controls={menuId} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((o) => !o)}>
        <span className="menu-icon" aria-hidden><span /><span /></span>
        <span aria-hidden>{open ? "Close" : "Menu"}</span>
      </button>
      <nav id={menuId} className="nav" aria-label="Mission sections">
        <ol style={{ "--progress": activeIndex < 0 ? 0 : activeIndex } as React.CSSProperties}>
          {items.map((t, i) => (
            <li key={t.id} className={t.planned ? "is-planned" : ""}>
              {t.planned ? (
                <span className="nav-planned" aria-disabled="true">
                  <span className="nav-index">{String(i + 1).padStart(2, "0")}</span>
                  <span className="nav-label">{t.short}</span>
                  <span className="soon-chip">Planned</span>
                  <span className="sr-only"> — not yet available</span>
                </span>
              ) : (
                <a
                  href={`#${t.id}`}
                  className={current === t.id ? "active" : ""}
                  aria-current={current === t.id ? "page" : undefined}
                  aria-label={t.label}
                  onClick={() => setOpen(false)}
                >
                  <span className="nav-index" aria-hidden>{String(i + 1).padStart(2, "0")}</span>
                  <span className="nav-label" aria-hidden>{t.short}</span>
                </a>
              )}
            </li>
          ))}
        </ol>
        <div className="nav-tools">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </nav>
    </header>
  );
}
