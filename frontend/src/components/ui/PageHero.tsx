import type { ReactNode } from "react";
import Starfield from "../layout/Starfield";

/**
 * Editorial page opening. Tones give each page its narrative mood:
 * cosmic (Connected Worlds), control (Mission Control), notebook (Field Guide).
 */
export default function PageHero({ kicker, title, children, aside, tone = "cosmic" }: {
  kicker: string;
  title: ReactNode;
  children?: ReactNode;
  aside?: ReactNode;
  tone?: "cosmic" | "control" | "notebook";
}) {
  return (
    <header className={`hero hero-${tone}`}>
      {tone !== "notebook" && <Starfield className="hero-stars" />}
      <div className="hero-inner">
        <div className="hero-text">
          <p className="kicker">{kicker}</p>
          <h1 className="hero-title">{title}</h1>
          {children && <div className="hero-lede">{children}</div>}
        </div>
        {aside && <div className="hero-aside">{aside}</div>}
      </div>
    </header>
  );
}
