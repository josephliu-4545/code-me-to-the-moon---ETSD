import { forwardRef, useId } from "react";
import type { Analysis } from "../../api/types";
import type { StageId } from "../../lib/evidence";
import EvidenceJourney, { type LabId } from "./EvidenceJourney";
import MemoryLab from "./MemoryLab";
import MethodExplorer from "./MethodExplorer";
import TrendLab from "./TrendLab";

interface Props {
  analysis: Analysis;
  stage: StageId;
  onStage: (s: StageId) => void;
  focusYear: number | null;
  onFocusYear: (y: number) => void;
  lab: LabId;
  onLab: (l: LabId) => void;
  labRef?: React.Ref<HTMLDivElement>;
}

/** Experience B: the interactive evidence explorer (journey, method labs, methodology). */
const EvidenceExpedition = forwardRef<HTMLElement, Props>(function EvidenceExpedition({ analysis, stage, onStage, focusYear, onFocusYear, lab, onLab, labRef }, ref) {
  const base = useId();
  return (
    <section className="expedition" ref={ref} tabIndex={-1} aria-labelledby={`${base}-title`}>
      <div className="expedition-sky" aria-hidden="true">
        <svg className="expedition-limb" viewBox="0 0 1200 260" preserveAspectRatio="xMidYMax slice">
          <defs>
            <radialGradient id={`${base}-atm`} cx="50%" cy="100%" r="75%">
              <stop offset="62%" stopColor="#48B8E8" stopOpacity="0" />
              <stop offset="70%" stopColor="#80E3EF" stopOpacity=".35" />
              <stop offset="78%" stopColor="#5676E8" stopOpacity=".12" />
              <stop offset="100%" stopColor="#5676E8" stopOpacity="0" />
            </radialGradient>
            <linearGradient id={`${base}-land`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#0d3a5c" />
              <stop offset="1" stopColor="#030711" />
            </linearGradient>
          </defs>
          <ellipse cx="600" cy="1130" rx="1560" ry="940" fill={`url(#${base}-atm)`} />
          <ellipse cx="600" cy="1150" rx="1420" ry="930" fill={`url(#${base}-land)`} className="limb-planet" />
          <path d="M-820 1150a1420 930 0 0 1 2840 0" className="limb-grid" />
          <g className="limb-satellite">
            <rect x="1012" y="60" width="16" height="12" rx="2" />
            <rect x="990" y="63" width="18" height="6" className="sat-panel" />
            <rect x="1032" y="63" width="18" height="6" className="sat-panel" />
            <path d="M1020 74l-40 120" className="sat-beam" />
          </g>
        </svg>
      </div>
      <header className="expedition-head">
        <p className="kicker">Evidence explorer</p>
        <h3 id={`${base}-title`} className="expedition-title">How do we know?</h3>
        <p className="expedition-sub">Follow the evidence from orbit to conclusion. Select any stage.</p>
      </header>
      <EvidenceJourney analysis={analysis} stage={stage} onStage={onStage} focusYear={focusYear} onFocusYear={onFocusYear} onOpenLab={onLab} />
      <div className="labs" ref={labRef} tabIndex={-1}>
        <div className="labs-switch" role="tablist" aria-label="Method labs">
          {([["trend", "Robust trend lab"], ["memory", "Year-to-year memory lab"]] as const).map(([id, label]) => (
            <button key={id} type="button" role="tab" id={`${base}-lab-${id}`} aria-selected={lab === id} aria-controls={`${base}-lab-panel`} tabIndex={lab === id ? 0 : -1} className={`labs-tab ${lab === id ? "is-active" : ""}`} onClick={() => onLab(id)}>{label}</button>
          ))}
        </div>
        <div role="tabpanel" id={`${base}-lab-panel`} aria-labelledby={`${base}-lab-${lab}`}>
          {lab === "trend" ? <TrendLab analysis={analysis} /> : <MemoryLab analysis={analysis} />}
        </div>
      </div>
      <MethodExplorer analysis={analysis} />
    </section>
  );
});

export default EvidenceExpedition;
