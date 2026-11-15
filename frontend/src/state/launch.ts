import { useCallback, useEffect, useReducer } from "react";

export type LaunchPhase = "idle" | "ignition" | "liftoff" | "transit" | "holding" | "docking" | "completed" | "failed" | "cancelled";
export interface LaunchState { phase: LaunchPhase; key: string; run: number; reduced: boolean }
export type LaunchEvent = { type: "launch"; key: string; reduced?: boolean } | { type: "advance"; run: number } | { type: "settled"; key: string; run: number; ok: boolean } | { type: "cancel" };
// A calm, readable launch arc; query completion still renders findings immediately.
export const PHASE_MS = { ignition: 600, liftoff: 1300, transit: 1600, docking: 900 } as const;
export const INITIAL_LAUNCH: LaunchState = { phase: "idle", key: "", run: 0, reduced: false };
export function launchReducer(state: LaunchState, event: LaunchEvent): LaunchState {
  if (event.type === "launch") return { phase: event.reduced ? "holding" : "ignition", key: event.key, run: state.run + 1, reduced: !!event.reduced };
  if (event.type === "cancel") return { ...state, phase: "cancelled" };
  if (event.run !== state.run) return state;
  if (event.type === "settled") {
    if (event.key !== state.key || !["ignition", "liftoff", "transit", "holding"].includes(state.phase)) return state;
    return { ...state, phase: event.ok ? state.reduced ? "completed" : "docking" : "failed" };
  }
  const next: Partial<Record<LaunchPhase, LaunchPhase>> = { ignition: "liftoff", liftoff: "transit", transit: "holding", docking: "completed" };
  return next[state.phase] ? { ...state, phase: next[state.phase]! } : state;
}
export function prefersReducedMotion(): boolean {
  return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
/** Query identity and a run generation isolate settlements and timers from older launches.
 * Results render independently; animation never gates data or starts network requests. */
export function useLaunchSequence(fetching: boolean, failed: boolean, key: string, settled: boolean) {
  const [state, dispatch] = useReducer(launchReducer, INITIAL_LAUNCH);
  const launch = useCallback((requestKey: string) => dispatch({ type: "launch", key: requestKey, reduced: prefersReducedMotion() }), []);
  const cancel = useCallback(() => dispatch({ type: "cancel" }), []);
  useEffect(() => {
    const duration = PHASE_MS[state.phase as keyof typeof PHASE_MS];
    if (!duration) return;
    const timer = window.setTimeout(() => dispatch({ type: "advance", run: state.run }), duration);
    return () => window.clearTimeout(timer);
  }, [state.phase, state.run]);
  useEffect(() => {
    if (!fetching && settled && state.key === key) dispatch({ type: "settled", key, run: state.run, ok: !failed });
  }, [fetching, failed, key, settled, state.key, state.run, state.phase]);
  return { ...state, launch, cancel };
}
