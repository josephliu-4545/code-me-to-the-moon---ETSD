/**
 * Layer 2 — question understanding.
 *
 * Transparent, rule-based intent matching (weighted phrase patterns). It is not a language model:
 * it recognises common phrasings of supported questions, asks for clarification when two different
 * intents match equally, and declines rather than forcing a question into the nearest category.
 */
import { asksForSecrets, looksLikeInjection } from "./safety";

export type Intent =
  | "overview"
  | "direction"
  | "magnitude"
  | "significance"
  | "why_no_significance"
  | "confidence_interval"
  | "causality_why"
  | "causality_proof"
  | "cause_evidence"
  | "reliability"
  | "excluded"
  | "missing"
  | "provenance"
  | "dataset_choice"
  | "dataset_disagreement"
  | "ols_vs_theil_sen"
  | "methodology"
  | "seasonal_months"
  | "autocorrelation"
  | "change_point"
  | "correlation"
  | "getting_started"
  | "prediction"
  | "secrets"
  | "injection";

type Rule = [RegExp, number];

/** Weighted phrase patterns. Specific multi-word phrasings carry more weight than single words. */
const RULES: Record<Exclude<Intent, "secrets" | "injection">, Rule[]> = {
  overview: [[/\bwhat(?:'s| is) (happening|going on)\b/, 3], [/\b(summar(y|ise|ize)|overview|tell me about|explain (the|this) (result|analysis|investigation))\b/, 3]],
  direction: [[/\b(increas|decreas|ris(e|ing)|fall(ing)?|declin|going (up|down)|warming|cooling|drying|wetting|greening|browning)\w*/, 2], [/\b(is there|any) (a )?trend\b/, 3], [/\bwhat does (this|the) trend mean\b/, 3], [/\btrend\b/, 1]],
  magnitude: [[/\bhow (much|fast|quickly|big|large|strong)\b/, 3], [/\b(rate|amount|magnitude|per (year|decade)|slope)\b/, 2], [/\bchanged?\b/, 1]],
  significance: [[/\b(statistically )?significan\w*/, 3], [/\bp[\s-]?values?\b/, 3], [/\bmann[\s–-]*kendall\b/, 1], [/\bis (it|that|this) real\b/, 2]],
  why_no_significance: [[/\b(why|how come)\b.{0,60}\b(no|not|n't|without|couldn't|could not|unavailable|missing|withheld)\b.{0,40}\b(significan\w*|test|p[\s-]?value|inference)/, 6], [/\bno significance test\b/, 5]],
  confidence_interval: [[/\bconfidence interval\b/, 4], [/\b(95 ?%|uncertainty) (interval|range)\b/, 4], [/\binterval\b/, 2], [/\buncertain(ty)?\b/, 1]],
  causality_why: [[/\bwhy (is|are|has|have|did|does|do)\b/, 3], [/\b(cause[sd]?|causing|driv(ing|er|ers|en)|reason for|because of|responsible for|due to)\b/, 3], [/\b(urban|land[\s-]?use|deforest|el ni(n|ñ)o|enso|greenhouse)\w*/, 1]],
  causality_proof: [[/\b(prove|proof|proves|demonstrat\w*|confirm\w*|show)\b.{0,50}\b(climate change|global warming|caus\w*)/, 6], [/\b(climate change|global warming)\b.{0,30}\b(caus\w*|responsible|behind|to blame)\b/, 5], [/\bis (this|it|that) (climate change|global warming)\b/, 5]],
  cause_evidence: [[/\b(what|which) (evidence|data|analysis|information)\b.{0,50}\b(need|needed|required|would)\b/, 5], [/\b(investigate|establish|determine|identify|attribut\w*)\b.{0,30}\b(cause|causes|driver|drivers|attribution)\b/, 5]],
  reliability: [[/\b(trust|reliab\w*|believ\w*|accura\w*|robust\w*|credib\w*|depend on)\b/, 3], [/\b(data )?quality\b/, 2], [/\bhow (good|sure|confident)\b/, 3], [/\blimitations?\b|\bcaveats?\b|\bweakness\w*/, 3]],
  excluded: [[/\bexclud\w*|\bdropped\b|\bremoved\b|\bleft out\b|\bnot used\b/, 3], [/\bwhich years\b/, 2], [/\bpassed quality control\b|\bquality[\s-]control\b|\bqc\b/, 3]],
  missing: [[/\bmissing\b|\bgaps?\b|\bincomplete\b/, 3], [/\bcoverage\b|\bcomplete(ness)?\b/, 2]],
  provenance: [[/\b(which|what) (dataset|data|source|satellite|product|model)\b(?!.{0,20}\bshould\b)/, 3], [/\b(source|provenance|version|doi|cite|citation|reference|where does the data)\b/, 2], [/\bnasa (power|imerg|modis|gldas|smap)\b/, 1]],
  dataset_choice: [[/\b(which|what) (dataset|data(set)?|source|product)\b.{0,30}\b(should|best|recommend|use)\b/, 6], [/\bbest dataset\b|\brecommend\w* (a )?dataset\b/, 6]],
  dataset_disagreement: [[/\b(disagree\w*|differ\w*|discrepan\w*|inconsistent|agreement|agree)\b.{0,40}\b(dataset|datasets|product|products|sources|records|gldas|smap|imerg|chirps|era5|power)\b/, 6], [/\b(datasets|products|records)\b.{0,30}\b(disagree\w*|differ\w*|agree\w*)\b/, 6], [/\bgldas\b.{0,20}\bsmap\b|\bsmap\b.{0,20}\bgldas\b/, 5]],
  ols_vs_theil_sen: [[/\bols\b|\bordinary least squares\b|\bleast[\s-]squares\b|\blinear regression\b/, 4], [/\btheil[\s–-]*sen\b/, 2]],
  methodology: [[/\b(method|methods|methodology|calculat\w*|comput\w*|estimat\w*)\b/, 2], [/\bseasonal kendall\b|\bsen'?s? slope\b/, 3], [/\bhow (was|is|did you) (the )?(trend|this|it)\b/, 3], [/\bwhy (does|did|is) (this|the) (analysis|app|trend|result)\b.{0,30}\b(use|using|used)\b/, 4]],
  seasonal_months: [[/\bwhich months\b|\bwhat months\b|\bmonths (used|contribut\w*|included)\b/, 6]],
  autocorrelation: [[/\b(auto[\s-]?correlat\w*|serial (correlation|dependence)|dependence|independen\w*|lag[\s-]?1)\b/, 4]],
  change_point: [[/\b(change[\s-]?point|abrupt|sudden|step change|jump|shift|pettitt|break ?point)\b/, 4]],
  correlation: [[/\b(correlat\w*|relationship|related to|associat\w*|vary together|linked|connection)\b/, 4]],
  getting_started: [[/\bhow (do|can) i (start|begin|use|run)\b|\bget(ting)? started\b|\bwhat can (you|i) (do|ask)\b|\bhelp\b/, 4]],
  prediction: [[/\b(predict\w*|forecast\w*|projection|project(ed)? (to|for)|next (year|decade)|in (20[3-9]\d|21\d\d)|future)\b/, 5]],
};

/** Short elliptical follow-ups that depend on the previous turn. */
const FOLLOW_UP_WHY = /^(and )?(but )?why\??$|^why (is )?(that|this|so)\??$|^how come\??$/;
const FOLLOW_UP_MORE = /^(tell me more|more|explain( more| that)?|go on|details?|elaborate)\.?\??$/;

export interface Classification {
  intent: Intent | null;
  status: "matched" | "follow_up" | "ambiguous" | "unsupported";
  /** For ambiguous questions: the competing intents, best first. */
  candidates: Intent[];
}

/** Intents where "why?" asks for a physical explanation of the finding. */
const PHYSICAL = new Set<Intent>(["overview", "direction", "magnitude", "causality_why"]);

export function classify(raw: string, previous: Intent | null): Classification {
  const q = raw.toLowerCase().replace(/[’`]/g, "'").trim();
  if (looksLikeInjection(q)) return { intent: "injection", status: "matched", candidates: [] };
  if (asksForSecrets(q)) return { intent: "secrets", status: "matched", candidates: [] };

  if (FOLLOW_UP_WHY.test(q)) {
    if (!previous) return { intent: null, status: "ambiguous", candidates: ["causality_why", "why_no_significance"] };
    if (PHYSICAL.has(previous)) return { intent: "causality_why", status: "follow_up", candidates: [] };
    if (previous === "significance" || previous === "why_no_significance") return { intent: "why_no_significance", status: "follow_up", candidates: [] };
    if (previous === "excluded" || previous === "missing") return { intent: "missing", status: "follow_up", candidates: [] };
    return { intent: previous, status: "follow_up", candidates: [] };
  }
  if (FOLLOW_UP_MORE.test(q)) {
    return previous ? { intent: previous, status: "follow_up", candidates: [] } : { intent: null, status: "unsupported", candidates: [] };
  }

  const scores: [Intent, number][] = [];
  for (const [intent, rules] of Object.entries(RULES) as [Intent, Rule[]][]) {
    const score = rules.reduce((s, [re, w]) => (re.test(q) ? s + w : s), 0);
    if (score > 0) scores.push([intent, score]);
  }
  scores.sort((a, b) => b[1] - a[1]);
  if (!scores.length || scores[0]![1] < 2) return { intent: null, status: "unsupported", candidates: scores.map((s) => s[0]) };

  const [best, second] = scores;
  if (second && second[1] === best![1] && !compatible(best![0], second[0])) {
    return { intent: null, status: "ambiguous", candidates: [best![0], second[0]] };
  }
  const isFollowUp = previous !== null && q.split(" ").length <= 5 && /\b(that|this|it|those|these)\b/.test(q);
  return { intent: best![0], status: isFollowUp ? "follow_up" : "matched", candidates: [] };
}

/** Pairs where a tie is resolved by the first intent without asking (they answer the same need). */
function compatible(a: Intent, b: Intent): boolean {
  const pairs: [Intent, Intent][] = [
    ["direction", "magnitude"],
    ["magnitude", "direction"],
    ["significance", "direction"],
    ["direction", "significance"],
    ["excluded", "missing"],
    ["missing", "excluded"],
    ["methodology", "ols_vs_theil_sen"],
    ["ols_vs_theil_sen", "methodology"],
  ];
  return pairs.some(([x, y]) => x === a && y === b);
}

export const INTENT_LABELS: Record<Intent, string> = {
  overview: "Summary of the investigation",
  direction: "Trend direction",
  magnitude: "Size of the change",
  significance: "Statistical significance",
  why_no_significance: "Why significance is (un)available",
  confidence_interval: "Confidence interval",
  causality_why: "Possible causes",
  causality_proof: "Causation and proof",
  cause_evidence: "Evidence needed for attribution",
  reliability: "Reliability",
  excluded: "Excluded years",
  missing: "Missing data",
  provenance: "Dataset and provenance",
  dataset_choice: "Choosing a dataset",
  dataset_disagreement: "Dataset agreement",
  ols_vs_theil_sen: "OLS versus Theil–Sen",
  methodology: "Methodology",
  seasonal_months: "Months used",
  autocorrelation: "Autocorrelation",
  change_point: "Abrupt changes",
  correlation: "Relationships between variables",
  getting_started: "Getting started",
  prediction: "Prediction",
  secrets: "Configuration and secrets",
  injection: "Instruction in the question",
};
