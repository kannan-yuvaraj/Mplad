import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, rupees } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import { OUTCOME } from "../plain.js";
import DocumentReader from "./DocumentReader.jsx";

/** The photo reader's own messages, re-said plainly. Unknown ones come back unchanged. */
function plainScan(text) {
  if (!text) return text;
  if (text.startsWith("Extracted text only.")) return "This is only the text the computer read. It has not been checked against any record — check or fix each part before saving.";
  if (text.startsWith("Photo reading is unavailable")) return "Reading photos does not work on this computer. Type the work number in by hand.";
  if (text === "no work reference found in the image") return "No work number could be found in the photo.";
  let m = text.match(/^(\S+) was read from the image but is not a work in this dataset(?:\. These real works differ from it by one character: (.+))?$/);
  if (m) return `The photo seems to say ${m[1]}, but there is no such work in the records.` + (m[2] ? ` These real works differ from it by just one letter or digit: ${m[2]}.` : "");
  m = text.match(/^The two readers disagree: (.+?) read (\S+), (.+?) read (\S+)\./);
  if (m) return `The two readers do not agree: ${m[1]} read ${m[2]}, but ${m[3]} read ${m[4]}. Look at the board and confirm which it says.`;
  m = text.match(/^Matched, but (.+) differ by one character and are also real works\./);
  if (m) return `It matches, but ${m[1]} are also real works that differ by just one letter or digit. The computer cannot be sure which — check which board you photographed.`;
  return text;
}

const OUTCOME_TONE = {
  VERIFIED_COMPLETE: "ok",
  VERIFIED_IN_PROGRESS: "ok",
  NOT_STARTED: "warn",
  NOT_FOUND: "bad",
  RECORD_MISMATCH: "bad",
  NO_ACCESS: "neutral",
};

/**
 * Record what an officer found on site — the only place in this product that creates
 * data. It captures the officer's own observation, attributed and immutable; it never
 * edits a government record.
 *
 * A photograph does three things when it arrives: it is read, it is matched to a work,
 * and it is checked against every photograph submitted before it. The third is the one a
 * human cannot do at scale, and the one this screen is loudest about.
 */
export default function FieldVerify({ workRef }) {
  const { user, token } = useAuth();
  const [history, setHistory] = useState([]);
  const [outcomes, setOutcomes] = useState({});
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState(null);      // { name, preview }
  const [scan, setScan] = useState(null);        // OCR result
  const [scanning, setScanning] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [doc, setDoc] = useState(null);          // Docling result for an attached document
  const [docKey, setDocKey] = useState(0);       // remounts the document reader on reset
  const [readers, setReaders] = useState(null);  // /api/ocr/status
  const fileRef = useRef(null);

  const load = () =>
    api.verifications(workRef).then((d) => {
      setHistory(d.verifications || []);
      setOutcomes(d.outcomes || {});
    }).catch(() => {});

  useEffect(() => { load(); }, [workRef]);
  useEffect(() => { api.ocrStatus().then(setReaders).catch(() => {}); }, []);

  function reset() {
    setOutcome(""); setNotes(""); setPhoto(null); setScan(null); setConfirmed(false);
    setDoc(null); setDocKey((k) => k + 1);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onPhoto(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    api.ocrStatus().then(setReaders).catch(() => {});
    setScanning(true);
    setScan(null);
    setConfirmed(false);
    setPhoto({ name: null, preview: URL.createObjectURL(file) });
    try {
      const res = await api.ocr(file, workRef);
      setPhoto((p) => ({ ...p, name: res.photo }));
      setScan(res);
      api.ocrStatus().then(setReaders).catch(() => {});
    } catch {
      setScan({ error: "Could not read that image." });
    } finally {
      setScanning(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    if (!outcome || saving || blocked) return;
    setSaving(true);
    try {
      // What the camera found travels with the finding. The reference read off the board
      // is a separate claim from the work being verified, and the two disagreeing is the
      // most useful thing a photograph can report — so it is stored, not resolved away.
      await api.verify(workRef, {
        outcome,
        notes,
        photo: photo?.name || null,
        ocr_text: scan?.lines?.map((l) => l.text).join(" ") || null,
        board_ref: scan?.match?.work_ref || null,
        board_amount: scan?.fields?.amount?.value ?? null,
        // Surya gives no confidence figure; where the second reader read the same
        // reference, its figure is the honest one to keep.
        ocr_confidence: scan?.fields?.work_ref?.confidence
          ?? (scan?.cross_check?.agrees ? scan.cross_check.confidence : null) ?? null,
        ocr_engine: scan?.engine || null,
        readers_agree: scan?.cross_check?.agrees ?? null,
        document: doc?.document || null,
        needed_confirmation: Boolean(scan?.match?.needs_confirmation || reuse.length),
        photo_reuse_count: reuse.length,
        reused_from: reuse[0]?.work_ref || null,
      });
      setSaved(true);
      reset();
      await load();
      setTimeout(() => setSaved(false), 3500);
    } catch {
      setScan({ error: "Could not save. Your account may not be allowed to record visits for this area." });
    } finally {
      setSaving(false);
    }
  }

  const match = scan?.match;
  const readRef = match?.work_ref;
  const wrongWork = readRef && readRef !== workRef;
  const reuse = scan?.reuse?.reuse || [];
  // A photograph reads as evidence. If it was already submitted elsewhere, or the board
  // does not clearly say which work it is, the officer acknowledges that before saving.
  const needsAck = Boolean(reuse.length || wrongWork || match?.needs_confirmation);
  const blocked = needsAck && !confirmed;

  return (
    <div className="card verify">
      <h3>Site visit report</h3>
      <ReaderStatus readers={readers} />

      {history.length > 0 && (
        <div className="verify-history">
          {history.map((v) => (
            <div key={v.id} className={"verify-entry " + (OUTCOME_TONE[v.outcome] || "neutral")}>
              <div className="ve-head">
                <span className="ve-outcome" title={v.outcome}>{OUTCOME[v.outcome]?.[0] || v.outcome.replace(/_/g, " ")}</span>
                <span className="ve-when">
                  {v.demo ? <span className="ve-demo">demo sample</span> : null}
                  {new Date(v.created_at).toLocaleDateString()}
                </span>
              </div>
              {v.notes && <div className="ve-notes">{v.notes}</div>}
              <div className="ve-actor">
                {v.actor} · {v.role}
                {v.photo && (
                  <a className="ve-photo" href={`/api/photo/${v.photo}`} target="_blank" rel="noreferrer">
                    view photograph
                  </a>
                )}
                {v.document && (
                  <a className="ve-photo" href={`/api/document/${v.document}`} target="_blank" rel="noreferrer">
                    view document
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!token ? (
        <p className="verify-locked">
          Sign in to write a site visit report. Every report shows the name of the officer who
          wrote it, so you cannot write one without signing in.{" "}
          <Link to="/login">Sign in →</Link>
        </p>
      ) : (
        <form onSubmit={submit} className="verify-form">
          <label className="verify-label">Photograph of the site or work board</label>
          <input ref={fileRef} type="file" accept="image/*" capture="environment"
            onChange={onPhoto} className="verify-file" />

          {scanning && (
            <div className="verify-scanning">
              Reading the photo… <ReadWait readers={readers} />
            </div>
          )}

          {photo?.preview && (
            <div className="verify-shot">
              <img src={photo.preview} alt="Site photograph" />

              {reuse.length > 0 && (
                <div className="verify-reuse">
                  <div className="vru-head">This photo has been sent in before</div>
                  {reuse.map((r) => (
                    <div key={r.photo + r.work_ref} className="vru-row">
                      <Link to={`/case/${r.work_ref}`}>{r.work_ref}</Link>
                      <span className="vru-when">
                        {new Date(r.first_seen).toLocaleDateString()} · {r.actor}
                      </span>
                      <span className="vru-level">
                        {r.exact_file ? "the exact same file" : r.note}
                        {" "}({Math.round(r.similarity * 100)}% match)
                      </span>
                    </div>
                  ))}
                  <p className="vru-note">
                    The computer compares what the pictures look like, so it still spots a copy
                    that was resized or saved again. This is a question, not proof: two stages of
                    the same road can honestly look the same from the roadside.
                  </p>
                </div>
              )}

              {scan && !scan.error && (
                <div className="verify-read">
                  <div className="vr-head">
                    Text the computer read from the photo
                    {scan.engine_label && (
                      <span className="vr-engine">
                        {scan.engine_label}{scan.seconds != null ? ` · ${scan.seconds} s` : ""}
                        {scan.fell_back_from ? " (the main reader was not ready)" : ""}
                      </span>
                    )}
                    {match?.matched && !wrongWork && !match?.needs_confirmation && (
                      <span className="vr-ok">✓ matches this work</span>
                    )}
                    {wrongWork && <span className="vr-warn">reads {readRef}</span>}
                  </div>

                  {scan.fields?.work_ref && (
                    <div className="vr-field">
                      <b>Work number</b> {scan.fields.work_ref.value}
                      {scan.fields.work_ref.confidence != null ? (
                        <span className="vr-conf">
                          {Math.round(scan.fields.work_ref.confidence * 100)}% sure it read the
                          letters right
                        </span>
                      ) : (
                        <span className="vr-conf muted">this reader gives no certainty figure</span>
                      )}
                    </div>
                  )}
                  {scan.fields?.amount && (
                    <div className="vr-field">
                      <b>Amount</b> {rupees(scan.fields.amount.value)}
                      {match?.corroboration && (
                        <span className={match.corroboration.agrees ? "vr-conf" : "vr-warn"}>
                          {match.corroboration.agrees
                            ? "agrees with the record"
                            : `record says ${rupees(match.corroboration.amount_on_record)}`}
                        </span>
                      )}
                    </div>
                  )}

                  {scan.cross_check && <SecondReader check={scan.cross_check} />}

                  {match?.reason && <p className="vr-reason" title={match.reason}>{plainScan(match.reason)}</p>}

                  {match?.alternatives?.length > 0 && (
                    <div className="vr-alts">
                      {match.alternatives.map((a) => (
                        <Link key={a} to={`/case/${a}`} className="vr-alt">{a}</Link>
                      ))}
                    </div>
                  )}

                  <div className="vr-lines">
                    {(scan.lines || []).map((l, i) => <span key={i}>{l.text}</span>)}
                  </div>
                  <p className="vr-note" title={scan.note}>{plainScan(scan.note)}</p>
                </div>
              )}
              {scan?.error && <div className="login-error">{scan.error}</div>}
            </div>
          )}

          {needsAck && (
            <label className="verify-ack">
              <input type="checkbox" checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)} />
              <span>
                I have looked at what is flagged above and this photograph belongs to{" "}
                <b>{workRef}</b>.
              </span>
            </label>
          )}

          <DocumentReader key={docKey} workRef={workRef} onRead={setDoc} />

          <label className="verify-label" htmlFor="outcome">What did you find?</label>
          <select id="outcome" className="select" value={outcome}
            onChange={(e) => setOutcome(e.target.value)}>
            <option value="">— choose what you found —</option>
            {Object.entries(outcomes).map(([key, meaning]) => (
              <option key={key} value={key}>{OUTCOME[key]?.[0] || key.replace(/_/g, " ")} — {OUTCOME[key]?.[1] || meaning}</option>
            ))}
          </select>

          <label className="verify-label" htmlFor="notes">Notes</label>
          <textarea id="notes" className="input verify-notes" rows={3} value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What you saw, who you spoke to, and anything the records do not show." />

          <div className="verify-actions">
            <button className="btn btn-primary" type="submit" disabled={!outcome || saving || blocked}>
              {saving ? "Saving…" : "Save report"}
            </button>
            {blocked && (
              <span className="verify-blocked">Tick the box above to confirm the photo first</span>
            )}
            {saved && <span className="verify-saved">✓ Saved — this report can never be changed</span>}
          </div>
          <p className="verify-foot">
            Signed in as <b>{user?.name}</b>. Verification records are immutable and
            attributed; correcting one means adding a new record, never editing the old.
          </p>
        </form>
      )}
    </div>
  );
}

/** Which reader will read the next photograph, and whether the main one is still starting. */
function ReaderStatus({ readers }) {
  if (!readers) return null;
  const photos = readers.photographs || {};
  const surya = (photos.engines || []).find((e) => e.engine === "surya");
  const docs = readers.documents;
  let photoText;
  if (surya?.loaded) photoText = "Photos are read by Surya OCR, and checked by a second reader.";
  else if (surya?.available) photoText = "Surya OCR is starting up — until it is ready, photos are read by RapidOCR.";
  else if (photos.primary) photoText = "Photos are read by RapidOCR (Surya OCR is not set up on this computer).";
  else photoText = "Reading photos does not work on this computer — type the work number by hand.";
  return (
    <p className="reader-status" title={surya?.failed || (surya?.missing || []).join("; ") || undefined}>
      {photoText}{" "}
      {docs?.available ? "Documents are read by Docling." : "Reading documents is not set up on this computer."}
    </p>
  );
}

/** What the second, independent reader made of the same photograph. */
function SecondReader({ check }) {
  if (check.error) {
    return <div className="vr-field"><b>Second reader</b> <span className="muted">could not read it</span></div>;
  }
  const tone = check.agrees === true ? "vr-conf" : check.agrees === false ? "vr-warn" : "muted";
  const text = check.agrees === true
    ? `${check.engine_label} read the same work number`
    : check.agrees === false
      ? `${check.engine_label} read ${check.work_ref} instead`
      : `${check.engine_label} could not find a work number`;
  return (
    <div className="vr-field">
      <b>Second reader</b>
      <span className={tone}>{check.agrees === true ? "✓ " : ""}{text}</span>
    </div>
  );
}

/** How long the officer should expect to wait, from the last read actually measured. */
function ReadWait({ readers }) {
  const surya = (readers?.photographs?.engines || []).find((e) => e.engine === "surya");
  if (!surya?.available) return null;
  if (!surya.loaded) return <>Surya is still starting, so this one may take a minute.</>;
  const secs = surya.last_read_seconds;
  return <>{secs ? `Surya took about ${Math.round(secs)} seconds last time` : "Surya takes a little while"}, then a second reader checks it.</>;
}
