import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, num, rupees } from "../api.js";
import { Band, Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { TREND_LEVEL, prettify, sevFill } from "../severity.js";
import { useI18n } from "../I18nContext.jsx";
import { IconTrend } from "../components/icons.jsx";
import { TREND_NAME, plainTrend } from "../plain.js";

/** Warm parchment tooltip — matches the one on Overview. */
const TIP = {
  background: "#ffffff", border: "1px solid #ddd5c6", borderRadius: 3,
  fontSize: 12, boxShadow: "0 2px 10px rgba(60,48,30,.12)",
};

/**
 * A temporal classification, coloured by what it means for a reviewer rather than
 * by how dramatic it sounds. "Normal" and "Stable" were previously painted the
 * alarm colour, so the two reassuring states looked exactly like a sudden change.
 */
function Tag({ value }) {
  return <Band value={TREND_LEVEL[value] || "NONE"} label={TREND_NAME[value] || prettify(value)} />;
}

export default function Trends() {
  const [d, setD] = useState(null);
  const { t } = useI18n();
  useEffect(() => { api.temporal().then(setD).catch(console.error); }, []);

  if (!d) return (<><Topbar title={t("trends.title", "Changes Over Time")} /><div className="content"><Loading /></div></>);

  const series = d.national_series.map((s) => ({
    period: s.period, works: s.works,
    median: s.median_amount ? Math.round(s.median_amount / 1000) : null,
  }));

  return (
    <>
      <Topbar title={t("trends.title", "Changes Over Time")}
        sub={t("trends.sub", "How the scheme is changing, year by year")}
        right={<span className="pill">{num(d.counts.agencies_analysed)} {t("trends.agenciesAnalysed", "agencies looked at")}</span>} />
      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconTrend size={16} /></span>
          <span>
            <strong>{t("trends.method", "How this was worked out:")}</strong>{" "}
            <span title={d.method_note}>Every chart here uses only the date a work was asked for.
            We do not use finish dates, because recent works have not had time to finish yet —
            using them would make every recent month look like it changed.</span>
          </span>
        </div>

        <Reveal><div className="grid cols-2">
          <div className="card">
            <h3>{t("trends.volume", "Number of works each month (whole country)")}</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={series}>
                <CartesianGrid stroke="#f1ece1" vertical={false} />
                <XAxis dataKey="period" stroke="#8a8175" fontSize={10} minTickGap={30} />
                <YAxis stroke="#8a8175" fontSize={11} />
                <Tooltip contentStyle={TIP} cursor={{ stroke: "#ddd5c6" }} />
                <Line type="monotone" dataKey="works" stroke="#a8452a" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            <div style={{ marginTop: 10 }}>
              <Tag value={d.national_volume.classification} />
              <span className="muted" style={{ fontSize: 12.5, marginLeft: 10 }} title={d.national_volume.explanation}>
                {plainTrend(d.national_volume.explanation)}
              </span>
            </div>
          </div>

          <div className="card">
            <h3>{t("trends.median", "Typical amount per work (in thousand rupees)")}</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={series}>
                <CartesianGrid stroke="#f1ece1" vertical={false} />
                <XAxis dataKey="period" stroke="#8a8175" fontSize={10} minTickGap={30} />
                <YAxis stroke="#8a8175" fontSize={11} />
                <Tooltip contentStyle={TIP} cursor={{ stroke: "#ddd5c6" }} />
                <Line type="monotone" dataKey="median" stroke="#2f5d3f" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            <div style={{ marginTop: 10 }}>
              <Tag value={d.national_amount.classification} />
              <span className="muted" style={{ fontSize: 12.5, marginLeft: 10 }} title={d.national_amount.explanation}>
                {plainTrend(d.national_amount.explanation)}
              </span>
            </div>
          </div>
        </div>

        </Reveal>
        <Reveal><div className="section-title">{t("trends.radar", "Kinds of work that are becoming more common")}</div></Reveal>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>{t("trends.workType", "Work type")}</th><th>{t("trends.status", "Status")}</th>
              <th className="num">{t("trends.recentWorks", "Recent works")}</th><th className="num">{t("trends.shareChange", "Change in share")}</th>
            </tr></thead>
            <tbody>
              {d.archetype_radar.slice(0, 12).map((a) => (
                <tr key={a.archetype_id}>
                  <td>{a.label}</td>
                  <td><Tag value={a.classification} /></td>
                  <td className="num">{num(a.recent_works)}</td>
                  <td className="num" style={{ color: a.delta >= 0 ? sevFill("LOW") : sevFill("MEDIUM") }}>
                    {a.delta >= 0 ? "+" : ""}{(a.delta * 100).toFixed(2)} points
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="section-title">
          {t("trends.agenciesChanged", "Agencies that suddenly changed what they do")} ({num(d.counts.agencies_changed)} of {num(d.counts.agencies_analysed)})
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>{t("trends.agency", "Agency")}</th><th>{t("trends.status", "Status")}</th>
              <th className="num">{t("trends.totalWorks", "Total works")}</th><th>{t("trends.whyFlagged", "Why it was flagged")}</th>
            </tr></thead>
            <tbody>
              {d.agency_trends.slice(0, 20).map((a) => (
                <tr key={a.entity}>
                  <td className="desc-cell">{a.entity}</td>
                  <td><Tag value={a.classification} /></td>
                  <td className="num">{num(a.total_works)}</td>
                  <td className="muted" style={{ fontSize: 12 }} title={a.explanation}>{plainTrend(a.explanation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
