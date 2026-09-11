import { useEffect, useState } from "react";
import { api, num } from "../api.js";
import { Band, Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { IconTarget } from "../components/icons.jsx";
import { BAND_LABEL } from "../plain.js";

/** The engine's verdict on the ranking, in plain words. Same three outcomes, same logic. */
function plainOrdering(o) {
  if (!o || !o.testable) {
    return "We need enough visits in at least two groups before we can check whether the \"HIGH\" works really turned out worse than the \"MEDIUM\" ones. Until then we make no claim.";
  }
  if (o.holds && o.separated) {
    return "So far, the works the computer called HIGH really did turn out worse than the ones it called MEDIUM, and the gap is big enough to trust. The order is working.";
  }
  if (o.holds) {
    return "So far the order looks right, but the likely ranges overlap — so it could be working or it could be luck. More visits will tell.";
  }
  return "So far, the works the computer called HIGH did NOT turn out worse than the lower groups. That is a problem with the system, and we show it instead of hiding it.";
}

/**
 * Has the model been right? The one screen this system is allowed to lose on.
 *
 * Everything else explains why a work was surfaced. This asks the only question that ever
 * settles it: when an officer actually went, what did they find — and did the works we
 * called HIGH turn out worse than the ones we called MEDIUM?
 *
 * Three things this page refuses to do, each of which costs it a number it would look
 * better with. It will not print a percentage off a handful of visits. It will not let a
 * bar chart imply a ranking that the intervals do not support. And it will not report
 * precision without saying that officers go where this model sends them, so the sample was
 * chosen by the thing being measured.
 */

function Bar({ row, widest }) {
  const width = row.reportable ? (row.rate / (widest || 1)) * 100 : 0;
  return (
    <div className="rota-bar-row">
      <div className="rota-bar-label"><Band value={row.band} label={BAND_LABEL[row.band]} /></div>
      <div className="rota-bar-track">
        {row.reportable ? (
          <>
            <span className="rota-bar-fill" style={{ width: `${Math.max(width, 1.5)}%` }} />
            {/* The interval, drawn over the bar. A point estimate on its own is the thing
                this page exists to avoid showing. */}
            <span
              className="score-interval"
              style={{
                left: `${(row.interval[0] / (widest || 1)) * 100}%`,
                width: `${((row.interval[1] - row.interval[0]) / (widest || 1)) * 100}%`,
              }}
            />
          </>
        ) : (
          <span className="score-nodata">not enough visits yet</span>
        )}
      </div>
      <div className="rota-bar-value">
        {row.reportable ? `${Math.round(row.rate * 100)}%` : "—"}
        <span className="plan-bar-share">
          {num(row.concerns_confirmed)} of {num(row.visits)}
        </span>
      </div>
    </div>
  );
}

export default function Scoreboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.calibration()
      .then(setData)
      .catch(() => setError("The site visit records could not be loaded."));
  }, []);

  if (error) {
    return (<><Topbar title="Was It Right?" /><div className="content">
      <div className="empty">{error}</div></div></>);
  }
  if (!data) {
    return (<><Topbar title="Was It Right?" /><div className="content"><Loading /></div></>);
  }

  const widest = Math.max(
    ...data.bands.filter((r) => r.reportable).map((r) => r.interval[1]), 0.1,
  );
  const readiness = data.label_readiness || {};

  return (
    <>
      <Topbar
        title="Was It Right?"
        sub="When officers really went to the works the computer flagged, what did they find?"
        right={<span className="pill">{num(data.visits)} site visits</span>}
      />

      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconTarget size={16} /></span>
          <span>
            <strong>The page that can prove us wrong.</strong> These results come only from real site visits. The scoring is not changed from them yet — that waits until there are enough visits to do it fairly — and we claim no accuracy before then.
          </span>
        </div>

        <Reveal>
          <div className="section-title">
            How often a visit found a real problem, for each clue-strength group
          </div>
          <div className="card">
            <div className="rota-bars">
              {data.bands.map((row) => (
                <Bar key={row.band} row={row} widest={widest} />
              ))}
            </div>

            <div className="plan-notes">
              {data.bands.map((row) => (
                <div key={row.band} className="plan-note">
                  <b>{BAND_LABEL[row.band] || row.band}</b>{" "}
                  {row.reportable
                    ? `${num(row.concerns_confirmed)} of ${num(row.visits)} visits found `
                      + `something wrong; ${num(row.cleared)} found the work was fine. The true `
                      + `figure is probably between ${Math.round(row.interval[0] * 100)}% and `
                      + `${Math.round(row.interval[1] * 100)}%.`
                    : `${num(row.visits)} visit${row.visits === 1 ? "" : "s"} so far. We only show a percentage after ${data.min_visits_for_a_rate} visits — until then the count is the honest number.`}
                </div>
              ))}
            </div>

            <p className="plan-cost-note">
              We do not show a percentage until there are {data.min_visits_for_a_rate} visits. Two
              problems found in three visits is just three visits — calling it "67%" would be
              misleading. A group with too few visits gets an empty bar, not a short one, because
              a short bar would look like a low score.
            </p>
          </div>
        </Reveal>

        <Reveal delay={80}>
          <div className="section-title">Did the most urgent works really turn out worse?</div>
          <div className="card dossier-reading" title={data.ordering.note}>{plainOrdering(data.ordering)}</div>
        </Reveal>

        <Reveal delay={140}>
          <div className="section-title">Why these visits are not a fair test of every work</div>
          <div className="card">
            <p style={{ margin: 0 }} title={data.sampling_caveat}>
              Officers mostly visit the works the computer tells them to, so these visits are not
              picked at random. Works the computer never flagged are hardly ever visited — which is
              why even a work with a clean record still has a case file and can still be visited.
              Until more of those are visited, this table shows how the flagged works turned out,
              not how well the computer sorts every work.
            </p>
          </div>
        </Reveal>

        <Reveal delay={200}>
          <div className="section-title">What officers recorded</div>
          <div className="grid cols-4 plan-figures">
            <div className="card stat">
              <div className="label">Works visited</div>
              <div className="value accent">{num(data.works_visited)}</div>
              <div className="foot">only the newest report for each work counts</div>
            </div>
            <div className="card stat">
              <div className="label">Older reports replaced</div>
              <div className="value">{num(data.superseded_records_excluded)}</div>
              <div className="foot">a correction is saved as a new report; each work counts once</div>
            </div>
            <div className="card stat">
              <div className="label">Demo samples left out</div>
              <div className="value">{num(data.demo_records_excluded)}</div>
              <div className="foot">made for the demo, never counted</div>
            </div>
            <div className="card stat">
              <div className="label">Visits still needed</div>
              <div className="value">
                {num(readiness.labels_needed_to_fit_weights ?? 0)}
              </div>
              <div className="foot">before the scoring can be tuned from results</div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <div className="dossier-chips">
              {data.outcomes.map((row) => (
                <span key={row.outcome} className="chip">
                  {row.outcome.replaceAll("_", " ").toLowerCase()} <b>{num(row.count)}</b>
                </span>
              ))}
            </div>
            <p className="plan-cost-note" title={readiness.note}>
              What officers find on real visits is the only real proof this system can ever get.
              Once there are {num((readiness.verifications ?? 0) + (readiness.labels_needed_to_fit_weights ?? 0))} or
              more reports, the scoring could be tuned to match what officers actually found. There
              are {num(readiness.verifications ?? 0)} now, so nothing is changed and no accuracy is claimed yet.
            </p>
          </div>
        </Reveal>
      </div>
    </>
  );
}
