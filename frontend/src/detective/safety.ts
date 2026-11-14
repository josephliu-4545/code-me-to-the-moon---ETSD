/**
 * Input and output guards. Questions are untrusted text: they are length-limited, stripped of
 * control characters, and never interpreted as instructions. Answers are rendered as React text
 * (never as HTML), and only internal anchors or DOI links built from validated catalog DOIs are linked.
 */
export const MAX_QUESTION_CHARS = 500;
export const MAX_TURNS_PER_CONVERSATION = 40;
export const MAX_CONVERSATIONS = 6;

// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2066-\u2069]/g;

export interface CleanQuestion {
  text: string;
  truncated: boolean;
  empty: boolean;
}

export function cleanQuestion(raw: string): CleanQuestion {
  const stripped = raw.replace(CONTROL, "").replace(/\s+/g, " ").trim();
  const truncated = stripped.length > MAX_QUESTION_CHARS;
  const text = truncated ? stripped.slice(0, MAX_QUESTION_CHARS) : stripped;
  return { text, truncated, empty: text.length === 0 };
}

const INJECTION = [
  /\b(ignore|disregard|forget|override)\b.{0,40}\b(instruction|rule|prompt|previous|above|evidence|guideline)s?\b/i,
  /\b(system|developer)\s*(prompt|message|instruction)s?\b/i,
  /\byou are now\b|\bact as\b|\bpretend (to be|you)\b|\bjailbreak\b|\bDAN\b/i,
  /\b(new|updated) (rules|instructions)\b/i,
  /<\s*\/?\s*(script|iframe|img|svg|style)\b/i,
  /\b(say|state|claim|report|answer) that\b.{0,60}\b(significant|proven|caused|p\s*=)/i,
];

const SECRETS = /\b(api[\s_-]*keys?|secret|token|password|credential|\.env|service[\s_-]*account|private[\s_-]*key|earth engine (key|credential)s?|env(ironment)? variables?)\b/i;

export function looksLikeInjection(text: string): boolean {
  return INJECTION.some((re) => re.test(text));
}

export function asksForSecrets(text: string): boolean {
  return SECRETS.test(text);
}

/** Defence in depth: never display anything shaped like a credential, even if it reached an answer. */
export function redactSecrets(text: string): string {
  return text
    .replace(/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "[redacted]")
    .replace(/\b(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|ya29\.[0-9A-Za-z_-]{20,})\b/g, "[redacted]")
    .replace(/\b[\w.-]+@[\w-]+\.iam\.gserviceaccount\.com\b/g, "[redacted]");
}

const DOI_RE = /^10\.\d{4,9}\/[^\s"<>]+$/;

/** Allowed link targets: in-app section anchors, or https://doi.org/ for a validated DOI. */
export function safeHref(href: string | undefined): string | undefined {
  if (!href) return undefined;
  if (/^#(explore|evaluation|compare|relationships|science)$/.test(href)) return href;
  const m = /^https:\/\/doi\.org\/(.+)$/.exec(href);
  if (!m) return undefined;
  let doi: string;
  try {
    doi = decodeURIComponent(m[1]!);
  } catch {
    return undefined; // malformed percent-encoding: reject, never throw into the UI
  }
  return DOI_RE.test(doi) ? href : undefined;
}
