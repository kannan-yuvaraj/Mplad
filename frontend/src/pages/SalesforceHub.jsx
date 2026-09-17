import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../I18nContext.jsx";
import { api, num, rupees } from "../api.js";
import { Band, Loading, Topbar } from "../components/Bits.jsx";
import { Reveal } from "../components/Reveal.jsx";
import { IconAssistant, IconCasework, IconCloud, IconQueue, IconReport, IconTarget } from "../components/icons.jsx";
import { STAGE_HELP, clueName, familyName, plainEvidence } from "../plain.js";

/** The queue's own reading of itself, re-said. Same three cases as the engine. */
function plainAgeing(a) {
  const r = a.reading || "";
  if (r.startsWith("Every one of")) {
    return `All ${num(a.open_cases)} open cases are still on the step they started on. Their review dates were set from the data snapshot of 26 May 2026, and nobody has worked this demonstration batch since — so every date has passed. That is a batch nobody has started, not a team that has fallen behind. These numbers start to mean something once officers begin working on the cases.`;
  }
  if (r.startsWith("Nothing open")) return "No open case has gone past its review date.";
  return `${num(a.late)} of ${num(a.open_cases)} open cases have gone past the date someone promised to review them, holding ${rupees(a.late_exposure_rupees)} of money at risk between them.`;
}

const STAGE_COLORS = {
  New: "#3b82f6",
  Assigned: "#a8452a",
  "In Progress": "#d97706",
  Verified: "#0d9488",
  Closed: "#15803d",
};

export default function SalesforceHub() {
  // One language for the whole product. The assistant answering in English while the
  // chrome around it is in Tamil is worse than not offering Tamil.
  const { lang } = useI18n();
  const [overview, setOverview] = useState(null);
  const [ageing, setAgeing] = useState(null);
  // No open case has ever moved: the ageing figures describe an unworked batch.
  const unstarted = (ageing?.reading || "").startsWith("Every one of");
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState([]);
  const [stageFilter, setStageFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeStage, setActiveStage] = useState("New");
  const [selectedFinding, setSelectedFinding] = useState("");
  const [updating, setUpdating] = useState(false);
  const [updateMsg, setUpdateMsg] = useState("");

  // Agentforce chat state
  const [agentQuery, setAgentQuery] = useState("");
  const [agentHistory, setAgentHistory] = useState([
    {
      role: "assistant",
      content:
        "**Welcome to the MPLADS assistant (Agentforce)**.\nAsk me about cases, money at risk, which level of government is handling a case, and what an officer should do next. A case is a work worth checking, with its clues — never proof that anyone did wrong.",
    },
  ]);
  const [agentBusy, setAgentBusy] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [ov, cs, ag] = await Promise.all([
        api.salesforceOverview(),
        api.salesforceCases({ limit: 500 }),
        // The queue is where a monitoring system fails invisibly, so it loads with
        // everything else rather than sitting behind a click nobody makes.
        api.salesforceAgeing().catch(() => null),
      ]);
      setOverview(ov);
      setCases(cs.items || []);
      setAgeing(ag);
      if (cs.items?.length > 0) {
        selectCaseRecord(cs.items[0]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function selectCaseRecord(c) {
    setSelectedCase(c);
    setActiveStage(c.investigation_status || "New");
    setSelectedFinding(c.officer_finding || "");
    setUpdateMsg("");
    try {
      const detail = await api.salesforceCase(c.work_ref);
      setSelectedEvidence(detail.evidence || []);
    } catch {
      setSelectedEvidence([]);
    }
  }

  async function handleStageUpdate(newStage, finding = selectedFinding) {
    if (!selectedCase || updating) return;
    setUpdating(true);
    setUpdateMsg("");
    try {
      const res = await api.updateSalesforceStage({
        work_ref: selectedCase.work_ref,
        stage: newStage,
        officer_finding: finding,
      });
      setActiveStage(newStage);
      setUpdateMsg(`✅ Case moved to step: ${newStage}`);
      // Refresh local list
      setCases((prev) =>
        prev.map((item) =>
          item.work_ref === selectedCase.work_ref
            ? { ...item, investigation_status: newStage, officer_finding: finding }
            : item
        )
      );
      setSelectedCase((prev) => ({
        ...prev,
        investigation_status: newStage,
        officer_finding: finding,
      }));
    } catch (e) {
      setUpdateMsg(`❌ Could not move the case: ${e}`);
    } finally {
      setUpdating(false);
    }
  }

  async function askAgentforce(q) {
    const question = (q || agentQuery).trim();
    if (!question || agentBusy) return;
    setAgentQuery("");
    setAgentHistory((prev) => [...prev, { role: "user", content: question }]);
    setAgentBusy(true);
    try {
      const res = await api.agentforceQuery(question, lang);
      setAgentHistory((prev) => [
        ...prev,
        { role: "assistant", content: res.answer || "No response received." },
      ]);
    } catch {
      setAgentHistory((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I could not reach the assistant just now. The system may still be starting — please try again in a moment.",
        },
      ]);
    } finally {
      setAgentBusy(false);
    }
  }

  const filteredCases = useMemo(() => {
    return cases.filter((c) => {
      if (stageFilter !== "all" && c.investigation_status !== stageFilter) return false;
      if (tierFilter !== "all" && c.escalation_tier !== tierFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matches =
          (c.work_ref || "").toLowerCase().includes(q) ||
          (c.description || "").toLowerCase().includes(q) ||
          (c.implementing_agency || "").toLowerCase().includes(q) ||
          (c.state || "").toLowerCase().includes(q);
        if (!matches) return false;
      }
      return true;
    });
  }, [cases, stageFilter, tierFilter, searchQuery]);

  if (loading || !overview) {
    return (
      <>
        <Topbar title="Case Tracking" />
        <div className="content">
          <Loading />
        </div>
      </>
    );
  }

  const org = overview.org;
  const stages = overview.path.stages;
  const activeStageGuidance =
    stages.find((s) => s.stage === activeStage)?.guidance || "";

  return (
    <>
      <Topbar
        title="Case Tracking"
        sub="Who is handling each case, how far it has got, and reports for the Ministry — kept in Salesforce"
        right={
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span className="pill pill-green" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: "50%", background: "#15803d", display: "inline-block" }} />
              Connected: {org.alias}
            </span>
          </div>
        }
      />

      <div className="content">
        {/* Org Banner */}
        <div
          className="card"
          style={{
            marginBottom: 20,
            background: "linear-gradient(135deg, #fdfbf7 0%, #f4eee1 100%)",
            borderColor: "rgba(168, 69, 42, 0.25)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: "var(--accent)" }}><IconCasework size={17} aria-hidden="true" /> Connected Salesforce account</h3>
                <span className="fam-tag" style={{ background: "#e0f2fe", color: "#0369a1", fontWeight: 700 }}>
                  Account ID: {org.org_id}
                </span>
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                Signed in as <strong>{org.username}</strong> · App: <strong>{overview.app.name}</strong> · Assistant topic: <strong>{overview.agentforce.topic}</strong>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button
                className="btn btn-primary"
                onClick={() => window.open(org.instance_url, "_blank")}
                title="Open Salesforce in a new tab"
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <IconCloud size={14} aria-hidden="true" /><span>Open Salesforce</span>
              </button>
            </div>
          </div>
        </div>

        {/* ------------------------------------------------------- the ageing queue
            A lead that was surfaced, assigned and then left for four months has not been
            monitored, it has been filed — and the exposure in it is still out there. Two
            silences are counted apart on purpose: *late* means somebody committed to a
            date and the date passed; *never picked up* means nobody ever started, which is
            usually a supervisor's failure rather than an officer's. */}
        {ageing && (
          <Reveal>
            <div className="section-title">Cases nobody has moved</div>
            <div className="card" style={{ marginBottom: 24 }}>
              {/* When no case has ever been worked, "500 past their review date" is a fact
                  about an untouched demonstration batch, not a department. Read first, it
                  looked like the system was failing — so the explanation goes above the
                  numbers in that state, and the alarm colour comes off. */}
              {unstarted && (
                <div className="dossier-reading" style={{ padding: "10px 14px", marginBottom: 14 }}
                     title={ageing.reading}>
                  {plainAgeing(ageing)}
                </div>
              )}
              <div className="grid cols-4" style={{ marginBottom: 14 }}>
                <div className="card stat">
                  <div className="label">Past their review date</div>
                  <div className={"value" + (unstarted ? "" : " accent")}>{num(ageing.late)}</div>
                  <div className="foot">of {num(ageing.open_cases)} still open</div>
                </div>
                <div className="card stat">
                  <div className="label">Money at risk in them</div>
                  <div className="value">{rupees(ageing.late_exposure_rupees)}</div>
                  <div className="foot">still waiting while nobody looks</div>
                </div>
                <div className="card stat">
                  <div className="label">Never picked up</div>
                  <div className="value">{num(ageing.never_picked_up)}</div>
                  <div className="foot">still on the step they started on</div>
                </div>
                <div className="card stat">
                  <div className="label">Most overdue</div>
                  <div className="value">{num(ageing.oldest_days_late)}</div>
                  <div className="foot">days past the promised date</div>
                </div>
              </div>

              {!unstarted && (
                <div className="dossier-reading" style={{ padding: "10px 14px" }} title={ageing.reading}>
                  {plainAgeing(ageing)}
                </div>
              )}

              <div className="dossier-chips" style={{ marginTop: 12 }}>
                {ageing.buckets.map((bucket) => (
                  <span key={bucket.label} className="chip">
                    {bucket.label} <b>{num(bucket.cases)}</b>
                  </span>
                ))}
              </div>
              <p className="plan-cost-note" title={`${ageing.note} ${ageing.contract}`}>
                "Late" means the review date has passed and nobody has written that they looked.
                "Never picked up" means the case is still on the step it started on — a different
                problem, usually for a supervisor rather than an officer. This checks how our own
                team is keeping up; a late case says nothing bad about the work itself.
              </p>
            </div>
          </Reveal>
        )}

        {/* 4 Metric Cards */}
        <Reveal>
          <div className="grid cols-4" style={{ marginBottom: 24 }}>
            <div className="card stat">
              <div className="label">Cases in Salesforce</div>
              <div className="value" style={{ fontSize: 24 }}>
                {overview.objects.Investigation_Case__c.records_loaded} HIGH
              </div>
              <div className="foot">the most important flagged works</div>
            </div>

            <div className="card stat">
              <div className="label">₹ Money at risk</div>
              <div className="value accent" style={{ fontSize: 24 }}>
                {rupees(overview.objects.Investigation_Case__c.total_exposure_rupees)}
              </div>
              <div className="foot">in these {overview.objects.Investigation_Case__c.records_loaded} cases</div>
            </div>

            <div className="card stat">
              <div className="label">Clues attached</div>
              <div className="value" style={{ fontSize: 24 }}>
                {overview.objects.Evidence__c.records_loaded} clues
              </div>
              <div className="foot">each clue is linked to its case</div>
            </div>

            <div className="card stat">
              <div className="label">Steps for each case</div>
              <div className="value" style={{ fontSize: 24, color: "#15803d" }}>
                5 steps
              </div>
              <div className="foot">with advice for the officer at each step</div>
            </div>
          </div>
        </Reveal>

        {/* Main Grid: Interactive Path & Casework + Agentforce */}
        <div className="grid cols-2" style={{ gap: 20, marginBottom: 24 }}>
          {/* Left Column: Interactive 5-Stage Path Console */}
          <div className="card" style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <h3 style={{ margin: 0 }}><IconTarget size={15} aria-hidden="true" /> Work on a case, step by step</h3>
              {selectedCase && (
                <Link to={`/case/${selectedCase.work_ref}`} className="link" style={{ fontSize: 13 }}>
                  See the case file →
                </Link>
              )}
            </div>

            {selectedCase ? (
              <>
                <div style={{ padding: "10px 14px", background: "var(--card-subtle, #f0ebd8)", borderRadius: 6, marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <strong style={{ fontSize: 15, color: "var(--text)" }}>{selectedCase.work_ref}</strong>
                      <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
                        {selectedCase.state} · {selectedCase.constituency}
                      </span>
                    </div>
                    <span className="pill" style={{ background: STAGE_COLORS[selectedCase.investigation_status] || "#3b82f6", color: "#fff", fontWeight: 700, fontSize: 11 }}>
                      {selectedCase.investigation_status}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 4 }}>
                    {selectedCase.description?.slice(0, 140)}…
                  </div>
                  <div style={{ display: "flex", gap: 14, marginTop: 6, fontSize: 12 }}>
                    <span>Money at risk: <strong style={{ color: "var(--accent)" }}>{rupees(selectedCase.exposure)}</strong></span>
                    <span>Handled at: <strong>{selectedCase.escalation_tier}</strong></span>
                    <span>Review by: <strong>{selectedCase.target_review_date}</strong></span>
                  </div>
                </div>

                {/* 5-Stage Visual Stepper */}
                <div style={{ marginBottom: 14 }}>
                  <div className="section-label" style={{ marginBottom: 8 }}>The five steps (click to move the case)</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
                    {stages.map((st, idx) => {
                      const isCurrent = activeStage === st.stage;
                      const isPast = stages.findIndex((s) => s.stage === activeStage) >= idx;
                      return (
                        <button
                          key={st.stage}
                          onClick={() => handleStageUpdate(st.stage)}
                          disabled={updating}
                          style={{
                            padding: "8px 4px",
                            fontSize: 11,
                            fontWeight: isCurrent ? 700 : 500,
                            borderRadius: 4,
                            border: "1px solid",
                            borderColor: isCurrent ? STAGE_COLORS[st.stage] : "#d1d5db",
                            background: isCurrent ? STAGE_COLORS[st.stage] : isPast ? "#f3f4f6" : "#ffffff",
                            color: isCurrent ? "#ffffff" : "var(--text)",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                            textAlign: "center",
                          }}
                        >
                          {st.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Stage Guidance Box */}
                <div
                  style={{
                    padding: "12px 14px",
                    background: "#fefcf6",
                    borderLeft: `4px solid ${STAGE_COLORS[activeStage] || "var(--accent)"}`,
                    borderRadius: "0 6px 6px 0",
                    marginBottom: 16,
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: STAGE_COLORS[activeStage] || "var(--accent)" }}>
                    What to do at this step: {activeStage}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--text)", marginTop: 4, fontStyle: "italic" }} title={activeStageGuidance}>
                    "{STAGE_HELP[activeStage] || activeStageGuidance}"
                  </div>
                </div>

                {/* Officer Finding Selector for Verified & Closed Stages */}
                {(activeStage === "Verified" || activeStage === "Closed") && (
                  <div style={{ marginBottom: 16, padding: "10px 12px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>
                      What the officer found on site (the computer learns from this):
                    </label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <select
                        className="input"
                        style={{ flex: 1, padding: "6px 10px", fontSize: 13 }}
                        value={selectedFinding}
                        onChange={(e) => {
                          setSelectedFinding(e.target.value);
                          handleStageUpdate(activeStage, e.target.value);
                        }}
                      >
                        <option value="">-- Choose what was found --</option>
                        {overview.findings?.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}

                {updateMsg && (
                  <div style={{ fontSize: 12, fontWeight: 600, color: updateMsg.startsWith("✅") ? "#15803d" : "#b91c1c", marginBottom: 12 }}>
                    {updateMsg}
                  </div>
                )}

                {/* Evidence Related List */}
                <div>
                  <div className="section-label" style={{ marginBottom: 8 }}>
                    Clues ({selectedEvidence.length} attached)
                  </div>
                  <div style={{ maxHeight: 150, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 6 }}>
                    {selectedEvidence.length === 0 ? (
                      <div className="muted" style={{ padding: 12, fontSize: 12 }}>No clues were attached to this case.</div>
                    ) : (
                      selectedEvidence.map((ev, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "8px 12px",
                            borderBottom: i < selectedEvidence.length - 1 ? "1px solid #f1f5f9" : "none",
                            fontSize: 12,
                          }}
                        >
                          <span className="fam-tag" style={{ marginRight: 6 }}>{familyName(ev.family)}</span>
                          <strong title={ev.signal}>{clueName(ev.signal)}:</strong> <span className="muted" title={ev.detail}>{plainEvidence(ev.detail)}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="empty">Pick a case below to see it and move it to the next step.</div>
            )}
          </div>

          {/* Right Column: Agentforce AI Copilot Terminal */}
          <div className="card" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex" }}><IconAssistant size={19} /></span>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16 }}>Case assistant (Agentforce)</h3>
                  <div className="muted" style={{ fontSize: 11 }}>
                    Topic: <strong>{overview.agentforce.topic}</strong> · never says "fraud"
                  </div>
                </div>
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: "4px 10px", fontSize: 11 }}
                onClick={() => setAgentHistory([])}
              >
                Clear
              </button>
            </div>

            {/* Quick Prompts */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
              {[
                "Show HIGH priority cases in Bihar",
                "Which case has the most money at risk?",
                "Show cases in Ministry Review tier",
                `Next step for ${selectedCase?.work_ref || "MP3018356-W86316"}`,
              ].map((p) => (
                <button
                  key={p}
                  className="chat-chip"
                  style={{ fontSize: 11, padding: "4px 10px" }}
                  onClick={() => askAgentforce(p)}
                >
                  → {p}
                </button>
              ))}
            </div>

            {/* Chat Messages */}
            <div
              style={{
                flex: 1,
                minHeight: 280,
                maxHeight: 340,
                overflowY: "auto",
                background: "#faf8f2",
                border: "1px solid #e7e2d4",
                borderRadius: 8,
                padding: 12,
                marginBottom: 12,
                display: "flex",
                flexDirection: "column",
                gap: 10,
              }}
            >
              {agentHistory.map((msg, i) => (
                <div
                  key={i}
                  style={{
                    alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                    maxWidth: "88%",
                    background: msg.role === "user" ? "var(--accent)" : "#ffffff",
                    color: msg.role === "user" ? "#ffffff" : "var(--text)",
                    padding: "8px 12px",
                    borderRadius: 8,
                    fontSize: 12.5,
                    lineHeight: 1.45,
                    border: msg.role === "user" ? "none" : "1px solid #e2ded5",
                    whiteSpace: "pre-line",
                  }}
                >
                  {msg.content}
                </div>
              ))}
              {agentBusy && (
                <div style={{ alignSelf: "flex-start", color: "var(--text-3)", fontSize: 12, fontStyle: "italic" }}>
                  The assistant is looking through the cases…
                </div>
              )}
            </div>

            {/* Input Row */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                askAgentforce();
              }}
              style={{ display: "flex", gap: 8 }}
            >
              <input
                className="input"
                placeholder="Ask about cases, money at risk, states, or what to do next…"
                value={agentQuery}
                onChange={(e) => setAgentQuery(e.target.value)}
                style={{ flex: 1, fontSize: 13 }}
                disabled={agentBusy}
              />
              <button className="btn btn-primary" type="submit" disabled={agentBusy || !agentQuery.trim()}>
                Ask
              </button>
            </form>
          </div>
        </div>

        {/* Filterable Investigation Cases Queue */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
            <div>
              <h3 style={{ margin: 0 }}><IconQueue size={15} aria-hidden="true" /> All cases in Salesforce ({filteredCases.length})</h3>
              <div className="muted" style={{ fontSize: 12 }}>
                The most urgent flagged works, copied into Salesforce so people can track them
              </div>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input
                className="input"
                placeholder="Search by work, agency, state…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ width: 200, fontSize: 12, padding: "6px 10px" }}
              />

              <select
                className="input"
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value)}
                style={{ fontSize: 12, padding: "6px 10px" }}
              >
                <option value="all">All steps ({cases.length})</option>
                {stages.map((s) => (
                  <option key={s.stage} value={s.stage}>
                    {s.label} ({overview.path.distribution[s.stage] || 0})
                  </option>
                ))}
              </select>

              <select
                className="input"
                value={tierFilter}
                onChange={(e) => setTierFilter(e.target.value)}
                style={{ fontSize: 12, padding: "6px 10px" }}
              >
                <option value="all">All levels</option>
                <option value="District Monitoring">District Monitoring</option>
                <option value="State Nodal">State Nodal</option>
                <option value="Ministry Review">Ministry Review</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table className="table" style={{ width: "100%", fontSize: 13 }}>
              <thead>
                <tr>
                  <th>Work number</th>
                  <th>State & agency</th>
                  <th>Money at risk</th>
                  <th>Handled at</th>
                  <th>Step</th>
                  <th>What was found</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.slice(0, 15).map((c) => {
                  const isSelected = selectedCase?.work_ref === c.work_ref;
                  return (
                    <tr
                      key={c.work_ref}
                      style={{
                        background: isSelected ? "var(--card-subtle, #f5f0e3)" : "transparent",
                        cursor: "pointer",
                      }}
                      onClick={() => selectCaseRecord(c)}
                    >
                      <td>
                        <strong style={{ color: "var(--accent)" }}>{c.work_ref}</strong>
                      </td>
                      <td>
                        <div>{c.state}</div>
                        <div className="muted" style={{ fontSize: 11 }}>{c.implementing_agency}</div>
                      </td>
                      <td>
                        <strong>{rupees(c.exposure)}</strong>
                      </td>
                      <td>
                        <span className="fam-tag" style={{ fontSize: 11 }}>{c.escalation_tier}</span>
                      </td>
                      <td>
                        <span
                          className="pill"
                          style={{
                            background: STAGE_COLORS[c.investigation_status] || "#3b82f6",
                            color: "#fff",
                            fontWeight: 600,
                            fontSize: 10.5,
                            padding: "2px 8px",
                          }}
                        >
                          {c.investigation_status}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: 12, color: c.officer_finding ? "var(--text)" : "var(--text-3)" }}>
                          {c.officer_finding || "—"}
                        </span>
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: "3px 8px", fontSize: 11 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            selectCaseRecord(c);
                          }}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {filteredCases.length > 15 && (
            <div className="muted" style={{ textAlign: "center", fontSize: 12, marginTop: 12 }}>
              Showing the top 15 of {filteredCases.length} matching cases.
            </div>
          )}
        </div>

        {/* Ministry Executive Reports & Dashboards Preview */}
        <Reveal delay={60}>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <h3 style={{ margin: 0 }}><IconReport size={15} aria-hidden="true" /> Summary reports for the Ministry</h3>
                <div className="muted" style={{ fontSize: 12 }}>
                  Three reports: money at risk by state, cases by level, and agencies with the most money at risk
                </div>
              </div>
              <span className="pill pill-green">Report preview</span>
            </div>

            <div className="grid cols-3" style={{ gap: 16 }}>
              {/* Report 1: State Exposure */}
              <div style={{ padding: 14, background: "#faf8f2", borderRadius: 8, border: "1px solid #e8e3d6" }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>Money at risk by state</div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 10 }}>Top 5 states</div>
                {overview.top_states.slice(0, 5).map((st) => (
                  <div key={st.state} style={{ marginBottom: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <span>{st.state}</span>
                      <strong>{rupees(st.exposure)}</strong>
                    </div>
                    <div className="meter" style={{ height: 5, marginTop: 2 }}>
                      <span style={{ width: `${Math.min(100, (st.exposure / overview.top_states[0].exposure) * 100)}%`, background: "var(--accent)" }} />
                    </div>
                  </div>
                ))}
              </div>

              {/* Report 2: Escalation Tiers */}
              <div style={{ padding: 14, background: "#faf8f2", borderRadius: 8, border: "1px solid #e8e3d6" }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>Cases by level</div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 10 }}>District, State or Ministry</div>
                {Object.entries(overview.escalation_tiers).map(([tier, count]) => (
                  <div key={tier} style={{ marginBottom: 10, padding: 8, background: "#ffffff", borderRadius: 6, border: "1px solid #eee" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <strong>{tier}</strong>
                      <span className="fam-tag">{count} cases</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Report 3: Deployed Metadata Info */}
              <div style={{ padding: 14, background: "#faf8f2", borderRadius: 8, border: "1px solid #e8e3d6" }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>What is set up in Salesforce</div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 10 }}>In the account "mplads" (technical names)</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-2)", lineHeight: 1.6 }}>
                  <li><strong>App:</strong> MPLADS Investigations</li>
                  <li><strong>Case records:</strong> Investigation_Case__c</li>
                  <li><strong>Clue records:</strong> Evidence__c</li>
                  <li><strong>Step guide:</strong> Investigation_Path</li>
                  <li><strong>Dashboard:</strong> MPLADS Executive Summary</li>
                  <li><strong>Assistant topic:</strong> Investigation Lookup</li>
                </ul>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </>
  );
}
