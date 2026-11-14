/**
 * Code Me to the Moon emblem: a planet inside a tilted golden ring, crossed by a
 * rising environmental signal. Original artwork inspired by the team poster's
 * celestial ring; it is not NASA insignia. Readable from 16 px (favicon) upward.
 */
export default function Logo({ size = 32, title }: { size?: number; title?: string }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" role={title ? "img" : undefined} aria-hidden={title ? undefined : true} aria-label={title} fill="none">
      {/* back half of the ring, behind the planet */}
      <path d="M3.2 19.6C1.4 16.9 7.6 12.5 16 10.6s15.3-1.5 16 1.5" stroke="var(--logo-ring, #E7AE68)" strokeWidth="1.3" strokeLinecap="round" opacity=".55" />
      <circle cx="16" cy="16" r="8.6" fill="var(--logo-planet, #101D35)" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8.6 13.6c2.6 1.2 12.2 1.2 14.8 0M7.6 17.8c3 1.3 13.8 1.3 16.8 0" stroke="currentColor" strokeWidth=".9" strokeLinecap="round" opacity=".45" />
      {/* rising signal */}
      <path d="M9.2 20.4l3.6-2.2 2.8 1 4.8-5.2" stroke="var(--logo-signal, #74B7E7)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      {/* front half of the ring */}
      <path d="M32 12.1c.7 3-5.6 7.4-14 9.3s-14.9 1.1-14.8-1.8" stroke="var(--logo-ring, #E7AE68)" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="27.2" cy="6.2" r="1.7" fill="var(--logo-ring, #E7AE68)" />
    </svg>
  );
}
