/**
 * Conversation state, kept per investigation so evidence never leaks between investigations.
 * Each conversation is permanently labelled with the investigation it belongs to.
 */
import { useCallback, useState } from "react";
import type { Answer } from "./answers";
import type { Investigation } from "./evidence";
import type { Intent } from "./intents";
import { MAX_CONVERSATIONS, MAX_TURNS_PER_CONVERSATION } from "./safety";

export interface Turn {
  id: number;
  role: "user" | "assistant";
  text?: string;
  answer?: Answer;
  truncated?: boolean;
}

export interface Conversation {
  investigation: Investigation;
  turns: Turn[];
  /** Intent of the last assistant answer, used to resolve short follow-ups. */
  lastIntent: Intent | null;
  /** Oldest turns dropped because of the history limit. */
  dropped: number;
}

export type ConversationStore = Record<string, Conversation>;

let nextId = 1;
export const newTurnId = () => nextId++;

export function appendTurns(store: ConversationStore, inv: Investigation, turns: Turn[], lastIntent: Intent | null): ConversationStore {
  const prev = store[inv.key] ?? { investigation: inv, turns: [], lastIntent: null, dropped: 0 };
  const all = [...prev.turns, ...turns];
  const overflow = Math.max(0, all.length - MAX_TURNS_PER_CONVERSATION);
  const next: Conversation = { investigation: prev.investigation, turns: all.slice(overflow), lastIntent: lastIntent ?? prev.lastIntent, dropped: prev.dropped + overflow };
  const rest = Object.entries(store).filter(([k]) => k !== inv.key);
  // Keep the most recent conversations only; the active one is always kept.
  const kept = rest.slice(Math.max(0, rest.length - (MAX_CONVERSATIONS - 1)));
  return { ...Object.fromEntries(kept), [inv.key]: next };
}

export function clearConversation(store: ConversationStore, key: string): ConversationStore {
  const rest = { ...store };
  delete rest[key];
  return rest;
}

export function useConversationStore() {
  const [store, setStore] = useState<ConversationStore>({});
  const append = useCallback((inv: Investigation, turns: Turn[], lastIntent: Intent | null) => setStore((s) => appendTurns(s, inv, turns, lastIntent)), []);
  const clear = useCallback((key: string) => setStore((s) => clearConversation(s, key)), []);
  return { store, append, clear };
}
export type ConversationApi = ReturnType<typeof useConversationStore>;
