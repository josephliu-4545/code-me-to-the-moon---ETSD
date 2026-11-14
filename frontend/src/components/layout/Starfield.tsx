/**
 * Decorative starfield (Orbit theme only). Generated once with a seeded PRNG into
 * two SVG data-URI tiles: a static layer and a slowly twinkling layer.
 * Pure CSS animation, hidden in the light theme, frozen under reduced motion.
 */
function tile(seed: number, count: number, size: number, maxR: number): string {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
  let dots = "";
  for (let i = 0; i < count; i++) {
    const r = (0.25 + rnd() * maxR).toFixed(2);
    const o = (0.25 + rnd() * 0.75).toFixed(2);
    const warm = rnd() > 0.85;
    dots += `<circle cx='${(rnd() * size).toFixed(1)}' cy='${(rnd() * size).toFixed(1)}' r='${r}' fill='${warm ? "%23F3D3A6" : "%23E9EEF8"}' fill-opacity='${o}'/>`;
  }
  return `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}'%3E${dots.replace(/</g, "%3C").replace(/>/g, "%3E")}%3C/svg%3E")`;
}

const FAR = tile(7, 140, 520, 0.7);
const NEAR = tile(91, 34, 760, 1.1);

export default function Starfield({ className = "" }: { className?: string }) {
  return (
    <div className={`starfield ${className}`} aria-hidden>
      <span className="stars stars-far" style={{ backgroundImage: FAR }} />
      <span className="stars stars-near" style={{ backgroundImage: NEAR }} />
    </div>
  );
}
