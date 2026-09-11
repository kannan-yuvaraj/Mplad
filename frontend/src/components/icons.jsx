/**
 * One icon family for the whole application.
 *
 * These replace the emoji and typographic glyphs (▤ ▦ ⚡ § ◈ 🧠 ⚖️ 🔔) that were
 * standing in as icons. Emoji render differently on every platform, carry a
 * colour we do not control, and read as consumer software; a government console
 * wants one restrained, monochrome, stroked set that inherits `currentColor`.
 *
 * All are 24×24 line icons at stroke-width 1.7, drawn on the same grid, so they
 * sit together at any size. Decorative by default — pass a `title` only when the
 * icon is the sole carrier of meaning, which in this app it never should be.
 */

function Svg({ size = 16, title, children, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : "true"}
      focusable="false"
      {...rest}
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

/* ------------------------------------------------------------ navigation */

export const IconDashboard = (p) => (
  <Svg {...p}>
    <rect x="3" y="3" width="7.5" height="7.5" />
    <rect x="13.5" y="3" width="7.5" height="4.5" />
    <rect x="13.5" y="10.5" width="7.5" height="10.5" />
    <rect x="3" y="13.5" width="7.5" height="7.5" />
  </Svg>
);

export const IconQueue = (p) => (
  <Svg {...p}>
    <path d="M9 5h12M9 12h12M9 19h12" />
    <path d="M3 5.5l1.4 1.4L7 4.3" />
    <path d="M3 12.5l1.4 1.4L7 11.3" />
    <path d="M3 19.5l1.4 1.4L7 18.3" />
  </Svg>
);

export const IconCasework = (p) => (
  <Svg {...p}>
    <rect x="2.5" y="6.5" width="19" height="13" rx="1" />
    <path d="M8.5 6.5V5a1.5 1.5 0 0 1 1.5-1.5h4A1.5 1.5 0 0 1 15.5 5v1.5" />
    <path d="M2.5 11.5h19" />
    <path d="M12 11.5v2.5" />
  </Svg>
);

export const IconTrend = (p) => (
  <Svg {...p}>
    <path d="M3 20V4" />
    <path d="M3 20h18" />
    <path d="M6.5 15.5l4-4.5 3.5 3 5-6.5" />
    <path d="M19 7.5h-3.2M19 7.5v3.2" />
  </Svg>
);

export const IconDuplicate = (p) => (
  <Svg {...p}>
    <rect x="8.5" y="8.5" width="12" height="12" rx="1" />
    <path d="M15.5 5.5v-1a1 1 0 0 0-1-1h-10a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h1" />
  </Svg>
);

export const IconCompliance = (p) => (
  <Svg {...p}>
    <path d="M12 3v18" />
    <path d="M5 7h14" />
    <path d="M5 7l-2.5 5.5a3 3 0 0 0 5 0Z" />
    <path d="M19 7l-2.5 5.5a3 3 0 0 0 5 0Z" />
    <path d="M8.5 21h7" />
  </Svg>
);

export const IconArchetype = (p) => (
  <Svg {...p}>
    <path d="M12 3.2 21 7.6 12 12 3 7.6Z" />
    <path d="m3 12.4 9 4.4 9-4.4" />
    <path d="m3 16.9 9 4.4 9-4.4" />
  </Svg>
);

export const IconTransparency = (p) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);

export const IconHelp = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.4 9.3a2.7 2.7 0 0 1 5.2.9c0 1.8-2.6 2.3-2.6 4" />
    <path d="M12 17.4h.01" />
  </Svg>
);

/* ---------------------------------------------------------------- domain */

export const IconSemantic = (p) => (
  <Svg {...p}>
    <circle cx="6" cy="6.5" r="2.5" />
    <circle cx="18" cy="6.5" r="2.5" />
    <circle cx="12" cy="17.5" r="2.5" />
    <path d="M8.4 7.6 10.6 15M15.6 7.6 13.4 15M8.5 6.5h7" />
  </Svg>
);

export const IconAlert = (p) => (
  <Svg {...p}>
    <path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5Z" />
    <path d="M10.3 19a2 2 0 0 0 3.4 0" />
  </Svg>
);

export const IconShield = (p) => (
  <Svg {...p}>
    <path d="M12 3 4.5 6v6c0 4.6 3.2 7.9 7.5 9 4.3-1.1 7.5-4.4 7.5-9V6Z" />
    <path d="m9 12 2.2 2.2L15.5 10" />
  </Svg>
);

export const IconAssistant = (p) => (
  <Svg {...p}>
    <rect x="3" y="4.5" width="18" height="13" rx="1.5" />
    <path d="M8 21l3-3.5h2L16 21" />
    <path d="M8.5 9.5h7M8.5 13h4.5" />
  </Svg>
);

export const IconField = (p) => (
  <Svg {...p}>
    <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11Z" />
    <circle cx="12" cy="10" r="2.6" />
  </Svg>
);

export const IconDocument = (p) => (
  <Svg {...p}>
    <path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8Z" />
    <path d="M14 3v5h5" />
    <path d="M8.5 13h7M8.5 16.5h5" />
  </Svg>
);

export const IconAgency = (p) => (
  <Svg {...p}>
    <path d="M3 21h18" />
    <path d="M4.5 21V9.5L12 5l7.5 4.5V21" />
    <path d="M9.5 21v-5.5h5V21" />
    <path d="M9.5 11.5h5" />
  </Svg>
);

/* ---------------------------------------------------------------- utility */

export const IconSearch = (p) => (
  <Svg {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m15.4 15.4 4.1 4.1" />
  </Svg>
);

export const IconChevronRight = (p) => (
  <Svg {...p}>
    <path d="m9.5 5 7 7-7 7" />
  </Svg>
);

export const IconClose = (p) => (
  <Svg {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
);

export const IconExternal = (p) => (
  <Svg {...p}>
    <path d="M14 4h6v6" />
    <path d="M20 4 10.5 13.5" />
    <path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V7.5A1.5 1.5 0 0 1 5 6h4.5" />
  </Svg>
);

export const IconContrast = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3a9 9 0 0 1 0 18Z" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconMic = (p) => (
  <Svg {...p}>
    <rect x="9" y="2.5" width="6" height="11.5" rx="3" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" />
    <path d="M12 18v3.5M9 21.5h6" />
  </Svg>
);

export const IconCloud = (p) => (
  <Svg {...p}>
    <path d="M7 18.5a4.5 4.5 0 0 1-.4-8.98 6 6 0 0 1 11.6 1.48A3.75 3.75 0 0 1 17.5 18.5Z" />
  </Svg>
);

export const IconTarget = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconReport = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="17" height="17" rx="1.5" />
    <path d="M8 16v-4M12 16V8M16 16v-6" />
  </Svg>
);

export const IconClock = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Svg>
);

export const IconRupee = (p) => (
  <Svg {...p}>
    <path d="M7 4.5h10M7 9h10M16.5 4.5c0 3.6-2.6 4.5-5.5 4.5h-1l7 10.5" />
    <path d="M7 9h3" />
  </Svg>
);

export const IconFlag = (p) => (
  <Svg {...p}>
    <path d="M5.5 21V3.5" />
    <path d="M5.5 4.5h11l-2 3.5 2 3.5h-11" />
  </Svg>
);

export const IconLayers = (p) => (
  <Svg {...p}>
    <path d="M12 3.2 20 7l-8 3.8L4 7Z" />
    <path d="m4 12 8 3.8L20 12" />
  </Svg>
);
