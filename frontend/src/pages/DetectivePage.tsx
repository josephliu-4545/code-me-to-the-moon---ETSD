import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { isUnreachable, type Analysis, type AnalysisRequest, type VariableInfo } from "../api/types";
import AnswerCard from "../components/detective/AnswerCard";
import "../components/detective/detective.css";
import { ErrorBox, Loading } from "../components/ResultPanels";
import EmptyState from "../components/ui/EmptyState";
import PageHero from "../components/ui/PageHero";
import { answerQuestion, num, suggestedQuestions, type Answer } from "../detective/answers";
import { newTurnId, type ConversationApi, type Turn } from "../detective/conversation";
import { analysisMatches, buildEvidence, toInvestigation, type Evidence, type Investigation } from "../detective/evidence";
import { classify } from "../detective/intents";
import { comparisonFromCache, relationshipsFromCache, type RelatedEvidence } from "../detective/related";
import { cleanQuestion, MAX_QUESTION_CHARS } from "../detective/safety";
import { fmtCoord, pText } from "../lib/format";
import { findSnapshot, useAnalysis } from "../state/useAnalysis";

/** Conversation bucket used before any investigation exists (only "how do I start" style guidance). */
const NO_INVESTIGATION: Investigation = { key: "__none__", variable: "", variableName: "No investigation", place: "", latitude: 0, longitude: 0, startYear: 0, endYearInclusive: 0, mode: "point", dataset: null };

function investigationLine(inv: Investigation): string {
  return `${inv.variableName} · ${inv.place} (${fmtCoord(inv.latitude, inv.longitude)}) · ${inv.startYear}–${inv.endYearInclusive}${inv.dataset ? ` · ${inv.dataset}` : ""}${inv.mode === "region" ? " · region" : ""}`;
}

function EvidencePanel({ e }: { e: Evidence }) {
  const t = e.trend;
  const rows: [string, string][] = [
    ["Dataset", `${e.dataset.source} — ${e.dataset.id} (${e.dataset.version})`],
    ["Footprint", `${e.footprint.description} · ${e.footprint.resolution}`],
    ["Data status", e.dataStatus.label],
    e.seasonal
      ? ["Years contributing (monthly)", `${e.seasonal.yearsContributing.length} of ${e.observations.yearsRequested}`]
      : ["Eligible years", `${e.observations.eligible.length} of ${e.observations.yearsRequested}`],
    ["Excluded years", e.observations.excluded.length ? e.observations.excluded.map((x) => x.year).join(", ") : "none"],
    [t.estimator, t.slope === null ? `unavailable${t.slopeUnavailableReason ? ` — ${t.slopeUnavailableReason}` : ""}` : `${num(t.slope)} ${e.units.slope ?? ""}`],
    ["95% interval", t.confidenceInterval ? `${num(t.confidenceInterval[0])} to ${num(t.confidenceInterval[1])}` : t.confidenceIntervalUnavailableReason ?? "not reported"],
    [t.test, t.significance ? `${pText(t.significance.pValue)} (α = ${t.significance.alpha})` : t.significanceUnavailableReason ?? "no test reported"],
    ["Result level", t.resultLevelLabel ?? "not reported"],
  ];
  if (e.seasonal) rows.splice(5, 0, ["Months used", e.seasonal.months.join(", ") || "none"]);
  return (
    <details className="dt-evidence" data-testid="evidence-panel">
      <summary>Evidence the assistant can use</summary>
      <dl>{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      <p className="note">Values are copied from the analysis returned by the application's backend; the assistant does not recalculate them.</p>
    </details>
  );
}

function Transcript({ turns, prefix }: { turns: Turn[]; prefix: string }) {
  return (
    <>
      {turns.map((t) =>
        t.role === "user" ? (
          <div key={t.id} className="dt-turn dt-user">
            <span className="sr-only">You asked:</span>
            <p>{t.text}</p>
            {t.truncated && <p className="note">Your question was shortened to {MAX_QUESTION_CHARS} characters.</p>}
          </div>
        ) : (
          <div key={t.id} className="dt-turn dt-assistant">
            <span className="sr-only">Detective answered:</span>
            {t.answer && <AnswerCard answer={t.answer} headingId={`${prefix}-a${t.id}`} />}
          </div>
        ),
      )}
    </>
  );
}

export default function DetectivePage({ submitted, place, variables, conversations }: {
  submitted: AnalysisRequest | null;
  place: string;
  variables: VariableInfo[];
  conversations: ConversationApi;
}) {
  const query = useAnalysis(submitted);
  const unreachable = isUnreachable(query.error);
  // Offline only: a clearly labelled saved snapshot of an earlier live retrieval (static file, no NASA request).
  const snapshot = useQuery({
    queryKey: ["snapshot", submitted],
    queryFn: () => findSnapshot(submitted!),
    enabled: submitted !== null && unreachable,
    staleTime: Infinity,
  });
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const variableName = variables.find((v) => v.id === submitted?.variable)?.name ?? submitted?.variable ?? "";
  const inv = submitted ? toInvestigation(submitted, variableName, place) : null;
  const analysis: Analysis | undefined = query.data ?? (unreachable ? snapshot.data ?? undefined : undefined);
  const current = analysis && inv && analysisMatches(analysis, inv) ? analysis : undefined;
  const evidence = useMemo(() => (current && inv ? buildEvidence(current, inv) : null), [current, inv?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const conversation = inv ? conversations.store[inv.key] : undefined;
  const earlier = Object.values(conversations.store).filter((c) => c.investigation.key !== inv?.key && c.investigation.key !== NO_INVESTIGATION.key && c.turns.length > 0);

  function related(): RelatedEvidence | null {
    if (!inv) return null;
    return {
      comparison: comparisonFromCache(queryClient.getQueriesData({ queryKey: ["compare"] }), inv),
      relationships: relationshipsFromCache(queryClient.getQueriesData({ queryKey: ["relationships"] }), inv),
    };
  }

  function ask(raw: string) {
    const q = cleanQuestion(raw);
    if (q.empty) return;
    const c = classify(q.text, conversation?.lastIntent ?? null);
    const a: Answer = answerQuestion(c, evidence, related());
    conversations.append(inv ?? NO_INVESTIGATION, [
      { id: newTurnId(), role: "user", text: q.text, truncated: q.truncated },
      { id: newTurnId(), role: "assistant", answer: a },
    ], a.intent && a.intent !== "injection" && a.intent !== "secrets" ? a.intent : null);
    setAnnouncement(`Answer ready: ${a.topic}.`);
    setDraft("");
    inputRef.current?.focus();
  }

  const noneConversation = !inv ? conversations.store[NO_INVESTIGATION.key] : undefined;
  const turns = (inv ? conversation : noneConversation)?.turns ?? [];
  const dropped = (inv ? conversation : noneConversation)?.dropped ?? 0;
  const suggestions = suggestedQuestions(evidence, evidence ? related() : null).slice(0, 6);
  const ready = !submitted || !!evidence;

  return (
    <div className="page page-detective">
      <PageHero kicker="AI Earth Detective" title="Ask about your investigation" tone="control">
        <p>Questions are answered from the analysis you ran in Explore Earth — its NASA data, statistics and caveats. Each answer separates what was observed from interpretation, uncertainty and background, and lists its evidence.</p>
      </PageHero>
      <div className="page-body dt-body">
        <aside className="dt-how" aria-labelledby="dt-how-h">
          <h2 id="dt-how-h" className="dt-how-title">How this assistant works</h2>
          <p>It is a rule-based, evidence-grounded assistant: it matches your question to supported topics and fills in answers from the analysis results. It does not use a generative language model, does not calculate new statistics, and makes no calls to external AI services.</p>
        </aside>

        {!submitted && (
          <EmptyState title="No investigation yet." action={<a className="btn btn-ink" href="#explore">Go to Explore Earth →</a>}>
            <p>Launch an investigation in Explore Earth, then come back to ask about it. You can still ask how to get started.</p>
          </EmptyState>
        )}

        {inv && (
          <section className="dt-active" aria-label="Active investigation" data-testid="active-investigation">
            <p className="kicker">Active investigation</p>
            <p className="dt-active-line">{investigationLine(inv)}</p>
            {evidence && <p className="dt-active-status">{evidence.dataStatus.label}</p>}
            {evidence && <EvidencePanel e={evidence} />}
          </section>
        )}

        {submitted && (query.isPending || query.isFetching) && !evidence && <Loading label="Waiting for the investigation's NASA data and statistics…" />}
        {submitted && unreachable && snapshot.isFetching && <Loading label="Looking for a saved snapshot…" />}
        {submitted && query.isError && !unreachable && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}
        {submitted && unreachable && snapshot.isSuccess && !snapshot.data && (
          <ErrorBox error={query.error} onRetry={() => query.refetch()} extra={<p>No saved snapshot matches this investigation, so there is no evidence to answer from.</p>} />
        )}

        <section className="dt-chat" aria-label="Conversation with the AI Earth Detective">
          <div className="dt-log" role="log" aria-label="Conversation history" data-testid="conversation">
            {dropped > 0 && <p className="note">{dropped} earlier messages were removed to keep the conversation short.</p>}
            {turns.length === 0 && ready && <p className="dt-empty">{evidence ? "Ask a question about this investigation, or choose a suggestion." : "Ask how to start, or launch an investigation first."}</p>}
            <Transcript turns={turns} prefix="cur" />
          </div>
          <p className="sr-only" role="status" aria-live="polite">{announcement}</p>

          {ready && (
            <div className="dt-suggestions" role="group" aria-label="Suggested questions">
              {suggestions.map((s) => <button key={s} type="button" className="dt-chip" onClick={() => ask(s)}>{s}</button>)}
            </div>
          )}

          <form className="dt-form" onSubmit={(ev) => { ev.preventDefault(); ask(draft); }}>
            <label htmlFor="dt-q" className="sr-only">Your question</label>
            <input
              id="dt-q"
              ref={inputRef}
              type="text"
              value={draft}
              maxLength={MAX_QUESTION_CHARS}
              onChange={(ev) => setDraft(ev.target.value)}
              placeholder={evidence ? `Ask about ${inv?.variableName.toLowerCase()} in ${inv?.place}…` : "Ask a question…"}
              disabled={!ready}
              autoComplete="off"
              aria-describedby="dt-q-hint"
            />
            <button type="submit" className="btn btn-ink" disabled={!ready || cleanQuestion(draft).empty}>Ask</button>
            <button type="button" className="btn btn-ghost" disabled={turns.length === 0} onClick={() => { conversations.clear(inv?.key ?? NO_INVESTIGATION.key); setAnnouncement("New conversation started."); inputRef.current?.focus(); }}>New conversation</button>
            <p id="dt-q-hint" className="dt-hint">{draft.length}/{MAX_QUESTION_CHARS} characters. Questions are not sent to any external service.</p>
          </form>
        </section>

        {earlier.length > 0 && (
          <details className="dt-earlier">
            <summary>Earlier conversations ({earlier.length}) — other investigations</summary>
            {earlier.map((c) => (
              <section key={c.investigation.key} className="dt-earlier-item" aria-label={`Conversation about ${investigationLine(c.investigation)}`}>
                <p className="dt-earlier-label">Answers below refer only to: {investigationLine(c.investigation)}</p>
                <Transcript turns={c.turns} prefix={`old${c.investigation.key.length}-${c.turns[0]?.id ?? 0}`} />
              </section>
            ))}
          </details>
        )}
      </div>
    </div>
  );
}
