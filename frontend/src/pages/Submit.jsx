import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Band, Hitl, Topbar } from "../components/Bits.jsx";
import { rupees } from "../api.js";

/**
 * The intake portal — an eSAKSHI-shaped submission, assessed in front of you.
 *
 * An Implementing Agency marks a work complete and uploads its evidence. On the
 * real portal that is where the trail ends: the file is stored and a human may
 * or may not ever open it. This page shows what our system does with the same
 * submission, one check at a time.
 *
 * **The stages stream.** They are not animated on a timer — each row fills in
 * when its check actually finishes, and OCR genuinely takes seconds while a
 * portfolio lookup is instant. A fake progress bar would make a fast machine
 * indistinguishable from a canned demo, which is precisely the accusation this
 * screen exists to answer.
 *
 * The plan arrives first so all eleven rows are on screen before any of them
 * resolve — a list that grows tells the viewer nothing about how much is left.
 */

const STATUS = {
  ok: { glyph: "✓", cls: "ok", label: "Clear" },
  attention: { glyph: "▲", cls: "attention", label: "Look at this" },
  blocked: { glyph: "■", cls: "blocked", label: "Needs a person" },
  info: { glyph: "·", cls: "info", label: "Context" },
  pending: { glyph: "", cls: "pending", label: "Waiting" },
};

const SCENARIOS = [
  {
    id: "clean",
    title: "Ordinary submission",
    blurb: "A board photograph that matches its record. Most submissions look like this, and the system should say so rather than inventing a concern.",
    // A work with band NONE. This was board 01 — the top-ranked lead in the whole
    // portfolio — so the "ordinary" sample came back HIGH and contradicted its label.
    file: "03-photo-first-submission.png",
    workRef: "",
    amount: "",
  },
  {
    id: "flagged",
    title: "A work already carrying evidence",
    blurb: "The same intake, for a work the engine had already surfaced. The submission is fine; the work is not ordinary.",
    file: "02-board-different-work.png",
    workRef: "",
    amount: "",
  },
  {
    id: "mismatch",
    title: "The board and the form disagree",
    blurb: "The agency types one reference; the photograph shows another. MPLADS references run in sequence, so one wrong digit is a different real work. Nothing is settled by the machine.",
    file: "04-photo-resubmitted.jpg",
    workRef: "MP3018356-W86316",
    amount: "",
  },
];

export default function Submit() {
  const [plan, setPlan] = useState([]);
  const [readers, setReaders] = useState([]);
  // Reading dominates the wall clock — every other stage finishes in
  // milliseconds — so this defaults to the fast reader to keep the page
  // responsive, and the label says what that costs.
  const [reader, setReader] = useState("rapidocr");
  const [stages, setStages] = useState({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [kind, setKind] = useState("photo");
  const [workRef, setWorkRef] = useState("");
  const [amount, setAmount] = useState("");
  const [open, setOpen] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const dropRef = useRef(null);

  useEffect(() => {
    fetch(`${base()}/api/submission/plan`)
      .then((r) => r.json())
      .then((d) => {
        setPlan(d.stages || []);
        setReaders(d.readers || []);
        // Follow the machine rather than assuming: if the fast reader is not
        // installed here, default to whatever is.
        if (d.readers?.length && !d.readers.some((r) => r.engine === "rapidocr")) {
          setReader(d.readers[0].engine);
        }
      })
      .catch(() => setPlan([]));
  }, []);

  function base() {
    // Always same-origin. Vite (dev and preview) proxies /api, and in the built
    // deployment the API serves this page itself. This used to return
    // `<host>:API_PORT` whenever the page URL had no port — which is every HTTPS
    // deployment — so on the live site uploads went to a port nothing listens on.
    return "";
  }

  async function submit(e) {
    e?.preventDefault();
    if (!file || running) return;
    setRunning(true);
    setError(null);
    setStages({});
    setOpen(null);
    setStartedAt(Date.now());

    const body = new FormData();
    body.append("file", file);
    body.append("kind", kind);
    body.append("work_ref", workRef.trim());
    body.append("amount", amount.trim());
    body.append("reader", kind === "photo" ? reader : "");

    try {
      const res = await fetch(`${base()}/api/submission/assess`, { method: "POST", body });
      if (!res.ok || !res.body) {
        const detail = await res.json().then((d) => d?.detail).catch(() => null);
        throw new Error(typeof detail === "string" ? detail : `The engine returned ${res.status}`);
      }

      // Parse the SSE stream by hand: EventSource cannot POST a file.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let cut;
        while ((cut = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          const evt = /^event: (.+)$/m.exec(chunk)?.[1];
          const raw = /^data: (.+)$/m.exec(chunk)?.[1];
          if (!evt || !raw) continue;
          const data = JSON.parse(raw);

          if (evt === "plan" && data.stages) setPlan(data.stages);
          if (evt === "stage") {
            setStages((prev) => ({ ...prev, [data.stage]: data }));
            if (data.stage === "lead") setOpen("lead");
          }
          if (evt === "error") setError(data.error);
        }
      }
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setRunning(false);
    }
  }

  async function loadScenario(s) {
    setError(null);
    try {
      const res = await fetch(`/demo/photos/${s.file}`);
      if (!res.ok) throw new Error("sample not found");
      const blob = await res.blob();
      setFile(new File([blob], s.file, { type: blob.type || "image/png" }));
      setKind("photo");
      setWorkRef(s.workRef);
      setAmount(s.amount);
      setStages({});
    } catch {
      setError(
        "The sample images are not being served. Pick a file of your own, or copy demo/photos into frontend/public/demo/photos."
      );
    }
  }

  const lead = stages.lead?.detail;
  const done = Object.keys(stages).length;
  const elapsed = stages.lead?.elapsed_ms;

  return (
    <div className="page">
      <Topbar
        title="Submit evidence for a work"
        sub="The eSAKSHI intake, assessed as it arrives"
        right={
          running ? (
            <span className="badge">Assessing… {done}/{plan.length || 11}</span>
          ) : done ? (
            <span className="badge">
              {done} checks{elapsed != null ? ` · ${(elapsed / 1000).toFixed(1)}s` : ""}
            </span>
          ) : null
        }
      />

      <p className="lede" style={{ maxWidth: "62ch" }}>
        This is the moment an Implementing Agency uploads a completion photograph or a
        sanction order. On the portal itself, that is where the trail ends. Here, every
        check runs against the submission while the officer is still on the page — and each
        row below fills in when its check actually finishes, not on a timer.
      </p>

      <div className="grid two" style={{ alignItems: "start", gap: 18 }}>
        {/* ---------------------------------------------------------- form */}
        <section className="card">
          <h2>Submission</h2>

          <div className="scenario-row">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                type="button"
                className="btn ghost sm"
                disabled={running}
                onClick={() => loadScenario(s)}
                title={s.blurb}
              >
                {s.title}
              </button>
            ))}
          </div>
          <p className="muted sm" style={{ marginTop: 6 }}>
            Or upload anything of your own — the assessment is the same code either way.
          </p>

          <form onSubmit={submit} style={{ marginTop: 14 }}>
            <label className="field">
              <span>What is being submitted</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)} disabled={running}>
                <option value="photo">Photograph of the work / site board</option>
                <option value="document">Sanction order, estimate or completion certificate</option>
              </select>
            </label>

            <div
              ref={dropRef}
              className={"dropzone" + (file ? " has-file" : "")}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!running && e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
              }}
            >
              <input
                id="submit-file"
                type="file"
                accept={kind === "photo" ? "image/*" : ".pdf,.doc,.docx,image/*"}
                disabled={running}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              <label htmlFor="submit-file">
                {file ? (
                  <>
                    <strong>{file.name}</strong>
                    <span className="muted sm">
                      {(file.size / 1024).toFixed(0)} KB · click to replace
                    </span>
                  </>
                ) : (
                  <>
                    <strong>Choose a file or drop one here</strong>
                    <span className="muted sm">Photographs up to 12 MB, documents up to 20 MB</span>
                  </>
                )}
              </label>
            </div>

            {kind === "photo" && readers.length > 1 && (
              <fieldset className="field readers">
                <legend>
                  Which reader <em className="muted">— the only slow step on this page</em>
                </legend>
                {readers.map((r) => (
                  <label key={r.engine} className="reader-opt">
                    <input
                      type="radio"
                      name="reader"
                      value={r.engine}
                      checked={reader === r.engine}
                      disabled={running}
                      onChange={(e) => setReader(e.target.value)}
                    />
                    <span>
                      <strong>{r.label}</strong>
                      <span className="muted sm">{r.note}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}

            <label className="field">
              <span>
                Work reference <em className="muted">— the work this is being claimed for</em>
              </span>
              <input
                value={workRef}
                onChange={(e) => setWorkRef(e.target.value)}
                placeholder="MP3018356-W86316 (optional — read from the file if left blank)"
                disabled={running}
              />
            </label>

            <label className="field">
              <span>
                Amount claimed <em className="muted">— optional</em>
              </span>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="e.g. 3997883"
                inputMode="numeric"
                disabled={running}
              />
            </label>

            <button className="btn primary" disabled={!file || running} type="submit">
              {running ? "Assessing…" : "Submit for assessment"}
            </button>
            {error && <p className="error sm" style={{ marginTop: 10 }}>{error}</p>}
          </form>

          <Hitl text="Nothing on this page is saved to the record. A submission that raises a question is routed to a person; the system never settles one itself." />
        </section>

        {/* ------------------------------------------------------- pipeline */}
        <section className="card">
          <h2>What the system does with it</h2>
          <ol className="stage-list">
            {(plan.length ? plan : Array.from({ length: 11 }, (_, i) => ({ stage: `s${i}`, title: "" }))).map(
              (p) => {
                const s = stages[p.stage];
                const meta = STATUS[s?.status || "pending"];
                const isOpen = open === p.stage;
                return (
                  <li key={p.stage} className={`stage ${meta.cls}${s ? " landed" : ""}`}>
                    <button
                      type="button"
                      className="stage-head"
                      disabled={!s}
                      onClick={() => setOpen(isOpen ? null : p.stage)}
                      aria-expanded={isOpen}
                    >
                      <span className="stage-mark" aria-hidden="true">
                        {s ? meta.glyph : running ? <span className="tick" /> : ""}
                      </span>
                      <span className="stage-text">
                        <strong>{p.title}</strong>
                        <span className="stage-headline">
                          {s ? s.headline : running ? "waiting…" : "not run yet"}
                        </span>
                      </span>
                      {s && (
                        <span className="stage-status" title={meta.label}>
                          {meta.label}
                        </span>
                      )}
                    </button>

                    {isOpen && s && (
                      <div className="stage-body">
                        <p className="why">{s.explain}</p>
                        <Detail stage={s} />
                        <pre className="raw">{JSON.stringify(s.detail, null, 2)}</pre>
                      </div>
                    )}
                  </li>
                );
              }
            )}
          </ol>
        </section>
      </div>

      {/* ------------------------------------------------------------ lead */}
      {lead && (
        <section className="card lead-card">
          <div className="lead-head">
            <div>
              <h2 style={{ margin: 0 }}>Investigation lead</h2>
              <p className="muted sm" style={{ margin: "4px 0 0" }}>
                {lead.work_ref} · assessed in {((elapsed || 0) / 1000).toFixed(1)}s
              </p>
            </div>
            <Band value={lead.band} />
          </div>

          <div className="lead-figures">
            <Figure label="Money at stake" value={lead.exposure_rupees != null ? rupees(lead.exposure_rupees) : "—"} />
            <Figure label="Evidence" value={`${(lead.evidence || []).length} pieces`} />
            <Figure label="Return on a visit" value={lead.audit_roi != null ? rupees(lead.audit_roi) : "—"} />
          </div>

          {(lead.submission_notes || []).length > 0 && (
            <ul className="notes">
              {lead.submission_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}

          {(lead.evidence || []).length > 0 && (
            <ul className="evidence">
              {lead.evidence.map((e, i) => (
                <li key={i}>{typeof e === "string" ? e : e.reason || e.signal || JSON.stringify(e)}</li>
              ))}
            </ul>
          )}

          <p className="next">
            <strong>Recommended next step.</strong> {lead.recommended_next_step}
          </p>

          <div className="lead-actions">
            {lead.work_ref && (
              <Link className="btn primary" to={`/case/${lead.work_ref}`}>
                Open the full case file
              </Link>
            )}
          </div>

          <Hitl text={lead.disclaimer || "This system identifies patterns warranting human investigation; it does not determine fraud."} />
        </section>
      )}
    </div>
  );
}

function Figure({ label, value }) {
  return (
    <div className="figure">
      <span className="figure-label">{label}</span>
      <strong className="figure-value">{value}</strong>
    </div>
  );
}

/** A readable summary per stage, above the raw payload. */
function Detail({ stage }) {
  const d = stage.detail || {};
  if (stage.stage === "identify" && (d.alternatives || []).length) {
    return (
      <p className="sm">
        Real references one character away:{" "}
        {d.alternatives.map((a) => (
          <code key={a} style={{ marginRight: 6 }}>{a}</code>
        ))}
      </p>
    );
  }
  if (stage.stage === "photo_forensics" && (d.matches || []).length) {
    return (
      <ul className="sm">
        {d.matches.slice(0, 4).map((m, i) => (
          <li key={i}>
            Also submitted for <code>{m.work_ref}</code>
            {m.first_seen ? ` on ${String(m.first_seen).slice(0, 10)}` : ""}
            {m.exact_file ? " — byte-identical file" : " — visually the same picture"}
          </li>
        ))}
      </ul>
    );
  }
  if (stage.stage === "cross_check" && d.record_amount != null && d.submitted_amount != null) {
    return (
      <p className="sm">
        Submitted <strong>{rupees(d.submitted_amount)}</strong> · on record{" "}
        <strong>{rupees(d.record_amount)}</strong>
        {d.difference ? ` · difference ${rupees(Math.abs(d.difference))}` : " · they agree"}
      </p>
    );
  }
  return null;
}
