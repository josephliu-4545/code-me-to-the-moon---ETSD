import { afterEach, describe, expect, it, vi } from "vitest";
import { createImageryStatus } from "./lib/imageryStatus";

describe("imagery status", () => {
  afterEach(() => vi.useRealTimers());
  it("ignores isolated and transient tile failures", () => {
    vi.useFakeTimers();
    const changed = vi.fn();
    const status = createImageryStatus(changed);
    status.failed(); status.failed();
    vi.advanceTimersByTime(20000);
    expect(changed).not.toHaveBeenCalled();
    status.failed(); status.loaded();
    vi.advanceTimersByTime(10000);
    expect(changed).not.toHaveBeenCalledWith(true);
  });
  it("reports repeated failures after a delay and clears when a tile loads", () => {
    vi.useFakeTimers();
    const changed = vi.fn();
    const status = createImageryStatus(changed);
    status.failed(); status.failed(); status.failed();
    vi.advanceTimersByTime(7999);
    expect(changed).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(changed).toHaveBeenLastCalledWith(true);
    status.loaded();
    expect(changed).toHaveBeenLastCalledWith(false);
  });
  it("cancels pending warnings when the map is removed", () => {
    vi.useFakeTimers();
    const changed = vi.fn();
    const status = createImageryStatus(changed);
    status.failed(); status.failed(); status.failed(); status.dispose();
    vi.runAllTimers();
    expect(changed).not.toHaveBeenCalled();
  });
});
