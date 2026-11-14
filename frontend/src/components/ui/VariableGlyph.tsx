import type { VariableId } from "../../api/types";

/** Small original line glyphs, one per environmental variable. Decorative: always aria-hidden. */
const PATHS: Record<VariableId, React.ReactNode> = {
  temperature: (
    <>
      <path d="M10 4.5a2 2 0 0 1 4 0v9.2a4 4 0 1 1-4 0z" />
      <path d="M12 9v7.5" />
      <path d="M17 6h2.5M17 9h2" />
    </>
  ),
  relative_humidity: (
    <>
      <path d="M12 3.5c3.6 4.4 5.5 7.6 5.5 10.2a5.5 5.5 0 0 1-11 0c0-2.6 1.9-5.8 5.5-10.2z" />
      <path d="M9.5 14.5c.4 1.4 1.4 2.3 2.8 2.5" />
    </>
  ),
  extreme_heat: (
    <>
      <circle cx="12" cy="12" r="3.8" />
      <path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7" />
    </>
  ),
  precipitation: (
    <>
      <path d="M7 11.5a4.5 4.5 0 0 1 8.7-1.6A3.4 3.4 0 1 1 17 16.5H7.5a2.5 2.5 0 0 1-.5-5z" />
      <path d="M9 19l-.8 2M13 19l-.8 2M17 19l-.8 2" />
    </>
  ),
  ndvi: (
    <>
      <path d="M5 19c0-8 5.5-13 14-14-.5 8.5-5.5 14-14 14z" />
      <path d="M5 19l8-8" />
    </>
  ),
  soil_moisture: (
    <>
      <path d="M3 9.5c3-1.4 6-1.4 9 0s6 1.4 9 0" />
      <path d="M3 14c3-1.2 6-1.2 9 0s6 1.2 9 0" opacity=".7" />
      <path d="M3 18.5c3-1 6-1 9 0s6 1 9 0" opacity=".45" />
      <path d="M12 2.5c1.4 1.7 2.1 2.9 2.1 3.9a2.1 2.1 0 0 1-4.2 0c0-1 .7-2.2 2.1-3.9z" />
    </>
  ),
};

export default function VariableGlyph({ id, size = 22 }: { id: VariableId; size?: number }) {
  return (
    <svg className="glyph" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[id] ?? <circle cx="12" cy="12" r="6" />}
    </svg>
  );
}
