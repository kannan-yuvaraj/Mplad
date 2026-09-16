import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Hitl, Topbar } from "../components/Bits.jsx";
import { api, rupees } from "../api.js";

/**
 * The heat map of India.
 *
 * Four things here are not decoration, and each answers an objection a careful
 * reviewer would otherwise raise:
 *
 * 1. **A works floor.** Lakshadweep has 72 works and 17 most-urgent ones — a
 *    23.6% rate, eleven times the national figure, built on seventeen works.
 *    Left alone it took the darkest tile on the map. States under the floor are
 *    hatched, never shaded: a pale fill reads as "a low rate", which is a
 *    different claim from "we will not say".
 * 2. **Significance, not just colour.** A state above the national rate on 600
 *    works has said nothing; the same gap on 36,000 works is real. Each state's
 *    rate carries a Wilson interval, and only states whose interval clears the
 *    national rate are marked. Everything else reads "cannot be separated".
 * 3. **A drill-down that stops where the data stops.** Constituency is the
 *    finest geography MPLADS publishes, and it has no boundary in any shapefile
 *    we hold — so it is a ranked list, not a second choropleth with invented
 *    borders.
 * 4. **A time-lapse of recommendations, labelled as such.** The only date every
 *    work carries is when it was recommended. Nothing here is construction
 *    progress, because MPLADS publishes none.
 */

const METRICS = [
  { id: "high_rate", short: "Most urgent", isRate: true,
    fmt: (v) => `${(v * 100).toFixed(2)}%`,
    blurb: "Works where three or more checks agree, as a share of that state's works." },
  { id: "lead_rate", short: "Flagged", isRate: true,
    fmt: (v) => `${(v * 100).toFixed(1)}%`,
    blurb: "Works where two or more checks agree, as a share of that state's works." },
  { id: "exposure_per_work", short: "Money per work", isRate: false,
    fmt: (v) => rupees(v),
    blurb: "Money in works that may not get finished, spread over that state's works." },
  { id: "works", short: "Works", isRate: false,
    fmt: (v) => v.toLocaleString("en-IN"),
    blurb: "The raw count — shown so you can see how much of the colour above is size." },
];

/**
 * The conventional heat ramp: green is calm, red is hot.
 *
 * Green and red are the classic pair a red-green colourblind reader cannot
 * separate, so on this page colour is never the only channel carrying the
 * answer. Four others run alongside it: every state prints its own figure in
 * the hover card, the ranked list beside the map repeats the whole ordering as
 * text, a hatch (not a pale shade) marks states with too few works, and a ring
 * marks the ones whose difference from the national rate survives their sample.
 * The steps also darken at both ends, so the ramp still reads in greyscale.
 */
const RAMP = ["#1f7a4d", "#62a83f", "#d8c33a", "#ef9c3a", "#d1512b", "#a8261b"];

export default function StateMap() {
  const [geo, setGeo] = useState(null);
  const [data, setData] = useState(null);
  const [sig, setSig] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [metric, setMetric] = useState(METRICS[0]);
  const [year, setYear] = useState(null);          // null = whole record
  const [playing, setPlaying] = useState(false);
  const [hover, setHover] = useState(null);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState(null);
  const [drill, setDrill] = useState(null);
  const [drillBusy, setDrillBusy] = useState(false);
  const drillRef = useRef(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch("/geo/india-states.json").then((r) => {
        if (!r.ok) throw new Error(`map outlines missing (${r.status})`);
        return r.json();
      }),
      api.mapStates(),
      api.mapSignificance().catch(() => null),
      api.mapTimeline().catch(() => null),
    ])
      .then(([g, d, s, t]) => {
        if (!alive) return;
        setGeo(g); setData(d); setSig(s); setTimeline(t);
      })
      .catch((e) => alive && setError(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  // The time-lapse. One interval, cleaned up on every change — a play button
  // that leaves a timer behind is how a demo ends up running two loops at once.
  useEffect(() => {
    if (!playing || !timeline) return undefined;
    const years = timeline.years;
    const id = setInterval(() => {
      setYear((current) => {
        const at = current == null ? -1 : years.indexOf(current);
        const next = at + 1;
        if (next >= years.length) { setPlaying(false); return null; }
        return years[next];
      });
    }, 900);
    return () => clearInterval(id);
  }, [playing, timeline]);

  const loadDrill = useCallback((state) => {
    setPicked(state); setDrill(null); setDrillBusy(true);
    // Wait a frame so the section exists before scrolling to it.
    requestAnimationFrame(() =>
      drillRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    api.mapConstituencies(state)
      .then(setDrill)
      .catch((e) => setDrill({ found: false, state, reason: String(e.message || e) }))
      .finally(() => setDrillBusy(false));
  }, []);

  /** Equirectangular with a cosine correction at India's mean latitude — the
   *  honest minimum for a country map, and it needs no projection library. */
  const projected = useMemo(() => {
    if (!geo) return null;
    const [minLon, minLat, maxLon, maxLat] = geo.bbox;
    const k = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
    const w = (maxLon - minLon) * k;
    const h = maxLat - minLat;
    const SIZE = 1000;
    const scale = SIZE / Math.max(w, h);
    const ox = (SIZE - w * scale) / 2;
    const oy = (SIZE - h * scale) / 2;
    const px = (lon) => ox + (lon - minLon) * k * scale;
    const py = (lat) => oy + (maxLat - lat) * scale;

    return {
      size: SIZE,
      shapes: geo.features.map((f) => ({
        state: f.properties.state,
        cx: px(f.properties.centroid[0]),
        cy: py(f.properties.centroid[1]),
        d: f.geometry.coordinates
          .map((poly) => poly
            .map((ring) => ring.map(([lo, la], i) =>
              `${i ? "L" : "M"}${px(lo).toFixed(1)} ${py(la).toFixed(1)}`).join("") + "Z")
            .join(""))
          .join(""),
      })),
    };
  }, [geo]);

  const byName = useMemo(() => {
    const m = {};
    (data?.states || []).forEach((s) => { m[s.state_name] = s; });
    return m;
  }, [data]);

  /** In year mode the value is a count for that year; counts need no floor. */
  const valueFor = useCallback((name) => {
    if (year != null) {
      const row = timeline?.by_year?.[String(year)]?.[name];
      return row ? row.works : 0;
    }
    const s = byName[name];
    if (!s) return null;
    const v = s[metric.id];
    return typeof v === "number" ? v : null;
  }, [year, timeline, byName, metric]);

  const steps = useMemo(() => {
    const names = projected ? projected.shapes.map((s) => s.state) : [];
    const values = names.map(valueFor)
      .filter((v) => typeof v === "number" && v > 0)
      .sort((a, b) => a - b);
    if (!values.length) return [];
    return [0.17, 0.34, 0.5, 0.67, 0.84]
      .map((q) => values[Math.floor(q * (values.length - 1))]);
  }, [projected, valueFor]);

  const stepOf = (name) => {
    const v = valueFor(name);
    if (typeof v !== "number" || v <= 0) return null;
    let i = 0;
    while (i < steps.length && v > steps[i]) i += 1;
    return i;
  };

  const withheld = (name) =>
    year == null && metric.isRate && byName[name]?.rate_withheld;

  /** States in the order the map colours them, filtered by the search box.
   *  A state with no value sorts last rather than sorting as zero — "we will
   *  not say" is not the bottom of the scale. */
  const ranked = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.states || [])
      .filter((s) => !q || s.state_name.toLowerCase().includes(q))
      .slice()
      .sort((a, b) => {
        const va = valueFor(a.state_name);
        const vb = valueFor(b.state_name);
        const na = typeof va !== "number";
        const nb = typeof vb !== "number";
        if (na !== nb) return na ? 1 : -1;
        if (na && nb) return b.works - a.works;
        return vb - va;
      });
  }, [data, query, valueFor]);

  const fillFor = (name) => {
    if (withheld(name)) return "url(#hatch)";
    const i = stepOf(name);
    return i == null ? "var(--map-empty, #eee8dc)" : RAMP[i];
  };

  const yearRow = (name) =>
    year != null ? timeline?.by_year?.[String(year)]?.[name] : null;

  const shown = hover || picked;
  const active = shown ? byName[shown] : null;
  const activeSig = shown ? sig?.states?.[shown] : null;
  const national = data?.national;

  function exportCsv() {
    const head = ["state", "works", "high", "leads", "high_rate", "lead_rate",
                  "exposure", "rate_withheld", "significance"];
    const lines = [head.join(",")].concat((data?.states || []).map((s) => [
      `"${s.state_name}"`, s.works, s.high, s.leads,
      s.high_rate ?? "", s.lead_rate ?? "", s.exposure, s.rate_withheld,
      sig?.states?.[s.state_name]?.verdict ?? "",
    ].join(",")));
    const url = URL.createObjectURL(
      new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "mplads-states.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page">
      <Topbar
        title="Heat map of India"
        sub="Where the flagged works are concentrated — and where the numbers are too thin to say"
        right={data && (
          <div className="map-top-actions">
            <span className="badge">{data.states.length} states &amp; UTs</span>
            <button className="btn ghost sm" onClick={exportCsv}>Download CSV</button>
          </div>
        )}
      />

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Working…</p>}

      {data && projected && (
        <>
          <div className="map-controls">
            <div className="metric-row">
              {METRICS.map((m) => (
                <button key={m.id} type="button"
                        className={"btn ghost sm" + (m.id === metric.id ? " on" : "")}
                        disabled={year != null}
                        aria-pressed={m.id === metric.id}
                        onClick={() => setMetric(m)}>{m.short}</button>
              ))}
            </div>

            {timeline && (
              <div className="timelapse">
                <button className="btn ghost sm"
                        onClick={() => { setPlaying((p) => !p); if (year == null) setYear(timeline.years[0]); }}>
                  {playing ? "Pause" : "Play the years"}
                </button>
                <input
                  id="map-year" type="range" min={0} max={timeline.years.length}
                  value={year == null ? timeline.years.length : timeline.years.indexOf(year)}
                  onChange={(e) => {
                    const i = Number(e.target.value);
                    setPlaying(false);
                    setYear(i >= timeline.years.length ? null : timeline.years[i]);
                  }}
                  aria-label="Year"
                />
                <span className="year-label">
                  {year == null ? "Whole record" : year}
                  {year != null && (
                    <em>{(timeline.totals[String(year)] || 0).toLocaleString("en-IN")} works recommended</em>
                  )}
                </span>
              </div>
            )}
          </div>

          <p className="muted sm metric-blurb">
            {year != null
              ? `Works recommended during ${year}. Recommendation date is the only date every work carries — this is when works entered the scheme, not when anything was built.`
              : metric.blurb}
          </p>

          <div className="map-layout">
            <div className="map-grid-wrap">
              <svg viewBox={`0 0 ${projected.size} ${projected.size}`}
                   className="india-map" role="img"
                   aria-label="Choropleth of India by state">
                <defs>
                  <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse"
                           patternTransform="rotate(45)">
                    <rect width="7" height="7" fill="#efe8da" />
                    <line x1="0" y1="0" x2="0" y2="7" stroke="#cdc2ac" strokeWidth="2.5" />
                  </pattern>
                </defs>
                {projected.shapes.map((s) => {
                  const mark = sig?.states?.[s.state]?.verdict;
                  const isOn = shown === s.state;
                  return (
                    <path
                      key={s.state} d={s.d} fill={fillFor(s.state)}
                      className={"st" + (isOn ? " on" : "")
                                 + (mark === "above" ? " sig-above" : "")}
                      onMouseEnter={() => setHover(s.state)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => loadDrill(s.state)}
                      tabIndex={0}
                      onFocus={() => setHover(s.state)}
                      onBlur={() => setHover(null)}
                      onKeyDown={(e) => { if (e.key === "Enter") loadDrill(s.state); }}
                    >
                      <title>
                        {s.state}
                        {withheld(s.state)
                          ? ` — ${byName[s.state].works} works, too few for a rate`
                          : valueFor(s.state) != null
                            ? ` — ${year != null
                                  ? `${valueFor(s.state).toLocaleString("en-IN")} works in ${year}`
                                  : metric.fmt(valueFor(s.state))}`
                            : ""}
                      </title>
                    </path>
                  );
                })}
                {/* Only states that clear the national rate get a marker, and it
                    is a shape, not a shade — the ramp already spends colour. */}
                {projected.shapes.filter((s) => sig?.states?.[s.state]?.verdict === "above")
                  .map((s) => (
                    <circle key={`m${s.state}`} cx={s.cx} cy={s.cy} r="5.5"
                            className="sig-dot" />
                  ))}
              </svg>

              <div className="map-legend">
                <span className="lg-label">Lower</span>
                {RAMP.map((c, i) => (
                  <span key={c} className="lg-step">
                    <i style={{ background: c }} />
                    {/* The break between steps, so the ramp is readable as
                        numbers and not only as colour. */}
                    <em>{i < steps.length && steps[i] != null
                      ? (year != null ? steps[i].toLocaleString("en-IN") : metric.fmt(steps[i]))
                      : ""}</em>
                  </span>
                ))}
                <span className="lg-label">Higher</span>
                {year == null && metric.isRate && (
                  <>
                    <span className="lg-sep" />
                    <span className="lg-item"><i className="lg-hatch" /> too few works to rate</span>
                    <span className="lg-item"><b className="lg-dot" /> above the national rate</span>
                  </>
                )}
                {national && year == null && metric.isRate && (
                  <span className="lg-nat">India: <b>{metric.fmt(national[metric.id])}</b></span>
                )}
              </div>
            </div>

            <aside className="map-side">
              {shown && active ? (
                <>
                  <h2>{shown}</h2>
                  <dl className="map-facts">
                    <div><dt>Works</dt><dd>{active.works.toLocaleString("en-IN")}</dd></div>
                    <div><dt>Flagged</dt><dd>{active.leads.toLocaleString("en-IN")}
                      {active.lead_rate != null && <em>{(active.lead_rate * 100).toFixed(1)}%</em>}</dd></div>
                    <div><dt>Most urgent</dt><dd>{active.high.toLocaleString("en-IN")}
                      {active.high_rate != null && <em>{(active.high_rate * 100).toFixed(2)}%</em>}</dd></div>
                    <div><dt>Money at risk</dt><dd>{rupees(active.exposure)}</dd></div>
                    <div><dt>Offices</dt><dd>{active.agencies}</dd></div>
                    {yearRow(shown) && (
                      <div><dt>In {year}</dt><dd>{yearRow(shown).works.toLocaleString("en-IN")} works
                        <em>{yearRow(shown).high} most urgent</em></dd></div>
                    )}
                  </dl>

                  {active.rate_withheld ? (
                    <p className="map-compare withheld-note">
                      <b>No rate shown.</b> {active.withheld_reason}. The counts above are
                      exact; it is the percentage that would mislead.
                    </p>
                  ) : activeSig && (
                    <p className={"map-compare sig-" + activeSig.verdict}>
                      <b>
                        {activeSig.verdict === "above" ? "Above the national rate."
                          : activeSig.verdict === "below" ? "Below the national rate."
                          : "Cannot be told from the national rate."}
                      </b>{" "}
                      {(activeSig.rate * 100).toFixed(2)}% against {(activeSig.national * 100).toFixed(2)}%,
                      95% interval [{(activeSig.ci_low * 100).toFixed(2)}%, {(activeSig.ci_high * 100).toFixed(2)}%].
                      <br />{activeSig.note}
                    </p>
                  )}

                  <div className="map-actions">
                    <button className="btn ghost sm" onClick={() => loadDrill(shown)}>
                      Break down by constituency
                    </button>
                    <button className="btn primary sm"
                            onClick={() => navigate(`/worklist?state=${encodeURIComponent(shown)}`)}>
                      See its works
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <h2>Point at a state</h2>
                  <p className="muted sm">
                    Colour carries the rate, not the count — a state with more works
                    surfaces more leads, and that is arithmetic, not a finding. Hatched
                    states have too few works for a rate to mean anything. A ring marks
                    the states whose difference from the national rate survives their
                    own sample size.
                  </p>
                  {national && (
                    <dl className="map-facts">
                      <div><dt>Works</dt><dd>{national.works.toLocaleString("en-IN")}</dd></div>
                      <div><dt>Flagged</dt><dd>{national.leads.toLocaleString("en-IN")}
                        <em>{(national.lead_rate * 100).toFixed(1)}%</em></dd></div>
                      <div><dt>Most urgent</dt><dd>{national.high.toLocaleString("en-IN")}
                        <em>{(national.high_rate * 100).toFixed(2)}%</em></dd></div>
                    </dl>
                  )}
                  {sig && (
                    <p className="muted sm">
                      <b>{sig.counts.above}</b> states sit above the national rate by more
                      than their sample allows · <b>{sig.counts.inconclusive}</b> cannot be
                      separated from it · <b>{sig.counts.no_rate}</b> have too few works.
                    </p>
                  )}
                </>
              )}
            </aside>
          </div>

          {/* The breakdown opens directly under the map, and scrolls into view.
              It used to render below the full ranked table of 36 states, ~2,000px
              down, so pressing the button appeared to do nothing at all. */}
          {(drillBusy || drill) && (
            <section className="card drill" ref={drillRef}>
              <div className="drill-head">
                <h2>{picked} — by constituency</h2>
                {drill?.found && (
                  <span className="muted sm">
                    {drill.state_totals.constituencies} constituencies ·
                    {" "}{drill.state_totals.works.toLocaleString("en-IN")} works ·
                    {" "}state rate {(drill.state_totals.high_rate * 100).toFixed(2)}%
                  </span>
                )}
                <button className="btn ghost sm" onClick={() => { setDrill(null); setPicked(null); }}>
                  Close
                </button>
              </div>

              {drillBusy && <p className="muted">Working…</p>}
              {drill && !drill.found && <p className="muted">{drill.reason}</p>}

              {drill?.found && (
                <>
                  <div className="tablewrap">
                    <table className="grid">
                      <thead>
                        <tr>
                          <th>Constituency</th><th>Member of Parliament</th>
                          <th className="n">Works</th><th className="n">Flagged</th>
                          <th className="n">Most urgent</th><th className="n">Rate</th>
                          <th className="n">Money at risk</th><th>Offices</th>
                        </tr>
                      </thead>
                      <tbody>
                        {drill.constituencies.map((r) => (
                          <tr key={r.constituency}>
                            <td><b>{r.constituency}</b></td>
                            <td className="muted">{r.mp_name || "—"}</td>
                            <td className="n">{r.works.toLocaleString("en-IN")}</td>
                            <td className="n">{r.leads}</td>
                            <td className="n">{r.high}</td>
                            <td className="n">
                              {r.high_rate == null
                                ? <span className="muted sm">too few works</span>
                                : `${(r.high_rate * 100).toFixed(2)}%`}
                            </td>
                            <td className="n">{rupees(r.exposure)}</td>
                            <td className="n">{r.agencies}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted sm">{drill.note}</p>
                </>
              )}
            </section>
          )}

          {/* The same ordering as text. Colour is doing real work on this page,
              and green against red is exactly the pair a red-green colourblind
              reader cannot separate — so the ranking exists in full beside the
              map, not as a fallback but as the other half of the answer. */}
          <section className="card ranked">
            <div className="ranked-head">
              <h2>Every state, ranked</h2>
              <span className="muted sm">
                {year != null ? `Works recommended in ${year}` : metric.blurb}
              </span>
              <input
                id="map-search" className="ranked-search" type="search"
                placeholder="Find a state…" value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Find a state"
              />
            </div>
            <div className="tablewrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th className="n">#</th><th>State or union territory</th>
                    <th className="n">Works</th><th className="n">Flagged</th>
                    <th className="n">Most urgent</th>
                    <th className="n">{year != null ? `Works in ${year}` : "Rate"}</th>
                    <th className="n">Money at risk</th>
                    <th>Against the national rate</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map((s, i) => {
                    const v = valueFor(s.state_name);
                    const mark = sig?.states?.[s.state_name];
                    return (
                      <tr key={s.state_name}
                          className={shown === s.state_name ? "on" : ""}
                          onMouseEnter={() => setHover(s.state_name)}
                          onMouseLeave={() => setHover(null)}
                          onClick={() => loadDrill(s.state_name)}
                          style={{ cursor: "pointer" }}>
                        <td className="n muted">{i + 1}</td>
                        <td>
                          <i className="swatch" style={{ background: fillFor(s.state_name) }} />
                          <b>{s.state_name}</b>
                        </td>
                        <td className="n">{s.works.toLocaleString("en-IN")}</td>
                        <td className="n">{s.leads.toLocaleString("en-IN")}</td>
                        <td className="n">{s.high.toLocaleString("en-IN")}</td>
                        <td className="n">
                          {typeof v === "number"
                            ? (year != null ? v.toLocaleString("en-IN") : metric.fmt(v))
                            : <span className="muted sm">too few works</span>}
                        </td>
                        <td className="n">{rupees(s.exposure)}</td>
                        <td>
                          {!mark || mark.verdict === "no_rate"
                            ? <span className="muted sm">no rate</span>
                            : mark.verdict === "above"
                              ? <span className="verdict up">● above</span>
                              : mark.verdict === "below"
                                ? <span className="verdict down">● below</span>
                                : <span className="verdict flat">● cannot be told apart</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!ranked.length && <p className="muted">No state matches “{query}”.</p>}
          </section>

          <div className="card map-note">
            <h2>Why this map stops at the state</h2>
            <p>{data.geography_note}</p>
            <p className="muted sm">{data.floor_note}</p>
            {sig && <p className="muted sm"><b>How states are marked.</b> {sig.note} {sig.method}</p>}
          </div>

          <Hitl text="A state's colour says where to ask questions, not where wrongdoing is. Every state on this map has honest works in it." />
        </>
      )}
    </div>
  );
}
