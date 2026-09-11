import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, num, rupees } from "../api.js";
import { Loading, Topbar } from "../components/Bits.jsx";
import { riskFill } from "../severity.js";
import { useI18n } from "../I18nContext.jsx";
import { IconArchetype } from "../components/icons.jsx";

function Bar({ value, color }) {
  return (
    <div className="mini-bar">
      <span style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
    </div>
  );
}

export default function Archetypes() {
  const [a, setA] = useState(null);
  const [open, setOpen] = useState(null);
  const nav = useNavigate();
  const { t } = useI18n();
  useEffect(() => { api.archetypes().then(setA).catch(console.error); }, []);

  if (!a) return (<><Topbar title={t("archetypes.title", "Work Types")} /><div className="content"><Loading /></div></>);

  const interpretable = a.filter((x) => x.interpretable !== false).length;
  const maxWorks = Math.max(...a.map((x) => x.n_works));

  return (
    <>
      <Topbar title={t("archetypes.title", "Work Types")}
        sub={t("archetypes.sub", "Kinds of work the computer worked out on its own, just by reading the descriptions")}
        right={<span className="pill">{a.length} · {interpretable} {t("archetypes.named", "named")}</span>} />
      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconArchetype size={16} /></span>
          <span>
            Nobody gave the computer this list. It read every description, worked out what
            each one means, and put works that mean the same thing together. Each group's name
            is made from the words that stand out most in it — <strong>taken from the works
            actually in the group</strong>. Where a group is held together by the language it is
            written in rather than the kind of work, we say so instead of making up a name.
          </span>
        </div>

        <div className="arch-list">
          {a.map((x, i) => {
            const isOpen = open === x.archetype_id;
            const uninterpretable = x.interpretable === false;
            return (
              <div className={"arch-card" + (isOpen ? " open" : "")} key={x.archetype_id}>
                <div className="arch-head" onClick={() => setOpen(isOpen ? null : x.archetype_id)}>
                  <div className="arch-rank">{String(i + 1).padStart(2, "0")}</div>

                  <div className="arch-main">
                    <div className="arch-name">
                      {uninterpretable
                        ? <span className="muted">{x.label}</span>
                        : x.label}
                      {uninterpretable && <span className="fam-tag">{t("archetypes.notInterpretable", "no clear meaning")}</span>}
                      {x.note && !uninterpretable && <span className="fam-tag">mixed by language</span>}
                    </div>
                    <div className="arch-sub">
                      {num(x.n_works)} works · {x.states} states · {num(x.agencies)} agencies
                      {x.top_state && <> · mostly {x.top_state}</>}
                    </div>
                    <Bar value={x.n_works / maxWorks} color="#a8452a" />
                  </div>

                  <div className="arch-metrics">
                    <div className="arch-metric">
                      <span className="m-label">{t("archetypes.medianSize", "Typical cost")}</span>
                      <span className="m-value">{rupees(x.median_amount)}</span>
                    </div>
                    <div className="arch-metric">
                      <span className="m-label">{t("archetypes.completedPct", "Finished")}</span>
                      <span className="m-value">{(x.completion_rate * 100).toFixed(0)}%</span>
                    </div>
                    <div className="arch-metric">
                      <span className="m-label">{t("archetypes.typicalDuration", "Usual time taken")}</span>
                      <span className="m-value">
                        {x.median_days_to_complete ? `${Math.round(x.median_days_to_complete)} days` : "—"}
                      </span>
                    </div>
                    <div className="arch-metric">
                      <span className="m-label">{t("archetypes.flagged", "Flagged")}</span>
                      <span className="m-value" style={{ color: riskFill(x.lead_rate) }}>
                        {(x.lead_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="arch-metric">
                      <span className="m-label">₹ Money at risk</span>
                      <span className="m-value">{rupees(x.total_exposure)}</span>
                    </div>
                  </div>
                  <div className="arch-chev">{isOpen ? "▾" : "▸"}</div>
                </div>

                {isOpen && (
                  <div className="arch-body">
                    {x.note && <p className="arch-note" title={x.note}>⚠ {x.note.startsWith("Grouped partly by language") ? "Grouped partly by language: these descriptions are written in Hindi or Gujarati using English letters, so the group is about how they are written as well as the kind of work." : x.note}</p>}
                    {x.top_terms && (
                      <div>
                        <div className="m-label" style={{ marginBottom: 6 }}>
                          {t("archetypes.distinctiveTerms", "Words that stand out in this group")}
                        </div>
                        <div className="chips">
                          {x.top_terms.split(",").slice(0, 8).map((t, ti) => (
                            <span className="chip" key={`${ti}-${t}`}>{t.trim()}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    <button className="btn" style={{ marginTop: 14 }}
                      onClick={(e) => { e.stopPropagation(); nav("/worklist"); }}>
                      {t("archetypes.viewFlagged", "See the flagged works")} →
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
