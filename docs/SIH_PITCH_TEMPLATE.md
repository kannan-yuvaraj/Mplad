# SIH 2026 · Master Pitch Template — PS 26102 · Team Morior Invictus

**How to use this file:** paste it whole into ChatGPT (or Gemini/Claude) and say
*"Generate slides from this template."* Every slide below specifies its title,
copy, layout zones, visual, and tone. The copy is already written with this
project's real figures — replace nothing unless a number has changed.

---

## Before you build a single slide — read this

### What the research says

| Source | The pattern that matters |
|---|---|
| Y Combinator / Sequoia decks | 10–12 slides. One idea per slide. Large type, plain background, no gimmicks. |
| Investor attention studies | A reviewer spends **~15–35 seconds per slide**. If a slide needs reading, it has failed. |
| SIH official evaluation | Scored on **Innovation · Invention · Technical Feasibility · Impact & Benefits · Architecture**. |
| SIH internal round weighting | Problem Understanding & Impact ~25% · Innovation & Technical Excellence ~30% · Feasibility the rest. |
| SIH past winners | *"Present like a startup — problem, solution, impact, scalability in 5 minutes."* And: **"Demo live — hardcoded demos get caught."** |

### The three decisions this template makes for you

1. **Lead with scale, not with the problem.** Every team at PS 26102 opens on
   "MPLADS has corruption problems." The judge has heard it nine times before
   lunch. You open on the one fact none of them can say: **210,993 real works.**

2. **Volunteer your weakest number before you are asked.** Slide 7 prints the
   0.050 silhouette and the screen that can prove you wrong. This is
   counter-intuitive and it is the single strongest move in the deck — it buys
   more credibility with a statistician on the panel than any dashboard.

3. **Every slide uses its whole canvas.** Each layout below is given as zones
   (left / right / bottom strip). No slide has a lonely headline floating in
   white space, and no slide is a wall of text. Where a zone would be empty, the
   template puts a proof strip there instead.

### Deck rules — apply to all slides

- **Bullets: 6–10 words. One line. Never two.**
- **Numbers are typed exactly** as written here. They are all real and all
  defensible. Do not round ₹47.11 Cr to "₹47 Cr" — precision reads as truth.
- **No jargon without a plain-English gloss in the same breath.** "Survival
  analysis — the maths hospitals use to study patient outcomes."
- **Never the word "fraud" as a claim.** The product is an *investigation lead*.
  A judge who catches you claiming fraud detection without fraud labels will
  spend the rest of your slot on it.
- **Footer on every slide:** `SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus`
  and the slide number. Nothing else.
- **Colour:** one accent only. Deep navy ground, saffron/amber accent, near-black
  text on white cards. Red **only** for the one number you want remembered.
- **Type:** one sans family. Headline 40–54pt, bullets 20–24pt, captions 14pt.
  If it does not read from four metres, it is too small.

---

# SLIDE 1 — Title

**Purpose:** establish that this is a working system, not a proposal, before you
have said a word.

### 🏆 Winning point
> **210,993 real government works.** Say the number out loud in your first
> sentence. Everything else in the deck is downstream of it.

### Content

**Title:** Public money, checked work by work.
**Subtitle:** An AI-assisted monitoring layer for MPLADS · Built on the live eSAKSHI record
**Team strip:** Team Morior Invictus · PS 26102 · Ministry of Statistics & Programme Implementation

### Layout
Full-bleed navy. **Title block left-centre (55% width).** **Right 40%:** one
screenshot of the live heat map of India, angled slightly, with a soft shadow.
**Bottom strip, full width, four cells, thin dividers between:**

| 2,10,993 | 37,705 | ₹1,302 Cr | 357 |
|---|---|---|---|
| real works checked | flagged for review | money at risk | automated tests passing |

### Visual
The heat-map screenshot. Not a logo, not a stock illustration. The judge must
see a working screen in the first two seconds.

### Tone
Calm and factual. No tagline, no slogan, no "revolutionising governance."

---

# SLIDE 2 — The Problem

**Purpose:** show you understand the *real* constraint, which is not corruption
— it is that nobody can look at two lakh works.

### 🏆 Winning point
> **"An officer has twenty days and two lakh works."** Frame it as an
> impossible-arithmetic problem, not a morality problem. Every other team will
> say "fraud is bad"; you say "the checking does not scale."

### Content

- Every MP gets ₹5 crore a year to fund local works.
- The record holds 2,10,993 works and grows daily.
- Nobody can read them. Checking is manual and reactive.
- Officers pick by complaint, or by district rota.
- Result: money sits in works nobody revisits.

### Layout
**Left 45%:** the five bullets, generous line spacing.
**Right 55%:** a single stark visual — a dense grid of 2,000 tiny grey squares
with **4 circled in amber**. Caption beneath: *"An officer can visit about four
works a week. There are 2,10,993."*

### Visual
That grid. It is the most memorable image in the deck because it needs no
explanation.

### Tone
Matter-of-fact, sympathetic to officials. **Never accusatory.** These are
overloaded public servants, not villains — and a judge from MoSPI is in the room.

---

# SLIDE 3 — The Solution

**Purpose:** land what the system does in one sentence a non-technical judge can
repeat to a colleague.

### 🏆 Winning point
> **"It does not find fraud. It decides where to look first."** This single
> sentence is your positioning. It is honest, it is defensible, and it separates
> you from every team claiming an AI fraud detector.

### Content

**Headline:** We rank where to look, and we prove why.

- Five independent checks run on every work.
- A work is flagged only when two checks agree.
- Each flag opens a case file with its evidence.
- Every case ends in "a human should check this."

### Layout
**Top band (full width):** the one-sentence positioning, large, centred.
**Below, five equal columns** — one per check, each with an icon, a name, and its
real count:

| High cost | Long delay | Odd numbers | Agency changed | Possible repeat |
|---|---|---|---|---|
| 14,041 | 8,605 | 4,056 | 34,966 | 17,142 |

**Bottom strip:** `Two or more must agree → 37,705 flagged → 4,478 most urgent`

### Visual
A left-to-right flow: five check boxes → a "2+ agree" gate → two output figures.
Keep it one line high. Do not draw a full architecture diagram here; that is
Slide 5.

### Tone
Plain and declarative. The counts do the persuading.

---

# SLIDE 4 — Key Innovation

**Purpose:** this is the **Innovation + Invention** score. Spend your best
material here.

### 🏆 Winning point
> **"Every other team measures how late the finished works were. That number is
> wrong, because it ignores every work that never finished."** Say this and the
> technical judge will lean forward. You are correcting a mistake your
> competitors are actively making.

### Content

**Headline:** We fixed a statistic everyone else gets wrong.

- Most teams measure delay on completed works only.
- That silently drops 1,25,220 unfinished works.
- We use survival analysis — the maths of patient outcomes.
- It counts the works still running, honestly.
- Held-out accuracy: **C-index 0.6759.**

### Layout
**Left 50%:** the bullets.
**Right 50%:** a two-panel before/after chart.
- Panel A, greyed, labelled *"What the naive number sees"* — only completed works.
- Panel B, in accent colour, labelled *"What we see"* — all works, unfinished ones
  shown as open-ended bars running off the right edge.

**Bottom strip, three cells:** `Cox survival model` · `IsolationForest anomalies`
· `MiniLM description clustering` — with the caption *"Three trained models. None
of them predicts fraud, because no fraud labels exist."*

### Visual
The two-panel chart is the hero. The open-ended bars running off the edge of
Panel B *is* the insight, drawn.

### Tone
Confident and specific. This is the one slide where you may sound technical —
but gloss every term in the same sentence.

---

# SLIDE 5 — How It Works / Architecture

**Purpose:** this is the **Architecture** and **Technical Feasibility** score. A
judge is checking whether this could actually run inside a ministry.

### 🏆 Winning point
> **"It reads the live portal, not a downloaded copy."** Most teams demo on a
> CSV someone scraped months ago. You poll the real eSAKSHI API and reconcile
> against the portal's own published totals.

### Content

- Live feed polls the official eSAKSHI API.
- Change detection: 20 requests drop to 4 when nothing moved.
- Reconciled against the portal's own totals — counts match exactly.
- Models score every work; case files carry the evidence.
- Cases hand off to Salesforce for the human work.

### Layout
**Full-width horizontal architecture band across the middle 60% of the slide**,
five stages left to right with arrows:

`eSAKSHI live API → ingest + reconcile → 3 models + 5 checks → case file with evidence → Salesforce casework`

**Above the band:** the headline.
**Below the band, three small proof cards:**
- *Reconciliation:* counts exact across 12 checks, 3 states
- *Freshness:* polled, not pushed — the portal offers no webhook
- *Stack:* Python · FastAPI · scikit-learn · lifelines · React

### Visual
The five-stage band. Label every arrow with what flows along it. **Do not** draw
a cloud-architecture diagram with fifteen boxes — a judge has 30 seconds.

### Tone
Engineering-confident. Mention the polling limitation yourself: *"the portal has
no webhook, so we poll — freshness is bounded by the interval, and we say so on
screen."* Naming your own constraint reads as mastery.

---

# SLIDE 6 — Live Demo

**Purpose:** SIH winners are explicit that **hardcoded demos get caught**. This
slide exists to hand over to a real screen.

### 🏆 Winning point
> **Upload a file the judge picks.** Say: *"Give me any photograph."* Eleven
> checks then run in front of them on data nobody pre-arranged. Nothing else in
> the room will look like this.

### Content

**Headline:** Take any work board photograph. Watch eleven checks run.

- Reads the board, matches it to a real work.
- Two readers must agree, or a human decides.
- Checks the amount against the record.
- Finds the same photo used for another work.
- Ends in a lead with its evidence.

### Layout
**Left 38%:** the five bullets as a numbered run-order for the presenter.
**Right 62%:** a screenshot of the `/submit` screen mid-assessment, with the
red **BLOCKED** row visible.
**Bottom strip, full width, in mono type — the actual output:**

```
■ Identify the work     file reads MP3017167-W136962 but form says MP3018356-W86316
▲ Check the photograph  already submitted for MP3017167-W136962
▲ Cross-check amount    ₹9,83,000 against ₹6,50,00,000 on record
▲ Investigation lead    HIGH — 4 pieces of evidence, 4 signal families
```

### Visual
That output block is the whole slide. It shows the system **refusing to decide**
— which is the point.

### Tone
Understated. Let the screen talk. **Rehearse the offline fallback** — a recorded
video and a screenshot deck — and never mention it unless the wifi dies.

---

# SLIDE 7 — Results & Proof

**Purpose:** this is **Impact & Benefits**, and it is where you win on
credibility rather than on features.

### 🏆 Winning point
> **The budget table.** "Fifty officer-days. Our plan protects ₹47.11 crore.
> Picking at random protects ₹0.5 crore." One table, ninety-four times the
> return, and it answers the only question an official actually asks.

### Content

**Headline:** Fifty officer-days. Where do you send them?

| Strategy | Works | Visits | Money protected |
|---|---|---|---|
| **Our plan** | **100** | **23** | **₹47.11 Cr** |
| Down our own list | 74 | 37 | ₹42.4 Cr |
| Biggest amounts first | 72 | 38 | ₹28.1 Cr |
| Riskiest first | 94 | 26 | ₹3.7 Cr |
| Picking at random | 55 | 47 | ₹0.5 Cr |

### Layout
**Left 55%:** the table, with the first row emphasised.
**Right 45%, stacked — the honesty block, boxed and titled "What we get wrong":**
- Our clustering scores 0.050. That is weak. We print it.
- We have a screen built to prove us wrong.
- Only a site visit is real evidence. We have 3.
- No fraud score — there are no fraud labels.

### Visual
Keep it a table. A bar chart of the same five rows works if the table feels
heavy, but the numbers must stay legible.

### Tone
**This is the slide that wins the room.** Deliver the honesty block without
apology, at the same volume as the table. *"We are telling you our weakest
number before you ask for it."*

---

# SLIDE 8 — Why This Matters / Scale

**Purpose:** the **scalability** leg of "problem, solution, impact, scalability."

### 🏆 Winning point
> **"It already runs on the whole country."** Not a pilot, not a district — 36
> states, 545 constituencies, 778 agencies, today. Scaling is not a plan, it is
> a completed fact.

### Content

- Runs on all 36 states and union territories today.
- Same engine works for any scheme with a work record.
- The ministry keeps its own data; nothing leaves.
- Ten languages, so an officer reads in their own.
- Costs one server. No GPU required to run.

### Layout
**Left 40%:** bullets.
**Right 60%:** the heat map of India, full colour, with the statistically
significant states ringed.
**Caption under map:** *"Delhi: 6.20% most-urgent rate against 2.13% nationally —
and the map refuses to colour a state with too few works to judge."*
**Bottom strip:** `36 states · 545 constituencies · 778 implementing agencies · 10 languages`

### Visual
The map, at full width of its zone. This is the slide's argument.

### Tone
Understated confidence. The map does the work.

---

# SLIDE 9 — Team

**Purpose:** credibility. Keep it to 20 seconds.

### 🏆 Winning point
> **Name what each person actually built**, not their designation. "Built the
> survival model" beats "ML Lead" every time with a technical judge.

### Content

Four to six members, each: **Name — the thing they built.**
Examples of the right phrasing:
- Built the survival model and the audit planner.
- Built the live portal feed and reconciliation.
- Built the React application and the heat map.
- Built the OCR pipeline and photo forensics.

**Mentor line:** one line, name and institution.

### Layout
**Even grid of member cards** — photo, name, one line each. 3×2 or 2×2.
**Bottom strip:** `357 automated tests · 47 API routes · 18 screens · one repository`
with the caption *"Everything in this deck runs from one `git clone`."*

### Visual
Real photographs, same crop, same background. Mismatched selfies read as
unprepared.

### Tone
Brief and factual. Do not read the slide aloud — let them read it while you
speak to the next point.

---

# SLIDE 10 — Call to Action

**Purpose:** tell the judge exactly what happens next. Most teams end on "thank
you" and waste the last slide.

### 🏆 Winning point
> **Ask for the one thing only MoSPI can give: field verification data.** It
> shows you know precisely what your system is missing and that you are not
> pretending otherwise.

### Content

**Headline:** What we need next is not code.

- Give us 500 real site visits. We can then measure ourselves.
- Connect the feed to the internal portal, not the public one.
- Pilot in one state for one quarter.
- Everything else is built and running today.

### Layout
**Left 50%:** the four asks, numbered, large.
**Right 50%:** a simple three-step timeline — `Pilot (1 state, 1 quarter)` →
`Measure against real visits` → `National rollout` — with honest labels under
each.
**Bottom strip, full width, the closing line in large type:**

> *"It gives investigators evidence and priorities — not accusations.
> An AI that knows what it doesn't know."*

### Visual
The timeline, kept to three steps. Resist adding a fourth.

### Tone
Direct. End on the quoted line, then stop talking. **Do not add a "Thank You"
slide** — it wastes your last frame of attention.

---

## Appendix slides — build them, keep them hidden

Judges ask questions. Have these ready to jump to, never in the main flow.

| # | Slide | Have it ready for |
|---|---|---|
| A1 | Data contract & known gaps | *"How clean is your data?"* |
| A2 | Vendor concentration — DARBHANGA, 570 payments, 11 vendors | *"Can you catch collusion?"* |
| A3 | OCR benchmark, 11 photograph conditions | *"What if the photo is bad?"* |
| A4 | Security: JWT, RBAC, hash-chained log | *"Is it safe for government?"* |
| A5 | Competitor comparison | *"How are you different?"* |
| A6 | Evidence trail & immutability | *"Can records be tampered with?"* |

---

## Final check — score your own deck before the judges do

Run this before you present. Any "no" is a slide to rebuild.

| Question | Where it is answered |
|---|---|
| Would this hold attention after 200 pitches? | Slide 1 number · Slide 4 correction · Slide 7 honesty |
| Is every word earning its place? | No bullet over 10 words. Count them. |
| Could a non-technical judge repeat our pitch? | *"They decide where officers should look first."* |
| Do we show, not tell? | Slide 6 is a live upload, not a screenshot tour |
| Have we named our own weaknesses? | Slide 7 honesty block |
| Can we survive the wifi dying? | Recorded demo + screenshot deck, rehearsed |
| Does it map to SIH scoring? | Innovation S4 · Feasibility S5 · Impact S7 · Architecture S5 · Invention S4 |

### Timing — 5 minutes

| Slide | Seconds |
|---|---|
| 1 Title | 15 |
| 2 Problem | 30 |
| 3 Solution | 35 |
| 4 Innovation | 50 |
| 5 Architecture | 40 |
| **6 Live demo** | **90** |
| 7 Results | 45 |
| 8 Scale | 25 |
| 9 Team | 15 |
| 10 Call to action | 25 |

The demo gets the largest single block. Cut Slide 8 before you cut Slide 6.

---

## Sources consulted

- [Y Combinator pitch deck template — Slidebean](https://slidebean.com/templates/y-combinator-pitch-deck-template)
- [How to Write a Y Combinator Pitch Deck — Storydoc](https://www.storydoc.com/blog/y-combinator-pitch-deck-examples)
- [The 12-Slide Framework That Gets Funded — Deckary](https://deckary.com/blog/pitch-deck-template)
- [Evaluation Guideline for Smart India Hackathon — Scribd](https://www.scribd.com/document/712193023/Evaluation-Guideline-for-Smart-India-Hackathon-2023)
- [SIH 2026 Complete Guide — Reskilll](https://reskilll.com/blogs/smart-india-hackathon-2026-complete-guide-registration-themes-winning/)
- [How To Win Smart India Hackathon — Tips From Past Winners](https://thenewviews.com/how-to-win-smart-india-hackathon/)
- [SIH Winners' PPTs and sources — GitHub](https://github.com/Aadiii00/SIH-Winners-PPt-and-Sources)
