import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, rupees } from "../api.js";

/**
 * Read a paper document an officer holds — a sanction order, work order or completion
 * certificate — with Docling, and say which works it mentions.
 *
 * A document is not a board. It can name several works, it has tables, and the reference
 * the officer is here for may simply not be in it. So this lists every work number found,
 * checks each against the records, and says plainly whether *this* work is among them.
 * Nothing here is saved on its own: the document travels with the site-visit report.
 */
export default function DocumentReader({ workRef, onRead }) {
  const [doc, setDoc] = useState(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const [showText, setShowText] = useState(false);
  const inputRef = useRef(null);

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setReading(true);
    setError("");
    setDoc(null);
    setShowText(false);
    try {
      const res = await api.ocrDocument(file, workRef);
      setDoc(res);
      onRead?.(res);
    } catch (err) {
      setError(`Could not read that document: ${err.message}`);
      onRead?.(null);
    } finally {
      setReading(false);
    }
  }

  function clear() {
    setDoc(null);
    setError("");
    onRead?.(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const refs = doc?.refs_found || [];

  return (
    <div className="doc-reader">
      <label className="verify-label" htmlFor="doc-file">
        Attach a document (optional) — sanction order, work order or certificate
      </label>
      <input id="doc-file" ref={inputRef} type="file" className="verify-file"
        accept="application/pdf,.pdf,image/*" onChange={onFile} />

      {reading && (
        <div className="verify-scanning">
          Reading the document… a scanned page can take a minute.
        </div>
      )}
      {error && <div className="login-error">{error}</div>}

      {doc && (
        <div className="verify-read">
          <div className="vr-head">
            Read by {doc.engine_label || "Docling"}
            {doc.pages ? ` · ${doc.pages} page${doc.pages === 1 ? "" : "s"}` : ""}
            {doc.seconds != null ? ` · ${doc.seconds} s` : ""}
            <button type="button" className="doc-clear" onClick={clear}>remove</button>
          </div>

          {doc.error ? (
            <p className="vr-reason">{doc.error}</p>
          ) : (
            <>
              <div className={"doc-verdict " + (doc.mentions_this_work ? "ok" : "warn")}>
                {doc.mentions_this_work
                  ? <>✓ This document mentions <b>{workRef}</b>.</>
                  : refs.length
                    ? <>This document does not mention <b>{workRef}</b>. Check it is the right paper.</>
                    : <>No work number was found in this document.</>}
              </div>

              {refs.length > 0 && (
                <div className="doc-refs">
                  <div className="m-label">Work numbers found ({refs.length})</div>
                  {refs.map((r) => (
                    <div key={r.work_ref} className="doc-ref">
                      {r.known
                        ? <Link to={`/case/${r.work_ref}`} className="plan-ref">{r.work_ref}</Link>
                        : <span className="plan-ref doc-unknown">{r.work_ref}</span>}
                      <span className={r.known ? "vr-conf" : "vr-warn"}>
                        {r.known ? "in the records" : "not in the records"}
                      </span>
                      {!r.known && r.alternatives?.length > 0 && (
                        <span className="doc-alts">
                          close to {r.alternatives.map((a) => (
                            <Link key={a} to={`/case/${a}`} className="vr-alt">{a}</Link>
                          ))}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {doc.amounts?.length > 0 && (
                <div className="vr-field">
                  <b>Amounts</b> {doc.amounts.slice(0, 4).map((a) => rupees(a)).join(" · ")}
                </div>
              )}

              <button type="button" className="doc-toggle" onClick={() => setShowText((v) => !v)}>
                {showText ? "Hide the text" : "Show the text the computer read"}
              </button>
              {showText && <pre className="doc-text">{doc.markdown || "(no text)"}</pre>}
              <p className="vr-note">
                This is only what the computer read from the document. It has not been checked
                against any record — read the document itself before relying on it.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
