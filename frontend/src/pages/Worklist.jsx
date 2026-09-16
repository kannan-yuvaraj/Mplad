import { Fragment, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, num, rupees } from "../api.js";
import { Band, Hitl, SkeletonRows, Topbar } from "../components/Bits.jsx";
import { useRole } from "../RoleContext.jsx";
import { useI18n } from "../I18nContext.jsx";
import { clueName, plainEvidence } from "../plain.js";

const PAGE = 25;

/** The detail that slides open beneath a row when it is clicked. */
function RowDetail({ workRef, onOpen, t }) {
  const [c, setC] = useState(null);

  useEffect(() => {
    let live = true;
    api.case(workRef).then((d) => live && setC(d)).catch(() => live && setC(false));
    return () => { live = false; };
  }, [workRef]);

  if (c === null) return <div className="row-detail-inner"><SkeletonRows rows={2} height={14} /></div>;
  if (c === false) return <div className="row-detail-inner muted">Could not load this work.</div>;

  const id = c.identity;
  return (
    <div className="row-detail-inner">
      <div className="detail-grid">
        <div className="detail-item">
          <div className="k">{t("case.archetype", "Work type")}</div>
          <div className="v">{c.archetype?.label || "—"}</div>
        </div>
        <div className="detail-item">
          <div className="k">{t("case.peerSize", "Number of similar works")}</div>
          <div className="v">{num(c.peer_context?.group_size)} {t("common.works", "works")}</div>
        </div>
        <div className="detail-item">
          <div className="k">{t("case.amountPercentile", "Costs more than")}</div>
          <div className="v">
            {c.peer_context?.amount_percentile != null
              ? `${Math.round(c.peer_context.amount_percentile * 100)} in 100 similar works`
              : "—"}
          </div>
        </div>
        <div className="detail-item">
          <div className="k">{t("case.completionRisk", "Chance it may not get finished")}</div>
          <div className="v">{Math.round((c.risk?.completion_risk || 0) * 100)}%</div>
        </div>
        <div className="detail-item">
          <div className="k">{t("case.earlyWarning", "Early warning")}</div>
          <div className="v">{c.early_warning?.level || "LOW"}</div>
        </div>
        <div className="detail-item">
          <div className="k">Agency building it</div>
          <div className="v" style={{ fontSize: 12.5 }}>{id.implementing_agency || "—"}</div>
        </div>
      </div>

      <div className="detail-evidence">
        <div className="k" style={{ fontSize: 9.5, textTransform: "uppercase",
          letterSpacing: 1, color: "var(--text-3)", fontWeight: 700, marginBottom: 6 }}>
          {t("case.evidence", "Why the computer flagged this work")}
        </div>
        <ul>
          {(c.evidence || []).map((e, i) => (
            <li key={i} title={`${e.signal} — ${e.detail}`}><b>{clueName(e.signal)}</b> — {plainEvidence(e.detail)}</li>
          ))}
        </ul>
      </div>

      <div className="detail-actions">
        <button className="btn btn-primary" onClick={onOpen}>
          {t("case.title", "Case File")} →
        </button>
      </div>
    </div>
  );
}

export default function Worklist() {
  // The filters seed from the address bar, so a link can carry them. The heat
  // map's "See its works" arrives as `?state=Delhi`, and before this the queue
  // opened unfiltered — the officer landed on all 37,705 leads having just asked
  // for one state's. Keeping them in the URL also makes a filtered queue
  // something you can send to a colleague.
  const [search, setSearch] = useSearchParams();
  const [data, setData] = useState(null);
  const [states, setStates] = useState([]);
  const [q, setQ] = useState(() => search.get("q") || "");
  const [state, setState] = useState(() => search.get("state") || "");
  const [band, setBand] = useState(() => (search.get("band") || "").toUpperCase());
  const [page, setPage] = useState(0);
  const [openRef, setOpenRef] = useState(null);
  const nav = useNavigate();
  const { params, role, scope } = useRole();
  const { t } = useI18n();

  // Write the filters back, replacing rather than pushing: typing in the search
  // box should not bury the previous page under thirty history entries.
  useEffect(() => {
    const next = {};
    if (q) next.q = q;
    if (state) next.state = state;
    if (band) next.band = band;
    setSearch(next, { replace: true });
  }, [q, state, band, setSearch]);

  useEffect(() => { api.states().then(setStates).catch(() => {}); }, []);

  useEffect(() => {
    setData(null);
    setOpenRef(null);
    let live = true;
    const timer = setTimeout(() => {
      api.worklist({ limit: PAGE, offset: page * PAGE, q, state, band, ...params })
        // Without the guard a slow early request could land after a fast later one
        // and repaint the table with the previous filter's rows.
        .then((d) => { if (live) setData(d); })
        .catch((e) => { if (live) console.error(e); });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [q, state, band, page, role, scope]);

  useEffect(() => { setPage(0); }, [q, state, band, role, scope]);

  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE);

  return (
    <>
      <Topbar
        title={t("worklist.title", "Works to Check")}
        sub={t("worklist.sub", "Most worth checking first — a work comes higher the more public money a check could protect and the more clues agree")}
        right={<span className="pill">{num(total)} {t("common.leads", "flagged works")}</span>}
      />
      <div className="content">
        <Hitl />

        <div className="toolbar">
          <input className="input" placeholder={t("worklist.search", "Search by what the work is, or who is building it")}
            value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="select" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">{t("worklist.allStates", "All states")}</option>
            {states.map((s) => <option key={s.state_name} value={s.state_name}>{s.state_name}</option>)}
          </select>
          <select className="select" value={band} onChange={(e) => setBand(e.target.value)}>
            <option value="">{t("worklist.allBands", "All clue levels")}</option>
            <option value="HIGH">HIGH · 3+ clues agree</option>
            <option value="MEDIUM">MEDIUM · 2 clues agree</option>
          </select>
        </div>

        {!data ? <SkeletonRows rows={8} /> : data.items.length === 0 ? (
          <div className="empty">{t("worklist.empty", "No works match these filters.")}</div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>#</th>
                    <th>{t("worklist.work", "Work")}</th>
                    <th>{t("worklist.state", "State")}</th>
                    <th>{t("worklist.confidence", "Clue strength")}</th>
                    <th className="num">{t("worklist.amount", "Amount")}</th>
                    <th className="num">{t("overview.exposure", "Money at risk")}</th>
                    <th className="num">{t("worklist.auditRoi", "Worth checking")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r, i) => {
                    const open = openRef === r.work_ref;
                    return (
                      <Fragment key={r.work_ref}>
                        <tr
                          className={"row-toggle" + (open ? " open" : "")}
                          onClick={() => setOpenRef(open ? null : r.work_ref)}
                        >
                          <td className="rank"><span className="chev">▸</span>{page * PAGE + i + 1}</td>
                          <td>
                            <div className="desc-cell">{r.description || "—"}</div>
                            <div className="muted" style={{ fontSize: 11 }}>
                              {r.archetype} · {r.n_families} {t("case.families", "kinds of clues")}
                            </div>
                          </td>
                          <td className="muted">{r.state}</td>
                          <td><Band value={r.band} /></td>
                          <td className="num">{rupees(r.recommended_amount)}</td>
                          <td className="num">{rupees(r.exposure_rupees)}</td>
                          <td className="num" style={{ fontWeight: 700, color: "var(--brick)" }}>
                            {rupees(r.audit_roi)}
                          </td>
                        </tr>
                        {open && (
                          <tr className="row-detail">
                            <td colSpan={7}>
                              <RowDetail
                                workRef={r.work_ref}
                                onOpen={() => nav(`/case/${r.work_ref}`)}
                                t={t}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="pager">
              <span className="muted">
                {t("worklist.page", "Page")} {page + 1} {t("worklist.of", "of")} {num(pages)}
                {" · "}{data.items.length} / {num(total)}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
                  ← {t("worklist.prev", "Previous")}
                </button>
                <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
                  {t("worklist.next", "Next")} →
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
