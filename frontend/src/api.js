const base = "";

/** Where the API is expected. Kept here so no screen hard-codes a port that can drift. */
export const API_PORT = 8020;
export const API_START_HINT =
  `python -m uvicorn mplads.api.app:app --host 0.0.0.0 --port ${API_PORT}`;

let authToken = null;
export function _setToken(tok) { authToken = tok; }
const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});

/**
 * The badge we are holding is no longer accepted — a twelve-hour token that has expired,
 * or one signed before a restart changed the key.
 *
 * This was a genuinely nasty failure. Reading is open in this deployment, so *most* screens
 * kept working; only the handful that check identity — the audit plan, the field rota, the
 * day pack — returned 401, for as long as the dead token sat in localStorage. Nothing ever
 * cleared it. The result reads as "those two pages are broken" rather than "you are signed
 * out", which is what it actually is.
 *
 * The server is right to reject it rather than quietly downgrade a scoped officer to an
 * unrestricted reader, so the correction belongs here: drop the credential, tell the app,
 * and fall back to the open-data reader that this deployment allows.
 */
function expireSession() {
  authToken = null;
  try {
    localStorage.removeItem("mplads.session");
  } catch { /* private mode — nothing to clear */ }
  window.dispatchEvent(new CustomEvent("mplads:session-expired"));
}

async function request(path, init = {}) {
  const withAuth = { ...init, headers: { ...(init.headers || {}), ...authHeaders() } };
  let res = await fetch(base + path, withAuth);
  if (res.status === 401 && authToken) {
    expireSession();
    // Retry once as the open-data reader. If this deployment required a badge to read,
    // this second attempt fails too and the error surfaces honestly.
    res = await fetch(base + path, init);
  }
  return res;
}

async function get(path) {
  const res = await request(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  stats: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/api/stats?${q}`);
  },
  states: () => get("/api/states"),
  models: () => get("/api/models"),
  /** Liveness and engine version — polled by the status indicator in the masthead. */
  health: () => get("/api/health"),
  roles: () => get("/api/roles"),
  setToken: _setToken,
  login: (username, password) =>
    fetch("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }),
  demoAccounts: () => get("/api/auth/accounts"),
  ocr: (file, workRef) => {
    const form = new FormData();
    form.append("file", file);
    // The work the officer is standing on, so a photograph already submitted for a
    // *different* sanction is reported and one re-taken for this work is not.
    if (workRef) form.append("work_ref", workRef);
    return fetch("/api/ocr", { method: "POST", headers: authHeaders(), body: form })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); });
  },
  /** A sanction order, work order or certificate (PDF or photo), read by Docling. */
  ocrDocument: (file, workRef) => {
    const form = new FormData();
    form.append("file", file);
    if (workRef) form.append("work_ref", workRef);
    return fetch("/api/ocr/document", { method: "POST", headers: authHeaders(), body: form })
      .then(async (r) => {
        if (!r.ok) {
          const detail = await r.json().then((d) => d.detail).catch(() => null);
          throw new Error(detail || String(r.status));
        }
        return r.json();
      });
  },
  /** Which readers this machine has and whether the photograph reader is ready. */
  ocrStatus: () => get("/api/ocr/status"),
  verifications: (ref) => get(`/api/verify/${encodeURIComponent(ref)}`),
  verify: (ref, body) =>
    fetch(`/api/verify/${encodeURIComponent(ref)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }),
  fieldSummary: () => get("/api/field/summary"),
  casework: (ref) => get(`/api/case/${encodeURIComponent(ref)}/casework`),
  auditPlan: (budgetDays) => get(`/api/audit-plan?budget_days=${budgetDays}`),
  auditAssignments: (budgetDays, auditors) =>
    get(`/api/audit-plan/assignments?budget_days=${budgetDays}&auditors=${auditors}`),
  // The day pack opens in a tab for the same reason the case report does: an officer
  // reads it before deciding to print it and carry it.
  dayPackUrl: (auditor, budgetDays, auditors) =>
    `/api/audit-plan/assignments/${auditor}/pack.pdf`
    + `?budget_days=${budgetDays}&auditors=${auditors}`,
  agencies: (limit = 40) => get(`/api/agencies?limit=${limit}`),
  agency: (name) => get(`/api/agency/${encodeURIComponent(name)}`),
  calibration: () => get("/api/calibration"),
  salesforceAgeing: () => get("/api/salesforce/ageing"),
  // The report opens in a tab rather than downloading through fetch: the browser renders
  // a PDF natively, and an officer usually wants to read it before deciding to keep it.
  caseReportUrl: (ref) => `/api/case/${encodeURIComponent(ref)}/report.pdf`,
  languages: () => get("/api/languages"),
  chatCapabilities: () => get("/api/chat/capabilities"),
  chat: (body) =>
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    }),
  strings: (lang) => get(`/api/strings?lang=${encodeURIComponent(lang)}`),
  portfolioInsight: (p = {}) => {
    const q = new URLSearchParams(
      Object.entries(p).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/api/insight/portfolio?${q}`);
  },
  caseInsight: (ref, lang = "en") =>
    get(`/api/insight/case/${encodeURIComponent(ref)}?lang=${encodeURIComponent(lang)}`),
  temporal: () => get("/api/temporal"),
  transparency: () => get("/api/transparency"),
  compliance: () => get("/api/compliance"),
  earlyWarning: () => get("/api/early-warning"),
  healthIndex: () => get("/api/health-index"),
  archetypes: () => get("/api/archetypes"),
  duplicates: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/api/duplicates?${q}`);
  },
  worklist: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/api/worklist?${q}`);
  },
  case: (ref) => get(`/api/case/${encodeURIComponent(ref)}`),
  salesforceOverview: () => get("/api/salesforce/overview"),
  salesforceCases: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/api/salesforce/cases?${q}`);
  },
  salesforceCase: (ref) => get(`/api/salesforce/case/${encodeURIComponent(ref)}`),
  updateSalesforceStage: (body) =>
    fetch("/api/salesforce/update-stage", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }),
  agentforceQuery: (question, lang = "en") =>
    fetch("/api/agentforce/query", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ question, lang }),
    }).then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }),
};

/**
 * Indian-convention rupee figure. Large crore values are grouped, so the national
 * total reads "₹11,565 Cr" rather than "₹11565.47 Cr" — and drops the paise, which
 * are noise at that magnitude.
 */
export function rupees(n) {
  if (n == null) return "—";
  const grouped = (v, digits) =>
    v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  if (n >= 1e7) {
    const cr = n / 1e7;
    return `₹${grouped(cr, cr >= 1000 ? 0 : 2)} Cr`;
  }
  if (n >= 1e5) return `₹${grouped(n / 1e5, 2)} L`;
  if (n >= 1e3) return `₹${grouped(n / 1e3, 0)}K`;
  return `₹${grouped(Math.round(n), 0)}`;
}

export function num(n) {
  return n == null ? "—" : Number(n).toLocaleString("en-IN");
}
