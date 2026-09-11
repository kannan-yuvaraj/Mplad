import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Logo, { NationalLockup } from "./Logo.jsx";
import { IconContrast, IconExternal } from "./icons.jsx";
import { useI18n } from "../I18nContext.jsx";
import { SECTIONS, resolveRoute, sectionFor } from "../nav.js";
import { api } from "../api.js";

/**
 * The eSAKSHI extract this deployment was built from (config.SNAPSHOT_DATE). The
 * API does not expose it, so it is stated once, here, and read everywhere else.
 * It is the date the data describes — not the date anyone opened the page.
 */
export const DATA_SNAPSHOT = "26 May 2026";

/**
 * Whether the engine is answering, polled once a minute. A console that shows
 * "online" without asking is decoration; this asks.
 */
export function useEngineHealth(everyMs = 60000) {
  const [h, setH] = useState({ state: "wait" });
  useEffect(() => {
    let live = true;
    const ping = () =>
      api.health()
        .then((d) => live && setH({ state: d.status === "ok" ? "ok" : "down", version: d.version }))
        .catch(() => live && setH({ state: "down" }));
    ping();
    const t = setInterval(ping, everyMs);
    return () => { live = false; clearInterval(t); };
  }, [everyMs]);
  return h;
}

/** The status chip in the masthead utility row. */
export function SystemStatus() {
  const h = useEngineHealth();
  const label = h.state === "ok" ? "System online" : h.state === "down" ? "System not reachable" : "Connecting…";
  return (
    <span className="sys-status" role="status" title={`Data: eSAKSHI snapshot of ${DATA_SNAPSHOT}`}>
      <span className={"live-dot " + (h.state === "ok" ? "" : h.state)} aria-hidden="true" />
      <b>{label}</b>
      {h.version && <span>· v{h.version}</span>}
    </span>
  );
}

/* ============================================================================
   The Government of India portal chrome.

   The stack — identity strip, tricolour rule, masthead, primary navigation,
   notice ticker, breadcrumb, footer — is the arrangement shared by india.gov.in,
   mospi.gov.in and the NIC-built scheme portals. It is the frame; the console
   sits inside it.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   Display preferences: text size and contrast.

   GIGW asks for both by name. They are real controls, not decoration: the whole
   type scale in tokens.css is derived from --font-scale, and the high-contrast
   mode redefines the palette rather than filtering it. Both persist, and both
   are written onto <html> so CSS alone applies them.
   --------------------------------------------------------------------------- */
const SIZE_KEY = "mplads.textSize";
const CONTRAST_KEY = "mplads.contrast";

export function useDisplayPrefs() {
  const [textSize, setTextSize] = useState(() => {
    try { return localStorage.getItem(SIZE_KEY) || "normal"; } catch { return "normal"; }
  });
  const [contrast, setContrast] = useState(() => {
    try { return localStorage.getItem(CONTRAST_KEY) || "normal"; } catch { return "normal"; }
  });

  useEffect(() => {
    document.documentElement.dataset.textSize = textSize;
    try { localStorage.setItem(SIZE_KEY, textSize); } catch { /* private mode */ }
  }, [textSize]);

  useEffect(() => {
    document.documentElement.dataset.contrast = contrast;
    try { localStorage.setItem(CONTRAST_KEY, contrast); } catch { /* private mode */ }
  }, [contrast]);

  return { textSize, setTextSize, contrast, setContrast };
}

/** The A- / A / A+ and contrast controls. */
export function DisplayControls() {
  const { textSize, setTextSize, contrast, setContrast } = useDisplayPrefs();
  const { t } = useI18n();
  const sizes = [
    ["small", "A-", t("a11y.textSmall", "Decrease text size"), "a-sm"],
    ["normal", "A", t("a11y.textNormal", "Normal text size"), "a-md"],
    ["large", "A+", t("a11y.textLarge", "Increase text size"), "a-lg"],
  ];
  return (
    <>
      <div className="gov-util-group" role="group"
           aria-label={t("a11y.textSizeGroup", "Text size")}>
        {sizes.map(([value, glyph, label, cls]) => (
          <button
            key={value}
            type="button"
            className={`gov-util-btn ${cls}`}
            aria-pressed={textSize === value}
            aria-label={label}
            title={label}
            onClick={() => setTextSize(value)}
          >
            {glyph}
          </button>
        ))}
      </div>
      <div className="gov-util-group">
        <button
          type="button"
          className="gov-util-btn"
          aria-pressed={contrast === "high"}
          aria-label={t("a11y.contrast", "High contrast")}
          title={t("a11y.contrast", "High contrast")}
          onClick={() => setContrast(contrast === "high" ? "normal" : "high")}
        >
          <IconContrast size={13} />
        </button>
      </div>
    </>
  );
}

/* -------------------------------------------------------------- identity strip */
export function IdentityStrip() {
  const { t } = useI18n();
  return (
    <>
      <div className="gov-identity">
        <div className="gov-identity-inner">
          <span className="goi">
            <NationalLockup />
          </span>
          <span className="sep" aria-hidden="true">|</span>
          <span>{t("gov.ministry", "Ministry of Statistics and Programme Implementation")}</span>
          <span className="gov-identity-right">
            <a href="https://www.india.gov.in/" target="_blank" rel="noopener noreferrer">
              {t("gov.nationalPortal", "National Portal of India")}
              <IconExternal size={10} style={{ marginLeft: 4, verticalAlign: -1 }} />
            </a>
            <a href="https://www.mospi.gov.in/" target="_blank" rel="noopener noreferrer">
              MoSPI
              <IconExternal size={10} style={{ marginLeft: 4, verticalAlign: -1 }} />
            </a>
          </span>
        </div>
      </div>
      <div className="tricolour-rule" aria-hidden="true" />
    </>
  );
}

/* -------------------------------------------------------------------- masthead */
export function Masthead({ utility }) {
  const { t } = useI18n();
  return (
    <header className="gov-masthead">
      <div className="gov-masthead-inner">
        <Link to="/" className="gov-emblem" aria-label={t("gov.home", "MPLADS eSAKSHI home")}>
          <Logo size={44} />
        </Link>

        <div className="gov-lockup">
          <div className="ministry-hi" lang="hi">सांख्यिकी और कार्यक्रम कार्यान्वयन मंत्रालय</div>
          <div className="ministry-en">Ministry of Statistics &amp; Programme Implementation</div>
          <div className="goi-line">{t("gov.goi", "Government of India")}</div>
        </div>

        <div className="gov-scheme">
          <div className="scheme-name">
            MPLADS<span className="dot" aria-hidden="true">·</span>eSAKSHI
          </div>
          <div className="scheme-sub">
            {t("gov.tagline", "Computer help for checking public works")
              .replace("&amp;", "&")}
          </div>
        </div>

        <div className="gov-utility">{utility}</div>
      </div>
    </header>
  );
}

/* ---------------------------------------------------------------- primary nav */
export function PrimaryNav() {
  const { pathname } = useLocation();
  const { t } = useI18n();
  const current = sectionFor(pathname);
  return (
    <nav className="gov-primary-nav" aria-label={t("gov.primaryNav", "Primary navigation")}>
      <div className="gov-primary-nav-inner">
        {SECTIONS.map((section) => {
          const first = section.items[0];
          const active = current?.id === section.id;
          return (
            <Link
              key={section.id}
              to={first.to}
              className={"gov-nav-item" + (active ? " active" : "")}
              aria-current={active ? "true" : undefined}
            >
              <span className="nav-step" aria-hidden="true">{section.step}</span>
              {t(section.key, section.label)}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/* -------------------------------------------------------------- notice ticker
   A standing element on Indian scheme portals. Ours carries the constraints a
   viewer must not miss, which is exactly what a notice band is for. */
export function NoticeTicker() {
  const { t } = useI18n();
  const [sil, setSil] = useState(null);
  useEffect(() => {
    api.models().then((m) => setSil(m?.archetype_clustering?.silhouette_at_chosen_k)).catch(() => {});
  }, []);
  const notices = [
    t("ticker.leads", "This system points out works worth checking — it never says anything is fraud. A person decides every action."),
    t("ticker.ground", "Only a visit to the site is real proof: no record says which works really had problems."),
    `Archetype separation (silhouette) is ${sil != null ? sil.toFixed(3) : "…"} — a separation measure, never an accuracy.`,
    t("ticker.amount", "The public data does not show how much was really spent, so we never say money was overspent."),
  ];
  // The track is rendered twice so the marquee wraps seamlessly at -50%.
  const run = [...notices, ...notices];
  return (
    <div className="gov-ticker">
      <span className="gov-ticker-label">{t("ticker.label", "Advisory")}</span>
      <div className="gov-ticker-view">
        <div className="gov-ticker-track">
          {run.map((n, i) => (
            <span className="gov-ticker-item" key={i} aria-hidden={i >= notices.length}>{n}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ breadcrumb */
export function Breadcrumbs({ trail }) {
  const { pathname } = useLocation();
  const { t } = useI18n();
  const page = resolveRoute(pathname);

  const crumbs = trail || [
    { label: t("gov.home", "Home"), to: "/" },
    ...(page?.sectionLabel
      ? [{ label: t(page.sectionKey, page.sectionLabel), to: null }]
      : []),
    ...(page ? [{ label: t(page.key, page.label), to: null, current: true }] : []),
  ];

  return (
    <nav className="gov-breadcrumb" aria-label={t("gov.breadcrumb", "Breadcrumb")}>
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} style={{ display: "inline-flex", gap: 7, alignItems: "center" }}>
          {i > 0 && <span className="sep" aria-hidden="true">›</span>}
          {c.to && !c.current ? (
            <Link to={c.to}>{c.label}</Link>
          ) : (
            <span aria-current={i === crumbs.length - 1 ? "page" : undefined}>{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}


/* ---------------------------------------------------------------------- footer
   The mandated disclosure block. Nothing here is invented: there is no fabricated
   helpline, no claimed NIC attribution, and the prototype status is stated
   plainly rather than buried. */
export function GovFooter() {
  const { t } = useI18n();
  const health = useEngineHealth(120000);
  return (
    <>
      <div className="tricolour-rule" aria-hidden="true" />
      <footer className="gov-footer">
        <div className="gov-footer-inner">
          <div className="gov-footer-org">
            <Logo size={38} />
            <div>
              <h2>{t("footer.scheme", "The Scheme")}</h2>
              <p>
                <strong>MPLADS · eSAKSHI</strong>
                <br />
                {t("footer.schemeBody",
                   "Members of Parliament Local Area Development Scheme — keeping an eye on every step of each work, under the Ministry of Statistics and Programme Implementation.")}
              </p>
            </div>
          </div>

          <div>
            <h2>{t("footer.sections", "Sections")}</h2>
            <ul>
              {SECTIONS.flatMap((s) => s.items).map((i) => (
                <li key={i.to}><Link to={i.to}>{t(i.key, i.label)}</Link></li>
              ))}
            </ul>
          </div>

          <div>
            <h2>{t("footer.related", "Related Portals")}</h2>
            <ul>
              <li>
                <a href="https://www.india.gov.in/" target="_blank" rel="noopener noreferrer">
                  National Portal of India
                </a>
              </li>
              <li>
                <a href="https://www.mospi.gov.in/" target="_blank" rel="noopener noreferrer">
                  Ministry of Statistics &amp; PI
                </a>
              </li>
              <li>
                <a href="https://www.mplads.gov.in/" target="_blank" rel="noopener noreferrer">
                  MPLADS Portal
                </a>
              </li>
              <li>
                <a href="https://guidelines.india.gov.in/" target="_blank" rel="noopener noreferrer">
                  GIGW Guidelines
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h2>{t("footer.aboutPortal", "About This Portal")}</h2>
            <p>
              {t("footer.aboutBody",
                 "Built for Smart India Hackathon 2026, problem statement SIH26102, by Team Morior Invictus. It reads the public MPLADS records and shows which works most deserve an officer's attention.")}
            </p>
            <p style={{ marginTop: 8 }}>
              <strong>{t("footer.owner", "Content owned by")}</strong>{" "}
              {t("footer.ownerBody", "Team Morior Invictus — this is a prototype, not an official government service.")}
            </p>
          </div>
        </div>

        <div className="gov-footer-bar">
          <div className="gov-footer-bar-inner">
            <span>
              {t("footer.leads", "Works worth checking, never proof of fraud. A person decides every action.")}
            </span>
            <span className="right">
              {t("footer.snapshot", "Data snapshot")}: {DATA_SNAPSHOT}{health.version ? ` · System version ${health.version}` : ""}
            </span>
          </div>
        </div>
      </footer>
    </>
  );
}

/**
 * The prototype disclaimer.
 *
 * A government-styled interface that is not a government service has to say so
 * where it cannot be missed, not only in the footer.
 */
export function PrototypeNotice() {
  const { t } = useI18n();
  return (
    <div className="gov-disclaimer" role="note">
      <strong>{t("disclaimer.label", "Disclaimer")}:</strong>{" "}
      {t("disclaimer.body",
         "Made for Smart India Hackathon 2026 (SIH26102, Ministry of Statistics and Programme Implementation) using public MPLADS / eSAKSHI data. This is not an official Government of India website, and nothing on it is an official finding.")}
    </div>
  );
}
