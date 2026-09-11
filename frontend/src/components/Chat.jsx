import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useI18n } from "../I18nContext.jsx";
import { IconAssistant, IconClose, IconMic } from "./icons.jsx";

/**
 * The assistant panel.
 *
 * It is an *agent* in the narrow, honest sense: it decides which read-only lookups to run
 * against the computed artifacts and shows you which ones it ran. It cannot compute, rank,
 * or write anything. Every figure it prints came out of a tool result, and the tool trace
 * under each answer is how you check that rather than take it on trust.
 *
 * The panel knows which screen you are on and offers questions about *that* — standing on a
 * case file, it offers questions about that work.
 */

/** MPLADS references look like MP3018356-W86316. Anchored so prose never matches. */
const WORK_REF = /\b(MP\d+-W\d+)\b/g;

/** Browser speech codes for the languages the interface actually ships. */
const SPEECH_LANG = {
  en: "en-IN", hi: "hi-IN", bn: "bn-IN", ta: "ta-IN", te: "te-IN", mr: "mr-IN",
  gu: "gu-IN", kn: "kn-IN", ml: "ml-IN", pa: "pa-IN",
};

/* ------------------------------------------------------------------ rendering */

/** Turn one line's inline markup into nodes: **bold** and clickable work references. */
function inline(text, nav, keyPrefix) {
  if (!text) return null;
  return text.split(/(\*\*.*?\*\*)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${keyPrefix}-b${i}`} className="chat-bold">
          {refs(part.slice(2, -2), nav, `${keyPrefix}-b${i}`)}
        </strong>
      );
    }
    return <span key={`${keyPrefix}-t${i}`}>{refs(part, nav, `${keyPrefix}-t${i}`)}</span>;
  });
}

/** Work references become buttons that open the case file. */
function refs(text, nav, keyPrefix) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(WORK_REF)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <button
        key={`${keyPrefix}-r${m.index}`}
        className="chat-ref"
        onClick={() => nav(`/case/${m[1]}`)}
        title={`Open the case file for ${m[1]}`}
      >
        {m[1]}
      </button>
    );
    last = m.index + m[1].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/**
 * Render an answer: paragraphs, bullets, numbered steps and pipe tables.
 *
 * The offline router writes plain prose, but a live model may return light markdown, and a
 * table of states is genuinely easier to read as a table than as a sentence.
 */
function render(text, nav) {
  if (!text) return null;
  const out = [];
  let table = [];

  const flush = (key) => {
    if (!table.length) return;
    const rows = table;
    table = [];
    out.push(
      <div key={`tw-${key}`} className="chat-table-wrap">
        <table className="chat-table">
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className={r === 0 ? "chat-tr-head" : ""}>
                {row.map((cell, c) => <td key={c}>{inline(cell.trim(), nav, `${key}-${r}-${c}`)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  text.split("\n").forEach((line, i) => {
    const s = line.trim();

    if (s.startsWith("|") && s.endsWith("|")) {
      const cells = s.slice(1, -1).split("|");
      if (!cells.every((c) => /^[-: ]*$/.test(c))) table.push(cells);
      return;
    }
    flush(i);

    if (!s) { out.push(<div key={`sp-${i}`} className="chat-gap" />); return; }

    if (s.startsWith("### ")) {
      out.push(
        <h4 key={`h3-${i}`} style={{ margin: "10px 0 4px", fontSize: 13.5, color: "var(--accent)", fontWeight: 700 }}>
          {inline(s.slice(4), nav, `h3${i}`)}
        </h4>
      );
      return;
    }

    if (s.startsWith("• ") || s.startsWith("- ")) {
      out.push(
        <div key={`li-${i}`} className="chat-li">
          <span className="chat-li-mark" aria-hidden="true">▪</span>
          <span>{inline(s.slice(2), nav, `li${i}`)}</span>
        </div>
      );
      return;
    }

    const num = s.match(/^(\d+)\.\s+(.*)$/);
    if (num) {
      out.push(
        <div key={`no-${i}`} className="chat-li">
          <span className="chat-li-num">{num[1]}</span>
          <span>{inline(num[2], nav, `no${i}`)}</span>
        </div>
      );
      return;
    }

    out.push(<p key={`p-${i}`} className="chat-p">{inline(s, nav, `p${i}`)}</p>);
  });

  flush("end");
  return out;
}

/* ------------------------------------------------------------------ component */

export default function Chat() {
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [cap, setCap] = useState(null);
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("all");
  const [copied, setCopied] = useState(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(null);
  const [voiceError, setVoiceError] = useState("");

  const bodyRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const nav = useNavigate();
  const { pathname } = useLocation();
  // One language for the whole product. A second picker inside the panel would let the
  // chrome and the assistant disagree about what language the user is reading.
  const { lang, t } = useI18n();

  useEffect(() => { api.chatCapabilities().then(setCap).catch(() => {}); }, []);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [turns, busy, open]);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      if (wide) setWide(false);
      else setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, wide]);

  // Stop any narration when the panel closes — a voice reading on into a closed panel
  // is startling, and there is no visible control left to stop it.
  useEffect(() => {
    if (!open && window.speechSynthesis) { window.speechSynthesis.cancel(); setSpeaking(null); }
  }, [open]);

  /** Questions about the screen the officer is actually standing on. */
  const contextPrompts = useMemo(() => {
    if (pathname.startsWith("/salesforce")) {
      return [
        "Show HIGH priority cases in Bihar",
        "What is the 5-stage investigation path?",
        "Which case has the highest exposure?",
        "What cases are loaded in Salesforce?",
      ];
    }
    if (pathname.startsWith("/case/")) {
      const ref = decodeURIComponent(pathname.split("/case/")[1] || "");
      return [
        `Tell me about ${ref}`,
        `What evidence flagged ${ref}?`,
        "What does HIGH confidence mean?",
      ];
    }
    if (pathname.startsWith("/worklist")) {
      return ["Show me the top leads", "How are leads ranked?", "What is Audit-ROI?"];
    }
    if (pathname.startsWith("/compliance")) {
      return ["Tell me about compliance checks", "What is the health index?", "What does CRITICAL mean?"];
    }
    if (pathname.startsWith("/trends")) {
      return ["Which agencies changed behaviour?", "What is a change-point?", "How many works in Bihar?"];
    }
    if (pathname.startsWith("/duplicates")) {
      return ["How do you detect duplicates?", "Why are most duplicates not concerning?"];
    }
    if (pathname.startsWith("/transparency")) {
      return ["Can you detect cost overruns?", "What can this data not tell me?", "What models did you train?"];
    }
    if (pathname.startsWith("/archetypes")) {
      return ["What work types did you discover?", "What is the silhouette score?"];
    }
    return ["How many investigation leads are there?", "What does exposure at risk mean?", "Show me the top leads"];
  }, [pathname]);

  async function ask(question) {
    const q = (question || "").trim();
    if (!q || busy) return;
    setDraft("");
    setVoiceError("");
    const history = turns.slice(-10).map((x) => ({ role: x.role, content: x.content }));
    setTurns((prev) => [...prev, { role: "user", content: q }]);
    setBusy(true);
    try {
      const res = await api.chat({ question: q, history, lang });
      setTurns((prev) => [...prev, {
        role: "assistant",
        content: res.text || res.answer || "",
        tools: res.tools_used || [],
        source: res.source,
        model: res.model,
      }]);
    } catch {
      setTurns((prev) => [...prev, {
        role: "assistant",
        source: "error",
        content: t("chat.unreachable",
          "I could not reach the assistant. The system may still be starting — try again in a moment."),
      }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  /* --------------------------------------------------------------- voice */

  function toggleListen() {
    if (listening) { recognitionRef.current?.stop(); setListening(false); return; }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      // Inline, not an alert() — a modal dialog over a live demo is the wrong answer.
      setVoiceError(t("chat.noVoice", "This browser cannot listen. Chrome or Edge can."));
      return;
    }
    try {
      const r = new Recognition();
      r.lang = SPEECH_LANG[lang] || "en-IN";
      r.interimResults = false;
      r.maxAlternatives = 1;
      r.onstart = () => { setListening(true); setVoiceError(""); };
      r.onresult = (e) => { const said = e.results?.[0]?.[0]?.transcript; if (said) ask(said); };
      r.onerror = () => {
        setListening(false);
        setVoiceError(t("chat.voiceFailed", "I could not hear that. Try again, or type it."));
      };
      r.onend = () => setListening(false);
      recognitionRef.current = r;
      r.start();
    } catch {
      setListening(false);
      setVoiceError(t("chat.voiceFailed", "I could not hear that. Try again, or type it."));
    }
  }

  function toggleSpeak(text, i) {
    if (!window.speechSynthesis) return;
    if (speaking === i) { window.speechSynthesis.cancel(); setSpeaking(null); return; }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/[*#|•◈]/g, " ").replace(/\s+/g, " ").trim());
    u.lang = SPEECH_LANG[lang] || "en-IN";
    u.onend = () => setSpeaking(null);
    u.onerror = () => setSpeaking(null);
    setSpeaking(i);
    window.speechSynthesis.speak(u);
  }

  async function copy(text, i) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(i);
      setTimeout(() => setCopied((c) => (c === i ? null : c)), 1800);
    } catch {
      setVoiceError(t("chat.copyFailed", "The browser did not allow copying."));
    }
  }

  function exportTranscript() {
    if (!turns.length) return;
    const body = turns.map((x) => {
      const who = x.role === "user" ? "Question" : "Assistant";
      const trace = x.tools?.length ? `\n\n_Tools used: ${x.tools.join(", ")}_` : "";
      return `## ${who}\n\n${x.content}${trace}`;
    }).join("\n\n---\n\n");
    const header = `# MPLADS assistant transcript\n\n_${new Date().toISOString()}_\n\n` +
      "Every number below was looked up in the results the system had already worked out — nothing was changed or made up.\n\n---\n\n";
    const url = URL.createObjectURL(new Blob([header + body], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `mplads-assistant-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const toolCount = cap?.tools?.length;
  const visiblePrompts = tab === "all"
    ? (cap?.categories || []).flatMap((c) => c.prompts.slice(0, 2))
    : (cap?.categories || []).find((c) => c.category === tab)?.prompts || [];

  return (
    <>
      <button
        className={"chat-fab" + (open ? " open" : "")}
        onClick={() => setOpen((o) => !o)}
        aria-label={t("chat.open", "Ask a question")}
        style={{ display: "flex", alignItems: "center", gap: 8 }}
      >
        <span className="chat-fab-icon" aria-hidden="true">{open ? <IconClose size={16} /> : <IconAssistant size={16} />}</span>
        {!open && <span className="chat-fab-label">Ask the assistant</span>}
      </button>

      {open && (
        <div className={"chat-panel" + (wide ? " wide" : "")} role="dialog"
             aria-label="Agentforce Assistant">
          <div className="chat-head">
            <div className="chat-head-left">
              <span className="chat-avatar" aria-hidden="true"><IconAssistant size={15} /></span>
              <div>
                <div className="chat-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span>Agentforce Assistant</span>
                  <span className="pill pill-green" style={{ fontSize: 9.5, padding: "1px 6px" }}>CRM Connected</span>
                </div>
                <div className="chat-sub">
                  <i className="chat-dot" aria-hidden="true" />
                  {cap
                    ? `${toolCount} tools · Agentforce Topic: Investigation Lookup`
                    : "connecting…"}
                </div>
              </div>
            </div>
            <div className="chat-head-actions">
              {turns.length > 0 && (
                <>
                  <button className="chat-head-btn" onClick={exportTranscript}
                          title={t("chat.export", "Save the conversation")}>⭳</button>
                  <button className="chat-head-btn" onClick={() => setTurns([])}
                          title={t("chat.clear", "Clear the conversation")}>⌫</button>
                </>
              )}
              <button className="chat-head-btn" onClick={() => setWide((w) => !w)}
                      title={wide ? t("chat.restore", "Restore") : t("chat.expand", "Expand")}>
                {wide ? "⤡" : "⤢"}
              </button>
              <button className="chat-head-btn close" onClick={() => setOpen(false)}
                      title={t("chat.close", "Close")}>✕</button>
            </div>
          </div>

          <div className="chat-body" ref={bodyRef}>
            {turns.length === 0 && (
              <div className="chat-intro">
                <p className="chat-intro-lead">
                  {t("chat.introLead",
                     "I only answer by looking things up in the results the system has already worked out. I don't know anything else about this data and I don't do my own sums, so I can't make up a number — and I show you where each answer came from.")}
                </p>

                <div className="chat-label">{t("chat.forThisScreen", "About this page")}</div>
                <div className="chat-chips">
                  {contextPrompts.map((p) => (
                    <button key={p} className="chat-chip context" onClick={() => ask(p)}>
                      <span className="chat-chip-arrow" aria-hidden="true">→</span>{p}
                    </button>
                  ))}
                </div>

                {cap?.categories?.length > 0 && (
                  <>
                    <div className="chat-label">{t("chat.orAsk", "Or ask about")}</div>
                    <div className="chat-tabs">
                      <button className={"chat-tab" + (tab === "all" ? " active" : "")}
                              onClick={() => setTab("all")}>{t("chat.all", "All")}</button>
                      {cap.categories.map((c) => (
                        <button key={c.category}
                                className={"chat-tab" + (tab === c.category ? " active" : "")}
                                onClick={() => setTab(c.category)}>
                          <span aria-hidden="true">{c.icon}</span> {c.category}
                        </button>
                      ))}
                    </div>
                    <div className="chat-chips">
                      {visiblePrompts.map((p) => (
                        <button key={p} className="chat-chip" onClick={() => ask(p)}>
                          <span className="chat-chip-arrow" aria-hidden="true">→</span>{p}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {turns.map((turn, i) => (
              <div key={i} className={"chat-turn " + turn.role}>
                <div className="chat-row">
                  {turn.role === "assistant" && <span className="chat-turn-avatar" aria-hidden="true"><IconAssistant size={12} /></span>}
                  <div className={"chat-bubble" + (turn.source === "error" ? " error" : "")}>
                    {turn.role === "assistant" ? render(turn.content, nav) : turn.content}

                    {turn.role === "assistant" && turn.source !== "error" && (
                      <div className="chat-bubble-actions">
                        <button className="chat-action" onClick={() => copy(turn.content, i)}>
                          {copied === i ? t("chat.copied", "Copied") : t("chat.copy", "Copy")}
                        </button>
                        <button className={"chat-action" + (speaking === i ? " active" : "")}
                                onClick={() => toggleSpeak(turn.content, i)}>
                          {speaking === i ? t("chat.stop", "Stop") : t("chat.listen", "Listen")}
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {turn.role === "assistant" && turn.tools?.length > 0 && (
                  <div className="chat-trace">
                    <span className="chat-trace-label">{t("chat.lookedUp", "Looked up")}</span>
                    {turn.tools.map((tool) => (
                      <span key={tool} className="chat-tool">{tool.replace(/^t_/, "")}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {busy && (
              <div className="chat-turn assistant">
                <div className="chat-row">
                  <span className="chat-turn-avatar" aria-hidden="true"><IconAssistant size={12} /></span>
                  <div className="chat-bubble chat-typing">
                    <i /><i /><i />
                    <span className="chat-typing-text">{t("chat.working", "Looking it up…")}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {voiceError && <div className="chat-notice">{voiceError}</div>}

          <form className="chat-input-row" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
            <button type="button"
                    className={"chat-voice" + (listening ? " listening" : "")}
                    onClick={toggleListen}
                    title={listening ? t("chat.stopListening", "Stop listening")
                                     : t("chat.speak", "Ask by speaking")}>
              {listening ? <span className="chat-voice-pulse" /> : <IconMic size={15} />}
            </button>
            <input
              className="input chat-input"
              placeholder={t("chat.placeholder", "Ask about a work, a state, or the numbers…")}
              value={draft}
              ref={inputRef}
              onChange={(e) => setDraft(e.target.value)}
              /* readOnly, never disabled — disabling blurs the box and every follow-up
                 question would need a fresh click. */
              readOnly={busy}
            />
            <button className="btn btn-primary chat-send" type="submit" disabled={busy || !draft.trim()}>
              {t("chat.send", "Send")}
            </button>
          </form>
        </div>
      )}
    </>
  );
}
