import { useCallback, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, num, rupees } from "../api.js";
import { Band } from "./Bits.jsx";
import { DATA_SNAPSHOT } from "./GovChrome.jsx";

/* ============================================================================
   The detection system, drawn as what it is.

   Three pieces the home page and the Detection Centre both build on:

     DetectionFlow   every work passing through the detectors into fusion, leads,
                     high priority and the audit plan — with the live count at
                     every node;
     AnomalyFeed     the highest-priority leads the engine surfaced, cycling, each
                     showing which detectors fired on it;
     DetectorBoard   one tile per detector, in one consistent unit.

   What "live" means here, stated once so no one has to guess: every number is
   fetched from the engine when the page opens, and every row in the feed is a
   real surfaced work. The data is the eSAKSHI snapshot of DATA_SNAPSHOT — the
   motion shows the engine's pass over it, never an invented "just detected"
   event. A system that fakes a stream is lying about the one thing it sells.
   ========================================================================== */

/**
 * The five signal families that fuse into a lead. `signal` is the exact name the
 * pipeline writes onto each lead (pipeline.py), which the worklist can filter by —
 * so each count is "leads where this detector fired", one unit for all five.
 */
export const SIGNAL_DETECTORS = [
  {
    signal: "Peer amount", short: "High cost", name: "Costs much more than similar works",
    catches: "Asks for far more money than works of the same kind in the same state.",
    to: "/archetypes",
  },
  {
    signal: "Peer duration", short: "Long delay", name: "Taking much longer than similar works",
    catches: "Still not finished, long after similar works were done.",
    to: "/worklist",
  },
  {
    signal: "Statistical outlier", short: "Odd numbers", name: "Unusual numbers",
    catches: "Its cost and age together look strange next to works across India.",
    to: "/worklist",
  },
  {
    signal: "Behavioural change", short: "Agency changed", name: "Agency suddenly changed",
    catches: "The office building it suddenly started doing things very differently from last year.",
    to: "/trends",
  },
  {
    signal: "Near-duplicate work", short: "Possible repeat", name: "Might be listed twice",
    catches: "Another work says the same thing in almost the same words — it may be one work counted twice.",
    to: "/duplicates",
  },
];

const SHORT = Object.fromEntries(SIGNAL_DETECTORS.map((x) => [x.signal, x.short]));
const PLAN_DAYS = 50;

/**
 * Everything the detection views read, fetched together so one stamp covers it.
 * Role scope flows into the per-work queries, so a Bihar officer sees Bihar.
 */
export function useDetection(params = {}) {
  const [d, setD] = useState({ families: {} });
  const [at, setAt] = useState(null);
  const [ms, setMs] = useState(null);
  const [busy, setBusy] = useState(true);
  const scopeKey = JSON.stringify(params);

  const load = useCallback(() => {
    setBusy(true);
    const t0 = performance.now();
    const jobs = {
      stats: api.stats(params),
      models: api.models(),
      temporal: api.temporal(),
      plan: api.auditPlan(PLAN_DAYS),
      feed: api.worklist({ band: "HIGH", limit: 12, ...params }),
    };
    SIGNAL_DETECTORS.forEach((x) => {
      jobs[`fam:${x.signal}`] = api.worklist({ signal: x.signal, limit: 1, ...params });
    });
    const names = Object.keys(jobs);
    Promise.allSettled(Object.values(jobs)).then((res) => {
      const out = { families: {} };
      res.forEach((r, i) => {
        if (r.status !== "fulfilled") return;
        const k = names[i];
        if (k.startsWith("fam:")) out.families[k.slice(4)] = r.value.total;
        else out[k] = r.value;
      });
      setD(out);
      setAt(new Date());
      setMs(Math.round(performance.now() - t0));
      setBusy(false);
    });
    // `params` is captured by value through scopeKey; re-run only when scope changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey]);

  useEffect(() => { load(); }, [load]);
  return { d, at, ms, busy, reload: load };
}

const fmt = (v) => (v == null ? "…" : num(v));

/* ---------------------------------------------------------------------------
   DetectionFlow — the pass over every work, as a flow diagram that moves.
   --------------------------------------------------------------------------- */
export function DetectionFlow({ d, variant = "dark" }) {
  const uid = useId().replace(/:/g, "");
  const n = d.stats?.national;
  const fam = d.families || {};
  const plan = d.plan?.totals;

  const W = 880;
  const H = 330;
  const src = { x: 84, y: 165, r: 56 };
  const det = { x: 206, w: 190, h: 40, ys: [49, 107, 165, 223, 281] };
  const fuse = { x: 492, y: 165, r: 34 };
  const leads = { x: 566, y: 141, w: 124, h: 48 };
  const high = { x: 730, y: 141, w: 136, h: 48 };

  const inPaths = det.ys.map(
    (y) => `M ${src.x + src.r} ${src.y} C ${src.x + src.r + 60} ${src.y}, ${det.x - 60} ${y}, ${det.x} ${y}`
  );
  const outPaths = det.ys.map(
    (y) => `M ${det.x + det.w} ${y} C ${det.x + det.w + 55} ${y}, ${fuse.x - fuse.r - 55} ${fuse.y}, ${fuse.x - fuse.r} ${fuse.y}`
  );
  const tail = [
    `M ${fuse.x + fuse.r} ${fuse.y} L ${leads.x} ${fuse.y}`,
    `M ${leads.x + leads.w} ${fuse.y} L ${high.x} ${fuse.y}`,
  ];

  const label = n
    ? `${num(n.total_works)} works go through five checks; ${num(n.surfaced_leads)} are flagged because two or more checks agree; ${num(n.bands?.HIGH || 0)} are most urgent${plan ? `; ${num(plan.works)} fit in ${PLAN_DAYS} days of visits` : ""}.`
    : "How works are checked, loading.";

  return (
    <svg className={`flow flow-${variant}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <defs>
        {[...inPaths, ...outPaths, ...tail].map((p, i) => (
          <path key={i} id={`${uid}-p${i}`} d={p} />
        ))}
      </defs>

      {/* the channels, and the data running along them */}
      {[...inPaths, ...outPaths, ...tail].map((p, i) => (
        <g key={i}>
          <path className="flow-link" d={p} />
          <path className="flow-run" d={p} style={{ animationDelay: `${(i % 5) * -0.22}s` }} />
        </g>
      ))}
      <g className="flow-dots">
        {[...inPaths, ...outPaths].map((_, i) => (
          <circle key={i} r="3" className="flow-dot">
            <animateMotion dur="2.6s" repeatCount="indefinite" begin={`${(i % 5) * 0.45 + (i >= 5 ? 1.3 : 0)}s`}>
              <mpath href={`#${uid}-p${i}`} />
            </animateMotion>
          </circle>
        ))}
        {tail.map((_, i) => (
          <circle key={`t${i}`} r="3.4" className="flow-dot hot">
            <animateMotion dur="1.4s" repeatCount="indefinite" begin={`${0.6 + i * 0.7}s`}>
              <mpath href={`#${uid}-p${inPaths.length + outPaths.length + i}`} />
            </animateMotion>
          </circle>
        ))}
      </g>

      {/* intake */}
      <circle className="node-pulse ring" cx={src.x} cy={src.y} r={src.r + 9} />
      <circle className="node" cx={src.x} cy={src.y} r={src.r} />
      <text className="lbl" x={src.x} y={src.y - 14} textAnchor="middle" fontSize="11">Works checked</text>
      <text className="num" x={src.x} y={src.y + 8} textAnchor="middle" fontSize="16">{fmt(n?.total_works)}</text>
      <text className="lbl" x={src.x} y={src.y + 26} textAnchor="middle" fontSize="10">all of them</text>

      {/* detectors */}
      {SIGNAL_DETECTORS.map((x, i) => {
        const y = det.ys[i];
        return (
          <g key={x.signal}>
            <rect className="node" x={det.x} y={y - det.h / 2} width={det.w} height={det.h} />
            <text x={det.x + 12} y={y + 4} fontSize="12">{x.short}</text>
            <text className="num" x={det.x + det.w - 12} y={y + 4} textAnchor="end" fontSize="12">
              {fmt(fam[x.signal])}
            </text>
          </g>
        );
      })}
      <text className="lbl" x={det.x} y={det.ys[0] - 30} fontSize="10" letterSpacing="1">
        FIVE CHECKS · WORKS EACH ONE CAUGHT
      </text>

      {/* fusion */}
      <circle className="node-pulse ring" cx={fuse.x} cy={fuse.y} r={fuse.r + 8} />
      <circle className="node hot" cx={fuse.x} cy={fuse.y} r={fuse.r} />
      <text x={fuse.x} y={fuse.y - 2} textAnchor="middle" fontSize="11" fontWeight="700">Combine</text>
      <text className="lbl" x={fuse.x} y={fuse.y + 13} textAnchor="middle" fontSize="10">2+ agree</text>

      {/* leads */}
      <rect className="node" x={leads.x} y={leads.y} width={leads.w} height={leads.h} />
      <text className="lbl" x={leads.x + 12} y={leads.y + 18} fontSize="10">FLAGGED</text>
      <text className="num" x={leads.x + 12} y={leads.y + 37} fontSize="16">{fmt(n?.surfaced_leads)}</text>

      {/* high priority */}
      <rect className="node hot" x={high.x} y={high.y} width={high.w} height={high.h} />
      <text className="lbl" x={high.x + 12} y={high.y + 18} fontSize="10">MOST URGENT</text>
      <text className="num" x={high.x + 12} y={high.y + 37} fontSize="16">{fmt(n?.bands?.HIGH)}</text>

      {/* into action */}
      <text className="lbl" x={high.x} y={high.y + high.h + 26} fontSize="11">
        {plan ? `→ ${num(plan.works)} works fit ${PLAN_DAYS} days of visits` : "→ visit plan"}
      </text>
      <text className="lbl" x={high.x} y={high.y + high.h + 42} fontSize="11">
        {plan ? `  protecting ${rupees(plan.exposure_rupees)}` : ""}
      </text>
    </svg>
  );
}

/* ---------------------------------------------------------------------------
   AnomalyFeed — the top surfaced leads, one after another.
   --------------------------------------------------------------------------- */
export function AnomalyFeed({ items = [], every = 3600, rows = 6, total }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const list = items.slice(0, rows);

  useEffect(() => {
    if (paused || list.length < 2) return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const t = setInterval(() => setI((x) => (x + 1) % list.length), every);
    return () => clearInterval(t);
  }, [paused, list.length, every]);

  if (!list.length) {
    return <div className="feed"><div className="feed-scan" /><div className="feed-empty">Loading…</div></div>;
  }

  return (
    <div
      className="feed"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="feed-scan" aria-hidden="true" />
      <ol className="feed-list" aria-live="off">
        {list.map((w, k) => {
          const on = k === i;
          return (
            <li key={w.work_ref} className={"feed-row" + (on ? " on" : "")}>
              <button type="button" className="feed-hit" onClick={() => setI(k)} aria-expanded={on}>
                <span className="feed-ref">{w.work_ref}</span>
                <span className="feed-desc">{w.description}</span>
                <span className="feed-state">{w.state}</span>
                <span className="feed-exp">{rupees(w.exposure_rupees)}</span>
              </button>
              {on && (
                <div className="feed-detail">
                  <div className="feed-why">
                    <Band value={w.band} />
                    <span className="feed-fired">{(w.signals || []).length} checks raised a concern:</span>
                    <span className="feed-chips">
                      {(w.signals || []).map((s) => (
                        <span className="feed-chip" key={s}>{SHORT[s] || s}</span>
                      ))}
                      {w.compliance_flags > 0 && (
                        <span className="feed-chip warn">{w.compliance_flags} record problem{w.compliance_flags > 1 ? "s" : ""}</span>
                      )}
                      {w.early_warning && w.early_warning !== "LOW" && (
                        <span className="feed-chip warn">{w.early_warning.toLowerCase()} risk of getting stuck</span>
                      )}
                    </span>
                    <Link to={`/case/${encodeURIComponent(w.work_ref)}`} className="link feed-open">
                      See why
                    </Link>
                  </div>
                  <span
                    key={`${i}-${paused}`}
                    className="feed-timer"
                    style={{ animationDuration: `${every}ms`, animationPlayState: paused ? "paused" : "running" }}
                    aria-hidden="true"
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="feed-foot">
        <span>
          Found by the computer in eSAKSHI records up to {DATA_SNAPSHOT} · {paused ? "paused on" : "showing"} the {list.length} most urgent works
        </span>
        <Link to="/worklist" className="link">
          See the full list{total ? ` (${num(total)})` : ""}
        </Link>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
   DetectorBoard — one tile per detector.
   --------------------------------------------------------------------------- */
export function DetectorBoard({ d }) {
  const s = d.stats;
  const fam = d.families || {};
  const leads = s?.national?.surfaced_leads;
  const ew = s?.early_warning;
  const ewHigh = ew ? (ew.levels?.HIGH || 0) + (ew.levels?.CRITICAL || 0) : null;

  const extra = {
    "Peer amount": s ? `compared within ${num(s.archetype_intelligence?.length)} kinds of work` : null,
    "Peer duration": s ? `fairly counts the ${num(s.national.open)} works not finished yet` : null,
    "Statistical outlier": d.models ? `${num(d.models.anomaly_detection.n_flagged)} works looked unusual to the computer` : null,
    "Behavioural change": d.temporal
      ? `${num(d.temporal.counts.agencies_changed)} of ${num(d.temporal.counts.agencies_analysed)} agencies changed suddenly`
      : null,
    "Near-duplicate work": s
      ? `${num(s.duplicates.concerning_pairs)} worth a look, out of ${num(s.duplicates.total_pairs)} similar pairs`
      : null,
  };

  const tiles = [
    ...SIGNAL_DETECTORS.map((x) => ({
      kind: "Check", ...x,
      count: fam[x.signal],
      unit: "flagged works it caught",
      share: leads && fam[x.signal] != null ? fam[x.signal] / leads : null,
      shareOf: "of flagged works",
      extra: extra[x.signal],
    })),
    {
      kind: "Watch", name: "Records in the right order", monitor: true,
      count: s?.compliance?.works_with_any_flag,
      unit: "works with a record problem",
      catches: "A step is missing, dated wrongly, or happened out of order — eight simple checks.",
      share: s ? s.compliance.works_with_any_flag / s.national.total_works : null,
      shareOf: "of all works",
      extra: s ? `${s.compliance.checks?.length} checks, each saying which rule it comes from` : null,
      to: "/compliance",
    },
    {
      kind: "Watch", name: "Early warning: may get stuck", monitor: true,
      count: ewHigh,
      unit: "unfinished works at high risk",
      catches: "Unfinished works that, going by how long similar works took, may never get finished.",
      share: ew && ew.open_works ? ewHigh / ew.open_works : null,
      shareOf: "of unfinished works",
      extra: ew ? `${num(ew.levels?.MEDIUM || 0)} more at medium risk` : null,
      to: "/compliance",
    },
  ];

  return (
    <div className="det-board">
      {tiles.map((x, i) => (
        <Link
          key={x.name}
          to={x.to}
          className={"det" + (x.monitor ? " monitor" : "")}
          style={{ "--d": `${i * 0.45}s` }}
        >
          <span className="det-kind">{x.kind}</span>
          <span className="det-name">{x.name}</span>
          <span className="det-count">{fmt(x.count)}</span>
          <span className="det-unit">{x.unit}</span>
          <span className="det-bar" aria-hidden="true">
            <span style={{ width: x.share == null ? "0%" : `${Math.max(2, Math.min(100, x.share * 100))}%` }} />
          </span>
          <span className="det-share">
            {x.share == null ? "…" : `${(x.share * 100).toFixed(x.share < 0.01 ? 2 : 1)}% ${x.shareOf}`}
          </span>
          <span className="det-catch">{x.catches}</span>
          {x.extra && <span className="det-extra">{x.extra}</span>}
        </Link>
      ))}
      <div className="det fusion">
        <span className="det-kind">The main rule</span>
        <span className="det-name">Flagged only when two checks agree</span>
        <span className="det-count">{fmt(leads)}</span>
        <span className="det-unit">works flagged · {fmt(s?.national?.bands?.HIGH)} most urgent</span>
        <span className="det-catch">
          One clue on its own is never enough. A work is flagged only when at least two different
          checks agree — and it always shows, in words, why it was flagged.
        </span>
        <span className="det-extra">It never says "fraud": no record shows which works were fraud, so the computer cannot learn it.</span>
      </div>
    </div>
  );
}
