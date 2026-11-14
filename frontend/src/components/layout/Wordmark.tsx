/** "Code Me to the Moon" wordmark; the second "o" of Moon is drawn as a crescent, echoing the team poster. */
export default function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`wordmark ${className}`} role="img" aria-label="Code Me to the Moon">
      <span aria-hidden>Code Me <span className="wm-small">to the</span> Mo</span>
      <svg className="wm-crescent" viewBox="0 0 20 20" aria-hidden>
        <circle cx="10" cy="10" r="7.2" fill="none" stroke="currentColor" strokeWidth="2.4" />
        <path d="M11.6 4.6a5.6 5.6 0 1 0 3.8 9.6 6.6 6.6 0 0 1-3.8-9.6z" fill="var(--accent)" />
      </svg>
      <span aria-hidden>n</span>
    </span>
  );
}
