import { useId } from "react";

/** Original vector spacecraft, nose along -Y; gradients provide restrained hull depth. */
export default function RocketIllustration() {
  const id = useId().replace(/:/g, "");
  return <g className="mission-rocket">
    <defs>
      <linearGradient id={`${id}-hull`}><stop stopColor="#41577A"/><stop offset=".3" stopColor="#EFF2F7"/><stop offset=".53" stopColor="#CDD5E1"/><stop offset="1" stopColor="#41577A"/></linearGradient>
      <linearGradient id={`${id}-flame`} x1="0" x2="0" y1="0" y2="1"><stop stopColor="#EFF2F7"/><stop offset=".4" stopColor="#90A1BA" stopOpacity=".8"/><stop offset="1" stopColor="#5878A7" stopOpacity="0"/></linearGradient>
    </defs>
    <g className="rocket-exhaust">
      <path fill={`url(#${id}-flame)`} d="M-25 74 Q-40 130 0 222 Q40 130 25 74Z" opacity=".45"/>
      <path fill={`url(#${id}-flame)`} d="M-15 73 Q-20 128 0 188 Q20 128 15 73Z"/>
      <path fill="#EFF2F7" d="M-8 74 Q-11 103 0 131 Q11 103 8 74Z"/>
      <path fill={`url(#${id}-flame)`} d="M-40 65 L-31 122 L-23 65Z M23 65 L31 122 L40 65Z"/>
    </g>
    <g className="rocket-hull" stroke="#202A3D" strokeWidth="1.4">
      <path fill="#41577A" d="M-20 16 L-49 63 L-48 79 L-17 62 M20 16 L49 63 L48 79 L17 62"/>
      <path fill={`url(#${id}-hull)`} d="M-42 56 V-9 Q-33-48-24-9 V56Z M24 56 V-9 Q33-48 42-9 V56Z"/>
      <path fill={`url(#${id}-hull)`} d="M-22 62 V-57 Q-20-91 0-114 Q20-91 22-57 V62Z"/>
      <path fill="#121826" d="M-22-55H22V-44H-22Z M-22 44H22V54H-22Z"/>
      <path fill="#090B12" d="M-15 62H15L20 76H-20Z M-40 56H-26L-23 67H-43Z M26 56H40L43 67H23Z"/>
      <circle cy="-23" r="10" fill="#082A46" stroke="#EFF2F7" strokeWidth="2"/>
      <path d="M-5-27Q0-32 5-27" fill="none" stroke="#90A1BA"/>
      <path d="M-15-4H15 M-15 30H15 M0 3V23" stroke="#687993" fill="none"/>
      <path d="M-4 10L0 3L4 10L0 18Z" fill="#EFF2F7" stroke="none"/>
    </g>
  </g>;
}
