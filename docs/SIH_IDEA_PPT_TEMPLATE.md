# SIH 2026 — Idea Submission Deck: Master Template

**Problem Statement 26102 · MoSPI · Team Morior Invictus**

Copy this whole file into a slide generator and say *"Generate slides from this
template."* Every slide below gives you the layout, the visual, the exact copy,
and the one line a judge will remember.

---

## Read this before you write a single slide

Four facts about the round you are actually in. They decide every choice below.

| Fact | What it forces |
|---|---|
| **Six slides maximum**, including the title slide | Nothing is "nice to have". Every box earns its place. |
| **An evaluator gives you 2–3 minutes** | The point of each slide must land in ~10 seconds of looking. |
| **No jury, no demo, no questions** — the PPT alone decides | The deck must answer the obvious objection *before* it is asked. |
| **~5 teams shortlisted per problem statement, nationally** | Being "good" loses. You need one thing nobody else has. |

**The official headings cannot be changed.** Proposed Solution, Technical
Approach, Feasibility and Viability, Impact and Benefits, Research and
References. Work inside them.

**Export to PDF.** The portal takes nothing else. If you build in Canva, open
the result in PowerPoint first — diagrams shift.

### The one thread running through all six slides

> Other teams will report how late the *finished* works were. That number ignores
> every work that never finished. We corrected it, turned the risk into a rupee
> figure, and we refuse to output a fraud score because there are no fraud labels
> in this data.

Say a version of that on slide 2, prove it on slide 3, defend it on slide 4, cash
it on slide 5. A deck that repeats one idea beats a deck that lists nine.

### Copy rules

- **6–10 words per bullet.** If it wraps to two lines, cut it.
- **Numbers, not adjectives.** Not "highly accurate" — "0.6759 on held-out data".
- **No paragraphs.** The official instructions say so explicitly.
- **Define any term you must use, in the same line.** "Censoring — works that never finished."
- **Write how you speak.** Read each bullet aloud. If you would not say it, rewrite it.

### Space rules — use the whole slide

The template's content area is roughly **12" × 5.3"** under the heading band.
Treat it as a grid and fill it:

- **Never leave more than ~1" of dead white space** in any direction.
- **Two columns beat one.** Text left (≈55%), visual right (≈45%) is the default.
- **Bottom strip (~0.8") is yours** — put the caveat, the source line, or the
  "so what" there. Judges read it.
- **0.5" margins minimum.** Do not crowd the edge.

---

# SLIDE 1 — TITLE PAGE

**Official fields (do not rename):** Problem Statement ID · Problem Statement
Title · Theme · PS Category · Team ID · Team Name

### 🏆 Winning point
*Most title slides are a form. Yours carries one line that makes the evaluator
want to turn the page.*

### Layout
- **Top-left third:** the official fields, small, plain, complete.
- **Centre-right (the space everyone wastes):** your solution name, large, plus
  **one** sentence of what it does.
- **Bottom strip:** a single row of three verified figures.

### Copy

```
PS ID:        SIH26102
PS Title:     AI-powered system to detect anomalies, fraud and
              inefficiencies in MPLAD Scheme implementation
Theme:        Smart Automation
PS Category:  Software
Team ID:      <your ID>
Team Name:    Morior Invictus
```

**Solution name + one line (centre-right, 28–32pt):**

> **An AI that knows what it doesn't know.**
> Reads every MP-funded work in India and tells an officer where to go and look.

**Bottom row — three figures, equal width:**

| 2,10,993 | ₹1,302 Cr | 4,478 |
|---|---|---|
| real works read | money at risk | need a human first |

### Visual
No logo soup. One restrained graphic: a faint outline of India, or nothing at
all. A clean title slide reads as confidence.

### Tone
Calm and factual. No exclamation marks. No "revolutionary".

---

# SLIDE 2 — IDEA TITLE / PROPOSED SOLUTION

**Official pointers:** Detailed explanation · How it addresses the problem ·
Innovation and uniqueness

### 🏆 Winning point
*You corrected a statistic every other team will get wrong. Say it in the first
ten seconds.*

This is the slide that shortlists you. Lead with the flaw in the obvious
approach, then your fix.

### Layout — three bands, full width

**Band 1 (top, full width): the wrong number and the right one.**
Two boxes side by side, an arrow between them.

```
   WHAT EVERYONE MEASURES              WHAT WE MEASURE
   "How late were the works             Every work — including the
    that finished?"                     1,25,220 that never finished
   Ignores the ones still open          Survival analysis, C-index 0.6759
```

**Band 2 (middle, left 55%): how it works, five bullets.**

- Five checks run on every work, not one score
- Cost · delay · odd numbers · duplicates · agency change
- A work is flagged only when two checks agree
- Compared against similar works, not a national average
- Every flag ends in "a human should check this"

**Band 2 (middle, right 45%): the funnel diagram.** See Visual below.

**Band 3 (bottom strip, full width): the three things nobody else does.**

- Plans a budget: 50 officer-days → ₹47.1 Cr covered
- Publishes a screen that can prove us wrong
- Refuses a fraud score — no fraud labels exist

### Visual
**A funnel, left to right.** Five check-boxes converge into one "2+ agree" gate,
which narrows to the flagged count, which narrows again to the urgent count.

```
2,10,993 works ─┬─ Stalling warning   50,666 ─┐
                ├─ Rule broken         5,946 ─┤
                ├─ Statistical outlier 4,220 ─┼─► 2+ agree ─► 37,705 ─► 4,478
                ├─ Possible repeat    47,709 ─┤              flagged   urgent
                └─ Agency changed    73 of 697┘
```

*(Possible repeat is a count of work **pairs**, not works. Say so on the slide.)*

This one diagram carries the whole method. Make it the largest object on the
slide.

### Tone
Confident, specific, slightly contrarian. You are correcting a mistake, not
boasting.

---

# SLIDE 3 — TECHNICAL APPROACH

**Official pointers:** Technologies to be used · Methodology and process
(flow charts / images / working prototype)

### 🏆 Winning point
*It is already built and running on the real national record — not a mock-up,
not 500 sample rows.*

Most decks in this round show an architecture diagram for something that does
not exist yet. Yours shows a system with a test count.

### Layout — two columns, hard split

**Left 45% — the flow, top to bottom.** Five stages, each one line:

```
1. INGEST     eSAKSHI public REST API, polled live
2. LEARN      50 work-types from descriptions
3. COMPARE    each work against its true peers
4. PREDICT    completion risk (Cox survival)
5. DECIDE     evidence + "go and check this"
```

**Right 55% — a real screenshot.** Not a wireframe. The heat map of India or the
case file. Label it with a one-line caption.

**Bottom strip, full width — the stack, as one line each:**

- **Models:** survival analysis · clustering · outlier detection
- **Built with:** Python · FastAPI · React · SQLite
- **Reading documents:** two OCR engines that must agree
- **Proof it runs:** 341 automated tests passing

### Visual
**One real screenshot, large.** If you show only one, show the map of India with
states shaded by rate — it is instantly legible and it says "this exists".

Add a small inset: the two-reader OCR disagreement, with the caption *"Two
readers. They disagree → a human decides."*

### Tone
Plain and concrete. Name the technique, then say what it does in ordinary words:
*"Survival analysis — counts the works that never finished."*

**Do not** list twenty libraries. A long stack list reads as padding.

---

# SLIDE 4 — FEASIBILITY AND VIABILITY

**Official pointers:** Feasibility of the idea · Potential challenges and risks ·
Strategies for overcoming them

### 🏆 Winning point
*You name your own weakest number before the judge finds it. Nobody else will.*

This is where most decks write "challenge: scalability / solution: cloud". That
is filler and evaluators know it. Real, specific risks — with the measured
number attached — is the single most credible thing you can do in this round.

### Layout — a three-column table, full width, filling the slide

| The honest risk | Why it is real | What we did |
|---|---|---|
| No fraud labels exist | Nothing says which works were problems | Refuse a fraud score; output leads with evidence |
| Work-type grouping is weak | Silhouette 0.050 — we publish it | Used as a lens, never as a verdict |
| "Amount spent" is unreliable | 98.35% equals the recommended figure | Never claim overspending |
| Small states mislead | 17 of 72 works = a 23.6% rate | No rate below 500 works; tile left blank |
| Officers only visit flagged works | The sample is not random | Stated on the results screen, with intervals |

### Bottom strip — feasibility in one row

- Runs on one laptop, no GPU, 90-second pipeline
- Uses only the public portal — no login, no scraping
- Live sync: 144 cheap checks, re-reads only what moved

### Visual
Keep it a **table** — this slide is about honesty, and a table reads as an
audit. If you want one graphic, use a small **"we can be wrong" panel**: three
bars where one is deliberately left empty with the label *"not enough visits yet"*.

### Tone
Unflinching. Do not soften with "however" or "we believe". State the limit, state
the response, move on. A judge who has read 200 decks of optimism will stop on
this one.

---

# SLIDE 5 — IMPACT AND BENEFITS

**Official pointers:** Impact on the target audience · Benefits (social,
economic, environmental)

### 🏆 Winning point
*One officer, fifty days: ₹47.1 crore covered instead of ₹0.5 crore. That single
comparison is the whole business case.*

Do not write "improves transparency". Show the arithmetic.

### Layout

**Top half, full width — the comparison chart.** Five bars, same budget:

```
Our plan            ████████████████████  ₹47.1 Cr   100 works, 23 visits
Our ranking         ██████████████████    ₹42.4 Cr
Biggest amounts     ████████████          ₹28.1 Cr
Riskiest first      ██                    ₹3.7 Cr
Picked at random    █                     ₹0.5 Cr
```

Caption underneath: *"Same 50 officer-days. Ninety-four times the money
checked."*

**Bottom half — three columns:**

**For the officer**
- Knows where to go on Monday morning
- Carries the day's list as a PDF
- Sees why each work was flagged

**For the Ministry**
- 2,10,993 works watched, not sampled
- ₹1,302 Cr of exposure made visible
- Live feed catches changes as they happen

**For the citizen**
- Look up what was funded in your area
- Ten languages, no login
- No risk scores shown in public — ever

### Visual
The bar chart **is** the slide. Make it big. Colour only your bar; leave the
others grey. One accent beats five.

### Tone
Concrete and restrained. Every claim is a number you can defend. The public
column ends on a restraint, not a boast — that lands harder.

---

# SLIDE 6 — RESEARCH AND REFERENCES

**Official pointer:** Details / links of the reference and research work

### 🏆 Winning point
*You read the actual portal, not a blog about it — and you found something in it
the data documentation got wrong.*

Most teams paste five links. Use this slide to prove you went to the source.

### Layout — two columns

**Left — what we read (with what it gave us):**

- MPLADS Guidelines 2023, MoSPI — the one-year completion rule
- eSAKSHI public portal — 2,10,993 works, read directly
- MoSPI dashboard totals — our counts reconcile exactly
- Lifelines / scikit-learn — survival and outlier methods
- Competition-law HHI — the vendor concentration measure

**Right — what we found by going to the source:**

- The portal has a public JSON API; no scraping needed
- 3,987 "corrupt rows" are the server's own subtotals
- Vendor names exist live, absent from every mirror
- Portal went live Apr 2023: 739 works → 53,501

### Bottom strip
One line: *"Every figure in this deck is reproducible from the public record.
Nothing is estimated."*

### Visual
A small reconciliation table — your count beside the portal's own count, matching.

| Andhra Pradesh, completed works | Amount |
|---|---|
| Portal's own money tile | ₹62,40,68,315 |
| What we summed | ₹62,40,68,315 |

Caption: *"Matches to the rupee — once you know the tile counts sanctioned value,
not spent value. Twelve checks, three states, every count exact."*

### Tone
Quiet and precise. This slide is not persuasion, it is evidence that you did the
work. Let it be slightly dry.

---

## Final check before you export

Run every slide against these five. If any answer is "no", fix it.

1. **Does slide 2 make one contrarian claim in the first ten seconds?**
   If a judge could swap your slide 2 with another team's, it is not specific enough.

2. **Is there a real screenshot on slide 3?**
   A wireframe says "we plan to". A screenshot says "we did".

3. **Does slide 4 contain a number that makes you uncomfortable?**
   If not, you have written filler. Put the silhouette in.

4. **Is slide 5 a comparison, not a list of adjectives?**
   "94× the money checked for the same days" is a benefit. "Improves efficiency" is not.

5. **Can a non-technical reader follow it without asking anything?**
   Hand it to someone outside your team. Watch where they stop. Fix that line.

### The three things that get decks rejected in this round

- **Paragraphs.** The instructions forbid them. Evaluators skip them anyway.
- **A stack list instead of a method.** Nobody is impressed by fifteen logos.
- **No caveats.** A deck with no stated limits reads as a deck that has not been tested.

### Last mechanical checks

- Six slides. Delete the instructions slide.
- Exported to **PDF**. Opened it once, in PowerPoint, and looked at every page.
- Team name and PS ID on the title slide, spelled exactly as registered.
- No figure appears that you cannot reproduce on demand.
