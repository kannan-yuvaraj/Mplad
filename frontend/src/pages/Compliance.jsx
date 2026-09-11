import { useEffect, useState } from "react";
import { api, num, rupees } from "../api.js";
import { Band, Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { authority, scoreFill, sev, sevFill } from "../severity.js";
import { useI18n } from "../I18nContext.jsx";
import { IconCompliance } from "../components/icons.jsx";
import { checkMeaning, checkName } from "../plain.js";

/** The health score's five parts, named and explained plainly. The engine's text stays as a tooltip. */
const COMPONENT = {
  "Completion performance": ["Works finished", (p) => `${p} of works have a record saying they were finished.`],
  "Record compliance": ["Records in order", (p) => `${p} of works have at least one problem in their records.`],
  "Investigation-lead rate": ["Works flagged", (p) => `${p} of works were flagged for checking.`],
  "Duplicate-candidate rate": ["Look-alike works", (p) => `${p} of works have another work described in a similar way.`],
  "Data completeness": ["Descriptions written", (p) => `${p} of works have a proper description.`],
};
function plainComponent(comp) {
  const known = COMPONENT[comp.name];
  const pct = (comp.explanation || "").match(/^([\d.]+%)/);
  if (!known) return [comp.name, comp.explanation];
  return [known[0], pct ? known[1](pct[1]) : comp.explanation];
}

const LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function Compliance() {
  const [c, setC] = useState(null);
  const [w, setW] = useState(null);
  const [h, setH] = useState(null);
  const { t } = useI18n();

  useEffect(() => {
    api.compliance().then(setC).catch(console.error);
    api.earlyWarning().then(setW).catch(() => {});
    api.healthIndex().then(setH).catch(() => {});
  }, []);

  if (!c || !w || !h) return (<><Topbar title={t("compliance.title", "Record Checks and Early Warnings")} /><div className="content"><Loading /></div></>);

  return (
    <>
      <Topbar title={t("compliance.title", "Record Checks and Early Warnings")}
        sub={t("compliance.sub", "Checking that each work's records happen in the right order, and spotting works that may never get finished")}
        right={<span className="pill">Health score {h.score}/100</span>} />
      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconCompliance size={16} /></span>
          <span title={c.authority_note}><strong>{t("compliance.authorityLead", "Where each rule comes from matters.")}</strong> The public data does not come with any official legal limits, so no check here claims to be an official rule. "Record problem" checks find records that break the usual order of steps (asked for → approved → finished). "Much more than usual" checks find works that are very different from similar ones. Neither one means someone did wrong.</span>
        </div>

        <div className="section-title">{t("compliance.healthIndex", "Overall health score of the scheme")} — {h.score}/100</div>
        <div className="card" style={{ marginBottom: 20 }}>
          {h.components.map((comp) => (
            <div key={comp.name} style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span style={{ fontWeight: 600 }} title={comp.name}>
                  {plainComponent(comp)[0]} <span className="muted">· counts for {(comp.weight * 100).toFixed(0)}% of the score</span>
                </span>
                <span>{(comp.value * 100).toFixed(1)}%</span>
              </div>
              <div className="meter">
                <span style={{ width: `${comp.value * 100}%`, background: scoreFill(comp.value) }} />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }} title={comp.explanation}>{plainComponent(comp)[1]}</div>
            </div>
          ))}
          <div className="muted" style={{ fontSize: 12, borderTop: "1px solid var(--line-soft)", paddingTop: 10 }} title={h.note}>
            This score is worked out by us — it is not an official government number. Every part is
            shown and explained above, and how much each part counts is shown too.
          </div>
        </div>

        <Reveal><div className="section-title">{t("compliance.earlyLevels", "Early warnings for unfinished works")}</div></Reveal>
        <div className="grid cols-4">
          {LEVELS.map((lvl) => (
            <div className="card stat sev-tile" key={lvl} style={{ "--sev": sevFill(lvl) }}>
              <div className="label">
                <i className="glyph" aria-hidden="true" style={{ color: sevFill(lvl) }}>{sev(lvl).glyph}</i>
                {lvl}
              </div>
              <div className="value" style={{ fontSize: 26, color: sev(lvl).ink }}>
                {num(w.levels[lvl] || 0)}
              </div>
              <div className="foot">{rupees(w.exposure_by_level?.[lvl] || 0)} {t("common.exposure", "money at risk")}</div>
            </div>
          ))}
        </div>
        <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }} title={w.method_note}>
          This is a risk level, not a sure prediction that a work will fail. It mixes what the
          computer learned from how long similar works took with how long this work has already
          been waiting. Every level comes with the sentence that explains it.
        </p>

        <Reveal><div className="section-title">{t("compliance.checks", "Record checks")}</div></Reveal>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>{t("compliance.check", "Check")}</th><th>{t("compliance.authority", "Based on")}</th><th>{t("compliance.severity", "How serious")}</th>
              <th className="num">{t("common.works", "Works")}</th><th>{t("compliance.meaning", "What it means")}</th>
            </tr></thead>
            <tbody>
              {c.checks.map((chk) => {
                const a = authority(chk.authority);
                return (
                  <tr key={chk.key}>
                    <td style={{ fontWeight: 600 }} title={chk.check}>{checkName(chk.check)}</td>
                    <td><span className="badge" style={{ color: a.ink, background: a.soft }}>{a.label}</span></td>
                    <td><Band value={chk.severity} /></td>
                    <td className="num">{num(chk.works_affected)}</td>
                    <td className="muted" style={{ fontSize: 12 }} title={chk.meaning}>{checkMeaning(chk.check, chk.meaning)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
