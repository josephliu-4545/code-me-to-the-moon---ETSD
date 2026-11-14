import type { LaunchPhase } from "../../state/launch";
import Starfield from "../layout/Starfield";

/** Decorative, original space artwork. It contains no observations or spatial data. */
export default function DiscoveryChamber({ phase, active }: { phase: LaunchPhase; active: boolean }) {
  return <div className={`discovery-chamber chamber-${phase} ${active ? "is-active" : ""}`} aria-hidden="true">
    <Starfield className="chamber-stars" />
    <div className="chamber-nebula chamber-nebula-one" />
    <div className="chamber-nebula chamber-nebula-two" />
    <div className="chamber-nebula chamber-nebula-three" />
    <img className="chamber-earth-art" src="/mission-earth-astronaut.png" alt="" />
    <svg className="chamber-orbits" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
      <ellipse cx="480" cy="250" rx="650" ry="190" transform="rotate(-18 480 250)" />
      <ellipse cx="480" cy="250" rx="760" ry="260" transform="rotate(-18 480 250)" />
      <path d="M-40 560 Q420 420 700 620 T1480 490" />
    </svg>
    <div className="chamber-beacon"><i /><i /><i /></div>
    <span className="chamber-caption">EARTH OBSERVATION / DISCOVERY CHAMBER</span>
  </div>;
}
