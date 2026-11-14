import { useCallback, useEffect, useReducer, useRef } from "react";

/**
 * Launch sequence for "Launch investigation".
 *
 * The animation is a visual metaphor for sending an analysis request; it never
 * gates the scientific result. Results render as soon as the query resolves —
 * this state only decides what the decorative layer and status line show.
 *
 *   idle ──launch──▶ launching ──liftoffDone──▶ orbiting (request still running)
 *                       │                            │
 *                       ├──settled(error)──▶ aborted  ├──settled(ok)──▶ arrived
 *                       └──settled(ok) … liftoffDone ─▶ arrived        └─settled(error)─▶ aborted
 */
export type LaunchPhase = "idle" | "launching" | "orbiting" | "arrived" | "aborted";

export interface LaunchState {
  phase: LaunchPhase;
  /** Outcome received while the short lift-off was still playing. */
  outcome: "ok" | "error" | null;
}

export type LaunchEvent = { type: "launch" } | { type: "liftoffDone" } | { type: "settled"; ok: boolean } | { type: "reset" };

export const LIFTOFF_MS = 1100;

export function launchReducer(state: LaunchState, event: LaunchEvent): LaunchState {
  switch (event.type) {
    case "launch":
      return { phase: "launching", outcome: null };
    case "reset":
      return { phase: "idle", outcome: null };
    case "settled":
      if (!event.ok && (state.phase === "launching" || state.phase === "orbiting")) return { phase: "aborted", outcome: "error" };
      if (state.phase === "launching") return { ...state, outcome: "ok" };
      if (state.phase === "orbiting") return { phase: "arrived", outcome: "ok" };
      return state;
    case "liftoffDone":
      if (state.phase !== "launching") return state;
      if (state.outcome === "ok") return { phase: "arrived", outcome: "ok" };
      return { phase: "orbiting", outcome: null };
  }
}

export function prefersReducedMotion(): boolean {
  try {
    return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Drives the launch phases from the real query state. */
export function useLaunchSequence(fetching: boolean, failed: boolean) {
  const [state, dispatch] = useReducer(launchReducer, { phase: "idle", outcome: null });
  const timer = useRef<number | undefined>(undefined);
  const wasFetching = useRef(fetching);

  const launch = useCallback(() => {
    window.clearTimeout(timer.current);
    dispatch({ type: "launch" });
    // Reduced motion: no flight; move straight to the waiting/arrived state.
    timer.current = window.setTimeout(() => dispatch({ type: "liftoffDone" }), prefersReducedMotion() ? 0 : LIFTOFF_MS);
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (wasFetching.current && !fetching) dispatch({ type: "settled", ok: !failed });
    wasFetching.current = fetching;
  }, [fetching, failed]);

  // A request answered from cache never enters the fetching state; treat it as settled once lift-off ends.
  useEffect(() => {
    if (state.phase === "orbiting" && !fetching) dispatch({ type: "settled", ok: !failed });
  }, [state.phase, fetching, failed]);

  return { phase: state.phase, launch };
}
