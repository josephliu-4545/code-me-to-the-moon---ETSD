import type { LaunchPhase } from "../../state/launch";

/** Path shared by the trail and the craft (SVG user units = CSS px inside the 360×300 stage). */
export const FLIGHT_PATH = "M 24 286 C 70 214, 150 150, 236 104 S 330 40, 356 14";

/**
 * Decorative flight of a small orbital craft from the launch button along an arc.
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
        <svg viewBox="0 0 40 20" width="34" height="17">
          <path className="craft-flame" d="M2 10c4-3.2 7-3.6 9-3.4v6.8C9 13.6 6 13.2 2 10z" />
          <path className="craft-body" d="M10 5.4h15c5 0 9.6 2.4 12.6 4.6-3 2.2-7.6 4.6-12.6 4.6H10z" />
          <circle className="craft-window" cx="26.5" cy="10" r="2" />
          <path className="craft-fin" d="M12 5.4l-3-3.6h5l3.4 3.6zM12 14.6l-3 3.6h5l3.4-3.6z" />
        </svg>
      </span>
    </div>
  );
}
