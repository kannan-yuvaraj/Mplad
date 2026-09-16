import {
  IconAgency,
  IconArchetype,
  IconCasework,
  IconDashboard,
  IconDuplicate,
  IconField,
  IconHelp,
  IconLayers,
  IconQueue,
  IconReport,
  IconTarget,
  IconTransparency,
  IconTrend,
} from "./components/icons.jsx";

/**
 * The application's information architecture, in one place.
 *
 * Organised the way the system works, not the way features were added:
 *
 *   1 · Detect   the engine and everything it surfaces — the centrepiece
 *   2 · Act      what officers do with a lead: plan, roster, brief, case-manage
 *   3 · Assure   how anyone checks the system: the workflow, the field results,
 *                the stated limits of the data
 *
 * It used to be Monitor · Field Operations · Casework · Intelligence · Trust,
 * which put the auditor tools second and the detection engines fourth of five.
 *
 * Three surfaces read from this and must never drift apart: the primary nav, the
 * section rail and the breadcrumb. **Paths must match the routes in App.jsx.**
 * Section keys are new on purpose: `t()` prefers a stored string over the English
 * fallback, and the stored strings still carry the old section names.
 */
export const SECTIONS = [
  {
    id: "detect",
    step: 1,
    key: "nav.step.detect",
    label: "Find",
    items: [
      { to: "/overview", Icon: IconDashboard, key: "nav.detectionCentre", label: "Detection Centre" },
      { to: "/worklist", Icon: IconQueue, key: "nav.worklist", label: "Works to Check" },
      { to: "/duplicates", Icon: IconDuplicate, key: "nav.duplicates", label: "Possible Duplicates" },
      { to: "/vendors", Icon: IconAgency, key: "nav.vendors", label: "Who Gets Paid" },
      { to: "/map", Icon: IconDashboard, key: "nav.map", label: "Work Heatmap" },
      { to: "/trends", Icon: IconTrend, key: "nav.trends", label: "Changes Over Time" },
      { to: "/archetypes", Icon: IconArchetype, key: "nav.archetypes", label: "Work Types" },
    ],
  },
  {
    id: "act",
    step: 2,
    key: "nav.step.act",
    label: "Act",
    items: [
      { to: "/audit-plan", Icon: IconReport, key: "nav.auditPlan", label: "Visit Plan" },
      { to: "/rota", Icon: IconField, key: "nav.rota", label: "Who Goes Where" },
      { to: "/agency", Icon: IconAgency, key: "nav.agency", label: "Agency Profile" },
      { to: "/salesforce", Icon: IconCasework, key: "nav.salesforce", label: "Case Tracking" },
    ],
  },
  {
    id: "assure",
    step: 3,
    key: "nav.step.assure",
    label: "Check",
    items: [
      { to: "/workflow", Icon: IconLayers, key: "nav.workflow", label: "Step by Step" },
      { to: "/submit", Icon: IconField, key: "nav.submit", label: "Submit Evidence" },
      { to: "/evidence", Icon: IconLayers, key: "nav.evidence", label: "Evidence Trail" },
      { to: "/public", Icon: IconTransparency, key: "nav.public", label: "Look Up My Area" },
      { to: "/scoreboard", Icon: IconTarget, key: "nav.scoreboard", label: "Was It Right?" },
      { to: "/transparency", Icon: IconTransparency, key: "nav.transparency", label: "About the Data" },
      { to: "/how", Icon: IconHelp, key: "nav.how", label: "How it works" },
    ],
  },
];

/**
 * Pages reachable without their own navigation entry. A case file belongs under
 * Detect; one agency's dossier (`/agency/:name`) keeps Act lit.
 */
const UNLISTED = {
  "/case": { key: "case.title", label: "Case File", sectionId: "detect", Icon: IconQueue },
  "/agency": { key: "nav.agency", label: "Agency Profile", sectionId: "act", Icon: IconAgency },
};

/** The flat page list, for lookups. */
export const PAGES = SECTIONS.flatMap((s) =>
  s.items.map((i) => ({ ...i, sectionId: s.id, sectionKey: s.key, sectionLabel: s.label }))
);

/** Resolve a pathname to its page and section, matching `/case/:ref` by prefix. */
export function resolveRoute(pathname) {
  const exact = PAGES.find((p) => p.to === pathname);
  if (exact) return exact;

  const prefix = Object.keys(UNLISTED).find((p) => pathname.startsWith(p + "/"));
  if (prefix) {
    const meta = UNLISTED[prefix];
    const section = SECTIONS.find((s) => s.id === meta.sectionId);
    return { ...meta, to: pathname, sectionKey: section?.key, sectionLabel: section?.label };
  }
  return null;
}

/** The section a pathname sits in, so the primary nav can light the right entry. */
export function sectionFor(pathname) {
  const page = resolveRoute(pathname);
  return page ? SECTIONS.find((s) => s.id === page.sectionId) : null;
}
