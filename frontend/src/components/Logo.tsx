export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label="Loggboken">
      <defs>
        <linearGradient id="loggboken-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1d4ed8" />
          <stop offset="100%" stopColor="#0891b2" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="48" fill="url(#loggboken-bg)" />

      {/* open logbook: filled, curved pages rather than flat panels */}
      <path d="M50 27 C 30 24 17 33 16 50 C 17 67 30 76 50 73 Z" fill="#f8fafc" />
      <path d="M50 27 C 70 24 83 33 84 50 C 83 67 70 76 50 73 Z" fill="#f8fafc" />

      {/* spine shadow */}
      <path
        d="M50 27 C 47 40 47 60 50 73 C 53 60 53 40 50 27 Z"
        fill="#1d4ed8"
        opacity="0.14"
      />

      {/* log entry lines */}
      <g stroke="#1d4ed8" strokeWidth="2.5" strokeLinecap="round" opacity="0.55">
        <line x1="26" y1="38" x2="42" y2="36" />
        <line x1="25" y1="48" x2="42" y2="46" />
        <line x1="26" y1="58" x2="42" y2="56" />
        <line x1="58" y1="36" x2="74" y2="38" />
        <line x1="58" y1="46" x2="75" y2="48" />
        <line x1="58" y1="56" x2="74" y2="58" />
      </g>

      {/* bookmark ribbon */}
      <path d="M45 18 L55 18 L55 34 L50 28.5 L45 34 Z" fill="#f59e0b" />
    </svg>
  )
}
