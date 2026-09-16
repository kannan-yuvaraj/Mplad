import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Overview from "./pages/Overview.jsx";
import Worklist from "./pages/Worklist.jsx";
import CaseFile from "./pages/CaseFile.jsx";
import HowItWorks from "./pages/HowItWorks.jsx";
import Trends from "./pages/Trends.jsx";
import Duplicates from "./pages/Duplicates.jsx";
import Transparency from "./pages/Transparency.jsx";
import Archetypes from "./pages/Archetypes.jsx";
import SalesforceHub from "./pages/SalesforceHub.jsx";
import AuditPlan from "./pages/AuditPlan.jsx";
import FieldRota from "./pages/FieldRota.jsx";
import AgencyDossier from "./pages/AgencyDossier.jsx";
import Scoreboard from "./pages/Scoreboard.jsx";
import Workflow from "./pages/Workflow.jsx";
import Submit from "./pages/Submit.jsx";
import StateMap from "./pages/StateMap.jsx";
import PublicView from "./pages/PublicView.jsx";
import Vendors from "./pages/Vendors.jsx";
import EvidenceLedger from "./pages/EvidenceLedger.jsx";
import { RoleProvider, RoleSwitcher, useRole } from "./RoleContext.jsx";
import { useScrollProgress } from "./hooks.js";
import { LanguageSwitcher } from "./I18nContext.jsx";
import Chat from "./components/Chat.jsx";
import Logo from "./components/Logo.jsx";
import Login from "./pages/Login.jsx";
import { useAuth } from "./AuthContext.jsx";
import { Topbar } from "./components/Bits.jsx";
import { SECTIONS, resolveRoute } from "./nav.js";
import {
  Breadcrumbs,
  DisplayControls,
  GovFooter,
  SystemStatus,
  IdentityStrip,
  Masthead,
  PrimaryNav,
  PrototypeNotice,
} from "./components/GovChrome.jsx";
import { useI18n } from "./I18nContext.jsx";

function Sidebar() {
  const link = ({ isActive }) => "nav-link" + (isActive ? " active" : "");
  const { role, scope, meta } = useRole();
  const { t } = useI18n();
  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand">
        <Logo size={38} className="brand-logo" />
        <div>
          <div className="brand-name">MPLADS Intelligence</div>
          <div className="brand-sub">{t("shell.brandSub", "Public Works Monitoring")}</div>
        </div>
      </NavLink>

      {/* A real navigation landmark, so "next landmark" reaches the section
          links rather than skipping from the primary nav to the page body. */}
      <nav className="sidebar-nav-scroll" aria-label={t("gov.sectionLinks", "Sections in this module")}>
        {SECTIONS.map((group) => (
          <div key={group.id}>
            <div className="nav-group-label"><span className="nav-step" aria-hidden="true">{group.step}</span>{t(group.key, group.label)}</div>
            {group.items.map((item) => (
              <NavLink key={item.to} to={item.to} className={link}>
                <span className="ic"><item.Icon size={15} /></span>
                {t(item.key, item.label)}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        {meta && (
          <div style={{ marginBottom: 12 }}>
            {t("shell.viewingAs", "Viewing as")}{" "}
            <b style={{ color: "var(--text-2)" }}>{meta.roles[role]?.label}</b>
            {scope && <> · {scope}</>}
          </div>
        )}
        {t("shell.chain", "Learn what is normal · Compare · Predict · Explain · Put in order")}
        <br />
        <br />
        {t("shell.leadsNotVerdicts",
           "These are works worth checking — not proof that anyone did wrong. A person always decides what happens next.")}
      </div>
    </aside>
  );
}

/**
 * Scroll to top whenever the route changes — dashboards should not inherit scroll.
 *
 * `"instant" in window` was checking for a property nothing defines, so it always
 * fell through to "auto", which honours `html { scroll-behavior: smooth }` and
 * animated the jump. "instant" is the valid keyword and is what was intended.
 */
function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}

/**
 * Name the browser tab after the page, the way a deployed service does — a tab
 * strip of eight identical "MPLADS Intelligence" tabs is the clearest sign of a
 * demo. Reads the same route table as the navigation.
 */
function DocumentTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    const suite = "MPLADS eSAKSHI";
    let name;
    if (pathname === "/") name = "Public Works Monitoring";
    else if (pathname === "/login") name = "Officer Sign-In";
    else if (pathname.startsWith("/case/")) name = `Case File ${decodeURIComponent(pathname.slice(6))}`;
    else name = resolveRoute(pathname)?.label || "Page not found";
    document.title = `${name} · ${suite}`;
  }, [pathname]);
  return null;
}

/** An unknown URL used to render the shell with an empty body and no explanation. */
function NotFound() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  return (
    <>
      <Topbar title={t("common.notFound", "Page not found")} sub={pathname} />
      <div className="content">
        <div className="empty">
          {t("common.notFoundBody", "There is nothing at this address.")}{" "}
          <Link to="/overview" className="link">
            {t("common.notFoundCta", "Go to the Detection Centre")}
          </Link>
        </div>
      </div>
    </>
  );
}

function SessionChip() {
  const { user, logout } = useAuth();
  if (!user) {
    return <NavLink to="/login" className="btn" style={{ padding: "6px 14px" }}>Sign in</NavLink>;
  }
  return (
    <span className="session-chip">
      <b>{user.name}</b>
      <button onClick={logout} title="Sign out">Sign out</button>
    </span>
  );
}

function ScopeNote() {
  const { user } = useAuth();
  if (!user) {
    return (
      <span className="muted scope-note">
        Changing the view shows the same facts the way a different official would see them —
        it does not give you any extra access. Sign in to write a site visit report.
      </span>
    );
  }
  return (
    <span className="muted scope-note">
      Signed in as <b>{user.role}</b>
      {user.scope ? <> · can only see <b>{user.scope}</b></> : <> · can see all of India</>}
      {" "}· everything you do is recorded in a log that cannot be changed.
    </span>
  );
}

function Shell() {
  const { pathname } = useLocation();
  const { t } = useI18n();
  const progress = useScrollProgress();
  const isLanding = pathname === "/";
  const isLogin = pathname === "/login";

  return (
    <div className="gov-page">
      <a className="skip-link" href="#main-content">
        {t("a11y.skip", "Skip to main content")}
      </a>
      <div className="scroll-progress" style={{ width: `${progress * 100}%` }} />
      <ScrollReset />
      <DocumentTitle />

      <IdentityStrip />
      <Masthead
        utility={
          <>
            <SystemStatus />
            <DisplayControls />
            <LanguageSwitcher />
            <SessionChip />
          </>
        }
      />
      <PrimaryNav />

      {isLanding || isLogin ? (
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
          </Routes>
        </main>
      ) : (
        <div className="shell">
          <Sidebar />
          <div className="main">
            <div className="role-bar">
              <span className="role-bar-label">
                {t("shell.stakeholder", "View as")}
              </span>
              <RoleSwitcher />
              <ScopeNote />
            </div>
            <Breadcrumbs />
            <main id="main-content" tabIndex={-1}>
            <Routes>
              <Route path="/overview" element={<Overview />} />
              <Route path="/worklist" element={<Worklist />} />
              <Route path="/audit-plan" element={<AuditPlan />} />
              <Route path="/rota" element={<FieldRota />} />
              <Route path="/agency" element={<AgencyDossier />} />
              <Route path="/agency/:name" element={<AgencyDossier />} />
              <Route path="/scoreboard" element={<Scoreboard />} />
              <Route path="/salesforce" element={<SalesforceHub />} />
              <Route path="/trends" element={<Trends />} />
              <Route path="/duplicates" element={<Duplicates />} />
              <Route path="/archetypes" element={<Archetypes />} />
              <Route path="/transparency" element={<Transparency />} />
              <Route path="/workflow" element={<Workflow />} />
              <Route path="/submit" element={<Submit />} />
              <Route path="/map" element={<StateMap />} />
              <Route path="/public" element={<PublicView />} />
              <Route path="/vendors" element={<Vendors />} />
              <Route path="/evidence" element={<EvidenceLedger />} />
              <Route path="/how" element={<HowItWorks />} />
              <Route path="/case/:ref" element={<CaseFile />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
            </main>
            <Chat />
          </div>
        </div>
      )}

      <PrototypeNotice />
      <GovFooter />
    </div>
  );
}

export default function App() {
  return (
    <RoleProvider>
      <Shell />
    </RoleProvider>
  );
}
