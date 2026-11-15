import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { Analysis } from "../api/types";
import MissionScientist from "./MissionScientist";

afterEach(() => vi.unstubAllGlobals());

it("opens with context-aware suggestions and sends the current analysis", async () => {
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    void url;
    void options;
    return new Response(JSON.stringify({ answer: "This is an estimated warming trend, not a station reading." }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const context = { variable: { name: "Air temperature" }, trend: { slope: 0.05 } } as unknown as Analysis;

  render(<MissionScientist context={context} />);
  await userEvent.click(screen.getByRole("button", { name: "Ask Mission Scientist" }));
  expect(screen.getByText("Explain this result")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Explain this result"));

  expect(await screen.findByText(/estimated warming trend/)).toBeInTheDocument();
  const payload = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
  expect(payload.context.trend.slope).toBe(0.05);
  expect(payload.messages.at(-1).content).toBe("Explain this result in plain language.");
});

it("explains why result questions need an investigation", async () => {
  render(<MissionScientist context={undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Ask Mission Scientist" }));
  expect(screen.getByText(/Launch an investigation/)).toBeInTheDocument();
});
