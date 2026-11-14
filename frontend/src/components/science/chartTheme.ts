/** Scientific charts use the shared midnight palette; shapes and labels carry meaning. */
export const CHART = {
  surface: "var(--chart-surface)",
  obs: "var(--chart-obs)", // observations / eligible annual values / variable A
  trend: "var(--chart-trend)", // fitted Theil–Sen line / variable B
  excluded: "var(--chart-excluded)", // hollow ring = excluded (shape carries meaning)
  series: "var(--chart-obs)",
  grid: "var(--chart-grid)",
  axis: "var(--chart-axis)",
  tick: "var(--chart-tick)",
  band: "var(--chart-band)",
  step: "var(--warning)", // detected sudden step (data break), dashed vertical marker
  font: "'IBM Plex Mono', ui-monospace, monospace",
} as const;

export const tickStyle = { fill: CHART.tick, fontSize: 11, fontFamily: CHART.font };
