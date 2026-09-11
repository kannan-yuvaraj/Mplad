import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { OUTCOME, plainGuidance } from "../plain.js";

/**
 * Where this work has got to as a piece of casework.
 *
 * The intelligence screens answer *why was this surfaced*. This answers *and what has
 * anyone done about it*, which is the question a reviewer opening the file six weeks later
 * actually has — and until now the two halves of the product could not see each other.
 *
 * A work that is not a case says so plainly rather than rendering an empty strip. "Nobody
 * has picked this up" is a real state and worth reading.
 */
export default function CaseworkStrip({ workRef }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let live = true;
    api.casework(workRef)
      .then((d) => { if (live) setData(d); })
      .catch(() => {});
    return () => { live = false; };
  }, [workRef]);

  if (!data) return null;

  if (!data.in_salesforce) {
    return (
      <div className="casework casework-absent">
        <span className="casework-dot" aria-hidden="true">○</span>
        <span>
          <strong>Not a Salesforce case yet.</strong> <span title={data.note}>Only the 500 works most worth checking are put into Salesforce for people to track; the rest stay on the list until an officer picks one up.</span>
          {data.verifications > 0 && (
            <> Even so, {data.verifications} site visit report{data.verifications === 1 ? "" : "s"} already exist{data.verifications === 1 ? "s" : ""} for it.</>
          )}
        </span>
      </div>
    );
  }

  const { stages, stage_index: at } = data;

  return (
    <div className="casework">
      <div className="casework-head">
        <div>
          <div className="section-label">Case tracking in Salesforce</div>
          <div className="casework-stage">{data.stage}</div>
        </div>
        <div className="casework-meta">
          <span className="casework-chip">{data.escalation_tier}</span>
          <span className="casework-due">review by {data.target_review_date}</span>
        </div>
      </div>

      {/* The Path, mirrored from Salesforce so an officer sees the same shape in both. */}
      <ol className="casework-path" aria-label="Case step">
        {stages.map((stage, i) => (
          <li
            key={stage}
            className={
              "casework-step"
              + (i < at ? " done" : "")
              + (i === at ? " current" : "")
            }
            style={{ "--i": i }}
          >
            <span className="casework-step-mark" aria-hidden="true">
              {i < at ? "✓" : i + 1}
            </span>
            <span className="casework-step-name">{stage}</span>
          </li>
        ))}
      </ol>

      <p className="casework-guidance" title={data.guidance}>{plainGuidance(data.stage, data.guidance)}</p>

      {data.findings?.length > 0 && (
        <div className="casework-findings">
          <div className="section-label">What officers found</div>
          {data.findings.map((f, i) => (
            <div key={i} className="casework-finding">
              <span className="casework-outcome" title={f.outcome}>{OUTCOME[f.outcome]?.[0] || f.outcome.replace(/_/g, " ")}</span>
              {f.notes && <span className="casework-notes">{f.notes}</span>}
              <span className="casework-by">{f.actor} · {f.when}</span>
            </div>
          ))}
          <p className="casework-label-note">
            Each of these teaches the system something. No record says which works really had
            problems, so reports like these are the only real proof it can ever get — and
            "nothing wrong" counts just as much as a confirmed problem.
          </p>
        </div>
      )}

      <Link to="/salesforce" className="casework-open">Open Case Tracking →</Link>
    </div>
  );
}
