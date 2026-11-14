import { useEffect, useRef, useId, type RefObject } from "react";
import { PHASE_MS, type LaunchPhase } from "../../state/launch";
import { easeFlight, flightRoute } from "../../lib/trajectory";
import RocketIllustration from "./RocketIllustration";

interface Props {
  phase: LaunchPhase; run: number; reduced: boolean;
  origin: RefObject<HTMLElement | null>; destination: RefObject<HTMLElement | null>;
}
/** One non-interactive SVG in document space. DOM measurements occur only on layout events. */
export default function LaunchCraft({ phase, run, reduced, origin, destination }: Props) {
  const smokeId = useId().replace(/:/g, "");
  const svg = useRef<SVGSVGElement>(null), path = useRef<SVGPathElement>(null), orbit = useRef<SVGPathElement>(null);
  const craft = useRef<SVGGElement>(null), smoke = useRef<SVGGElement>(null);
  const progress = useRef(0), length = useRef(0), mobile = useRef(false), holdPoint = useRef({ x: 0, y: 0 });
  const active = ["ignition", "liftoff", "transit", "holding", "docking"].includes(phase) && !reduced;
  const paint = useRef<(p: number) => void>(() => {});
  const paintOrbit = useRef<(angle: number) => void>(() => {});
  useEffect(() => {
    if (!active || !svg.current || !path.current) return;
    progress.current = 0;
    let pending = 0;
    const measure = () => {
      const root = svg.current, route = path.current, from = origin.current, to = destination.current;
      if (!root || !route || !from || !to) return;
      const bounds = root.getBoundingClientRect(), a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
      const start = { x:a.x+a.width/2-bounds.x, y:a.y+a.height/2-bounds.y };
      const end = { x:b.x+b.width/2-bounds.x, y:b.y+b.height/2-bounds.y };
      mobile.current = bounds.width < 640;
      holdPoint.current = end;
      route.setAttribute("d", flightRoute(start,end,bounds.width));
      const rx = mobile.current ? 30 : 52, ry = mobile.current ? 17 : 29;
      orbit.current?.setAttribute("d", `M ${end.x-rx} ${end.y} A ${rx} ${ry} 0 1 0 ${end.x+rx} ${end.y} A ${rx} ${ry} 0 1 0 ${end.x-rx} ${end.y}`);
      smoke.current?.setAttribute("transform", `translate(${start.x} ${start.y+55})`);
      // SVG geometry is absent in jsdom; real browsers provide these methods.
      length.current = route.getTotalLength?.() ?? 0;
      route.style.strokeDasharray = `${length.current}`;
      paint.current(progress.current);
    };
    paint.current = (p) => {
      const route = path.current, ship = craft.current, total = length.current;
      if (!route || !ship || !total) return;
      const here = route.getPointAtLength(p*total), ahead = route.getPointAtLength(Math.min(total,p*total+1)), behind = route.getPointAtLength(Math.max(0,p*total-1));
      const angle = Math.atan2(ahead.y-behind.y,ahead.x-behind.x)*180/Math.PI+90;
      const scale = (mobile.current ? 0.57 : 0.9)*(1-0.5*p);
      ship.setAttribute("transform", `translate(${here.x} ${here.y}) rotate(${angle}) scale(${scale})`);
      route.style.strokeDashoffset = `${total*(1-p)}`;
    };
    paintOrbit.current = (angle) => {
      const ship = craft.current;
      if (!ship) return;
      const rx = mobile.current ? 30 : 52, ry = mobile.current ? 17 : 29;
      const x = holdPoint.current.x + Math.cos(angle) * rx;
      const y = holdPoint.current.y + Math.sin(angle) * ry;
      const tangent = Math.atan2(Math.cos(angle) * ry, -Math.sin(angle) * rx) * 180 / Math.PI + 90;
      const scale = mobile.current ? .42 : .64;
      ship.setAttribute("transform", `translate(${x} ${y}) rotate(${tangent}) scale(${scale})`);
    };
    const schedule = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(measure); };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    [svg.current.parentElement,origin.current,destination.current].forEach(el => { if (el) observer?.observe(el); });
    window.addEventListener("resize",schedule); window.addEventListener("scroll",schedule,{passive:true});
    return () => { cancelAnimationFrame(pending); observer?.disconnect(); window.removeEventListener("resize",schedule); window.removeEventListener("scroll",schedule); };
  }, [active,run,origin,destination]);

  useEffect(() => {
    if (!active) return;
    if (phase === "holding") {
      let frame = 0, started = performance.now();
      const tick = (now: number) => {
        paintOrbit.current(((now - started) / 6400) * Math.PI * 2);
        frame = requestAnimationFrame(tick);
      };
      const visibility = () => {
        cancelAnimationFrame(frame);
        svg.current?.classList.toggle("is-paused", document.hidden);
        if (!document.hidden) { started = performance.now(); frame = requestAnimationFrame(tick); }
      };
      if (!document.hidden) frame = requestAnimationFrame(tick);
      document.addEventListener("visibilitychange", visibility);
      return () => { cancelAnimationFrame(frame); document.removeEventListener("visibilitychange", visibility); };
    }
    let frame = 0, started = performance.now();
    let from = progress.current;
    const end = phase === "liftoff" ? 0.3 : phase === "transit" ? 0.72 : phase === "docking" ? 1 : from;
    const duration = PHASE_MS[phase as keyof typeof PHASE_MS] ?? 0;
    const tick = (now: number) => {
      const t = duration ? Math.min(1,(now-started)/duration) : 1;
      progress.current = from+(end-from)*easeFlight(t);
      paint.current(progress.current);
      if (t<1) frame = requestAnimationFrame(tick);
    };
    const visibility = () => {
      cancelAnimationFrame(frame);
      svg.current?.classList.toggle("is-paused", document.hidden);
      if (!document.hidden) { from = progress.current; started = performance.now(); frame = requestAnimationFrame(tick); }
    };
    if (!document.hidden) frame = requestAnimationFrame(tick);
    document.addEventListener("visibilitychange",visibility);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("visibilitychange",visibility); };
  },[active,phase,run]);
  if (!active) return null;
  return <svg ref={svg} className={`mission-flight flight-${phase}`} aria-hidden="true" data-run={run}>
    <defs><radialGradient id={smokeId}><stop stopColor="#CDD5E1" stopOpacity=".9"/><stop offset=".6" stopColor="#687993" stopOpacity=".6"/><stop offset="1" stopColor="#41577A" stopOpacity="0"/></radialGradient></defs>
    <path ref={path} className="mission-route" fill="none" />
    <path ref={orbit} className="mission-orbit" fill="none" />
    <g ref={smoke} className="mission-smoke">
      {Array.from({length:10},(_,i)=><circle key={i} className={`smoke-puff puff-${i}`} r={13+i%3*5} style={{fill:`url(#${smokeId})`,"--puff-x":`${(i%2 ? 1 : -1)*(35+i*12)}px`,"--puff-y":`${15+i%3*16}px`,animationDelay:`${i*45}ms`} as React.CSSProperties}/>)}
      <circle className="ignition-flash" r="26" />
    </g>
    <g ref={craft} className="mission-vessel"><RocketIllustration/></g>
  </svg>;
}
