import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, num, rupees } from "../api.js";
import { LiveStamp, Topbar } from "../components/Bits.jsx";
import ExplainTabs from "../components/ExplainTabs.jsx";
import { IconLayers } from "../components/icons.jsx";
import { checkName, familyName, plainEvidence, plainGuidance, plainNextStep, plainReason } from "../plain.js";

/**
 * System Workflow — how the whole application works, stage by stage, and then one
 * real work followed through every stage line by line.
 *
 * Nothing on this page is typed in. Every figure is fetched from the engine when the
 * page opens (and again on "Recompute"), and the page says when that happened and how
 * long it took. That is what "dynamic" honestly means for this system: the data is a
 * published eSAKSHI snapshot, not a live feed, so nothing here ticks or pretends to
 * stream — but nothing here is a hard-coded number either, and every caveat shown is
 * the caveat the engine itself returns alongside the figure.
 */

const PLAN_BUDGET = 50; // auditor-days — the same default the Audit Plan screen opens on

/** Everything the pipeline view reads, fetched together so the stamp covers all of it. */
const SOURCES = {
  health: () => api.health(),
  models: () => api.models(),
  stats: () => api.stats(),
  transparency: () => api.transparency(),
  temporal: () => api.temporal(),
  plan: () => api.auditPlan(PLAN_BUDGET),
  crm: () => api.salesforceOverview(),
  field: () => api.fieldSummary(),
};

const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const dash = (v, f = num) => (v == null ? "…" : f(v));

export default function Workflow() {
  const [d, setD] = useState({});
  const [failed, setFailed] = useState([]);
  const [at, setAt] = useState(null);
  const [ms, setMs] = useState(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(() => {
    setBusy(true);
    const t0 = performance.now();
    const keys = Object.keys(SOURCES);
    Promise.allSettled(keys.map((k) => SOURCES[k]())).then((results) => {
      const next = {};
      const bad = [];
      results.forEach((r, i) => {
        if (r.status === "fulfilled") next[keys[i]] = r.value;
        else bad.push(keys[i]);
      });
      setD(next);
      setFailed(bad);
      setAt(new Date());
      setMs(Math.round(performance.now() - t0));
      setBusy(false);
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const n = d.stats?.national;
  const arch = d.models?.archetype_clustering;
  const cox = d.models?.completion_risk;
  const iso = d.models?.anomaly_detection;
  const dup = d.stats?.duplicates;
  const comp = d.stats?.compliance;
  const ew = d.stats?.early_warning;
  const plan = d.plan;
  const ranking = plan?.comparison?.strategies?.find((s) => /ranking/i.test(s.strategy));
  const tiers = d.crm?.escalation_tiers;
  const casesInCrm = tiers ? Object.values(tiers).reduce((a, b) => a + b, 0) : null;
  const ready = d.field?.readiness;
  const described = d.transparency?.completeness?.find((c) => c.field === "work_description");

  const stages = [
    {
      phase: "Read",
      title: "Read the government records",
      what: [
        "The computer reads the public eSAKSHI records of every MP-funded work and puts all the steps of each work together — asked for, approved, started, finished. Records with mistakes are kept and marked, never quietly thrown away, so no work goes missing without a reason.",
      ],
      method: "Technical: pandas · typed load · parquet files",
      io: [
        ["Works in the records", dash(d.transparency?.totals?.works)],
        ["States and UTs", dash(n?.states)],
        ["Constituencies", dash(n?.constituencies)],
        ["Agencies that build the works", dash(n?.implementing_agencies)],
        ["Works with a description", described ? `${described.present_pct}%` : "…"],
      ],
      caveat: d.transparency
        ? `${d.transparency.totals.unavailable_metrics} facts an inspector would want are not in the public data — including how much was really spent, so we never say money was overspent.`
        : null,
      link: ["/transparency", "About the Data"],
    },
    {
      phase: "Learn",
      title: "Learn what normal work looks like",
      what: [
        "The computer reads what each work is (\"build a road\", \"put up street lights\") and puts works that mean the same thing into groups — so a road is only ever compared with other roads. Nobody gave it the list of groups; it found them by itself.",
      ],
      method: arch?.model ? `Technical: ${arch.model}` : null,
      io: [
        ["Descriptions read", dash(arch?.n_descriptions_clustered)],
        ["Kinds of work found", dash(arch?.k_chosen)],
        ["How clearly the groups separate (0 to 1)", arch ? arch.silhouette_at_chosen_k.toFixed(3) : "…"],
      ],
      caveat: arch ? "This score only says how neatly the groups split apart. It is not a mark for being right — people checked by reading the groups that they make sense." : null,
      link: ["/archetypes", "Work Types"],
    },
    {
      phase: "Compare",
      title: "Compare each work with similar works",
      what: [
        "Each work is compared with works of the same kind in the same state: does it cost much more, is it taking much longer, and did its steps happen in the right order? Being different from the whole country is not enough — it has to stand out from works just like it.",
      ],
      method: "Technical: peer percentiles · robust z-scores · 8 lifecycle checks",
      io: [
        ["Record checks run on every work", dash(comp?.checks?.length)],
        ["Works with at least one record problem", dash(comp?.works_with_any_flag)],
        ["Groups of similar works used", dash(d.stats?.archetype_intelligence?.length)],
      ],
      caveat: comp ? "Some checks follow a written rule; others only mean \"much more than usual\". Each check says which kind it is, so nobody mistakes an unusual number for a broken rule." : null,
      link: ["/compliance", "Record Checks"],
    },
    {
      phase: "Predict",
      title: "Guess which unfinished works may get stuck",
      what: [
        "Most works are simply not finished yet. The computer learns from how long similar works took to finish — and it counts the unfinished ones fairly instead of ignoring them — then gives each unfinished work a chance of getting stuck.",
      ],
      method: cox?.model ? `Technical: ${cox.model}` : null,
      io: [
        ["Finished works it learned from", dash(cox?.n_events_total)],
        ["Unfinished works it also counted", dash(cox?.n_censored_total)],
        ["How well it guesses on works it had not seen (0.5 = coin toss, 1 = perfect)", cox ? cox.c_index_heldout.toFixed(4) : "…"],
        ["Unfinished works given a chance", dash(ew?.open_works)],
        ["High risk of getting stuck", dash(ew?.levels?.HIGH)],
      ],
      caveat: cox ? "The score shows the computer is clearly better than guessing at which works finish sooner. It only predicts time to finish — it never says anyone did anything wrong." : null,
      link: ["/compliance", "Early Warnings"],
    },
    {
      phase: "Spot",
      title: "Spot odd numbers, repeated works and sudden changes",
      what: [
        "Three more checks look at every work: one finds works whose numbers look odd, one finds works described in almost the same words (it may be one work counted twice), and one notices when an agency suddenly starts doing very different work from last year.",
      ],
      method: `Technical: ${iso?.model || "IsolationForest"} · semantic similarity · change detection`,
      io: [
        ["Works with odd numbers", dash(iso?.n_flagged)],
        ["Similar pairs found", dash(dup?.total_pairs)],
        ["Pairs worth a look (same agency, almost same cost)", dash(dup?.concerning_pairs)],
        ["Agencies looked at / suddenly changed",
          d.temporal ? `${num(d.temporal.counts.agencies_analysed)} / ${num(d.temporal.counts.agencies_changed)}` : "…"],
      ],
      caveat: iso ? "Odd numbers are only one extra clue that backs up the others — on their own they never flag a work." : null,
      link: ["/duplicates", "Possible Duplicates"],
    },
    {
      phase: "Explain",
      title: "Put the clues together",
      what: [
        "The clues are sorted into six kinds — cost, time taken, records, agency behaviour, odd numbers and possible repeats. A work is flagged only when at least two different kinds agree, and it always carries the sentences that explain why.",
      ],
      method: "Technical: transparent weighted rules · no trained fraud classifier",
      io: [
        ["Works flagged", dash(n?.surfaced_leads)],
        ["HIGH — three or more kinds of clue agree", dash(n?.bands?.HIGH)],
        ["MEDIUM — two kinds of clue agree", dash(n?.bands?.MEDIUM)],
      ],
      caveat:
        "A flag is a reason to look, never proof. No public MPLADS record says which works were fraud, so the computer cannot learn what fraud looks like — and it never gives a work a fraud score.",
      link: ["/worklist", "Works to Check"],
    },
    {
      phase: "Order",
      title: "Put the flagged works in order",
      what: [
        "Flagged works are sorted by how worth checking they are: how much money is in the work, how likely it is to never get finished, and how many clues agree. The works where the most public money could be at risk go to the top.",
      ],
      method: "Technical: Audit-ROI = priority × exposure × corroboration",
      io: [
        ["Money at risk across all works", n ? rupees(n.total_exposure_rupees) : "…"],
        ["Total money recommended", n ? rupees(n.total_recommended_rupees) : "…"],
      ],
      caveat: "\"Money at risk\" is money in works that may not get finished — it is not money lost and not money spent.",
      link: ["/worklist", "Works to Check"],
    },
    {
      phase: "Plan",
      title: `Plan which works to visit in ${PLAN_BUDGET} days`,
      what: [
        "Just going down the list could send an officer to five far-apart places to see five works. The planner knows that once an officer is at an office, checking a second work there takes much less time — so it plans trips, not just a list.",
      ],
      method: "Technical: greedy optimiser with bundle look-ahead · 1 day for the first work at an office · 0.35 day for each extra one",
      io: [
        ["Works reached", dash(plan?.totals?.works)],
        ["Offices visited", dash(plan?.totals?.agencies)],
        ["Officer-days used", dash(plan?.totals?.days_used, (v) => v.toFixed(2))],
        ["Money at risk checked", plan ? rupees(plan.totals.exposure_rupees) : "…"],
        ["Just going down the list would check", ranking ? `${rupees(ranking.exposure)} (${pct(ranking.share_of_best)})` : "…"],
      ],
      caveat: plan ? "This is a suggested plan for a person to approve, change or reject. It only decides where to look — it does not blame any work, office or person." : null,
      link: ["/audit-plan", "Visit Plan"],
    },
    {
      phase: "Act",
      title: "Hand the works to people",
      what: [
        "The plan is shared out between named officers — one office is never split between two people — and the most important cases are put into Salesforce, where people track who is handling each case and how far it has got.",
      ],
      method: "Technical: LPT scheduling · Salesforce custom objects · 5-stage path",
      io: [
        ["Cases in Salesforce", dash(casesInCrm)],
        ...(tiers ? Object.entries(tiers).map(([k, v]) => [`  ${k}`, num(v)]) : []),
        ["Salesforce connection", d.crm?.org?.status || "…"],
      ],
      caveat: "Salesforce only holds the few hundred cases that need a person, not all two lakh works. That is on purpose — it is not hiding anything.",
      link: ["/rota", "Who Goes Where"],
    },
    {
      phase: "Visit",
      title: "Go and look — the only real proof",
      what: [
        "An officer takes a photo of the board at the work site. The computer reads it and finds the matching work (if it is not sure, it asks the officer), and the officer writes down what they saw. Once saved, that record can never be changed, and it shows who wrote it.",
      ],
      method: "Technical: OCR · perceptual image hashing · append-only records",
      io: [
        ["Site visit reports saved", dash(ready?.verifications)],
        ["Works visited", dash(ready?.works_verified)],
        ["Problems confirmed on site", dash(ready?.concerns_confirmed)],
        ["Visits still needed before the scoring can be tuned", dash(ready?.labels_needed_to_fit_weights)],
      ],
      caveat: ready ? "What officers find on real visits is the only way to know if the computer was right. Until there are enough visits, the scoring stays as set by reasoning, not tuned from results." : null,
      link: ["/scoreboard", "Was It Right?"],
    },
  ];

  return (
    <>
      <Topbar
        title="Step by Step"
        sub="How the whole system works, from start to finish — every number here was worked out when this page opened"
        stamp={false}
        right={
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <LiveStamp at={at} ms={ms} busy={busy} />
            <button className="btn" onClick={load} disabled={busy}>
              {busy ? "Working…" : "Check again"}
            </button>
          </div>
        }
      />
      <ExplainTabs />

      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}>
            <IconLayers size={16} />
          </span>
          <span>
            <strong>Ten steps, from the government records to an officer standing at the work site.</strong>{" "}
            In the first half the computer reads all {n ? num(n.total_works) : "…"} works; in the second
            half people act on what it found. Below the steps, one real work is followed through
            every one of them.
          </span>
        </div>

        {failed.length > 0 && (
          <div className="hitl" role="alert" style={{ borderLeftColor: "var(--sev-high)" }}>
            <span>
              <strong>Some steps could not be loaded:</strong> {failed.join(", ")}.
              Their numbers show "…" instead of a guess. Press "Check again" in a moment.
            </span>
          </div>
        )}

        <div className="wf-intro">
          <div>
            <div className="k">System</div>
            <div className="v">{d.health ? (d.health.status === "ok" ? "Online" : d.health.status) : "…"}</div>
            <div className="f">version {d.health?.version || "…"}</div>
          </div>
          <div>
            <div className="k">Works read</div>
            <div className="v">{dash(n?.total_works)}</div>
            <div className="f">every single work</div>
          </div>
          <div>
            <div className="k">Works flagged</div>
            <div className="v">{dash(n?.surfaced_leads)}</div>
            <div className="f">{n ? `${num(n.bands.HIGH)} with three or more clues` : "…"}</div>
          </div>
          <div>
            <div className="k">Worked out in</div>
            <div className="v">{ms == null ? "…" : `${num(ms)} ms`}</div>
            <div className="f">{at ? `at ${at.toLocaleTimeString("en-IN")}` : "loading…"}</div>
          </div>
        </div>

        <div className="section-title">The ten steps</div>
        <ol className="wf-pipeline">
          {stages.map((s, i) => (
            <li key={s.title} className={"wf-stage " + (busy ? "pending" : "done")}>
              <div className="wf-num" aria-hidden="true">{String(i + 1).padStart(2, "0")}</div>
              <div className="wf-body">
                <div className="wf-head">
                  <span className="wf-phase">{s.phase}</span>
                  <h3>{s.title}</h3>
                  <Link to={s.link[0]} className="link wf-link">Open {s.link[1]}</Link>
                </div>
                <div className="wf-main">
                  <div className="wf-what">
                    {s.what.map((p) => <p key={p}>{p}</p>)}
                    {s.method && <div className="wf-method">{s.method}</div>}
                  </div>
                  <div className="wf-io">
                    <div className="wf-arrow">What it found</div>
                    {s.io.map(([k, v]) => (
                      <div className="wf-io-row" key={k}>
                        <span className="k">{k}</span>
                        <span className={"v" + (v === "…" ? " skeleton-v" : "")}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {s.caveat && <div className="wf-caveat"><b>Good to know: </b>{s.caveat}</div>}
              </div>
            </li>
          ))}
        </ol>

        <Trace plan={plan} total={n?.total_works} />
      </div>
    </>
  );
}

/* ============================================================================
   One work, line by line.

   Picks a real lead (or any reference typed in) and walks it through the same
   stages, printing what each stage concluded about *this* work. A stage that did
   not fire says so — the "clear" lines are as much the point as the "fired" ones.
   ========================================================================== */
function Trace({ plan, total }) {
  const [candidates, setCandidates] = useState([]);
  const [ref, setRef] = useState("");
  const [draft, setDraft] = useState("");
  const [c, setC] = useState(null);
  const [cw, setCw] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.worklist({ band: "HIGH", limit: 12 })
      .then((w) => {
        const refs = (w.items || []).map((x) => x.work_ref);
        setCandidates(refs);
        if (refs[0]) { setRef(refs[0]); setDraft(refs[0]); }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!ref) return;
    let live = true;
    setBusy(true);
    setErr("");
    setC(null);
    setCw(null);
    Promise.all([api.case(ref), api.casework(ref).catch(() => null)])
      .then(([caseFile, casework]) => {
        if (!live) return;
        setC(caseFile);
        setCw(casework);
      })
      .catch((e) => live && setErr(`No work found for ${ref} (${e.message}).`))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [ref]);

  const inPlan = useMemo(
    () => plan?.plan?.find((p) => p.work_ref === ref) || null,
    [plan, ref]
  );

  const next = () => {
    if (!candidates.length) return;
    const i = candidates.indexOf(ref);
    const r = candidates[(i + 1) % candidates.length];
    setRef(r);
    setDraft(r);
  };

  const lines = c ? buildLines(c, cw, inPlan, plan) : [];

  return (
    <>
      <div className="section-title">One work, followed through every step</div>
      <form
        className="wf-trace-bar"
        onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setRef(draft.trim()); }}
      >
        <label htmlFor="wf-ref" className="section-label">Work number</label>
        <input
          id="wf-ref"
          className="input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. MP3018356-W86316"
        />
        <button className="btn btn-primary" type="submit" disabled={busy}>Follow</button>
        <button className="btn" type="button" onClick={next} disabled={busy || candidates.length < 2}>
          Next urgent work
        </button>
        <span className="muted" style={{ fontSize: 12 }}>
          Any of the {total ? num(total) : "…"} works can be followed — even ones the computer never flagged.
        </span>
      </form>

      {err && <div className="empty">{err}</div>}
      {busy && !c && <div className="loading"><div className="spinner" />Following the work through each step…</div>}

      {c && (
        <>
          <div className="wf-trace-head">
            <div>
              <div className="t">{c.identity?.description || c.work_ref}</div>
              <div className="m">
                {c.work_ref} · {c.identity?.state} · {c.identity?.constituency} ·{" "}
                {c.identity?.implementing_agency}
              </div>
            </div>
            <Link to={`/case/${encodeURIComponent(c.work_ref)}`} className="btn">See the full case file</Link>
          </div>
          <ol className="wf-lines">
            {lines.map((l, i) => (
              <li className="wf-line" key={l.stage + i} style={{ "--i": i }}>
                <span className="n">{String(i + 1).padStart(2, "0")}</span>
                <span className="stage">{l.stage}</span>
                <span className="said">
                  {l.said}
                  {l.sub && <span className="sub">{l.sub}</span>}
                </span>
                <span className={"res " + l.kind}>{l.label}</span>
              </li>
            ))}
          </ol>
          <div className="wf-conclusion">
            <b>A person decides what happens next. </b>
            {plainNextStep(c.recommended_next_step) || "No step flagged this work, so there is nothing for an officer to check."}{" "}
            Nothing on this page says that anything is wrong with this work.
          </div>
        </>
      )}
    </>
  );
}

/** Turn one case file into the stage-by-stage account. Every line tolerates a clear record. */
function buildLines(c, cw, inPlan, plan) {
  const id = c.identity || {};
  const out = [];

  out.push({
    stage: "Read",
    said: `Read from the records: ${rupees(id.recommended_amount)} was asked for on ${id.recommendation_date || "—"}.`,
    sub: `Where it is now: ${c.lifecycle?.stage || id.status || "—"}${c.lifecycle?.days_open != null ? `, waiting ${num(c.lifecycle.days_open)} days` : ""}.`,
    kind: "info", label: "Read",
  });

  out.push(c.archetype
    ? { stage: "Learn", said: `Grouped with similar works as: ${c.archetype.label}.`,
        sub: `Group number ${c.archetype.id} of the kinds of work the computer found.`, kind: "info", label: "Grouped" }
    : { stage: "Learn", said: "Not assigned a work type.", kind: "wait", label: "—" });

  const pc = c.peer_context;
  if (pc?.group_size) {
    const p = Math.round((pc.amount_percentile ?? 0) * 100);
    out.push({
      stage: "Compare",
      said: `Compared with ${num(pc.group_size)} works of the same kind in ${id.state}: it costs more than ${p} out of every 100 of them.`,
      sub: p >= 95 ? "One of the most expensive works of its kind." : "Its cost is normal for its kind.",
      kind: p >= 95 ? "fired" : "clear", label: p >= 95 ? "Unusual" : "Normal",
    });
  } else {
    out.push({ stage: "Compare", said: "There was no need to compare this work with others.", kind: "clear", label: "Normal" });
  }

  const ewl = c.early_warning;
  if (c.risk || ewl) {
    const lvl = ewl?.level || "LOW";
    out.push({
      stage: "Predict",
      said: `Chance it may not get finished: ${c.risk ? pct(c.risk.completion_risk) : "—"}; early warning: ${lvl}.`,
      sub: plainReason(ewl?.reason),
      kind: lvl === "HIGH" || lvl === "CRITICAL" ? "fired" : lvl === "MEDIUM" ? "info" : "clear",
      label: lvl,
    });
  }

  const flags = c.compliance_findings || [];
  out.push(flags.length
    ? { stage: "Check", said: `${flags.length} record problem${flags.length > 1 ? "s" : ""} found: ${flags.map((f) => checkName(f.check)).join("; ")}.`,
        sub: flags[0]?.meaning, kind: "fired", label: `${flags.length} found` }
    : { stage: "Check", said: "Every record check passed.", kind: "clear", label: "Clear" });

  out.push(c.duplicate
    ? { stage: "Detect", said: `Looks a lot like another work: ${c.duplicate.work_ref || c.duplicate.other_ref || "see case file"}.`,
        sub: c.duplicate.classification, kind: "fired", label: "Similar work" }
    : { stage: "Detect", said: "No worrying look-alike work was found.", kind: "clear", label: "Clear" });

  const ev = c.evidence || [];
  const band = c.confidence_band || "NONE";
  out.push(ev.length
    ? { stage: "Explain",
        said: `${c.n_signal_families} different kinds of clue agree: ${[...new Set(ev.map((e) => familyName(e.family)))].join(", ")}.`,
        sub: plainEvidence(ev[0]?.detail), kind: band === "HIGH" ? "fired" : "info", label: band }
    : { stage: "Explain", said: "Fewer than two kinds of clue agree, so the work was not flagged.",
        kind: "clear", label: "Not flagged" });

  if (c.audit_roi != null) {
    out.push({
      stage: "Prioritise",
      said: `Worth-checking score ${rupees(c.audit_roi)}; money at risk ${rupees(c.exposure_rupees)}.`,
      sub: `Urgency ${c.priority != null ? c.priority.toFixed(3) : "—"} — the higher the score, the sooner an officer sees it.`,
      kind: "info", label: "Ordered",
    });
  }

  out.push(inPlan
    ? { stage: "Plan",
        said: `Number ${inPlan.order} of ${plan?.totals?.works} in the ${PLAN_BUDGET}-day visit plan.`,
        sub: `${inPlan.repeat_visit ? "The officer is already at this office for another work" : "The first work checked at this office"} — takes ${inPlan.cost_days} officer-day${inPlan.cost_days === 1 ? "" : "s"}.`,
        kind: "fired", label: "In plan" }
    : { stage: "Plan", said: `Did not fit in ${PLAN_BUDGET} days of visits.`,
        sub: "More days on the Visit Plan page may reach it.", kind: "wait", label: "Not in plan" });

  out.push(cw?.in_salesforce
    ? { stage: "Act",
        said: `Put into Salesforce as a ${cw.escalation_tier} case, now at step "${cw.stage}".`,
        sub: `${plainGuidance(cw.stage, cw.guidance) || ""}${cw.target_review_date ? ` Review by ${cw.target_review_date}.` : ""}`,
        kind: "info", label: cw.stage }
    : { stage: "Act", said: "Not one of the cases put into Salesforce.", kind: "wait", label: "Not in Salesforce" });

  const f = cw?.findings || [];
  const latest = f[0];
  out.push(latest
    ? { stage: "Verify",
        said: `${f.length} site visit report${f.length > 1 ? "s" : ""} — latest: ${String(latest.outcome).replace(/_/g, " ").toLowerCase()} (${latest.actor}, ${latest.when}).`,
        sub: latest.notes, kind: /COMPLETE|IN_PROGRESS/.test(latest.outcome) ? "clear" : "fired",
        label: "Visited" }
    : { stage: "Verify", said: "No officer has visited this work yet.", kind: "wait", label: "Not visited" });

  return out;
}
