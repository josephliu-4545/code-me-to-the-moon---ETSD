import type { GuardVisual, ProvenanceKind, StageId } from "../../lib/evidence";

/** Decorative line art for the evidence expedition. Always aria-hidden: meaning is carried by text. */

export function StageGlyph({ id, kind = "other" }: { id: StageId; kind?: ProvenanceKind }) {
  const common = { viewBox: "0 0 48 48", className: `stage-glyph glyph-${id}`, "aria-hidden": true, focusable: false } as const;
  switch (id) {
    case "dataset":
      return kind === "model" ? (
        <svg {...common}>
          <circle cx="24" cy="24" r="15" className="g-fill" />
          <path d="M9 24h30M24 9v30M12 16h24M12 32h24M17 10.5c-3 8-3 19 0 27M31 10.5c3 8 3 19 0 27" className="g-line" />
          <circle cx="24" cy="24" r="15" className="g-stroke" />
        </svg>
      ) : (
        <svg {...common}>
          <path d="M6 40a26 26 0 0 1 36 0" className="g-limb" />
          <g transform="rotate(-24 24 18)">
            <rect x="19" y="13" width="10" height="10" rx="1.5" className="g-fill g-stroke" />
            <rect x="4" y="15" width="13" height="6" className="g-panel" />
            <rect x="31" y="15" width="13" height="6" className="g-panel" />
          </g>
          <path d="M24 26l-6 10M24 26l6 10" className="g-beam" />
        </svg>
      );
    case "observations":
      return (
        <svg {...common}>
          <path d="M5 34h38" className="g-line" />
          {[8, 13, 18, 23, 28, 33, 38].map((x, i) => (
            <circle key={x} cx={x + 1} cy={[28, 22, 25, 17, 20, 13, 16][i]} r="2.3" className={i === 3 ? "g-hollow" : "g-dot"} />
          ))}
          <path d="M8 40h4M14 40h4M20 40h4M32 40h4" className="g-tick" />
        </svg>
      );
    case "screening":
      return (
        <svg {...common}>
          <path d="M7 10h34l-12 14v12l-10 5V24z" className="g-fill g-stroke" />
          <circle cx="15" cy="6" r="2" className="g-dot" />
          <circle cx="24" cy="5" r="2" className="g-hollow" />
          <circle cx="33" cy="6" r="2" className="g-dot" />
          <path d="M24 42v4" className="g-beam" />
        </svg>
      );
    case "eligible":
      return (
        <svg {...common}>
          {[0, 1, 2, 3].map((r) => [0, 1, 2, 3].map((c) => (
            <rect key={`${r}-${c}`} x={8 + c * 9} y={8 + r * 9} width="6.5" height="6.5" rx="1.3" className={(r * 4 + c) % 5 === 3 ? "g-cell-off" : "g-cell-on"} />
          )))}
        </svg>
      );
    case "trend":
      return (
        <svg {...common}>
          <path d="M6 40V8M6 40h36" className="g-line" />
          {[[12, 31], [18, 27], [23, 30], [29, 21], [35, 22], [40, 15]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="2.2" className="g-dot" />)}
          <path d="M9 34L43 13" className="g-trend" />
        </svg>
      );
    case "finding":
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="16" className="g-stroke" />
          <circle cx="24" cy="24" r="9" className="g-fill g-stroke" />
          <path d="M24 3v8M24 37v8M3 24h8M37 24h8" className="g-line" />
          <circle cx="24" cy="24" r="2.5" className="g-core" />
        </svg>
      );
  }
}

/** Concept illustrations for the scientific guardrails. */
export function GuardGlyph({ visual }: { visual: GuardVisual }) {
  const common = { viewBox: "0 0 160 96", className: `guard-art art-${visual}`, "aria-hidden": true, focusable: false } as const;
  switch (visual) {
    case "cause":
      return (
        <svg {...common}>
          <path d="M10 78h70" className="a-axis" />
          {[[16, 66], [26, 60], [36, 63], [46, 52], [56, 54], [66, 44]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="3" className="a-dot" />)}
          <path d="M12 70L74 40" className="a-trend" />
          <path d="M88 52h18" className="a-link-broken" />
          <circle cx="126" cy="52" r="17" className="a-question" />
          <text x="126" y="59" textAnchor="middle" className="a-q-text">?</text>
          <path d="M116 42l20 20" className="a-strike" />
        </svg>
      );
    case "area":
      return (
        <svg {...common}>
          {[0, 1, 2, 3, 4].map((c) => [0, 1, 2].map((r) => <rect key={`${c}-${r}`} x={12 + c * 28} y={8 + r * 28} width="28" height="28" className={c === 2 && r === 1 ? "a-cell-on" : "a-cell"} />))}
          <circle cx="82" cy="56" r="3.4" className="a-pin" />
          <path d="M82 56l12-14" className="a-leader" />
          <text x="97" y="40" className="a-label">your point</text>
        </svg>
      );
    case "inference":
      return (
        <svg {...common}>
          <path d="M30 70a50 50 0 0 1 100 0" className="a-gauge" />
          <path d="M80 70l-26-30" className="a-needle-off" />
          <circle cx="80" cy="70" r="5" className="a-hub" />
          <rect x="40" y="78" width="80" height="14" rx="7" className="a-chip" />
          <text x="80" y="88.5" textAnchor="middle" className="a-chip-text">not evaluated</text>
        </svg>
      );
    case "inconclusive":
      return (
        <svg {...common}>
          <path d="M30 70a50 50 0 0 1 100 0" className="a-gauge" />
          <path d="M62 24a50 50 0 0 1 36 0" className="a-gauge-band" />
          <path d="M80 70V26" className="a-needle" />
          <circle cx="80" cy="70" r="5" className="a-hub" />
          <text x="80" y="90" textAnchor="middle" className="a-label">test run · inconclusive</text>
        </svg>
      );
    case "indicative":
      return (
        <svg {...common}>
          <path d="M30 70a50 50 0 0 1 100 0" className="a-gauge" />
          <path d="M30 70a50 50 0 0 1 85-35" className="a-gauge-on" />
          <path d="M80 70l28-28" className="a-needle" />
          <circle cx="80" cy="70" r="5" className="a-hub" />
          <text x="132" y="34" className="a-label">*</text>
        </svg>
      );
    case "nochange":
      return (
        <svg {...common}>
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => <rect key={i} x={12 + i * 14} y="40" width="10" height="16" rx="2" className={[1, 4, 5, 8].includes(i) ? "a-cell-on" : "a-cell-gap"} />)}
          <text x="80" y="80" textAnchor="middle" className="a-label">gaps ≠ zero</text>
        </svg>
      );
    case "station":
    case "satellite":
      return (
        <svg {...common}>
          <path d="M4 82h152" className="a-axis" />
          <g className={visual === "station" ? "a-dim" : ""}>
            <rect x="18" y="20" width="44" height="44" className="a-cell" />
            <path d="M18 34h44M18 50h44M32 20v44M48 20v44" className="a-grid" />
            <text x="40" y="76" textAnchor="middle" className="a-label">{visual === "satellite" ? "retrieval" : "model grid"}</text>
          </g>
          <path d="M78 46h10" className="a-link-broken" />
          <g>
            <path d="M118 82V44M108 82l10-38 10 38" className="a-station" />
            <circle cx="118" cy="38" r="5" className="a-pin" />
            <path d="M110 30a12 12 0 0 1 16 0M106 25a18 18 0 0 1 24 0" className="a-wave" />
            <text x="118" y="16" textAnchor="middle" className="a-label">ground station</text>
          </g>
        </svg>
      );
    case "step":
      return (
        <svg {...common}>
          <path d="M10 78h140" className="a-axis" />
          <path d="M14 62h62v-28h70" className="a-trend" />
          <path d="M14 66L146 30" className="a-dash" />
          <path d="M76 20v62" className="a-mark" />
        </svg>
      );
    case "months":
      return (
        <svg {...common}>
          {Array.from({ length: 12 }, (_, i) => <rect key={i} x={12 + i * 11.5} y="36" width="9" height="24" rx="2" className={[0, 1, 2, 3, 10, 11].includes(i) ? "a-cell-on" : "a-cell-gap"} />)}
        </svg>
      );
    case "years":
      return (
        <svg {...common}>
          {Array.from({ length: 10 }, (_, i) => <circle key={i} cx={18 + i * 14} cy="48" r="5" className={[2, 6].includes(i) ? "a-ring" : "a-dot"} />)}
        </svg>
      );
    case "dataset":
      return (
        <svg {...common}>
          <rect x="44" y="14" width="72" height="68" rx="6" className="a-cell" />
          <path d="M56 32h48M56 46h48M56 60h30" className="a-grid" />
          <circle cx="116" cy="16" r="10" className="a-chip" />
          <text x="116" y="20" textAnchor="middle" className="a-chip-text">!</text>
        </svg>
      );
  }
}
