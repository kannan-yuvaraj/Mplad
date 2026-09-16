import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Hitl, Topbar } from "../components/Bits.jsx";
import { api, num } from "../api.js";

/**
 * The evidence ledger — every field record, and what each has actually been
 * through.
 *
 * **The five steps are derived, never declared.** A workflow where someone
 * clicks "certified" records that a button was pressed. Each step here names a
 * fact already in the record: whether a person is attributed to it, whether a
 * camera read the photograph, whether two independent readers returned the same
 * reference, whether its hash sits in the append-only chain. None of them can be
 * set by hand, which is the only reason it is worth printing them beside a hash
 * chain at all.
 *
 * **The chain result is reported precisely.** A fork — two writers appending
 * from the same tip — is an implementation bug and reads completely differently
 * from an altered row, which is tampering. The page separates them rather than
 * showing one red light for both, because calling our own race "tampering
 * detected" would be a false accusation against the log.
 */

const STEP_GLYPH = { true: "✓", false: "·" };

export default function EvidenceLedger() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showDemo, setShowDemo] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.evidenceLedger(400)
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.records.filter((r) =>
      (showDemo || !r.demo) &&
      (!needle || (r.work_ref || "").toLowerCase().includes(needle)
        || (r.actor || "").toLowerCase().includes(needle)
        || (r.outcome || "").toLowerCase().includes(needle)));
  }, [data, q, showDemo]);

  const chain = data?.chain;
  const clean = chain?.contents_verified;

  return (
    <div className="page">
      <Topbar
        title="Evidence trail"
        sub="Every site record, what it has been through, and whether the log can be trusted"
        right={data && <span className="badge">{num(data.count)} records</span>}
      />

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Working…</p>}

      {data && (
        <>
          {/* The chain verdict, stated precisely rather than as one light. */}
          <div className={"card chain-card " + (clean ? "ok" : "warn")}>
            <div className="chain-head">
              <span className={"chain-glyph " + (clean ? "ok" : "warn")}>
                {clean ? "✓" : "▲"}
              </span>
              <div>
                <h2>
                  {clean
                    ? "No record has been altered"
                    : "Records have been altered — investigate"}
                </h2>
                <p className="muted sm">
                  {num(chain.entries)} entries checked, each hash recomputed from its own
                  contents.
                </p>
              </div>
            </div>
            <p className="chain-verdict">{chain.verdict}</p>
            <dl className="chain-facts">
              <div><dt>Rows altered</dt>
                <dd className={chain.rows_altered_count ? "bad" : "good"}>
                  {chain.rows_altered_count}</dd></div>
              <div><dt>Links out of order</dt>
                <dd>{chain.link_breaks_count}</dd></div>
              <div><dt>Forks</dt><dd>{chain.forks_count}</dd></div>
              <div><dt>Entries</dt><dd>{num(chain.entries)}</dd></div>
            </dl>
            <p className="muted sm">{data.immutability}</p>
          </div>

          {/* What the five steps mean, before the table that uses them. */}
          <div className="card">
            <h2>What each record has been through</h2>
            <div className="steps-legend">
              {data.steps.map((s) => (
                <div key={s.key} className="step-def">
                  <b>{s.label}</b>
                  <span>{s.meaning}</span>
                  <em>{num(data.tally[s.key] || 0)} of {num(data.count)}</em>
                </div>
              ))}
            </div>
            <p className="muted sm">{data.note}</p>
          </div>

          <div className="card">
            <div className="ranked-head">
              <h2>The records</h2>
              <label className="inline-check">
                <input type="checkbox" checked={showDemo}
                       onChange={(e) => setShowDemo(e.target.checked)} />
                Include records seeded for the walkthrough
              </label>
              <input className="ranked-search" type="search" value={q}
                     onChange={(e) => setQ(e.target.value)}
                     placeholder="Find a work or officer…" aria-label="Find a work or officer" />
            </div>

            <div className="tablewrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Work</th><th>What the officer found</th><th>Recorded by</th>
                    <th>When</th>
                    {data.steps.map((s) => <th key={s.key} className="n step-col">{s.label}</th>)}
                    <th>Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <Link to={`/case/${r.work_ref}`} className="link">{r.work_ref}</Link>
                        {r.demo && <span className="pill demo">walkthrough</span>}
                      </td>
                      <td>{r.outcome || "—"}
                        {r.needed_confirmation
                          ? <span className="pill open">identity needed a human</span> : null}
                        {r.photo_reuse_count
                          ? <span className="pill open">photo seen before</span> : null}
                      </td>
                      <td>{r.actor}<span className="muted sm"> · {r.role || "—"}</span></td>
                      <td className="muted sm">{(r.recorded_at || "").slice(0, 16).replace("T", " ")}</td>
                      {data.steps.map((s) => (
                        <td key={s.key} className="n step-col"
                            title={`${s.label}: ${r.steps[s.key] ? "yes" : "no"}`}>
                          <span className={r.steps[s.key] ? "step yes" : "step no"}>
                            {STEP_GLYPH[String(Boolean(r.steps[s.key]))]}
                          </span>
                        </td>
                      ))}
                      <td className="mono sm muted">{r.row_hash || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!rows.length && <p className="muted">No record matches that filter.</p>}
          </div>

          {data.readiness && (
            <div className="card">
              <h2>How far the ground truth has come</h2>
              <p>
                Site visits are the only thing that can say what really happened. There are{" "}
                <b>{num(data.readiness.usable ?? data.readiness.count ?? 0)}</b> of them so
                far, against the <b>{num(data.readiness.target ?? 500)}</b> this system
                would need before it could fairly re-weight itself from them.
              </p>
              <p className="muted sm">
                Records seeded for the walkthrough are excluded from that count — a
                demonstration cannot be allowed to make the evidence base look further
                along than it is.
              </p>
              <Link to="/scoreboard" className="link">See whether the model has been right</Link>
            </div>
          )}

          <Hitl text="A record is what an officer wrote and what the camera saw, kept apart on purpose. Where the two disagree, that disagreement is the most useful thing in the file." />
        </>
      )}
    </div>
  );
}
