import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, num, rupees } from "../api.js";
import { Band, Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { IconAgency } from "../components/icons.jsx";
import { clueName } from "../plain.js";

/**
 * The engine's comparison sentence, said plainly. The engine decides which of its four
 * readings applies (too few works / well above / well below / ordinary); this keeps that
 * decision and only changes the words. The engine's sentence stays as the tooltip.
 */
function plainReading(s, works) {
  const r = s.reading || "";
  const pct = (v) => `${(v * 100).toFixed(1)}%`;
  const per100 = (v) => Math.round(v * 100);
  if (!s.comparable || r.includes("too few")) {
    return `${num(works)} works are too few to compare fairly. The works listed below are still worth reading, but the share is not.`;
  }
  const base = `The computer flagged ${pct(s.rate)} of this agency's works (about ${per100(s.rate)} in every 100). Across India it flags ${pct(s.national_rate)}.`;
  if (r.includes("times the national rate")) {
    return `${base} That is about ${s.rate_multiple} times more often than usual — a reason to look more closely, not proof of anything.`;
  }
  if (r.includes("below the ordinary rate")) {
    return `${base} That is less often than usual.`;
  }
  return `${base} That is normal. This agency is listed because it is big and because of the works below, not because it stands out.`;
}

/**
 * The page an auditor reads on the way to a visit.
 *
 * Every other screen here is organised around a work. An auditor's day is not — they
 * travel to an implementing agency and see whatever that body is building, which is
 * exactly why the plan batches by agency and the rota is dealt out in whole agencies.
 *
 * The care this page needs is in the comparison. A district office with four thousand
 * works surfaces more leads than one with forty, and reading the raw count as a signal is
 * how a large agency gets investigated for being large. So every figure that could be read
 * as an accusation is shown beside the national rate for the same measure, and where the
 * agency is ordinary the page says so in words rather than leaving a bar to imply
 * otherwise.
 */

function Rate({ label, value, national, format = (v) => `${(v * 100).toFixed(1)}%` }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value == null ? "—" : format(value)}</div>
      <div className="foot">
        {national == null ? "—" : `${format(national)} across India`}
      </div>
    </div>
  );
}

export default function AgencyDossier() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [list, setList] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.agencies(60).then((d) => setList(d.items)).catch(console.error);
  }, []);

  useEffect(() => {
    if (!name) { setData(null); return; }
    let live = true;
    setData(null);
    setError("");
    api.agency(name)
      .then((d) => { if (live) setData(d); })
      .catch(() => { if (live) setError("There is no agency with this name in the records."); });
    return () => { live = false; };
  }, [name]);

  const filtered = useMemo(() => {
    if (!list) return [];
    const needle = filter.trim().toLowerCase();
    return needle
      ? list.filter((row) =>
          row.implementing_agency.toLowerCase().includes(needle)
          || (row.state || "").toLowerCase().includes(needle))
      : list;
  }, [list, filter]);

  /* ------------------------------------------------------------------ the picker */
  if (!name) {
    return (
      <>
        <Topbar title="Agency Profile" sub="The offices that build the works, and what we know about each one" />
        <div className="content">
          <div className="hitl">
            <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconAgency size={16} /></span>
            <span>
              <strong>Information about an office, not an accusation.</strong> Agencies are
              listed by how much money at risk they hold — and big agencies naturally hold
              more. Open one to see what share of its works were flagged; that fair
              comparison is the one worth acting on.
            </span>
          </div>

          <div className="card">
            <input
              className="input"
              placeholder="Search by agency or state…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Search agencies"
            />
          </div>

          {!list ? <Loading /> : (
            <div className="card">
              <div className="table-wrap">
                <table className="plan-table">
                  <thead>
                    <tr>
                      <th>Agency</th><th>State</th>
                      <th style={{ textAlign: "right" }}>Works</th>
                      <th style={{ textAlign: "right" }}>Money at risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => (
                      <tr
                        key={row.implementing_agency}
                        className="row-click"
                        onClick={() =>
                          navigate(`/agency/${encodeURIComponent(row.implementing_agency)}`)}
                      >
                        <td className="plan-agency">{row.implementing_agency}</td>
                        <td>{row.state}</td>
                        <td style={{ textAlign: "right" }}>{num(row.works)}</td>
                        <td style={{ textAlign: "right" }}>{rupees(row.exposure_rupees)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </>
    );
  }

  /* ------------------------------------------------------------------ one dossier */
  if (error) {
    return (
      <>
        <Topbar title="Agency Profile" />
        <div className="content">
          <div className="empty">
            {error} <Link to="/agency" className="link">Back to the list</Link>
          </div>
        </div>
      </>
    );
  }
  if (!data) {
    return (<><Topbar title="Agency Profile" /><div className="content"><Loading /></div></>);
  }
  if (!data.available) {
    return (
      <>
        <Topbar title="Agency Profile" />
        <div className="content"><div className="empty">{data.note}</div></div>
      </>
    );
  }

  const p = data.portfolio;
  const s = data.surfaced;

  return (
    <>
      <Topbar
        title={data.implementing_agency}
        sub={`${data.states.join(", ")} · ${num(p.works)} works`}
        right={<Link to="/agency" className="pill">All agencies</Link>}
      />

      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconAgency size={16} /></span>
          <span title={data.contract}><strong>Information, not an accusation.</strong> Nothing here says this agency or anyone in it did wrong. The works below are only worth checking, and a person decides what to do about them.</span>
        </div>

        {/* ------------------------------------------------------ the comparison */}
        <Reveal>
          <div className="section-title">How this agency compares</div>
          <div className="card dossier-reading" title={s.reading}>{plainReading(s, p.works)}</div>
          <div className="grid cols-4 plan-figures" style={{ marginTop: 12 }}>
            <Rate label="Works flagged" value={s.rate} national={s.national_rate} />
            <Rate label="Not finished yet" value={p.open_rate} national={p.national_open_rate} />
            <div className="card stat">
              <div className="label">Money at risk in flagged works</div>
              <div className="value accent">{rupees(s.exposure_rupees)}</div>
              <div className="foot">{num(s.high)} HIGH · {num(s.medium)} MEDIUM</div>
            </div>
            <div className="card stat">
              <div className="label">Typical work costs</div>
              <div className="value">{rupees(p.median_work_rupees)}</div>
              <div className="foot">
                {rupees(p.national_median_work_rupees)} across India
              </div>
            </div>
          </div>
        </Reveal>

        {/* -------------------------------------------------- what officers found */}
        <Reveal delay={70}>
          <div className="section-title">What officers found here</div>
          <div className="card">
            <p className="plan-cost-note" style={{ marginTop: 0 }} title={data.field_history_note}>
              {data.field_history.length > 0
                ? "What officers wrote down when they visited, including visits where nothing was wrong. These count for more than anything the computer says — a real visit is the only proof there is."
                : "No officer has written up a visit to this agency yet. The first one to do so gives the first real proof about it."}
            </p>
            {data.field_history.length > 0 && (
              <div className="table-wrap">
                <table className="plan-table">
                  <thead>
                    <tr><th>Work</th><th>What they found</th><th>Officer</th><th>When</th><th>Note</th></tr>
                  </thead>
                  <tbody>
                    {data.field_history.map((row, i) => (
                      <tr key={`${row.work_ref}-${i}`}>
                        <td>
                          <Link to={`/case/${row.work_ref}`} className="plan-ref">
                            {row.work_ref}
                          </Link>
                        </td>
                        <td>{row.outcome.replaceAll("_", " ").toLowerCase()}</td>
                        <td>
                          {row.actor}
                          {row.demo && <span className="chip" style={{ marginLeft: 6 }} title="A sample record made for the demo, not a real visit">demo sample</span>}
                        </td>
                        <td>{row.when}</td>
                        <td className="plan-agency">{row.notes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Reveal>

        {/* ------------------------------------------------------------ the leads */}
        <Reveal delay={130}>
          <div className="section-title">
            Works worth checking while you are there
          </div>
          <div className="card">
            {data.top_leads.length === 0 ? (
              <div className="empty" style={{ padding: 16 }}>
                Nothing at this agency was flagged.
              </div>
            ) : (
              <div className="table-wrap">
                <table className="plan-table">
                  <thead>
                    <tr>
                      <th>Work</th><th>What it is</th><th>Clue strength</th>
                      <th style={{ textAlign: "right" }}>Money at risk</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_leads.map((row) => (
                      <tr key={row.work_ref}>
                        <td>
                          <Link to={`/case/${row.work_ref}`} className="plan-ref">
                            {row.work_ref}
                          </Link>
                        </td>
                        <td className="plan-agency" title={row.description}>
                          {row.description}
                        </td>
                        <td><Band value={row.band} /></td>
                        <td style={{ textAlign: "right" }}>
                          {rupees(row.exposure_rupees)}
                        </td>
                        <td className="plan-agency">{row.signals.map(clueName).join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Reveal>

        {/* ------------------------------------------------------ same-trip pairs */}
        {data.internal_duplicates.length > 0 && (
          <Reveal delay={190}>
            <div className="section-title">Look-alike works one visit could sort out</div>
            <div className="card">
              <p className="plan-cost-note" style={{ marginTop: 0 }}>
                Both works in each pair belong to this agency, so one trip can show whether they
                really are two separate works. The same description is often used for different
                works, and that is normal — this is a question to ask, not proof of anything.
              </p>
              <div className="table-wrap">
                <table className="plan-table">
                  <thead>
                    <tr><th>Work</th><th>Work</th><th>How alike</th><th>What it is</th></tr>
                  </thead>
                  <tbody>
                    {data.internal_duplicates.map((pair) => (
                      <tr key={`${pair.a}-${pair.b}`}>
                        <td><Link to={`/case/${pair.a}`} className="plan-ref">{pair.a}</Link></td>
                        <td><Link to={`/case/${pair.b}`} className="plan-ref">{pair.b}</Link></td>
                        <td>{(pair.similarity * 100).toFixed(1)}% · {pair.classification === "EXACT" ? "same words" : pair.classification.toLowerCase().replaceAll("_", " ")}</td>
                        <td className="plan-agency">{pair.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Reveal>
        )}

        {/* ------------------------------------------------------- what they build */}
        <Reveal delay={240}>
          <div className="section-title">What this agency builds</div>
          <div className="card">
            <div className="dossier-chips">
              {p.categories.map((row) => (
                <span key={row.category} className="chip">
                  {row.category} <b>{num(row.works)}</b>
                </span>
              ))}
            </div>
            <p className="plan-cost-note">
              {num(p.completed)} finished, {num(p.open)} not finished yet
              {p.median_completed_days
                ? ` · finished works usually took about ${num(Math.round(p.median_completed_days))} days`
                : ""}
              . Areas (constituencies): {data.constituencies.join(", ")}.
            </p>
          </div>
        </Reveal>
      </div>
    </>
  );
}
