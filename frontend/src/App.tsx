import { useEffect, useRef, useState } from "react";
import type { Analysis, AnalysisRequest } from "./api/types";
import SiteHeader, { type NavItem } from "./components/layout/SiteHeader";
import Wordmark from "./components/layout/Wordmark";
import Starfield from "./components/layout/Starfield";
import { ErrorBox, Loading } from "./components/ResultPanels";
import CompareDatasetsPage from "./pages/CompareDatasetsPage";
import DetectivePage from "./pages/DetectivePage";
import EvaluationPage from "./pages/EvaluationPage";
import ExplorePage from "./pages/ExplorePage";
import InvestigationPage from "./pages/InvestigationPage";
import RelationshipsPage from "./pages/RelationshipsPage";
import SciencePage from "./pages/SciencePage";
import { readStoredInvestigation, storeInvestigation, type StoredInvestigation } from "./state/investigation";
import { requestIdentity, toRequest, useSelection } from "./state/selection";
import { useTheme } from "./state/theme";
import { useConversationStore } from "./detective/conversation";
import { findSnapshot, useVariables } from "./state/useAnalysis";

const TABS = [
  { id: "explore", label: "Explore Earth", short: "Explore Earth" },
  { id: "history", label: "Historical Discovery", short: "Historical Discovery" },
  { id: "findings", label: "Mission Findings", short: "Mission Findings" },
  { id: "evaluation", label: "Scientific Evaluation", short: "Evaluation" },
  { id: "compare", label: "Compare Datasets", short: "Compare" },
  { id: "relationships", label: "Earth System Relationships", short: "Relationships" },
  { id: "detective", label: "AI Earth Detective", short: "Detective" },
  { id: "living", label: "Living Environment", short: "Living Environment", planned: true },
  { id: "science", label: "Scientific Information", short: "Field Guide" },
] as const satisfies readonly NavItem[];
type Tab = Exclude<(typeof TABS)[number]["id"], "living">;
const ROUTES: Tab[] = ["explore", "history", "findings", "evaluation", "compare", "relationships", "detective", "science"];

function currentTab(): Tab {
  const h = window.location.hash.replace("#", "") as Tab;
  return ROUTES.includes(h) ? h : "explore";
}

const POSTER = `${import.meta.env.BASE_URL}brand/code-me-to-the-moon.webp`;

export default function App() {
  const [tab, setTab] = useState<Tab>(currentTab);
  const [selection, update] = useSelection();
  const [submitted, setSubmitted] = useState<AnalysisRequest | null>(null);
  const [submittedPlace, setSubmittedPlace] = useState("");
  // A saved snapshot is valid only for the exact request it was loaded for (stale-result protection).
  const [snapshotState, setSnapshotState] = useState<{ key: string; analysis: Analysis } | null>(null);
  const snapshot = snapshotState && submitted && snapshotState.key === requestIdentity(submitted) ? snapshotState.analysis : null;
  const setSnapshot = (a: Analysis | null) => setSnapshotState(a && submitted ? { key: requestIdentity(submitted), analysis: a } : null);
  /** Load the saved snapshot for the submitted investigation (static file; no NASA request). */
  const loadSnapshot = async (): Promise<boolean> => {
    if (!submitted) return false;
    const key = requestIdentity(submitted);
    const s = await findSnapshot(submitted);
    setSnapshotState(s ? { key, analysis: s } : null);
    return s !== null;
  };
  // After a reload, offer (never auto-run) the investigation last executed in this tab.
  const [resumable, setResumable] = useState<StoredInvestigation | null>(readStoredInvestigation);
  const execute = (request: AnalysisRequest, place: string) => {
    setSnapshotState(null);
    setSubmittedPlace(place);
    setSubmitted(request);
    setResumable(null);
    storeInvestigation({ request, place });
  };
  const conversations = useConversationStore();
  const variables = useVariables();
  const [theme, , toggleTheme] = useTheme();

  useEffect(() => {
    const onHash = () => setTab(currentTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const firstTab = useRef(true);
  useEffect(() => {
    // New section: start at the top, as a page navigation would (not on first load).
    if (firstTab.current) {
      firstTab.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
  }, [tab]);

  return (
    <div className={`app app-${tab}`}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <SiteHeader items={TABS} current={tab} theme={theme} onToggleTheme={toggleTheme} />
      {variables.data?.offline && (
        <div className="offline-banner" role="status">
          <strong>Offline mode</strong>
          <span>The analysis backend is not reachable. Live NASA retrievals are unavailable; you can view clearly labelled saved snapshots of earlier live retrievals for the Yangon 2015–2024 demo.</span>
        </div>
      )}
      {resumable && !submitted && variables.data && (
        <div className="resume-banner" role="region" aria-label="Previous investigation">
          <p>
            <strong>Previous investigation not reloaded.</strong>{" "}
            {resumable.place || "Selected location"} · {resumable.request.variable.replace(/_/g, " ")} · {resumable.request.startYear}–{resumable.request.endYear - 1}.
            {" "}Results are not re-requested automatically, to avoid repeating NASA and Earth Engine requests.
          </p>
          <div className="resume-actions">
            <button type="button" className="btn btn-ink" onClick={() => execute(resumable.request, resumable.place)}>Resume investigation</button>
            <button type="button" className="btn btn-ghost" onClick={() => { setResumable(null); storeInvestigation(null); }}>Dismiss</button>
          </div>
        </div>
      )}
      <main id="main" tabIndex={-1}>
        {variables.isPending && (
          <div className="arrival">
            <Starfield />
            <figure className="arrival-art">
              <img src={POSTER} width={640} height={640} alt="Code Me to the Moon — NASA Space Apps Challenge 2026 team artwork: an astronaut facing a ringed planet over a golden horizon." />
            </figure>
            <div className="arrival-status"><Loading label="Connecting to the analysis service…" /></div>
          </div>
        )}
        {variables.isError && (
          <div className="page page-status">
            <ErrorBox error={variables.error} onRetry={() => variables.refetch()} />
          </div>
        )}
        {variables.data && (
          <div className="view" key={tab}>
            {tab === "explore" && (
              <ExplorePage
                variables={variables.data.variables}
                selection={selection}
                onChange={update}
                submitted={submitted}
                submittedPlace={submittedPlace}
                snapshot={snapshot}
                onSnapshot={setSnapshot}
                onLoadSnapshot={loadSnapshot}
                onSubmit={() => execute(toRequest(selection), selection.placeName)}
                theme={theme}
              />
            )}
            {(tab === "history" || tab === "findings") && (
              <InvestigationPage
                section={tab}
                submitted={submitted}
                selection={selection}
                onChange={update}
                snapshot={snapshot}
                onStart={(request) => execute(request, selection.placeName)}
                onSnapshot={(value, request) => setSnapshotState(value ? { key: requestIdentity(request), analysis: value } : null)}
              />
            )}
            {tab === "evaluation" && <EvaluationPage submitted={submitted} snapshot={snapshot} onLoadSnapshot={loadSnapshot} />}
            {tab === "compare" && <CompareDatasetsPage selection={selection} />}
            {tab === "relationships" && <RelationshipsPage variables={variables.data.variables} selection={selection} />}
            {tab === "detective" && <DetectivePage submitted={submitted} place={submittedPlace} variables={variables.data.variables} conversations={conversations} snapshot={snapshot} onLoadSnapshot={loadSnapshot} />}
            {tab === "science" && <SciencePage variables={variables.data.variables} caveats={variables.data.caveats} />}
          </div>
        )}
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <img className="footer-art" src={POSTER} width={112} height={112} alt="" loading="lazy" />
          <div className="footer-brand">
            <Wordmark />
            <p className="footer-mission">Earth System Trend Detective · NASA Space Apps Challenge 2026</p>
          </div>
          <p className="footer-data">Data: NASA POWER, GPM IMERG, MODIS, GLDAS and SMAP via NASA services and Google Earth Engine. Values describe grid cells or sampling areas, not exact addresses. Statistical results are descriptive or indicative; see Scientific Information.</p>
        </div>
      </footer>
    </div>
  );
}
