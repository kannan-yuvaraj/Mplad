import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Topbar } from "../components/Bits.jsx";
import { api, num, rupees } from "../api.js";

/**
 * The public page: what was funded near you.
 *
 * **What it deliberately does not show.** No risk band, no lead, no priority,
 * no "money at risk". Those are working notes an official uses to decide where
 * to send an inspector. Published against a named Member of Parliament they
 * would read as an accusation the data cannot support — there are no fraud
 * labels anywhere in MPLADS, and a band is a prompt to go and look, not a
 * finding. The API that feeds this page does not return those fields at all,
 * so the omission cannot be undone by a careless change here.
 *
 * What it does show is the record: what was recommended, for how much, by
 * which office, and whether the record says it finished.
 */
export default function PublicView() {
  const [search, setSearch] = useSearchParams();
  const [index, setIndex] = useState(null);
  const [state, setStateFilter] = useState(() => search.get("state") || "");
  const [picked, setPicked] = useState(() => search.get("in") || "");
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    api.publicConstituencies().then(setIndex)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!picked) { setDetail(null); return undefined; }
    let alive = true;
    setBusy(true);
    api.publicConstituency(picked)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setDetail({ found: false, reason: String(e.message || e) }))
      .finally(() => alive && setBusy(false));
    return () => { alive = false; };
  }, [picked]);

  useEffect(() => {
    const next = {};
    if (state) next.state = state;
    if (picked) next.in = picked;
    setSearch(next, { replace: true });
  }, [state, picked, setSearch]);

  const rows = useMemo(() => {
    if (!index) return [];
    const needle = q.trim().toLowerCase();
    return index.constituencies.filter((c) =>
      (!state || c.state === state) &&
      (!needle || c.constituency.toLowerCase().includes(needle)
        || c.state.toLowerCase().includes(needle)));
  }, [index, state, q]);

  return (
    <div className="page">
      <Topbar
        title="Look up my area"
        sub="What was funded where you live, straight from the public record"
        right={index && <span className="badge">{num(index.total_works)} works</span>}
      />

      {error && <p className="error">{error}</p>}

      <div className="card public-intro">
        <p>
          Every Member of Parliament can recommend works in their constituency. This page
          shows what was recommended, what it cost and whether the record says it was
          finished. <b>It shows no risk scores and makes no judgement about anyone.</b>
        </p>
      </div>

      {!index && !error && <p className="muted">Working…</p>}

      {index && (
        <div className="public-layout">
          <aside className="public-picker">
            <label className="field">
              <span>State or union territory</span>
              <select value={state} onChange={(e) => { setStateFilter(e.target.value); setPicked(""); }}>
                <option value="">All states</option>
                {index.states.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Search</span>
              <input value={q} onChange={(e) => setQ(e.target.value)}
                     placeholder="Constituency name…" type="search" />
            </label>

            <p className="muted sm">{rows.length} constituencies</p>
            <ul className="const-list">
              {rows.slice(0, 260).map((c) => (
                <li key={`${c.state}/${c.constituency}`}>
                  <button
                    type="button"
                    className={"const-btn" + (picked === c.constituency ? " on" : "")}
                    onClick={() => setPicked(c.constituency)}
                  >
                    <b>{c.constituency}</b>
                    <span>{c.state}</span>
                    <em>{num(c.works)} works</em>
                  </button>
                </li>
              ))}
            </ul>
            {rows.length > 260 && (
              <p className="muted sm">Showing the first 260 — narrow it with the search box.</p>
            )}
          </aside>

          <section className="public-detail">
            {!picked && (
              <div className="card empty-state">
                <h2>Pick a constituency</h2>
                <p className="muted">
                  Choose one on the left to see the works recommended there — what each one
                  was for, which office is carrying it out, and what the record says about
                  whether it finished.
                </p>
              </div>
            )}

            {busy && <p className="muted">Working…</p>}

            {detail && !detail.found && !busy && (
              <div className="card"><p className="muted">{detail.reason}</p></div>
            )}

            {detail?.found && !busy && (
              <>
                <div className="card">
                  <div className="pd-head">
                    <div>
                      <h2>{detail.constituency}</h2>
                      <p className="muted sm">
                        {detail.state}
                        {detail.mp_name ? ` · Member of Parliament: ${detail.mp_name}` : ""}
                      </p>
                    </div>
                  </div>
                  <dl className="pd-facts">
                    <div><dt>Works recommended</dt><dd>{num(detail.totals.works)}</dd></div>
                    <div><dt>Recorded finished</dt><dd>{num(detail.totals.completed)}</dd></div>
                    <div><dt>Not finished yet</dt><dd>{num(detail.totals.open)}</dd></div>
                    <div><dt>Amount recommended</dt><dd>{rupees(detail.totals.recommended)}</dd></div>
                    <div><dt>Offices involved</dt><dd>{detail.totals.agencies}</dd></div>
                  </dl>
                </div>

                <div className="card">
                  <div className="ranked-head">
                    <h2>The works</h2>
                    <span className="muted sm">
                      Showing {num(detail.showing)} of {num(detail.totals.works)}, newest first
                    </span>
                  </div>
                  <div className="tablewrap">
                    <table className="grid">
                      <thead>
                        <tr>
                          <th>What it is for</th><th>Kind</th><th>Office carrying it out</th>
                          <th className="n">Amount</th><th className="n">Recommended</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.works.map((w) => (
                          <tr key={w.work_ref}>
                            <td>{w.description || <span className="muted">not described</span>}</td>
                            <td className="muted">{w.category || "—"}</td>
                            <td className="muted">{w.agency || "—"}</td>
                            <td className="n">
                              {w.recommended_amount == null ? "—" : rupees(w.recommended_amount)}
                            </td>
                            <td className="n">{w.recommended_on || "—"}</td>
                            <td>
                              <span className={"pill " + (w.status === "Finished" ? "done" : "open")}>
                                {w.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted sm">{detail.note}</p>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
