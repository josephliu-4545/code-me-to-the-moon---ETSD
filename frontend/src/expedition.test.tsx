/// <reference types="node" />
import { readFileSync } from "node:fs";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Analysis } from "./api/types";
import { Cautions, ResultSummary } from "./components/ResultPanels";
import MissionFindings from "./components/expedition/MissionFindings";
import MethodExplorer from "./components/expedition/MethodExplorer";
import MemoryLab from "./components/expedition/MemoryLab";
import { schematicFits, SCHEMATIC } from "./components/expedition/TrendLab";
import { guardrails, headlineParts, methodNotes, yearRecords } from "./lib/evidence";

import heatRaw from "../public/snapshots/yangon-2015-2024-extreme_heat.json?raw";
// Historical NDVI retrieval (2026-11-13, annual method, no eligible years): exercises the "no result" paths.
import ndviRaw from "./test-fixtures/ndvi-yangon-2015-2024-annual-2026-11-13.json?raw";
import precipRaw from "../public/snapshots/yangon-2015-2024-precipitation.json?raw";
import tempRaw from "../public/snapshots/yangon-2015-2024-temperature.json?raw";

/** Real saved NASA retrievals shipped with the app (Yangon, 2015–2024). */
const RAW: Record<string, string> = { temperature: tempRaw, precipitation: precipRaw, ndvi: ndviRaw, extreme_heat: heatRaw };
const snap = (name: string): Analysis => JSON.parse(RAW[name]!);
const temperature = () => snap("temperature"); // inference, not significant
const precipitation = () => snap("precipitation"); // descriptive: serial dependence blocked the test
const ndvi = () => snap("ndvi"); // no eligible years (historical annual-method retrieval)
const heat = () => snap("extreme_heat"); // annual-only, threshold methodology

describe("Experience A: discovery in seconds", () => {
  it("separates a short headline from its qualification without upgrading a descriptive slope", () => {
    render(<ResultSummary analysis={precipitation()} />);
    const h = screen.getByRole("heading", { level: 2 });
    expect(h).toHaveTextContent("A downward estimated trend in precipitation.");
    expect(h).not.toHaveTextContent(/significant/i);
    expect(screen.getByText("This result is descriptive. A significance test was not reported.")).toBeInTheDocument();
    expect(screen.getByText("Not evaluated")).toBeInTheDocument();
    expect(screen.queryByText("Not significant")).not.toBeInTheDocument();
  });

  it("keeps the full scientific statement available behind progressive disclosure", async () => {
    render(<ResultSummary analysis={precipitation()} />);
    const details = screen.getByText("Full scientific statement").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("Full scientific statement"));
    expect(details).toHaveAttribute("open");
    expect(within(details).getByText(/described without a significance test/)).toBeInTheDocument();
  });

  it("says inconclusive prominently and never 'not evaluated' when a test was run", () => {
    const h = headlineParts(temperature());
    expect(h.headline).toMatch(/evidence is inconclusive/);
    expect(h.significance).toBe("Not significant");
    expect(h.qualifier).toMatch(/not proof of no change/);
  });
});

describe("Experience B: evidence explorer", () => {
  it("selects evidence stages and reveals the matching backend evidence", async () => {
    render(<MissionFindings analysis={temperature()} />);
    const journey = screen.getByRole("list", { name: "Evidence journey" });
    expect(screen.getByRole("heading", { name: "NASA dataset", level: 4 })).toBeInTheDocument();
    await userEvent.click(within(journey).getByRole("button", { name: /Scientific finding/ }));
    expect(screen.getByRole("heading", { name: "Scientific finding", level: 4 })).toBeInTheDocument();
    expect(screen.getByText("Includes zero")).toBeInTheDocument();
    await userEvent.click(within(journey).getByRole("button", { name: /^Trend/ }));
    const panel = screen.getByRole("heading", { name: "Trend", level: 4 }).closest("section")!;
    expect(within(panel).getByText("+0.0205")).toBeInTheDocument();
    expect(within(panel).getByText("Theil–Sen slope")).toBeInTheDocument();
  });

  it("inspects a year's real months and links it to the chart focus", async () => {
    render(<MissionFindings analysis={ndvi()} />);
    await userEvent.click(within(screen.getByRole("list", { name: "Evidence journey" })).getByRole("button", { name: /Eligible years/ }));
    await userEvent.click(screen.getByRole("button", { name: /^2018: set aside, 3 of 12 months with data/ }));
    const card = screen.getByRole("article", { name: "Year 2018 details" });
    expect(within(card).getByText("Set aside")).toBeInTheDocument();
    expect(within(card).getByText("March: missing")).toBeInTheDocument();
    expect(within(card).getByText("January: data")).toBeInTheDocument();
    expect(within(card).getByText("A whole three-month season had no data.")).toBeInTheDocument();
    expect(within(card).getByText("missing_calendar_quarter")).toBeInTheDocument();
    expect(screen.getByText("Inspecting 2018")).toBeInTheDocument();
  });

  it("never treats missing or unreported months as zero", () => {
    const a = ndvi();
    const r = yearRecords(a).find((y) => y.year === 2018)!;
    expect(r.months.filter((m) => m === "missing")).toHaveLength(9);
    r.months.forEach((m, i) => { if (m !== "valid") expect(r.monthValues[i]).toBeNull(); });
    const annualOnly = yearRecords(heat())[0]!;
    expect(annualOnly.monthSource).toBe("none");
    expect(annualOnly.months.every((m) => m === "unknown")).toBe(true);
  });

  it("explains unavailable inference as 'not evaluated', not 'not significant'", () => {
    render(<MemoryLab analysis={precipitation()} />);
    expect(screen.getByText("Not evaluated / reported")).toBeInTheDocument();
    expect(screen.getByText(/Some years may be related to earlier years, making the usual significance test unreliable\./)).toBeInTheDocument();
    expect(screen.getByText("Material lag-1 serial dependence detected")).toBeInTheDocument();
    expect(screen.getByText(/invented series, not NASA data/)).toBeInTheDocument();
  });

  it("labels the Theil–Sen lab as schematic and shows the outlier effect only on invented points", () => {
    const clean = schematicFits(SCHEMATIC);
    const spiked = schematicFits(SCHEMATIC.map((v, i) => (i === 6 ? 9.2 : v)));
    expect(Math.abs(spiked.ols - clean.ols)).toBeGreaterThan(Math.abs(spiked.robust - clean.robust));
    render(<MissionFindings analysis={temperature()} />);
    expect(screen.getByText(/invented points, not NASA data/)).toBeInTheDocument();
    expect(screen.getByText(/An ordinary fit was not computed on the real data/)).toBeInTheDocument();
  });
});

describe("B5: methodology preservation", () => {
  it("keeps every extreme-heat threshold note verbatim behind Technical details", () => {
    const a = heat();
    render(<MethodExplorer analysis={a} />);
    for (const v of ["Hyndman-Fan type 8", "interpolated February 28/March 1 threshold", "Zhang-style leave-one-year-out replacement bootstrap for 1991-2020", "1991", "2020"]) {
      expect(screen.getAllByText(v).length).toBeGreaterThan(0);
    }
  });

  it("preserves every string methodology note and caveat at least once across topics", async () => {
    const a = precipitation();
    const notes = methodNotes(a).map((n) => n.value);
    for (const v of Object.values(a.methodology.trend_method)) expect(notes).toContain(v);
    for (const v of Object.values(a.methodology.source as Record<string, string>)) expect(notes).toContain(v);
    for (const c of a.caveats) expect(notes).toContain(c);
    render(<MethodExplorer analysis={a} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBeGreaterThanOrEqual(3);
    await userEvent.click(screen.getByRole("tab", { name: /uncertainty/ }));
    expect(screen.getByText(/two-sided Mann-Kendall test/)).toBeInTheDocument();
  });
});

describe("Experience C: scientific guardrails", () => {
  it("renders only relevant boundaries and attaches each backend limitation exactly once", () => {
    const desc = guardrails(precipitation()).map((g) => g.title);
    expect(desc).toContain("No significance test means no significance conclusion.");
    expect(desc).not.toContain("“No trend detected” is not “no change”.");
    const none = guardrails(ndvi()).map((g) => g.title);
    expect(none).toContain("Absence of a result is not absence of change.");
    expect(none).not.toContain("A trend is not a cause.");
    const a = heat();
    const attached = guardrails(a).flatMap((g) => g.notes).filter((n) => a.limitations.includes(n));
    expect([...attached].sort()).toEqual([...a.limitations].sort());
  });

  it("starts compact and reveals relevance and verbatim notes on selection", async () => {
    const onShow = vi.fn();
    render(<Cautions analysis={temperature()} onShowEvidence={onShow} />);
    expect(screen.queryByText("In this investigation")).not.toBeInTheDocument();
    const card = screen.getByRole("button", { name: /An area is not an address/ });
    expect(card).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(card);
    expect(card).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/0\.5° × 0\.625° grid cell/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /See the supporting evidence/ }));
    expect(onShow).toHaveBeenCalledWith("dataset");
  });

  it("uses a 'test run · inconclusive' visual for not-detected results, not 'not evaluated'", () => {
    expect(guardrails(temperature()).find((g) => g.id === "inference")!.visual).toBe("inconclusive");
    expect(guardrails(precipitation()).find((g) => g.id === "inference")!.visual).toBe("inference");
  });
});

describe("motion and responsiveness", () => {
  it("disables expedition animations under prefers-reduced-motion and collapses layouts on small screens", () => {
    const css = readFileSync(`${process.cwd()}/src/styles/expedition.css`, "utf8");
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const sel of [".stage-panel", ".guard-detail", ".limb-satellite"]) expect(reduced).toContain(sel);
    expect(css).toMatch(/@media \(max-width: 640px\)[\s\S]*\.journey-stages \{ grid-template-columns: repeat\(2/);
  });
});
