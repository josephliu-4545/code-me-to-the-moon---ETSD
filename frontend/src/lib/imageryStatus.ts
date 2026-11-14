/** Delay warnings until repeated Blue Marble failures occur without a successful tile. */
export function createImageryStatus(onChange: (unavailable: boolean) => void) {
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  return {
    failed() {
      failures += 1;
      if (failures >= 3 && timer === undefined) {
        timer = setTimeout(() => { timer = undefined; if (failures >= 3) onChange(true); }, 8000);
      }
    },
    loaded() {
      failures = 0;
      clearTimeout(timer);
      timer = undefined;
      onChange(false);
    },
    dispose() { clearTimeout(timer); },
  };
}
