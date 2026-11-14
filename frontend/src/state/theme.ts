import { useCallback, useEffect, useState } from "react";

/** Orbit (dark, default) and Mission Briefing (light). */
export type Theme = "dark" | "light";
export const THEME_KEY = "estd-theme";

function stored(): Theme | null {
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null; // storage blocked (privacy mode, sandboxed frame)
  }
}

/** Saved choice first; otherwise the system preference; otherwise Orbit. */
export function initialTheme(): Theme {
  const saved = stored();
  if (saved) return saved;
  try {
    return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme, animate = false) {
  const root = document.documentElement;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (animate && !reduce) {
    root.classList.add("theme-transition");
    window.setTimeout(() => root.classList.remove("theme-transition"), 450);
  }
  root.dataset.theme = theme;
  root.style.colorScheme = "dark";
}

export function useTheme(): [Theme, (t: Theme) => void, () => void] {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [explicit, setExplicit] = useState(() => stored() !== null);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Follow live system changes until the user makes an explicit choice.
  useEffect(() => {
    if (explicit || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => setThemeState(mq.matches ? "light" : "dark");
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, [explicit]);

  const setTheme = useCallback((t: Theme) => {
    applyTheme(t, true);
    setThemeState(t);
    setExplicit(true);
    try {
      window.localStorage.setItem(THEME_KEY, t);
    } catch {
      /* not persisted; the choice still applies for this visit */
    }
  }, []);
  const toggle = useCallback(() => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"), [setTheme]);
  return [theme, setTheme, toggle];
}
