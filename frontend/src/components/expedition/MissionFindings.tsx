import { useRef, useState } from "react";
import type { Analysis } from "../../api/types";
import type { StageId } from "../../lib/evidence";
import { ProvenanceCard, ResultSummary } from "../ResultPanels";
import SeriesChart from "../SeriesChart";
import TrendChart from "../TrendChart";
import SeasonalChart from "../science/SeasonalChart";
import EvidenceExpedition from "./EvidenceExpedition";
import type { LabId } from "./EvidenceJourney";
import ScientificGuardrails from "./ScientificGuardrails";

function reveal(el: HTMLElement | null) {
  if (!el) return;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
  el.focus?.({ preventScroll: true });
}

/**
 * The Earth Evidence Expedition: discovery → evidence → guardrails, sharing one
 * selected stage and one focus year so charts, timeline and limitations stay connected.
 * Mounted per result (keyed by the caller), so selections reset for a new investigation.
 */
export default function MissionFindings({ analysis, place }: { analysis: Analysis; place?: string }) {
  const [stage, setStage] = useState<StageId>("dataset");
  const [focusYear, setFocusYear] = useState<number | null>(null);
  const [lab, setLab] = useState<LabId>("trend");
  const expeditionRef = useRef<HTMLElement>(null);
  const labRef = useRef<HTMLDivElement>(null);

  const selectYear = (year: number) => setFocusYear((y) => (y === year ? null : year));
  const inspectYearFromChart = (year: number) => {
    setFocusYear(year);
    setStage("eligible");
  };

  return (
    <>
      <ResultSummary analysis={analysis} place={place} />
      <section className="layer layer-data" aria-labelledby="layer-4">
        <h3 id="layer-4" className="layer-title"><span className="layer-num" aria-hidden>04</span>What does the data look like?</h3>
        <div className="charts">
          <TrendChart analysis={analysis} focusYear={focusYear} onSelectYear={inspectYearFromChart} />
          <SeriesChart analysis={analysis} />
          <SeasonalChart analysis={analysis} />
        </div>
      </section>
      <EvidenceExpedition
        ref={expeditionRef}
        analysis={analysis}
        stage={stage}
        onStage={setStage}
        focusYear={focusYear}
        onFocusYear={selectYear}
        lab={lab}
        onLab={(l) => { setLab(l); reveal(labRef.current); }}
        labRef={labRef}
      />
      <ScientificGuardrails analysis={analysis} onShowEvidence={(s) => { setStage(s); reveal(expeditionRef.current); }} />
      <div className="dossier-foot dossier-foot-single">
        <ProvenanceCard analysis={analysis} />
        <a className="text-link" href="#evaluation">Open Mission Control for the full evidence review →</a>
      </div>
    </>
  );
}
