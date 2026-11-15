export interface Point { x: number; y: number }
export function flightRoute(origin: Point, destination: Point, width: number) {
  const lift = Math.min(320, Math.max(100, origin.y * 0.45));
  const bend = Math.min(width - 50, Math.max(origin.x, destination.x) + width * 0.22);
  return `M ${origin.x} ${origin.y} C ${origin.x} ${origin.y-lift}, ${bend} ${origin.y-lift}, ${bend} ${origin.y-40} S ${destination.x+Math.min(150,width*0.15)} ${destination.y}, ${destination.x} ${destination.y}`;
}
/** Quintic smootherstep keeps both velocity and acceleration gentle at phase edges. */
export function easeFlight(t: number) {
  const bounded = Math.max(0, Math.min(1, t));
  return bounded * bounded * bounded * (bounded * (bounded * 6 - 15) + 10);
}
