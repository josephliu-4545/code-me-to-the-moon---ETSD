/**
 * Team access key for a shared backend (sent as X-API-Key).
 * Entered by each teammate and kept only in this browser; never bundled into the build.
 */
const STORAGE_KEY = "estd.teamAccessKey";

export function readAccessKey(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeAccessKey(value: string | null): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode): the key lasts only for this request */
  }
}
