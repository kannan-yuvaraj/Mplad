import { Fragment, useEffect, useMemo, useState } from "react";
import { Hitl, Topbar } from "../components/Bits.jsx";
import { api, num, rupees } from "../api.js";

/**
 * Vendor concentration — who actually gets paid, and how narrowly.
 *
 * The vendor on each disbursement exists only on the live portal feed, never in
 * the CSV snapshot the rest of the site is built on, so this page answers a
 * question the system could not answer at all until the feed was built: *is one
 * district paying the same few firms for everything?*
 *
 * **Three things this screen must keep saying out loud.**
 *
 * 1. Concentration is not wrongdoing. A rural district may have four firms able
 *    to build a school. Reading a high index as a finding would accuse every
 *    remote district in India of something.
 * 2. No index under the payment floor. Three payments to one vendor is an index
 *    of 1.0 and means nothing; those authorities show counts and no index.
 * 3. Coverage is whatever the feed has synced — five states at the time of
 *    writing, not the nation. The banner says so rather than letting the table
 *    imply a national picture.
 */

const BANDS = {
  CONCENTRATED: { glyph: "▲", label: "Concentrated", cls: "hot" },
  MODERATE: { glyph: "◆", label: "Moderate", cls: "mid" },
  SPREAD: { glyph: "●", label: "Spread", cls: "ok" },
};

export default function Vendors() {
  const [data, setData] = useState(null);
  const [band, setBand] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.vendors(200)
      .then((d) => {
        if (!d?.available) throw new Error(d?.reason || "the live feed is not running here");
        setData(d);
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.authorities.filter((a) =>
      (!band || a.band === band) &&
      (!needle || a.authority.toLowerCase().includes(needle)
        || (a.top_vendor || "").toLowerCase().includes(needle)));
  }, [data, band, q]);

  const dist = data?.distribution;

  return (
    <div className="page">
      <Topbar
        title="Who gets paid"
        sub="How narrowly each district office spreads its money across vendors"
        right={data && (
          <span className="badge">
            {num(data.coverage.authorities_with_an_index)} offices measured
          </span>
        )}
      />

      {error && (
        <div className="card">
          <p className="error">{error}</p>
          <p className="muted sm">
            This page reads the live portal feed. Start it with{" "}
            <code>python -m ingestion.cli live-sync</code> and reload.
          </p>
        </div>
      )}

      {!data && !error && <p className="muted">Working…</p>}

      {data && (
        <>
          <div className="card coverage-note">
            <b>What this covers.</b> {num(data.coverage.payment_rows_read)} vendor payments
            across {data.coverage.states_covered.length} state
            {data.coverage.states_covered.length === 1 ? "" : "s"} —{" "}
            {data.coverage.states_covered.join(", ")} — because that is how far the live
            feed has synced. It is not a national picture and should not be read as one.
            {data.source === "snapshot" && (
              <>
                {" "}<b>This is a saved copy, not the live feed</b>
                {data.snapshot_taken_at
                  ? `, taken ${data.snapshot_taken_at.slice(0, 10)}` : ""}
                {" "}— the live feed runs on the machine that syncs the portal, not on
                this server.
              </>
            )}
            {" "}{num(data.coverage.authorities_below_floor)} offices had fewer than{" "}
            {data.coverage.min_payments_for_an_index} payments, so they are listed with
            their counts and <b>no index</b>.
          </div>

          {dist && dist.count > 0 && (
            <div className="grid four stat-row">
              <Stat label="Offices measured" value={num(dist.count)} />
              <Stat label="Typical office" value={dist.median.toFixed(3)}
                    sub="middle of the range" />
              <Stat label="Top tenth starts at" value={dist.p90.toFixed(3)}
                    sub="9 in 10 sit below this" />
              <Stat label="Most concentrated" value={dist.max.toFixed(3)}
                    sub="highest measured" />
            </div>
          )}

          <div className="card">
            <div className="ranked-head">
              <h2>Every office, most concentrated first</h2>
              <div className="metric-row">
                {["", "CONCENTRATED", "MODERATE", "SPREAD"].map((b) => (
                  <button key={b || "all"} type="button"
                          className={"btn ghost sm" + (band === b ? " on" : "")}
                          onClick={() => setBand(b)}>
                    {b ? BANDS[b].label : "All"}
                    {b && data.distribution?.bands?.[b] != null
                      ? ` (${data.distribution.bands[b]})` : ""}
                  </button>
                ))}
              </div>
              <input className="ranked-search" type="search" value={q}
                     onChange={(e) => setQ(e.target.value)}
                     placeholder="Find an office or vendor…" aria-label="Find an office or vendor" />
            </div>

            <div className="tablewrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>District office</th><th>State</th>
                    <th className="n">Payments</th><th className="n">Vendors</th>
                    <th className="n">Index</th><th className="n">In effect</th>
                    <th className="n">Biggest share</th>
                    <th>Biggest vendor</th><th className="n">Money</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => {
                    const meta = a.band ? BANDS[a.band] : null;
                    const isOpen = open === a.authority;
                    return (
                      <Fragment key={a.authority}>
                        <tr
                            className={isOpen ? "on" : ""}
                            onClick={() => setOpen(isOpen ? null : a.authority)}
                            style={{ cursor: "pointer" }}>
                          <td>
                            {meta && <span className={"vband " + meta.cls}>{meta.glyph}</span>}
                            <b>{a.authority}</b>
                          </td>
                          <td className="muted">{a.state || "—"}</td>
                          <td className="n">{num(a.payments)}</td>
                          <td className="n">{num(a.vendors)}</td>
                          <td className="n">
                            {a.index_withheld
                              ? <span className="muted sm">too few payments</span>
                              : a.hhi.toFixed(3)}
                          </td>
                          <td className="n">
                            {a.effective_vendors == null ? "—" : `${a.effective_vendors} vendors`}
                          </td>
                          <td className="n">
                            {a.top_vendor_share == null ? "—"
                              : `${(a.top_vendor_share * 100).toFixed(0)}%`}
                          </td>
                          <td className="muted">{a.top_vendor || "—"}</td>
                          <td className="n">{rupees(a.total_disbursed)}</td>
                        </tr>
                        {isOpen && (
                          <tr className="detail-row">
                            <td colSpan={9}>
                              {a.index_withheld ? (
                                <p className="muted sm">{a.withheld_reason}.</p>
                              ) : (
                                <>
                                  <p className="sm">
                                    An index of <b>{a.hhi.toFixed(3)}</b> is the same as the
                                    money being split evenly between about{" "}
                                    <b>{a.effective_vendors} vendors</b>, against{" "}
                                    {num(a.vendors)} who were actually paid. That places this
                                    office above{" "}
                                    <b>{Math.round((a.percentile_among_comparable || 0) * 100)}%</b>{" "}
                                    of the offices measured here.
                                  </p>
                                  <table className="grid inner">
                                    <thead>
                                      <tr><th>Vendor</th><th className="n">Share</th>
                                        <th className="n">Paid</th></tr>
                                    </thead>
                                    <tbody>
                                      {(a.top_vendors || []).map((v) => (
                                        <tr key={v.vendor_id}>
                                          <td>{v.vendor_name}</td>
                                          <td className="n">
                                            {v.share == null ? "—" : `${(v.share * 100).toFixed(1)}%`}
                                          </td>
                                          <td className="n">{rupees(v.disbursed)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  <p className="muted sm">
                                    A question for the District Authority, not a finding. A
                                    district with few firms able to do the work will
                                    concentrate for reasons that have nothing to do with
                                    wrongdoing.
                                  </p>
                                </>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!rows.length && <p className="muted">Nothing matches that filter.</p>}
          </div>

          <div className="card">
            <h2>How the index works</h2>
            <p>
              It is the <b>Herfindahl-Hirschman Index</b>, the measure competition
              regulators use. Square each vendor's share of an office's money and add them
              up. One vendor taking everything gives 1.0; a hundred equal vendors give
              0.01. It is used here instead of simply counting vendors because an office
              with fifty vendors where one takes 90% of the money is concentrated, and a
              count would call it diverse.
            </p>
            <p className="muted sm">{data.benchmark_note}</p>
          </div>

          <Hitl text={data.contract} />
        </>
      )}
    </div>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}
