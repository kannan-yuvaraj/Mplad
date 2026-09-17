import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Topbar } from "../components/Bits.jsx";
import ExplainTabs from "../components/ExplainTabs.jsx";
import { IconAlert, IconArchetype, IconCompliance, IconHelp, IconQueue, IconTrend } from "../components/icons.jsx";

const STEPS = [
  { n: 1, Icon: IconArchetype, title: "Learn what normal looks like",
    plain: "There are over 2 lakh works — roads, halls, street lights, water tanks. The computer reads what each work is and puts similar ones together, so a road is compared with roads and a hall with halls, not with everything at once." },
  { n: 2, Icon: IconCompliance, title: "Compare each work with works just like it",
    plain: "For every work we find truly similar works in the same state and of the same kind, then ask: does this one cost much more, or is it taking much longer, than those? Being different from the average for all of India is not enough — it must stand out from works just like it." },
  { n: 3, Icon: IconTrend, title: "Predict which works may not finish",
    plain: "Many works are still being built. Looking at how long similar works took to finish, the computer guesses how likely each unfinished work is to get stuck. Money in works that may never get finished is called 'money at risk'." },
  { n: 4, Icon: IconAlert, title: "Notice when behaviour changes",
    plain: "For each agency that builds works, we watch how its kind of work changes over the years. A sudden change is worth a second look — though it can have an innocent reason, like a new officer or a new rule." },
  { n: 5, Icon: IconQueue, title: "Explain, and put in order",
    plain: "We only flag a work when at least two different kinds of clue agree — never on one hunch. Each flagged work gets a simple 'case file' saying exactly why, and the one thing a person should check next. The list is put in order so officers look at the biggest money at risk first." },
];

function metricCard(m, title, plain) {
  if (!m) return null;
  return (
    <div className="card">
      <h3>{title}</h3>
      <p className="muted" style={{ fontSize: 13, marginBottom: 10 }}>{plain[0]}</p>
      <p style={{ fontSize: 12, color: "var(--text-2)" }} title={m.note}>{plain[1]}</p>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 6 }}>Technical name: {m.model}</div>
    </div>
  );
}

export default function HowItWorks() {
  const [m, setM] = useState(null);
  useEffect(() => { api.models().then(setM).catch(() => setM({})); }, []);

  const arch = m?.archetype_clustering;
  const risk = m?.completion_risk;
  const anom = m?.anomaly_detection;

  return (
    <>
      <Topbar title="How this works" sub="Explained simply" />
      <ExplainTabs />
      <div className="content">
        <div className="hitl">
          <span aria-hidden="true" style={{ color: "var(--primary)", display: "inline-flex", marginTop: 1 }}><IconHelp size={16} /></span>
          <span>
            This system is a <strong>helper for the officers who check works</strong>. It does
            not accuse anyone. It reads public records of government-funded local works and
            points to the ones most worth a person's time — always saying why.
          </span>
        </div>

        <div className="card" style={{ marginBottom: 22 }}>
          <h3>What problem does it solve?</h3>
          <p style={{ fontSize: 14, color: "var(--text)" }}>
            Members of Parliament recommend local development works — roads, community halls,
            street lights, water supply. There are over <strong>2,10,000</strong> of them
            across the country. No officer can check them all by hand. This system reads
            every work and makes a short list, in order, of the ones that look unusual next to
            truly similar works — so the little time officers have goes where it matters most.
            Every item is <strong>a reason to look, not proof of wrongdoing</strong>.
          </p>
        </div>

        <div className="section-title">The five steps</div>
        {STEPS.map((s) => (
          <div className="card" key={s.n} style={{ marginBottom: 12, display: "flex", gap: 16 }}>
            <div className="evidence-icon" style={{ width: 40, height: 40, fontSize: 20, flexShrink: 0 }}><s.Icon size={18} /></div>
            <div>
              <div style={{ fontWeight: 660, fontSize: 15 }}>
                <span className="muted" style={{ marginRight: 8 }}>Step {s.n}</span>{s.title}
              </div>
              <p className="muted" style={{ fontSize: 13.5, marginTop: 4 }}>{s.plain}</p>
            </div>
          </div>
        ))}

        <div className="section-title">The three computer models we trained — and what their scores really mean</div>
        <div className="grid cols-3">
          {metricCard(arch,
            arch ? `Grouping works · ${arch.k_chosen} kinds of work` : "Grouping works",
            ["The computer turns each description into numbers that capture its meaning, and puts similar ones together. We tried different numbers of groups and kept the clearest.",
             "Its \"how neatly the groups split\" score (about 0.05) is not a mark for being right. People checked the groups by reading them."])}
          {metricCard(risk,
            risk ? `Chance of not finishing · scores ${risk.c_index_heldout.toFixed(2)} (0.5 = coin toss)` : "Chance of not finishing",
            ["The same kind of maths used to study how long things last. It remembers that many works are simply not finished yet — which is not the same as failed.",
             "On works it had never seen, it picked which would finish sooner clearly better than a coin toss. It only predicts time — never wrongdoing."])}
          {metricCard(anom,
            anom ? `Odd-numbers finder · ${anom.n_flagged?.toLocaleString("en-IN")} flagged` : "Odd-numbers finder",
            ["It learns what a normal work's cost and age look like, and points out the odd ones as one extra clue.",
             "It only backs up other clues — on its own it never flags a work, and it never decides anyone did wrong."])}
        </div>

        <div className="card" style={{ marginTop: 20 }}>
          <h3>What we are careful NOT to claim</h3>
          <ul style={{ fontSize: 13.5, color: "var(--text-2)", paddingLeft: 18, lineHeight: 1.9 }}>
            <li>We do <strong>not</strong> call anything fraud. No record in this data says which works were fraud, so any "fraud detector" would be made up.</li>
            <li>The "how neatly the groups split" score (called silhouette, about 0.05) <strong>is not a mark for being right</strong>. It only measures how far apart the groups are.</li>
            <li>"Money at risk" is money that <strong>could</strong> be stuck in works that may not get finished — it is not money lost or stolen.</li>
            <li>Every case ends with <strong>"a person should check…"</strong>. People decide; the computer only points.</li>
          </ul>
        </div>
      </div>
    </>
  );
}
