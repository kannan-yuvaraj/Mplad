import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, API_START_HINT, num, rupees } from "../api.js";
import { Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { sev } from "../severity.js";
import { useDebounced } from "../hooks.js";
import { IconReport } from "../components/icons.jsx";

/**
 * The audit plan: where to send a finite number of auditor-days.
 *
 * Every other screen answers "what looks unusual?". This one answers the question an
 * official asks immediately afterwards, which is harder, because cases do not cost the
 * same to check — five works at one district office are one trip, and five works in five
 * districts are five trips.
 *
 * The comparison table is the argument. A recommendation nobody can check is a demand;
 * showing what each alternative strategy would have covered for the same budget turns it
 * into something a reviewer can disagree with.
 */

const STRATEGY_NOTE = {
  "Optimised plan":
    "Thinks about travel. It picks the work that protects the most money for each day spent, "
    + "then checks more works at that same office while the officer is already there.",
  "Audit-ROI ranking":
    "Our own list, followed from the top. Good — but it sends the officer all over the country.",
  "Biggest cheques first":
    "What most people would try first. But a big work is not the same as a risky work.",
  "Highest risk first":
    "Only looks at risk and ignores money. Checks many works but protects very little money.",
  "Random selection":
    "Picking works by chance. Every other way has to do better than this.",
};

/** The strategy names the engine returns, said plainly. The engine's name stays as a tooltip. */
const STRATEGY_LABEL = {
  "Optimised plan": "Our smart plan",
  "Audit-ROI ranking": "Going down our list",
  "Biggest cheques first": "Biggest amounts first",
  "Highest risk first": "Riskiest first",
  "Random selection": "Picking at random",
};
const stratName = (s) => STRATEGY_LABEL[s] || s;

/**
 * A counted-up number that settles rather than snapping into place.
 *
 * A hidden document has no compositor, so `requestAnimationFrame` never fires — and this
 * counted from zero, meaning a page loaded in a background tab showed a permanent "₹0"
 * where the headline figure should be. Worse than an unanimated number, because a reader
 * has no way to tell a stuck animation from a real zero. So: animate only when there are
 * frames coming, and otherwise land on the true figure immediately.
 */
function Figure({ value, format = num, duration = 700 }) {
  const [shown, setShown] = useState(value ?? 0);
  useEffect(() => {
    if (value == null) return undefined;

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || document.hidden) {
      setShown(value);
      return undefined;
    }

    let frame;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min((now - start) / duration, 1);
      // easeOutExpo: fast first, so the figure is readable almost immediately
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      setShown(value * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    // Backgrounded mid-count, the frames stop. Land on the real figure rather than
    // freezing part-way there.
    const onHide = () => {
      if (document.hidden) {
        cancelAnimationFrame(frame);
        setShown(value);
      }
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, [value, duration]);
  return <>{format(shown)}</>;
}

export default function AuditPlan() {
  const [budget, setBudget] = useState(50);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  // Kept apart from `data` on purpose. A failed request and an empty pipeline are
  // different problems with different fixes, and this page used to report both as
  // "run the pipeline first" — which is wrong, unactionable, and permanent.
  const [failed, setFailed] = useState("");
  const [attempt, setAttempt] = useState(0);

  // The figure under the slider tracks the thumb exactly; only the request waits for it
  // to settle. Firing on every change queued a request per step of the drag, and the
  // screen sat on whichever one happened to land last.
  const askedBudget = useDebounced(budget);

  useEffect(() => {
    let live = true;
    setBusy(true);
    setFailed("");
    api.auditPlan(askedBudget)
      .then((d) => { if (live) { setData(d); setFailed(""); } })
      .catch((err) => {
        // Swallowing this was the bug: the page fell through to "no plan available" and
        // stayed there, because the only thing that re-runs this effect is the budget
        // changing and the budget control is not rendered in that branch.
        console.error(err);
        if (live) setFailed(String(err.message || err));
      })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [askedBudget, attempt]);

  // The API is commonly still booting when the first page is opened. One automatic retry
  // covers that without the reader having to know it happened.
  useEffect(() => {
    if (!failed || attempt > 0) return undefined;
    const timer = setTimeout(() => setAttempt(1), 1200);
    return () => clearTimeout(timer);
  }, [failed, attempt]);

  const strategies = data?.comparison?.strategies || [];
  const best = strategies.find((s) => s.optimised);
  const runnerUp = useMemo(
    () => strategies.filter((s) => !s.optimised).sort((a, b) => b.exposure - a.exposure)[0],
    [strategies],
  );
  const gain = best && runnerUp ? best.exposure - runnerUp.exposure : 0;

  if (!data && busy) {
    return (<><Topbar title="Visit Plan" /><div className="content"><Loading /></div></>);
  }
  if (!data && failed) {
    return (
      <>
        <Topbar title="Visit Plan" />
        <div className="content">
          <div className="empty">
            <p><b>Could not reach the system.</b> {failed}</p>
            <p className="muted">
              The plan is worked out on the server. If it is still starting, this fixes
              itself; otherwise start it with{" "}<code>{API_START_HINT}</code>.
            </p>
            <button className="btn" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </div>
        </div>
      </>
    );
  }
  if (!data?.available) {
    return (
      <>
        <Topbar title="Visit Plan" />
        <div className="content">
          <div className="empty">
            <p>{data?.note || "No checked works are available yet. The checks need to be run first."}</p>
            <button className="btn" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </div>
        </div>
      </>
    );
  }

  const totals = data.totals;
  const plan = data.plan || [];
  const visible = expanded ? plan : plan.slice(0, 25);

  return (
    <>
      <Topbar
        title="Visit Plan"
        sub="Officers only have so many days — this plan shows which works to visit to protect the most money"
        right={<span className="pill">{num(totals.works)} works · {num(totals.agencies)} office visits</span>}
      />

      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconReport size={16} /></span>
          <span>
            <strong>A suggestion, not a decision.</strong> A person can approve, change or reject this plan. It only decides where to look first — it does not blame any work, office or person.
          </span>
        </div>

        {/* ---------------------------------------------------------- budget dial */}
        <div className="card plan-budget">
          <div className="plan-budget-head">
            <div>
              <div className="section-label">Officer-days available</div>
              <div className="plan-budget-value">
                <Figure value={budget} format={(v) => Math.round(v)} duration={420} /> days
              </div>
            </div>
            <div className="plan-budget-presets">
              {data.budget_presets.map((preset) => (
                <button
                  key={preset}
                  className={"plan-preset" + (preset === budget ? " active" : "")}
                  onClick={() => setBudget(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
          <input
            type="range" min={5} max={250} step={5} value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="plan-slider"
            aria-label="Officer-days available"
          />
          <p className="plan-cost-note" title={data.comparison.cost_model.note}>
            Checking the first work at an office takes {data.comparison.cost_model.first_visit_days ?? 1} full
            day — travel, the visit and writing it up. Each extra work at that same office takes
            only {data.comparison.cost_model.same_agency_days} of a day, because the officer is already
            there. That is why a plan does better than just going down a list, which could send one
            officer to five far-apart places to see five works.
          </p>
        </div>

        {/* ---------------------------------------------------------- headline */}
        <Reveal>
          <div className="grid cols-4 plan-figures">
            <div className="card stat">
              <div className="label">Money at risk checked</div>
              <div className="value accent">
                <Figure value={totals.exposure_rupees} format={rupees} />
              </div>
              <div className="foot">in {totals.days_used} officer-days</div>
            </div>
            <div className="card stat">
              <div className="label">Works reached</div>
              <div className="value"><Figure value={totals.works} /></div>
              <div className="foot">{num(totals.repeat_visits)} with no extra travel</div>
            </div>
            <div className="card stat">
              <div className="label">Office visits</div>
              <div className="value"><Figure value={totals.agencies} /></div>
              <div className="foot">across {num(totals.states)} states</div>
            </div>
            <div className="card stat">
              <div className="label">Extra money checked vs next best way</div>
              <div className="value" style={{ color: sev("LOW").ink }}>
                <Figure value={gain} format={rupees} />
              </div>
              <div className="foot">compared with {runnerUp ? stratName(runnerUp.strategy).toLowerCase() : "—"}</div>
            </div>
          </div>
        </Reveal>

        {/* ---------------------------------------------------------- comparison */}
        <Reveal delay={80}>
          <div className="section-title">Five ways to choose, same number of days</div>
          <div className="card">
            <div className="plan-bars">
              {strategies.map((s, i) => (
                <div key={s.strategy} className={"plan-bar-row" + (s.optimised ? " winner" : "")}
                  style={{ "--i": i }}>
                  <div className="plan-bar-label">
                    <span className="plan-bar-name" title={s.strategy}>{stratName(s.strategy)}</span>
                    <span className="plan-bar-meta">
                      {num(s.works)} works · {num(s.agencies)} office visits
                    </span>
                  </div>
                  <div className="plan-bar-track">
                    <span
                      className="plan-bar-fill"
                      style={{ width: `${Math.max(s.share_of_best * 100, 1.5)}%` }}
                    />
                  </div>
                  <div className="plan-bar-value">
                    ₹{s.exposure_crore} Cr
                    <span className="plan-bar-share">{Math.round(s.share_of_best * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="plan-notes">
              {strategies.map((s) => (
                <div key={s.strategy} className="plan-note">
                  <b>{stratName(s.strategy)}</b> {STRATEGY_NOTE[s.strategy]}
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        {/* ---------------------------------------------------------- curve */}
        <Reveal delay={140}>
          <div className="section-title">More days, more money checked</div>
          <div className="card">
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={data.curve} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                  <CartesianGrid stroke="var(--line-soft)" vertical={false} />
                  <XAxis dataKey="budget_days" tick={{ fontSize: 11 }}
                    label={{ value: "officer-days", position: "insideBottom", offset: -2, fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} width={44}
                    label={{ value: "₹ Cr", angle: -90, position: "insideLeft", fontSize: 10 }} />
                  <Tooltip
                    formatter={(v, n) => [`₹${v} Cr`, n === "optimised_crore" ? "Our smart plan" : "Going down our list"]}
                    labelFormatter={(v) => `${v} officer-days`}
                    contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid var(--line)" }}
                  />
                  <Legend formatter={(v) => (v === "optimised_crore" ? "Our smart plan" : "Going down our list")}
                    wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="optimised_crore" stroke="var(--brick)"
                    strokeWidth={2.5} dot={{ r: 3 }} animationDuration={900} />
                  <Line type="monotone" dataKey="ranking_crore" stroke="var(--forest)"
                    strokeWidth={2} strokeDasharray="5 3" dot={{ r: 3 }} animationDuration={900} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="plan-cost-note">
              The difference is travel. With any number of days, the plan reaches more works than
              going down the list, because it finishes one office before moving to the next.
            </p>
          </div>
        </Reveal>

        {/* ---------------------------------------------------------- the plan */}
        <Reveal delay={200}>
          <div className="section-title">The suggested order of visits</div>
          <div className="card">
            <div className="table-wrap">
              <table className="plan-table">
                <thead>
                  <tr>
                    <th>#</th><th>Work</th><th>State</th><th>Agency building it</th>
                    <th style={{ textAlign: "right" }}>Money at risk</th>
                    <th style={{ textAlign: "right" }}>Days</th>
                    <th style={{ textAlign: "right" }}>Days so far</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.work_ref} className={row.repeat_visit ? "plan-repeat" : ""}>
                      <td className="plan-order">{row.order}</td>
                      <td>
                        <Link to={`/case/${row.work_ref}`} className="plan-ref">{row.work_ref}</Link>
                      </td>
                      <td>{row.state}</td>
                      <td className="plan-agency" title={row.implementing_agency}>
                        {row.implementing_agency}
                        {row.repeat_visit && <span className="plan-tag">same trip</span>}
                      </td>
                      <td style={{ textAlign: "right" }}>{rupees(row.exposure_rupees)}</td>
                      <td style={{ textAlign: "right" }}>{row.cost_days}</td>
                      <td style={{ textAlign: "right" }} className="plan-cum">
                        {row.cumulative_days}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {plan.length > 25 && (
              <button className="plan-more" onClick={() => setExpanded((e) => !e)}>
                {expanded ? "Show first 25 only" : `Show all ${num(plan.length)} works in the plan`}
              </button>
            )}
            <p className="plan-cost-note">
              Rows marked <b>same trip</b> take only {data.comparison.cost_model.same_agency_days} of
              a day instead of a full day — the officer is already at that office for an earlier
              work in the plan. That is how the plan fits in more works.
            </p>
          </div>
        </Reveal>

        {/* ---------------------------------------------------------- by state */}
        {data.by_state?.length > 0 && (
          <Reveal delay={260}>
            <div className="section-title">Money checked in each state</div>
            <div className="card">
              <div style={{ height: Math.max(200, data.by_state.length * 26) }}>
                <ResponsiveContainer>
                  <BarChart data={data.by_state} layout="vertical"
                    margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid stroke="var(--line-soft)" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `₹${Math.round(v / 1e7)}Cr`} />
                    <YAxis type="category" dataKey="state" width={110} tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(v) => [rupees(v), "money at risk"]}
                      contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid var(--line)" }}
                    />
                    <Bar dataKey="exposure_rupees" radius={[0, 3, 3, 0]} animationDuration={800}>
                      {data.by_state.map((_, i) => (
                        <Cell key={i} fill={i === 0 ? "var(--brick)" : "var(--brass)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Reveal>
        )}
      </div>
    </>
  );
}
