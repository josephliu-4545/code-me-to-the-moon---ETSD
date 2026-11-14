import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getJson } from "./api/client";
import { ApiError } from "./api/types";
import { ErrorBox } from "./components/ResultPanels";
import { readAccessKey, writeAccessKey } from "./state/accessKey";

describe("team access key", () => {
  const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
  beforeEach(() => {
    window.localStorage.clear();
    fetchMock.mockClear();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends X-API-Key only when a key is saved", async () => {
    await getJson("/api/v2/variables", {});
    expect((fetchMock.mock.calls[0] as unknown[])[1]).toMatchObject({ headers: undefined });
    writeAccessKey("team-key");
    expect(readAccessKey()).toBe("team-key");
    await getJson("/api/v2/variables", {});
    expect((fetchMock.mock.calls[1] as unknown[])[1]).toMatchObject({ headers: { "X-API-Key": "team-key" } });
    writeAccessKey(null);
    expect(readAccessKey()).toBeNull();
  });

  it("shows the key form for api_key_required and a clear title for rate limits", () => {
    const { unmount } = render(<ErrorBox error={new ApiError(401, "This shared backend requires a team access key", "api_key_required")} />);
    expect(screen.getByText("Team access key required")).toBeInTheDocument();
    expect(screen.getByLabelText("Team access key")).toBeInTheDocument();
    unmount();
    render(<ErrorBox error={new ApiError(429, "Too many requests", "rate_limited")} onRetry={() => undefined} />);
    expect(screen.getByText("Please slow down")).toBeInTheDocument();
    expect(screen.queryByLabelText("Team access key")).not.toBeInTheDocument();
  });
});
