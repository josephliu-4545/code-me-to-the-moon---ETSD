import type { VariableId, VariableInfo } from "../api/types";

export interface QuestionPlan {
  variable: VariableId;
  placeQuery: string;
  startYear: number;
  endYearInclusive: number;
  dataset?: string;
}

const VARIABLE_TERMS: Array<[VariableId, RegExp]> = [
  ["soil_moisture", /\b(soil moisture|soil water)\b/i],
  ["relative_humidity", /\b(relative humidity|humidity)\b/i],
  ["extreme_heat", /\b(extreme heat|hot days?|heat extremes?|heatwave)\b/i],
  ["precipitation", /\b(precipitation|rainfall|rain)\b/i],
  ["ndvi", /\b(ndvi|vegetation|greenness|plant cover)\b/i],
  ["temperature", /\b(air temperature|temperature|warming|hotter|cooler)\b/i],
];

/** A conservative deterministic planner. It configures only questions with one named variable and place. */
export function planInvestigationQuestion(raw: string, variables: VariableInfo[]): QuestionPlan | null {
  const variable = VARIABLE_TERMS.find(([, pattern]) => pattern.test(raw))?.[0];
  const place = raw.match(/\b(?:in|at|near|for)\s+(.+?)(?=\s+(?:from|between|during)\s+\d{4}\b|\s+(?:getting|becoming|changed|changing|change)\b|[?.,;]|$)/i)?.[1]?.trim();
  if (!variable || !place || place.length < 2) return null;

  const info = variables.find((item) => item.id === variable);
  if (!info) return null;
  const years = [...raw.matchAll(/\b(19\d{2}|20\d{2}|2100)\b/g)].map((match) => Number(match[1]));
  const startYear = years.length >= 2 ? Math.min(years[0]!, years[1]!) : info.default_period[0];
  const endExclusive = years.length >= 2 ? Math.max(years[0]!, years[1]!) + 1 : info.default_period[1];
  if (endExclusive <= startYear || endExclusive - startYear > info.max_years) return null;

  return {
    variable,
    placeQuery: place,
    startYear,
    endYearInclusive: endExclusive - 1,
    dataset: variable === "soil_moisture" ? info.default_dataset : undefined,
  };
}
