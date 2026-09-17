import { useEffect, useState } from "react";
import { api, num } from "../api.js";
import { Loading, Topbar } from "../components/Bits.jsx";
import ExplainTabs from "../components/ExplainTabs.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { scoreFill, sev } from "../severity.js";
import { useI18n } from "../I18nContext.jsx";
import { IconShield } from "../components/icons.jsx";
import { OUTCOME } from "../plain.js";

/**
 * How far a number is from the raw record. Measured straight from government data
 * is the reassuring case, absent-from-the-data the one a reader must not miss —
 * so it rides the same ladder as everything else. "Derived" and "Unavailable" were
 * previously the same terracotta, which flattened the honest distinction this
 * whole screen exists to draw.
 */
const TYPE = {
  "Direct measurement": { level: "LOW", t: "Counted directly" },
  "Model-derived": { level: "MEDIUM", t: "Worked out by the computer" },
  Unavailable: { level: "HIGH", t: "Not available" },
};

/**
 * How much weight a figure can carry. The badge shows the confidence word, so it
 * is coloured by the confidence — not by the section it sits under, which would
 * put a reassuring green marker next to the word "High" inside the Unavailable
 * table and read as the opposite of what it means.
 */
const CONFIDENCE = { High: "LOW", Medium: "MEDIUM", Low: "HIGH", None: "HIGH" };
const SURE = { High: "Very sure", Medium: "Fairly sure", Low: "Not very sure", None: "Not available" };

/**
 * Each fact the engine lists, re-said for a reader with no statistics. Keyed by the
 * engine's own metric name; the engine's exact wording stays available as a tooltip.
 * Every number here is the engine's number — only the words around it changed.
 */
const METRIC = {
  "Works monitored": ["Number of works", "eSAKSHI public records (Lok Sabha 17, 18 and Rajya Sabha)",
    "Counted from the records one by one, and matched against the portal's own totals for each MP."],
  "Recommended amount": ["Money recommended", "The recommended amount in the records",
    "The only money figure we can trust. It is what was asked for — not what was actually spent."],
  "Completion status": ["Whether a work is finished", "The \"work completed\" step in the records",
    "Whether there is a record saying it was finished, and on which date."],
  "Work archetype": ["Kind of work", "Computer grouping of the descriptions",
    "The computer groups works by meaning on its own. Its \"how neatly the groups split\" score is about 0.05 — that is not a mark for being right."],
  "Peer comparison percentile": ["How it compares with similar works", "Groups of similar works (same kind, same state)",
    "Each work is compared only with works that really are like it, leaving itself out."],
  "Completion risk": ["Chance it may not get finished", "A model of how long works take to finish",
    "On works it had not seen, it guessed which finish sooner right 0.676 of the time (0.5 is a coin toss). It predicts time only — never wrongdoing."],
  "Early-warning level": ["Early warning level", "Finish-time model + how long it is stuck compared with similar works",
    "A risk level with a reason, not a sure prediction that the work will fail."],
  "Near-duplicate candidates": ["Possible duplicates", "Comparing the meaning of descriptions, within the same state and kind of work",
    "The same description is often used for different works, and that is normal. A match is a question for a person, not proof."],
  "₹ exposure at risk": ["₹ Money at risk", "Amount recommended × chance it may not get finished",
    "Money that could be stuck in works that may not get finished. NOT money lost, NOT missing money, NOT money spent."],
  "Verified actual expenditure": ["Money really spent", "The \"actual amount\" column",
    "For 98.35% of finished works it is exactly the same as the amount recommended, and nearly all the rest differ by tiny amounts. So it only confirms the work finished — it does not show real spending."],
  "Payment tranches / releases": ["Payments made in parts", "—",
    "No public MPLADS record shows payments, money released, or certificates of how money was used."],
  "Cost estimate": ["Cost estimate", "—",
    "There is no estimate in the data, so we cannot tell if a work went over budget. We show works that asked for unusually much instead."],
  "Physical progress %": ["How much is really built (%)", "—",
    "The portal only shows paperwork steps, so we show paperwork progress — never how much is actually built."],
  "Sanction date": ["Date of approval", "—",
    "In 100.00% of 179,676 works, the approval date is just a copy of the date it was asked for. We can tell if it was approved, but not when."],
  "Photographic / geotagged evidence": ["Photos and map locations", "Attachment numbers in the records",
    "The records show that documents exist, but the files need a login and cannot be downloaded. We do not claim to check photos from the portal."],
  "District": ["District", "—",
    "There is no district column. One field is a district office and another is a constituency, so anything we said about districts would be made up."],
};
const metricPlain = (m) => METRIC[m.metric] || [m.metric, m.source, m.note];

/** The record columns whose completeness is measured, named plainly. */
const FIELD_NAME = {
  work_description: "What the work is (description)",
  recommendation_date: "Date it was asked for",
  recommended_amount: "Money recommended",
  state_name: "State",
  implementing_agency: "Agency building it",
  archetype_id: "Kind of work (from the computer)",
  activity_category: "Official category",
};

/** What each future field would let the system do. */
const UNLOCKS = {
  actual_expenditure: "See how the money was really used",
  payment_tranches: "Spot strange payment patterns",
  cost_estimate: "Really tell if a work went over budget",
  physical_progress_pct: "Track how much is really built",
  sanction_date: "Check the approval happened at the right time",
  vendor_id: "Spot the same contractor winning again and again, or working together unfairly",
  "geo_lat, geo_lon": "Put works on a map and spot clusters",
  evidence_photos: "Catch the same photo being used for different works",
};


export default function Transparency() {
  const [d, setD] = useState(null);
  const { t } = useI18n();
  useEffect(() => { api.transparency().then(setD).catch(console.error); }, []);

  if (!d) return (<><Topbar title={t("transparency.title", "About the Data")} /><ExplainTabs /><div className="content"><Loading /></div></>);

  const group = (type) => d.metrics.filter((m) => m.type === type);

  return (
    <>
      <Topbar title={t("transparency.title", "About the Data")}
        sub={t("transparency.sub", "What we count directly, what the computer works out, and what the public data simply does not have")}
        right={<span className="pill">{d.totals.unavailable_metrics} {t("transparency.fieldsUnavailable", "facts not available")}</span>} />
      <ExplainTabs />
      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconShield size={16} /></span>
          <span title={d.statement}><strong>We never make up government data we do not have. If a fact is missing, we list it as missing, show how we know, and say what we look at instead.</strong></span>
        </div>

        <Reveal><div className="grid cols-3">
          <div className="card stat">
            <div className="label">{t("transparency.measured", "Counted directly")}</div>
            <div className="value" style={{ fontSize: 28, color: sev("LOW").ink }}>{d.totals.available_metrics}</div>
            <div className="foot">{t("transparency.measuredFoot", "taken straight from government records")}</div>
          </div>
          <div className="card stat">
            <div className="label">{t("transparency.derived", "Worked out by the computer")}</div>
            <div className="value" style={{ fontSize: 28, color: sev("MEDIUM").ink }}>{d.totals.derived_metrics}</div>
            <div className="foot">{t("transparency.derivedFoot", "calculated, with how sure we are")}</div>
          </div>
          <div className="card stat">
            <div className="label">{t("transparency.unavailable", "Not available")}</div>
            <div className="value" style={{ fontSize: 28, color: sev("HIGH").ink }}>{d.totals.unavailable_metrics}</div>
            <div className="foot">{t("transparency.unavailableFoot", "missing from public data — we do not make it up")}</div>
          </div>
        </div>

        </Reveal>
        {["Direct measurement", "Model-derived", "Unavailable"].map((type) => (
          <div key={type}>
            <div className="section-title">{TYPE[type].t}</div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("transparency.metric", "What")}</th><th>{t("transparency.source", "Where it comes from")}</th>
                  <th>{t("transparency.confidenceCol", "How sure")}</th><th>{t("transparency.note", "Note")}</th></tr></thead>
                <tbody>
                  {group(type).map((m) => (
                    <tr key={m.metric}>
                      <td style={{ fontWeight: 600 }} title={m.metric}>{metricPlain(m)[0]}</td>
                      <td className="muted" style={{ fontSize: 12 }} title={m.source}>{metricPlain(m)[1]}</td>
                      <td>
                        <span className="badge sev" title={`Confidence: ${m.confidence}`} style={{
                          color: sev(CONFIDENCE[m.confidence]).ink,
                          background: sev(CONFIDENCE[m.confidence]).soft,
                        }}>
                          <i className="glyph" aria-hidden="true">{sev(CONFIDENCE[m.confidence]).glyph}</i>
                          {SURE[m.confidence] || m.confidence}
                        </span>
                      </td>
                      <td className="muted" style={{ fontSize: 12 }} title={m.note}>{metricPlain(m)[2]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}

        <div className="section-title">{t("transparency.completeness", "How complete each fact is")}</div>
        <div className="card">
          {d.completeness.map((f) => (
            <div key={f.field} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span title={f.field}>{FIELD_NAME[f.field] || f.field}</span><span>{f.present_pct}% filled in</span>
              </div>
              <div className="meter">
                <span style={{ width: `${f.present_pct}%`, background: scoreFill(f.present_pct / 100) }} />
              </div>
            </div>
          ))}
        </div>

        <div className="section-title">What officers found on real visits</div>
        <GroundTruth />

        <div className="section-title">{t("transparency.readyFor", "Ready for more government data")}</div>
        <div className="card">
          <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
            The system already has empty slots ready for facts that MoSPI could share with us
            later. They are empty today; when the data arrives, nothing has to be rebuilt.
          </p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Fact</th><th>Type</th><th>What it would let us do</th></tr></thead>
              <tbody>
                {d.future_fields.map((f) => (
                  <tr key={f.field}>
                    <td style={{ fontFamily: "monospace", fontSize: 12 }}>{f.field}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{f.dtype}</td>
                    <td title={f.unlocks}>{UNLOCKS[f.field] || f.unlocks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * The one honest answer to "how accurate is it?".
 *
 * Nothing in the source data says which works were actually problems, so no score on
 * this site has ever been checked against an outcome. Officers recording what they
 * found on site are the only way that ever changes — and this counts how far off it
 * still is, rather than implying it has already happened.
 */
function GroundTruth() {
  const [d, setD] = useState(null);
  const { t } = useI18n();
  useEffect(() => { api.fieldSummary().then(setD).catch(() => setD({ error: true })); }, []);

  if (!d) return <div className="card"><Loading /></div>;
  if (d.error) return null;

  const r = d.readiness;
  const target = r.verifications + r.labels_needed_to_fit_weights;
  const pct = target ? (r.verifications / target) * 100 : 0;

  return (
    <div className="card">
      <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
        No record anywhere says which MPLADS works really had problems, so every score on this
        site is set by careful reasoning, not learned from results. A site visit report is an
        officer writing down what they saw when they went and looked — the only real proof this
        system can ever get, one visit at a time.
      </p>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <div className="label">Site visit reports</div>
          <div className="value" style={{ fontSize: 28 }}>{num(r.verifications)}</div>
          <div className="foot">across {num(r.works_verified)} works</div>
        </div>
        <div className="card stat">
          <div className="label">Problems confirmed on site</div>
          <div className="value" style={{ fontSize: 28,
            color: r.concerns_confirmed > 0 ? sev("HIGH").ink : undefined }}>
            {num(r.concerns_confirmed)}
          </div>
          <div className="foot">not started, not found, or different from the record</div>
        </div>
        <div className="card stat">
          <div className="label">Visits still needed</div>
          <div className="value" style={{ fontSize: 28 }}>{num(r.labels_needed_to_fit_weights)}</div>
          <div className="foot">before the scoring can be tuned ({num(target)} in total)</div>
        </div>
      </div>

      <div className="meter" style={{ marginBottom: 14 }}>
        <span style={{ width: `${Math.max(pct, 0.5)}%`, background: scoreFill(pct / 100) }} />
      </div>

      {Object.keys(r.by_outcome).length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 14 }}>
          <table>
            <thead><tr><th>Result</th><th>Meaning</th><th style={{ textAlign: "right" }}>Reports</th></tr></thead>
            <tbody>
              {Object.entries(r.by_outcome).map(([k, n]) => (
                <tr key={k}>
                  <td style={{ fontWeight: 600 }} title={k}>{OUTCOME[k]?.[0] || k.replace(/_/g, " ")}</td>
                  <td className="muted" style={{ fontSize: 12 }} title={d.outcomes[k]}>{OUTCOME[k]?.[1] || d.outcomes[k]}</td>
                  <td style={{ textAlign: "right", fontFamily: "monospace" }}>{num(n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12.5, lineHeight: 1.7 }} title={r.note}>
        Once there are {num(target)} or more reports, the scoring could be tuned to match what
        officers really found. There are {num(r.verifications)} now, so nothing is changed and no
        accuracy is claimed. Once saved, a report can never be changed, and it shows which officer
        wrote it; a correction is saved as a new report.
        {d.ocr_available
          ? " The computer reads the number off a photo of the site board, so nobody has to type it in while standing in a field."
          : " Reading photos does not work on this computer, so work numbers are typed in by hand."}
      </p>
    </div>
  );
}
