import type { LaunchPhase } from "../../state/launch";

/** Path shared by the trail and the craft (SVG user units = CSS px inside the 360×300 stage). */
export const FLIGHT_PATH = "M 24 286 C 70 214, 150 150, 236 104 S 330 40, 356 14";

/**
 * Decorative flight of a small shuttle from the launch button along an arc.
 * Plays once per launch (~1.1 s). Never rendered under reduced motion, never
 * focusable, and removed immediately if the request fails.
 */
export default function LaunchCraft({ phase }: { phase: LaunchPhase }) {
  if (phase !== "launching") return null;
  return (
    <div className="launch-stage" aria-hidden>
      <svg className="launch-trail" viewBox="0 0 360 300" width="360" height="300">
        <path d={FLIGHT_PATH} pathLength={1} />
      </svg>
      <span className="launch-craft" style={{ offsetPath: `path("${FLIGHT_PATH}")` }}>
        <svg viewBox="0 0 52 28" width="50" height="27">
          <path className="craft-flame" d="M0 14c5-4 9-4.5 13-3.500v7C9 18.5 5 18 0 14z" />
          <path className="craft-flame" d="M4 6.500c3-1.5 6-1.5 9-.5v3c-3 .5-6 0-9-2.500zM4 21.500c3 1.5 6 1.5 9 .5v-3c-3-.5-6 0-9 2.500z" />
          <path className="craft-flame craft-flame-core" d="M6 14c3-1.8 5-2 7-1.600v3.200c-2 .4-4 .2-7-1.600z" />
          <rect className="craft-fin" x="12" y="3.5" width="14" height="5" rx="2.5" />
          <rect className="craft-fin" x="12" y="19.5" width="14" height="5" rx="2.5" />
          <path className="craft-fin" d="M17 9 30 9 24 1.500h-5zM17 19h13l-6 7.500h-5z" opacity=".75" />
          <path className="craft-body" d="M13 9h22c7 0 12 2.5 16 5-4 2.5-9 5-16 5H13z" />
          <path className="craft-nose" d="M41 10.200c3.8 1 7 2.3 10 3.8-3 1.5-6.2 2.8-10 3.800z" />
          <rect className="craft-window-ring" x="29" y="11" width="9" height="6" rx="3" />
          <rect className="craft-window" x="30.2" y="12.2" width="6.6" height="3.6" rx="1.8" />
          <path className="craft-stripe" d="M16 9h2.500v10H16zM21 9h1.500v10H21z" />
        </svg>
      </span>
    </div>
  );
}
