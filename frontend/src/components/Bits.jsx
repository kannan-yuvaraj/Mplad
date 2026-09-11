import { useState } from "react";
import { sev } from "../severity.js";

/**
 * When a figure on screen was fetched, and how long it took.
 *
 * Every page loads its data from the engine as it opens, so the moment the page
 * mounted is the moment its figures were computed — this says so instead of
 * leaving the reader to wonder whether the numbers are typed in.
 */
export function LiveStamp({ at, ms, busy }) {
  const state = busy ? "wait" : at ? "" : "wait";
  return (
    <span className="live-stamp" title="The numbers on this page are worked out fresh each time it opens">
      <span className={"live-dot " + state} aria-hidden="true" />
      {busy || !at
        ? "Working…"
        : `Updated ${at.toLocaleTimeString("en-IN")}${ms != null ? ` · ${ms} ms` : ""}`}
    </span>
  );
}

export function Topbar({ title, sub, right, stamp = true }) {
  // The page mounts when its data is requested; that time is the honest stamp.
  const [mounted] = useState(() => new Date());
  return (
    <div className="topbar">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {right}
        {stamp && <LiveStamp at={mounted} />}
      </div>
    </div>
  );
}

/**
 * A severity level, shown three ways at once: colour, glyph and its written label.
 * Colour is the redundant channel here, never the load-bearing one — red and amber
 * collapse together under deuteranopia, so the shape and the word are what a
 * reviewer actually reads.
 */
export function Band({ value, label }) {
  const level = String(value || "").toUpperCase();
  const { glyph } = sev(level);
  return (
    <span className={`badge sev ${level}`} title={`Level: ${label || value}`}>
      <i className="glyph" aria-hidden="true">{glyph}</i>
      {label || value}
    </span>
  );
}

export function Loading({ label = "Loading" }) {
  return (
    <div className="loading">
      <div className="spinner" />
      {label}…
    </div>
  );
}

/** Shimmering placeholder rows — used while a table loads. */
export function SkeletonRows({ rows = 6, height = 46 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height, opacity: 1 - i * 0.09 }} />
      ))}
    </div>
  );
}

export function Hitl({ text }) {
  return (
    <div className="hitl">
      <span aria-hidden="true" style={{ color: "var(--primary)", marginTop: 1, display: "inline-flex" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" focusable="false">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8.2v4.6M12 15.6h.01" />
        </svg>
      </span>
      <span>{text || (
        <><strong>Works worth checking — not proof of wrongdoing.</strong> They are put in
        order by how much public money a check could protect, using clues anyone can see and
        that back each other up. A person looks at the evidence and decides what happens.</>
      )}</span>
    </div>
  );
}
