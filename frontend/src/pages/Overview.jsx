import { Link } from "react-router-dom";
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { num, rupees } from "../api.js";
import { Loading, LiveStamp, Topbar } from "../components/Bits.jsx";
import { CountUp } from "../components/Reveal.jsx";
import Insight from "../components/Insight.jsx";
import { AnomalyFeed, DetectionFlow, DetectorBoard, useDetection } from "../components/Detection.jsx";
import { useRole } from "../RoleContext.jsx";
import { useI18n } from "../I18nContext.jsx";
import { sev, sevFill } from "../severity.js";

/**
 * The Detection Centre — the console's front page.
 *
 * It was the "National Overview": a notice, an AI briefing, four totals, two
 * charts and a 981-pixel table of work types. The first figure sat 593px down a
 * 900px screen, and none of the detectors appeared on it at all. It now leads
 * with the detection pass, then the detectors, then what they surfaced, and puts
 * the portfolio charts and the written briefing underneath as context.
 *
 * Everything on it follows the stakeholder view: a scoped officer sees the pass,
 * the detectors and the feed for their own jurisdiction.
 */

const TIP = {
  background: "#ffffff", border: "1px solid #d6dbe1", borderRadius: 0,
  fontSize: 12, boxShadow: "0 2px 10px rgba(14,42,71,.14)",
};

const BAND_LEGEND = [
  { band: "HIGH", note: "3+ clues agree" },
  { band: "MEDIUM", note: "2 clues agree" },
  { band: "LOW", note: "1 clue" },
  { band: "NONE", note: "no clues" },
];

export default function Overview() {
  const { params, scope } = useRole();
  const { t } = useI18n();
  const { d, at, ms, busy, reload } = useDetection(params);
  const s = d.stats;

  const right = (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      {scope && <span className="pill">Scoped to {scope}</span>}
      <LiveStamp at={at} ms={ms} busy={busy} />
      <button className="btn" onClick={reload} disabled={busy}>{busy ? "Working…" : "Check again"}</button>
    </div>
  );

  if (!s) {
    return (
      <>
        <Topbar title={t("dc.title", "Detection Centre")} stamp={false} right={right} />
        <div className="content airy"><Loading label="Checking the works" /></div>
      </>
    );
  }

  const n = s.national;
  const bands = ["HIGH", "MEDIUM", "LOW", "NONE"].map((b) => ({ band: b, works: n.bands[b] || 0 }));
  const topStates = (s.by_state || []).slice(0, 10).map((x) => ({
    state: x.state_name.length > 14 ? x.state_name.slice(0, 13) + "…" : x.state_name,
    full: x.state_name,
    exposure: +(x.exposure / 1e7).toFixed(1),
  }));

  return (
    <>
      <Topbar
        title={t("dc.title", "Detection Centre")}
        sub={t("dc.sub", "Every MPLADS work checked in five ways — what the computer found, and where to look first")}
        stamp={false}
        right={right}
      />

      <div className="content airy">
        {/* ------------------------------------------------------- the pass */}
        <div className="dc-top">
          <section className="dc-flow">
            <header className="dc-card-head">
              <h2>How every work is checked</h2>
              <span className="muted">Real counts at every step · a flag is never proof</span>
            </header>
            <DetectionFlow d={d} variant="light" />
          </section>

          <div className="dc-kpis">
            <div className="dc-kpi">
              <span className="k">Works checked</span>
              <span className="v"><CountUp end={n.total_works} /></span>
              <span className="f">{num(n.completed)} finished · {num(n.open)} not finished yet</span>
            </div>
            <div className="dc-kpi">
              <span className="k">Works flagged</span>
              <span className="v"><CountUp end={n.surfaced_leads} /></span>
              <span className="f">two or more different checks agree</span>
            </div>
            <div className="dc-kpi hot">
              <span className="k">Most urgent</span>
              <span className="v"><CountUp end={n.bands.HIGH || 0} /></span>
              <span className="f">three or more checks agree</span>
            </div>
            <div className="dc-kpi">
              <span className="k">Money at risk</span>
              <span className="v">{rupees(n.total_exposure_rupees)}</span>
              <span className="f">money in works that may not get finished — not money lost</span>
            </div>
          </div>
        </div>

        {/* -------------------------------------------------------- detectors */}
        <header className="dc-section">
          <h2>The checks</h2>
          <p>Click a check to see every work it caught.</p>
        </header>
        <DetectorBoard d={d} />

        {/* ----------------------------------------------------- what it found */}
        <header className="dc-section">
          <h2>Most urgent works</h2>
          <Link to="/worklist" className="link">See the full list of works to check</Link>
        </header>
        <div className="dc-split">
          <AnomalyFeed items={d.feed?.items || []} total={d.feed?.total} rows={7} />

          <section className="card">
            <h3>{t("overview.bands", "How strong the clues are")}</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={bands} margin={{ left: 0, right: 10, top: 8 }}>
                <XAxis dataKey="band" stroke="#4a5765" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#64707e" fontSize={11} tickLine={false} axisLine={false}
                  tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)} />
                <Tooltip contentStyle={TIP} cursor={{ fill: "rgba(20,64,110,.07)" }}
                  formatter={(v) => [num(v), "Works"]} />
                <Bar dataKey="works" animationDuration={1100}>
                  {bands.map((b) => <Cell key={b.band} fill={sevFill(b.band)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="legend">
              {BAND_LEGEND.map(({ band, note }) => (
                <span key={band}>
                  <i className="dot" style={{ background: sevFill(band) }} />
                  <b className="legend-glyph" aria-hidden="true">{sev(band).glyph}</b>
                  {band} · {note}
                </span>
              ))}
            </div>
          </section>
        </div>

        {/* ----------------------------------------------------------- context */}
        <header className="dc-section">
          <h2>Where the money at risk is</h2>
          <Link to="/archetypes" className="link">The {num(s.archetype_intelligence?.length || s.archetypes?.length || 0)} kinds of work used for comparing</Link>
        </header>
        <div className="dc-split">
          <section className="card">
            <h3>{t("overview.byState", "Money at risk by state (top 10, in crore rupees)")}</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={topStates} layout="vertical" margin={{ left: 6, right: 22 }}>
                <XAxis type="number" stroke="#64707e" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="state" stroke="#4a5765" fontSize={11}
                  width={94} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={TIP} cursor={{ fill: "rgba(20,64,110,.07)" }}
                  formatter={(v) => [`₹${v} Cr`, "Money at risk"]}
                  labelFormatter={(_, p) => p?.[0]?.payload?.full} />
                <Bar dataKey="exposure" fill="#14406e" animationDuration={1100} />
              </BarChart>
            </ResponsiveContainer>
          </section>
          <div>
            <Insight kind="portfolio" params={params} />
            <p className="dc-note">
              <b>A person decides every action.</b> Works are put in order by how much public money a
              check could protect, using clues anyone can see. A flag is a reason to look, never proof.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
