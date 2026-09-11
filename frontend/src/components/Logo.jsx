/**
 * The scheme mark — and, deliberately, not a national emblem.
 *
 * Use of the State Emblem of India is restricted by the State Emblem of India
 * (Prohibition of Improper Use) Act, 2005. We have no licensed asset and will not
 * draw an imitation of one, so this application does what a portal without the
 * asset should do: it states the national identity typographically (see
 * `NationalLockup` below) and uses a plain departmental seal for the scheme.
 *
 * The seal is a struck-ring device — a ruled outer ring, a 24-point spoke course
 * reading as a chakra without reproducing one, and three ascending bars for the
 * ledger being monitored. Drawn in `currentColor`, so it inherits its surface.
 */
export default function Logo({ size = 36, className = "", title = "MPLADS eSAKSHI scheme mark" }) {
  const spokes = Array.from({ length: 24 }, (_, i) => i * 15);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      role="img"
      aria-label={title}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{title}</title>

      {/* struck seal — a ruled double ring, the way a department stamp is cut */}
      <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="1" opacity="0.45" />
      <circle cx="24" cy="24" r="19.5" stroke="currentColor" strokeWidth="2" />

      {/* 24-point spoke course, set between the rings */}
      {spokes.map((deg) => (
        <line
          key={deg}
          x1="24"
          y1="3.4"
          x2="24"
          y2="5.4"
          stroke="currentColor"
          strokeWidth="1.1"
          strokeLinecap="butt"
          opacity={deg % 90 === 0 ? 0.95 : 0.42}
          transform={`rotate(${deg} 24 24)`}
        />
      ))}

      {/* the ledger under monitoring: three ascending bars on a ruled baseline */}
      <path d="M14.5 33h19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" />
      <rect x="16" y="25" width="4.5" height="6" fill="currentColor" opacity="0.5" />
      <rect x="21.75" y="21" width="4.5" height="10" fill="currentColor" opacity="0.75" />
      <rect x="27.5" y="16.5" width="4.5" height="14.5" fill="currentColor" />
    </svg>
  );
}

/**
 * The national identity, set in type rather than drawn.
 *
 * Bilingual and in the conventional order — Devanagari above the English — which
 * is how it appears across india.gov.in and the ministry portals.
 */
export function NationalLockup({ className = "" }) {
  return (
    <span className={className}>
      <span lang="hi">भारत सरकार</span>
      <span aria-hidden="true"> | </span>
      <span lang="en">Government of India</span>
    </span>
  );
}
