/** Clip a geographic ring at the dateline instead of drawing across the world. */
export function splitAtDateline(ring: [number, number][]): [number, number][][] {
  if (!ring.length) return [];
  const unwrapped: [number, number][] = [ring[0]!];
  for (const [x, y] of ring.slice(1)) {
    const previous = unwrapped[unwrapped.length - 1]![0];
    unwrapped.push([x + 360 * Math.round((previous - x) / 360), y]);
  }
  const clip = (points: [number, number][], edge: number, greater: boolean) => {
    const result: [number, number][] = [];
    for (let i = 0; i < points.length; i++) {
      const a = points[i]!, b = points[(i + 1) % points.length]!;
      const insideA = greater ? a[0] >= edge : a[0] <= edge;
      const insideB = greater ? b[0] >= edge : b[0] <= edge;
      if (insideA) result.push(a);
      if (insideA !== insideB) result.push([edge, a[1] + (b[1] - a[1]) * (edge - a[0]) / (b[0] - a[0])]);
    }
    return result;
  };
  const xs = unwrapped.map(([x]) => x);
  const polygons: [number, number][][] = [];
  for (let zone = Math.floor((Math.min(...xs) + 180) / 360); zone <= Math.floor((Math.max(...xs) + 180) / 360); zone++) {
    const points = clip(clip(unwrapped.slice(0, -1), -180 + zone * 360, true), 180 + zone * 360, false);
    if (points.length >= 3) {
      const shifted: [number, number][] = points.map(([x, y]) => [x - zone * 360, y]);
      shifted.push(shifted[0]!); polygons.push(shifted);
    }
  }
  return polygons;
}

export function circlePolygon(lat: number, lon: number, radiusKm: number, steps = 72): [number, number][] {
  const coords: [number, number][] = [];
  const R = 6371.0088;
  const d = radiusKm / R;
  const φ1 = (lat * Math.PI) / 180;
  const λ1 = (lon * Math.PI) / 180;
  for (let i = 0; i <= steps; i++) {
    const θ = (2 * Math.PI * i) / steps;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(d) + Math.cos(φ1) * Math.sin(d) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(Math.sin(θ) * Math.sin(d) * Math.cos(φ1), Math.cos(d) - Math.sin(φ1) * Math.sin(φ2));
    coords.push([(((λ2 * 180) / Math.PI + 540) % 360) - 180, (φ2 * 180) / Math.PI]);
  }
  return coords;
}

