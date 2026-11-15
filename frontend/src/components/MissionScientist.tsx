import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Analysis, ChatMessage } from "../api/types";

const SUGGESTIONS = [
  ["Explain this result", "Explain this result in plain language."],
  ["How strong is the evidence?", "How strong is the evidence, and what should I be cautious about?"],
  ["What can’t this data tell me?", "What can’t this data tell me?"],
] as const;

export default function MissionScientist({ context }: { context?: Analysis }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, busy]);

  async function ask(content: string) {
    const clean = content.trim();
    if (!clean || busy) return;
    const next = [...messages, { role: "user" as const, content: clean }];
    setMessages(next);
    setDraft("");
    setError("");
    setBusy(true);
    try {
      const response = await api.chat(next.slice(-12), context);
      setMessages([...next, { role: "assistant", content: response.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mission Scientist could not answer right now.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  return (
    <aside className={`mission-chat ${open ? "is-open" : ""}`} aria-label="Mission Scientist chatbot">
      {open && (
        <section className="mission-chat-panel" role="dialog" aria-label="Mission Scientist">
          <header className="mission-chat-head">
            <div><span className="mission-chat-signal" aria-hidden /><p className="kicker">AI field assistant</p><h2>Mission Scientist</h2></div>
            <button type="button" className="mission-chat-close" onClick={() => setOpen(false)} aria-label="Close Mission Scientist">×</button>
          </header>
          <div className="mission-chat-log" ref={scrollRef} aria-live="polite">
            <div className="mission-chat-message assistant">
              {context
                ? "I can explain this investigation using its NASA data, methods, and stated limitations."
                : "Launch an investigation and I can interpret its results. I can still answer questions about how the app works."}
            </div>
            {messages.map((message, index) => <div className={`mission-chat-message ${message.role}`} key={`${message.role}-${index}`}>{message.content}</div>)}
            {busy && <div className="mission-chat-message assistant is-thinking">Checking the evidence…</div>}
            {error && <p className="mission-chat-error" role="alert">{error}</p>}
          </div>
          {context && messages.length === 0 && <div className="mission-chat-suggestions">
            {SUGGESTIONS.map(([label, prompt]) => <button type="button" key={label} onClick={() => void ask(prompt)}>{label}</button>)}
          </div>}
          <form className="mission-chat-form" onSubmit={submit}>
            <label className="sr-only" htmlFor="mission-question">Ask a question</label>
            <textarea id="mission-question" rows={2} value={draft} maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about the findings…" />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send question">↑</button>
          </form>
          <p className="mission-chat-note">AI can make mistakes. Check the charts, provenance, and limitations.</p>
        </section>
      )}
      <button type="button" className="mission-chat-launch" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Ask Mission Scientist">
        <span aria-hidden>✦</span><span>Ask the scientist</span>
      </button>
    </aside>
  );
}
