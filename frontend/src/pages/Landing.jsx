import { Link } from "react-router-dom";
import { num, rupees } from "../api.js";
import CivicShow from "../components/CivicShow.jsx";
import { AnomalyFeed, DetectorBoard, useDetection } from "../components/Detection.jsx";
import { DATA_SNAPSHOT } from "../components/GovChrome.jsx";
import { IconAgency, IconCasework, IconField, IconReport } from "../components/icons.jsx";

/**
 * The home page — the detection system at work, first.
 *
 * The previous page opened on "Two lakh public works. One afternoon to check
 * them." and then ran 6.7 screens of problem essay, a five-step lesson, a
 * six-card feature grid and a closing call to action; the words "detect" and
 * "anomaly" did not appear once in the first viewport. This page opens on the
 * thing the system does — every work passing through the detectors — with the
 * live count at every stage, then shows what it surfaced, then the detectors,
 * and only then, quietly, the tools people use to act on it.
 *
 * The explanatory material did not disappear: the stage-by-stage account lives
 * on the System Workflow page, and the stated limits on Data Transparency.
 */
export default function Landing() {
  const { d, at, ms, busy } = useDetection();
  const plan = d.plan?.totals;

  return (
    <div className="landing dx">
      {/* ----------------------------------------------------------- the pass */}
      <section className="dx-hero">
        <div className="dx-hero-inner">
          <div className="dx-hero-copy">
            <span className="dx-kicker">
              <span className={"live-dot" + (busy ? " wait" : "")} aria-hidden="true" />
              Ministry of Statistics &amp; Programme Implementation · MPLADS
            </span>

            <h1>Public money, checked work by work.</h1>

            <p className="dx-lede">
              MPs fund classrooms, water lines and roads where people live. This service
              reads the public record of that work and points officials at the few worth a
              closer look.
            </p>

            <p className="dx-caveat">
              It never says anyone did wrong — only where someone should go and check.
            </p>

            <div className="dx-cta">
              <Link to="/overview" className="btn btn-primary">See what was found</Link>
              <Link to="/public" className="btn">Look up my area</Link>
            </div>

            <p className="dx-status">
              Public eSAKSHI record up to {DATA_SNAPSHOT}
              {at && !busy ? ` · worked out here in ${ms} ms` : " · working it out…"}
            </p>
          </div>

          <div className="dx-hero-art">
            <CivicShow />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------ what it found */}
      <section className="dx-band">
        <div className="dx-wrap">
          <header className="dx-head">
            <div>
              <span className="dx-eyebrow">What the computer found</span>
              <h2>The most urgent works, one at a time</h2>
              <p>
                Each row is a real work the computer flagged. Click one to see which checks raised a
                concern; point at the list to stop it moving.
              </p>
            </div>
          </header>
          <AnomalyFeed items={d.feed?.items || []} total={d.feed?.total} />
        </div>
      </section>

      {/* ---------------------------------------------------------- detectors */}
      <section className="dx-band alt">
        <div className="dx-wrap">
          <header className="dx-head">
            <div>
              <span className="dx-eyebrow">How it finds them</span>
              <h2>Five checks, two watches, one simple rule</h2>
              <p>
                Each check looks for a different kind of problem. None of them decides on its own —
                a work is flagged only when two different checks agree.
              </p>
            </div>
            <Link to="/workflow" className="link">See every step</Link>
          </header>
          <DetectorBoard d={d} />
        </div>
      </section>

      {/* ------------------------------------------------------- acting on it */}
      <section className="dx-band quiet">
        <div className="dx-wrap">
          <header className="dx-head compact">
            <div>
              <span className="dx-eyebrow">From finding to action</span>
              <h2>What officers do with a flagged work</h2>
            </div>
          </header>
          <div className="act-row">
            <Link to="/audit-plan" className="act">
              <IconReport size={20} />
              <span>
                <h3>Visit Plan</h3>
                <p>{plan ? `${num(plan.works)} works, ${rupees(plan.exposure_rupees)}, in 50 days of visits` : "Which works to visit when there is only so much time"}</p>
              </span>
            </Link>
            <Link to="/rota" className="act">
              <IconField size={20} />
              <span>
                <h3>Who Goes Where</h3>
                <p>The plan shared out between officers, day by day</p>
              </span>
            </Link>
            <Link to="/salesforce" className="act">
              <IconCasework size={20} />
              <span>
                <h3>Case Tracking</h3>
                <p>Who is handling each case and how far it has got, kept in Salesforce</p>
              </span>
            </Link>
            <Link to="/agency" className="act">
              <IconAgency size={20} />
              <span>
                <h3>Agency Profile</h3>
                <p>What an officer reads about an office before visiting it</p>
              </span>
            </Link>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- limits */}
      <section className="dx-assure">
        <div className="dx-assure-inner">
          <span><b>A flag is not proof.</b> A person always decides what to do.</span>
          <span><b>Only a visit to the site</b> can show what really happened.</span>
          <span><b>We never say money was overspent</b> — the public data does not show what was really spent.</span>
          <span className="dx-assure-links">
            <Link to="/transparency" className="link">About the Data</Link>
            <Link to="/scoreboard" className="link">Was It Right?</Link>
          </span>
        </div>
      </section>
    </div>
  );
}
