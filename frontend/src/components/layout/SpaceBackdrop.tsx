/**
 * Decorative deep-space backdrops. Each page gets its own scene so the pages are visually distinct:
 * black hole with accretion disk (history), nebula and bright star (findings), radar scan (evaluation), binary stars (compare),
 * constellation network (relationships), aurora (detective), galaxy band (field guide).
 * Pure SVG/CSS, aria-hidden and non-interactive. Carries no data and is never evidence.
 */
const SCENES: Record<string, "trails" | "blackhole" | "nebula" | "radar" | "binary" | "network" | "aurora" | "galaxy"> = {
  history: "blackhole", findings: "nebula", evaluation: "radar", compare: "binary",
  relationships: "network", detective: "aurora", science: "galaxy",
};
const CONSTELLATIONS = [
  "M1020 150 L1085 118 L1150 160 L1212 132 L1268 190",
  "M1150 160 L1168 236 L1230 270",
  "M930 360 L990 330 L1040 372 L1010 430 L945 418 Z",
  "M1240 420 L1300 392 L1352 440 L1330 500",
  "M1040 372 L1168 236", "M1230 270 L1240 420", "M1010 430 L1100 560 L1210 590 L1330 500", "M1100 560 L1060 680",
];
const NODES = [[1020,150],[1085,118],[1150,160],[1212,132],[1268,190],[1168,236],[1230,270],[930,360],[990,330],[1040,372],[1010,430],[945,418],[1240,420],[1300,392],[1352,440],[1330,500],[1100,560],[1210,590],[1060,680]];

/** Deterministic star-trail arcs around a celestial pole. */
const TRAILS = Array.from({ length: 34 }, (_, i) => {
  const r = 46 + i * 21;
  const c = 2 * Math.PI * r;
  const arc = c * (0.1 + ((i * 37) % 17) / 100);
  return { r, dash: `${arc.toFixed(0)} ${(c - arc).toFixed(0)}`, offset: ((i * 53) % 100) / 100 * c, o: 0.22 + ((i * 29) % 10) / 22, warm: i % 5 === 0 };
});

export default function SpaceBackdrop({ tone }: { tone: string }) {
  const scene = SCENES[tone] ?? "galaxy";
  return (
    <div className={`space-backdrop space-${tone} scene-${scene}`} aria-hidden>
      {scene === "galaxy" && <><span className="space-galaxy" /><div className="spiral"><span className="spiral-arms" /><span className="spiral-arms spiral-arms-2" /><span className="spiral-core" /></div></>}
      {scene === "trails" && (
        <svg className="scene-art trails-art" viewBox="0 0 1440 800" preserveAspectRatio="xMaxYMin slice" focusable="false">
          <g className="trails-spin">
            {TRAILS.map((t) => <circle key={t.r} cx="1120" cy="210" r={t.r} strokeDasharray={t.dash} strokeDashoffset={t.offset} strokeOpacity={t.o} className={t.warm ? "is-warm" : ""} />)}
          </g>
          <circle cx="1120" cy="210" r="3" className="trails-pole" />
        </svg>
      )}
      {scene === "blackhole" && (
        <div className="bh"><span className="bh-glow" /><span className="bh-disk bh-disk-back" /><span className="bh-halo" /><span className="bh-core" /><span className="bh-disk bh-disk-front" /><span className="bh-streak" /></div>
      )}
      {scene === "nebula" && <>
        <span className="nebula-cloud nebula-a" /><span className="nebula-cloud nebula-b" /><span className="nebula-cloud nebula-c" />
        <span className="nebula-star"><i /></span><span className="nova-ring" /><span className="nova-ring nova-ring-2" /><span className="nova-ring nova-ring-3" />
      </>}
      {scene === "radar" && (
        <div className="radar">
          <span className="radar-glow" /><span className="radar-rings" /><span className="radar-sweep" /><span className="radar-cross" />
          <i style={{ left: "62%", top: "30%" }} /><i style={{ left: "34%", top: "58%", animationDelay: "1.2s" }} /><i style={{ left: "70%", top: "68%", animationDelay: "2.4s" }} /><i style={{ left: "44%", top: "24%", animationDelay: "3.1s" }} />
        </div>
      )}
      {scene === "binary" && (
        <div className="binary"><span className="binary-ring" /><span className="binary-ring binary-ring-2" /><span className="binary-bridge" /><div className="binary-orbit"><span className="binary-star binary-star-a" /><span className="binary-star binary-star-b" /></div></div>
      )}
      {scene === "aurora" && <><span className="crescent" /><span className="horizon" /><span className="aurora aurora-a" /><span className="aurora aurora-b" /><span className="aurora aurora-c" /></>}
      {scene === "network" && <div className="saturn"><span className="saturn-ring saturn-ring-back" /><span className="saturn-body" /><span className="saturn-ring saturn-ring-front" /></div>}
      {scene === "network" && (
        <svg className="scene-art" viewBox="0 0 1440 800" preserveAspectRatio="xMaxYMid slice" focusable="false">
          <g className="space-constellation network-lines">
            {CONSTELLATIONS.map((d) => <path key={d} d={d} pathLength={1} />)}
            {NODES.map(([x, y], i) => <circle key={`${x}-${y}`} cx={x} cy={y} r={i % 4 === 0 ? 4 : 2.6} style={{ animationDelay: `${(i % 6) * 0.5}s` }} />)}
          </g>
        </svg>
      )}
      <span className="space-stars space-stars-far" />
      <span className="space-stars space-stars-near" />
      <span className="space-meteor space-meteor-a" />
      <span className="space-meteor space-meteor-b" />
      {scene !== "radar" && <span className="space-meteor space-meteor-c" />}
    </div>
  );
}
