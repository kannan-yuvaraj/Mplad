import { useEffect, useRef, useState } from "react";

/**
 * The home page's moving panel: three scenes that cross-fade, telling the whole
 * story in the order it happens — money is granted, things get built, someone
 * goes and checks.
 *
 * **Why these are drawings and not photographs.** Press and agency photographs
 * of Parliament and of public works are copyrighted, and shipping one whose
 * licence we cannot verify into a submission would put the team at real risk
 * for a decorative gain. These are original stylised compositions instead.
 *
 * **It is photo-ready.** Drop licensed images into `frontend/public/media/` and
 * list them in `public/media/civic.json` as
 * `[{ "src": "/media/one.jpg", "caption": "…", "credit": "…" }]`; each one
 * replaces a drawn scene in order, keeps the same cross-fade, and prints its
 * credit. Nothing else changes. Government photographs released under
 * GODL-India or CC-BY are the usual source, and the credit line is required by
 * both — which is why there is nowhere to put a photo without also putting its
 * attribution.
 *
 * Neither the State Emblem nor the Ashoka Chakra is drawn. The emblem's use is
 * restricted by the State Emblem of India (Prohibition of Improper Use) Act,
 * 2005, and this project already declines to reproduce it.
 */

const SCENES = [
  { id: "chamber", label: "Parliament grants the funds" },
  { id: "works", label: "Works are built where people live" },
  { id: "check", label: "An officer goes and looks" },
];

const HOLD_MS = 5200;

export default function CivicShow({ className = "" }) {
  const [at, setAt] = useState(0);
  const [photos, setPhotos] = useState(null);
  const paused = useRef(false);

  // Optional licensed photographs. Absent by default, and its absence is not an
  // error — the drawings are the shipped state, not a placeholder.
  useEffect(() => {
    let alive = true;
    fetch("/media/civic.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((list) => {
        if (alive && Array.isArray(list) && list.length) setPhotos(list);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return undefined;
    const id = setInterval(() => {
      if (!paused.current) setAt((i) => (i + 1) % SCENES.length);
    }, HOLD_MS);
    return () => clearInterval(id);
  }, []);

  const shot = photos?.[at];

  return (
    <div
      className={`civicshow ${className}`}
      onMouseEnter={() => { paused.current = true; }}
      onMouseLeave={() => { paused.current = false; }}
    >
      <div className="cs-stage" role="img" aria-label={SCENES[at].label}>
        {SCENES.map((s, i) => (
          <div key={s.id} className={"cs-scene" + (i === at ? " on" : "")} aria-hidden={i !== at}>
            {photos?.[i]
              ? <img src={photos[i].src} alt={photos[i].caption || SCENES[i].label} loading="lazy" />
              : <Scene id={s.id} />}
          </div>
        ))}
        <div className="cs-shade" />
        <p className="cs-caption">{shot?.caption || SCENES[at].label}</p>
      </div>

      <div className="cs-foot">
        <div className="cs-dots">
          {SCENES.map((s, i) => (
            <button
              key={s.id} type="button"
              className={"cs-dot" + (i === at ? " on" : "")}
              aria-label={s.label}
              aria-current={i === at}
              onClick={() => setAt(i)}
            />
          ))}
        </div>
        <span className="cs-credit">
          {shot?.credit || "Original drawings. The State Emblem is not reproduced."}
        </span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- the scenes */

function Scene({ id }) {
  if (id === "works") return <WorksScene />;
  if (id === "check") return <CheckScene />;
  return <ChamberScene />;
}

const SKY = (
  <>
    <rect width="640" height="400" fill="url(#cs-sky)" />
    <g className="cs-dawn">
      {[196, 156, 118].map((r, i) => (
        <circle key={r} cx="320" cy="300" r={r} fill="none" stroke="var(--civic-glow)"
                strokeOpacity={0.06 + i * 0.04} strokeWidth="1" />
      ))}
    </g>
  </>
);

function Defs() {
  return (
    <defs>
      <linearGradient id="cs-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--civic-sky-top)" />
        <stop offset="100%" stopColor="var(--civic-sky-bottom)" />
      </linearGradient>
      <linearGradient id="cs-stone" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--civic-stone-top)" />
        <stop offset="100%" stopColor="var(--civic-stone-bottom)" />
      </linearGradient>
    </defs>
  );
}

/** Scene 1 — the chamber. A domed legislature over a colonnade. */
function ChamberScene() {
  const columns = Array.from({ length: 11 }, (_, i) => 108 + i * 38);
  return (
    <svg viewBox="0 0 640 400" className="cs-svg" xmlns="http://www.w3.org/2000/svg">
      <Defs />
      {SKY}
      <rect x="0" y="336" width="640" height="64" fill="var(--civic-ground)" />
      <g className="cs-rise">
        {columns.map((x, i) => (
          <g key={x} style={{ "--i": i }} className="cs-col">
            <rect x={x} y="238" width="19" height="98" rx="2" fill="url(#cs-stone)" />
            <rect x={x - 3} y="233" width="25" height="7" rx="2" fill="var(--civic-stone-top)" />
            <rect x={x - 3} y="330" width="25" height="7" rx="2" fill="var(--civic-stone-bottom)" />
          </g>
        ))}
      </g>
      <rect x="92" y="214" width="456" height="20" rx="3" fill="var(--civic-stone-top)" />
      <rect x="82" y="204" width="476" height="12" rx="3" fill="var(--civic-stone-bottom)" />
      <g className="cs-dome">
        <rect x="246" y="160" width="148" height="46" rx="4" fill="url(#cs-stone)" />
        {[270, 300, 330, 358].map((x) => (
          <rect key={x} x={x} y="171" width="9" height="26" rx="2"
                fill="var(--civic-sky-bottom)" opacity=".55" />
        ))}
        <path d="M246 160 A74 66 0 0 1 394 160 Z" fill="url(#cs-stone)" />
        <rect x="314" y="84" width="11" height="15" rx="2" fill="var(--civic-stone-top)" />
        <circle cx="320" cy="78" r="6.5" fill="var(--civic-glow)" opacity=".9" />
      </g>
      {[0, 1, 2].map((i) => (
        <rect key={i} x={162 - i * 24} y={336 + i * 9} width={316 + i * 48} height="9" rx="1.5"
              fill="var(--civic-stone-bottom)" opacity={0.9 - i * 0.18} />
      ))}
    </svg>
  );
}

/** Scene 2 — what the money builds: a school, a water line, a road. */
function WorksScene() {
  return (
    <svg viewBox="0 0 640 400" className="cs-svg" xmlns="http://www.w3.org/2000/svg">
      <Defs />
      {SKY}
      <rect x="0" y="300" width="640" height="100" fill="var(--civic-ground)" />
      {/* road running to the horizon */}
      <path d="M250 400 L300 300 L340 300 L430 400 Z" fill="var(--civic-stone-bottom)" opacity=".28" />
      {[0, 1, 2, 3].map((i) => (
        <rect key={i} x={318 - i * 3} y={310 + i * 22} width={6 + i * 2} height="12" rx="1"
              fill="var(--civic-glow)" opacity={.25 + i * .12} className="cs-dash" style={{ "--i": i }} />
      ))}
      {/* school block */}
      <g className="cs-rise" style={{ "--i": 0 }}>
        <rect x="76" y="212" width="170" height="90" rx="3" fill="url(#cs-stone)" />
        <path d="M68 212 L161 176 L254 212 Z" fill="var(--civic-stone-top)" />
        {[96, 128, 160, 192].map((x) => (
          <rect key={x} x={x} y="238" width="22" height="26" rx="2"
                fill="var(--civic-sky-bottom)" opacity=".6" />
        ))}
        <rect x="150" y="262" width="24" height="40" rx="2" fill="var(--civic-sky-bottom)" opacity=".8" />
      </g>
      {/* water tank on legs */}
      <g className="cs-rise" style={{ "--i": 2 }}>
        <rect x="470" y="168" width="84" height="46" rx="6" fill="url(#cs-stone)" />
        <rect x="464" y="162" width="96" height="10" rx="4" fill="var(--civic-stone-top)" />
        {[484, 536].map((x) => (
          <rect key={x} x={x} y="214" width="9" height="88" fill="var(--civic-stone-bottom)" />
        ))}
        <rect x="470" y="248" width="84" height="7" rx="2" fill="var(--civic-stone-bottom)" opacity=".7" />
        <circle cx="512" cy="300" r="5" fill="var(--civic-glow)" opacity=".85" className="cs-pulse" />
      </g>
      {/* health centre */}
      <g className="cs-rise" style={{ "--i": 4 }}>
        <rect x="286" y="236" width="118" height="66" rx="3" fill="url(#cs-stone)" />
        <rect x="278" y="228" width="134" height="12" rx="3" fill="var(--civic-stone-top)" />
        <rect x="336" y="248" width="18" height="6" rx="1" fill="var(--civic-glow)" opacity=".9" />
        <rect x="342" y="242" width="6" height="18" rx="1" fill="var(--civic-glow)" opacity=".9" />
      </g>
    </svg>
  );
}

/** Scene 3 — the check: a site board, and someone standing at it. */
function CheckScene() {
  return (
    <svg viewBox="0 0 640 400" className="cs-svg" xmlns="http://www.w3.org/2000/svg">
      <Defs />
      {SKY}
      <rect x="0" y="322" width="640" height="78" fill="var(--civic-ground)" />
      {/* the work behind */}
      <g opacity=".38">
        <rect x="392" y="214" width="150" height="108" rx="3" fill="url(#cs-stone)" />
        {[410, 444, 478, 512].map((x) => (
          <rect key={x} x={x} y="238" width="20" height="24" rx="2"
                fill="var(--civic-sky-bottom)" opacity=".7" />
        ))}
      </g>
      {/* the site board */}
      <g className="cs-rise" style={{ "--i": 0 }}>
        <rect x="150" y="150" width="212" height="132" rx="4" fill="url(#cs-stone)" />
        <rect x="150" y="150" width="212" height="24" rx="4" fill="var(--civic-glow)" opacity=".85" />
        {[188, 206, 224, 242, 260].map((y, i) => (
          <rect key={y} x="168" y={y} width={176 - i * 22} height="7" rx="2"
                fill="var(--civic-sky-bottom)" opacity={.5 - i * .06} />
        ))}
        <rect x="196" y="282" width="8" height="46" fill="var(--civic-stone-bottom)" />
        <rect x="308" y="282" width="8" height="46" fill="var(--civic-stone-bottom)" />
      </g>
      {/* the officer: a plain silhouette, no face, no uniform */}
      <g className="cs-rise" style={{ "--i": 3 }}>
        <circle cx="440" cy="256" r="15" fill="var(--civic-stone-top)" />
        <path d="M418 322 q0-38 22-38 t22 38 Z" fill="var(--civic-stone-top)" />
        <rect x="462" y="272" width="26" height="20" rx="2" fill="var(--civic-glow)" opacity=".9" />
      </g>
      {/* the scan: what the camera reads off the board */}
      <rect className="cs-scan" x="150" y="150" width="212" height="4"
            fill="var(--civic-glow)" opacity=".75" />
    </svg>
  );
}
