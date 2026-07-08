export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label="Loggboken">
      <defs>
        <linearGradient id="loggboken-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1d5fa8" />
          <stop offset="100%" stopColor="#4f95d9" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="48" fill="url(#loggboken-bg)" />
      <circle cx="50" cy="50" r="46" fill="none" stroke="#f6ca47" strokeWidth="1.5" opacity="0.6" />

      {/* closed logbook, tilted, with a worn leather strap and buckle */}
      <g transform="rotate(-10 50 50)">
        {/* page block, peeking out from behind the cover */}
        <rect x="30" y="25" width="37" height="49" rx="3" fill="#f5e6c8" />
        {/* stacked page-edge lines, for thickness */}
        <line x1="65" y1="29" x2="65" y2="71" stroke="#d8c199" strokeWidth="1" />
        <line x1="67.5" y1="29" x2="67.5" y2="71" stroke="#d8c199" strokeWidth="1" />

        {/* cover */}
        <rect x="27" y="23" width="34" height="49" rx="4" fill="#5b3a1e" stroke="#d4a017" strokeWidth="1.2" />
        {/* spine hinge */}
        <line x1="33.5" y1="23" x2="33.5" y2="72" stroke="#2e1a0d" strokeWidth="1.3" opacity="0.6" />

        {/* star emblem stamped on the cover */}
        <path
          d="M44 32 L45.6 35.7 L49.6 36.1 L46.6 38.7 L47.5 42.6 L44 40.5 L40.5 42.6 L41.4 38.7 L38.4 36.1 L42.4 35.7 Z"
          fill="#f6ca47"
          opacity="0.9"
        />

        {/* leather strap and buckle */}
        <rect x="27" y="50" width="34" height="6.5" fill="#2e1a0d" opacity="0.88" />
        <rect x="53" y="49" width="8" height="8.5" rx="1.5" fill="none" stroke="#f6ca47" strokeWidth="1.6" />
        <circle cx="57" cy="53.25" r="1.2" fill="#f6ca47" />

        {/* bookmark ribbon peeking from the top */}
        <path d="M38 23 L44 23 L44 13 L41 16 L38 13 Z" fill="#d97706" />
      </g>
    </svg>
  )
}
