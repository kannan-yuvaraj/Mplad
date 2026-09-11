import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, API_START_HINT, num, rupees } from "../api.js";
import { Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { sev } from "../severity.js";
import { useDebounced } from "../hooks.js";
import { IconField } from "../components/icons.jsx";
import { rotaBound } from "../plain.js";

/**
 * The audit plan with names against it.
 *
 * The plan screen answers "where should the days go". A supervising officer has to issue
 * something with people on it, and that is a second problem with one hard rule: an
 * implementing agency is never split between two auditors. The plan's entire saving is
 * that the second work at an agency is cheap *because* somebody is already standing there,
 * and sending two people pays for that journey twice.
 *
 * So the unit on this page is the trip, not the work — which is also why the honest
 * failure mode, more auditors than trips, is shown as idle names rather than papered over
 * by splitting an agency in half.
 */

const TEAM_PRESETS = [1, 2, 4, 6, 8, 12];

export default function FieldRota() {
  const [budget, setBudget] = useState(50);
  const [auditors, setAuditors] = useState(4);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(1);
  // A failed request and an empty plan are different problems. This page reported both as
  // "no plan available - run the pipeline first" and then had no way back, because the
  // only thing that re-runs the fetch is a dial that is not rendered in that branch.
  const [failed, setFailed] = useState("");
  const [attempt, setAttempt] = useState(0);

  // The number under the slider follows the thumb; only the request waits for it to
  // settle. Without this a drag from 5 to 250 days queued a request per step.
  const askedBudget = useDebounced(budget);
  const askedAuditors = useDebounced(auditors);

  useEffect(() => {
    let live = true;
    setBusy(true);
    setFailed("");
    api.auditAssignments(askedBudget, askedAuditors)
      .then((d) => { if (live) { setData(d); setFailed(""); } })
      .catch((err) => {
        console.error(err);
        if (live) setFailed(String(err.message || err));
      })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [askedBudget, askedAuditors, attempt]);

  // The API is commonly still booting when the first page is opened. One automatic retry
  // covers that without the reader having to know it happened.
  useEffect(() => {
    if (!failed || attempt > 0) return undefined;
    const timer = setTimeout(() => setAttempt(1), 1200);
    return () => clearTimeout(timer);
  }, [failed, attempt]);

  if (!data && busy) {
    return (<><Topbar title="Who Goes Where" /><div className="content"><Loading /></div></>);
  }
  if (!data && failed) {
    return (
      <>
        <Topbar title="Who Goes Where" />
        <div className="content">
          <div className="empty">
            <p><b>Could not reach the system.</b> {failed}</p>
            <p className="muted">
              The schedule is worked out on the server. If it is still starting, this fixes
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
        <Topbar title="Who Goes Where" />
        <div className="content">
          <div className="empty">
            <p>{data?.note || "No plan is available yet. The checks need to be run first."}</p>
            <button className="btn" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </div>
        </div>
      </>
    );
  }

  const balance = data.balance;
  const people = data.people || [];

  return (
    <>
      <Topbar
        title="Who Goes Where"
        sub="The visit plan shared out between officers — who visits which office, on which day"
        right={
          <span className="pill">
            {num(data.trips)} office visits · {num(data.works)} works
          </span>
        }
      />

      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconField size={16} /></span>
          <span><strong>A draft schedule, not an order.</strong> A supervisor should change it as needed — the computer does not know who is on leave, which places are near each other, or who already knows an office. It does not blame any work, office or person.</span>
        </div>

        {/* ------------------------------------------------------------- the dials */}
        <div className="card plan-budget">
          <div className="plan-budget-head">
            <div>
              <div className="section-label">Officer-days available</div>
              <div className="plan-budget-value">{budget} days</div>
            </div>
            <div className="plan-budget-presets">
              {[10, 20, 50, 100, 250].map((preset) => (
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

          <div className="plan-budget-head" style={{ marginTop: 18 }}>
            <div>
              <div className="section-label">Officers on the team</div>
              <div className="plan-budget-value">{auditors} officers</div>
            </div>
            <div className="plan-budget-presets">
              {TEAM_PRESETS.map((preset) => (
                <button
                  key={preset}
                  className={"plan-preset" + (preset === auditors ? " active" : "")}
                  onClick={() => setAuditors(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
          <p className="plan-cost-note" title={data.constraint}>
            One rule is never broken: all the works at one office go to the same officer. The plan
            saves time because the second work at an office is quick when someone is already
            there — sending two people would pay for that trip twice.
          </p>
        </div>

        {/* ------------------------------------------------------------ headline */}
        <Reveal>
          <div className="grid cols-4 plan-figures">
            <div className="card stat">
              <div className="label">Busiest officer</div>
              <div className="value accent">{balance.busiest_days}</div>
              <div className="foot">days of work · least busy {balance.quietest_days}</div>
            </div>
            <div className="card stat">
              <div className="label">Difference in workload</div>
              <div className="value">{balance.spread_days}</div>
              <div className="foot">days between the busiest and least busy</div>
            </div>
            <div className="card stat">
              <div className="label">Office visits</div>
              <div className="value">{num(data.trips)}</div>
              <div className="foot">each one handled by just one officer</div>
            </div>
            <div className="card stat">
              <div className="label">Money at risk checked</div>
              <div className="value" style={{ color: sev("LOW").ink }}>
                {rupees(data.exposure_rupees)}
              </div>
              <div className="foot">across {num(data.works)} works</div>
            </div>
          </div>
        </Reveal>

        {/* ------------------------------------------------------------- balance */}
        <Reveal delay={70}>
          <div className="section-title">How fairly the work is shared</div>
          <div className="card">
            <div className="rota-bars">
              {people.map((person) => (
                <div key={person.auditor} className="rota-bar-row">
                  <div className="rota-bar-label">{person.label}</div>
                  <div className="rota-bar-track">
                    <span
                      className="rota-bar-fill"
                      style={{
                        width: `${Math.max(
                          (person.auditor_days / (balance.busiest_days || 1)) * 100, 1.5,
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="rota-bar-value">
                    {person.auditor_days} d
                    <span className="plan-bar-share">{person.works} works</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="plan-cost-note" title={balance.note}>
              The longest trips are handed out first, each to whoever has the least work so far.
              There is no quick way to find the perfect split, but this way is proven never to give
              the busiest officer more than {rotaBound(askedAuditors).toFixed(2)} times what the
              perfect split would. The real difference it reached is shown above.
            </p>
            {data.idle?.length > 0 && (
              <p className="plan-cost-note">
                <b>{data.idle.join(", ")}</b> {data.idle.length === 1 ? "has" : "have"} no
                visits with this many officers. We show that honestly instead of splitting an
                office between two people — a schedule that looks full but takes more days than
                the plan allowed is worse than one with a gap.
              </p>
            )}
          </div>
        </Reveal>

        {/* --------------------------------------------------------- the rounds */}
        <Reveal delay={130}>
          <div className="section-title">Each officer's schedule</div>
          <div className="grid cols-2 rota-grid">
            {people.map((person) => {
              const expanded = open === person.auditor;
              return (
                <div key={person.auditor} className="card rota-card">
                  <button
                    className="rota-card-head"
                    onClick={() => setOpen(expanded ? 0 : person.auditor)}
                    aria-expanded={expanded}
                  >
                    <div>
                      <div className="rota-card-name">{person.label}</div>
                      <div className="rota-card-meta">
                        {num(person.agency_visits)} office visits · {num(person.works)} works ·{" "}
                        {person.auditor_days} days of work spread over {person.calendar_days}{" "}
                        days
                      </div>
                      <div className="rota-card-meta">
                        {person.states.join(", ") || "—"}
                      </div>
                    </div>
                    <div className="rota-card-figure">
                      {rupees(person.exposure_rupees)}
                      <span>{expanded ? "hide" : "show"} the schedule</span>
                    </div>
                  </button>

                  {expanded && (
                    <div className="rota-schedule">
                      {person.schedule.length === 0 && (
                        <div className="empty" style={{ padding: 14 }}>
                          Nothing was given to this officer with this many people on the team.
                        </div>
                      )}
                      {person.schedule.map((visit, index) => (
                        <div key={visit.implementing_agency} className="rota-visit">
                          <div className="rota-visit-head">
                            <span className="rota-day">
                              {visit.day_from === visit.day_to
                                ? `Day ${visit.day_from}`
                                : `Days ${visit.day_from}–${visit.day_to}`}
                            </span>
                            <span className="rota-visit-agency"
                              title={visit.implementing_agency}>
                              {index + 1}. {visit.implementing_agency}
                            </span>
                          </div>
                          <div className="rota-visit-meta">
                            {visit.state} · {visit.work_count} work
                            {visit.work_count === 1 ? "" : "s"} · {visit.cost_days}{" "}
                            days · {rupees(visit.exposure_rupees)}
                          </div>
                          <ul className="rota-works">
                            {visit.works.map((work) => (
                              <li key={work.work_ref}>
                                <Link to={`/case/${work.work_ref}`} className="plan-ref">
                                  {work.work_ref}
                                </Link>
                                <span className="rota-work-band">{work.band}</span>
                                <span className="rota-work-exposure">
                                  {rupees(work.exposure_rupees)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}

                      <a
                        className="btn rota-pack"
                        href={api.dayPackUrl(person.auditor, askedBudget, askedAuditors)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Printable visit sheet (PDF)
                      </a>
                      <p className="plan-cost-note">
                        The schedule on paper to carry along, with a box to tick for every
                        work and the time estimates printed on it — so an officer who finds
                        the estimates wrong on the ground can say so.
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Reveal>
      </div>
    </>
  );
}
