import { NavLink } from "react-router-dom";
import { EXPLAIN_PAGES } from "../nav.js";
import { useI18n } from "../I18nContext.jsx";

/**
 * One "How it works" entry in the navigation, three views under it.
 *
 * These were three separate nav entries — Step by Step, About the Data and How it
 * works — that all answered "how does this system work and what can I trust?".
 * Merged into one entry so the sidebar has fewer places a judge must choose
 * between. Each view keeps its own address, so every existing link still lands.
 */
export default function ExplainTabs() {
  const { t } = useI18n();
  return (
    <nav className="explain-tabs" aria-label={t("explain.tabs", "Ways to understand this system")}>
      {EXPLAIN_PAGES.map((p) => (
        <NavLink
          key={p.to}
          to={p.to}
          end
          className={({ isActive }) => "explain-tab" + (isActive ? " active" : "")}
        >
          {t(p.tabKey, p.tab)}
        </NavLink>
      ))}
    </nav>
  );
}
