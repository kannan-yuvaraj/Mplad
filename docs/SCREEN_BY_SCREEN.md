# The website, screen by screen

**Every screen mapped to the Project Constitution — what it is, what to say, and what a judge will ask.**
Figures below were read from the running site on 2026-09-06, not from memory.

> **The one rule that governs every screen.** Constitution §12: *"AI SHALL NOT DECLARE FRAUD."*
> Every screen outputs an **investigation lead** with evidence, and ends in a human decision.
> If you remember nothing else, remember that the product's job is to answer **"where should I
> look first?"** — never **"who is guilty?"**

---

## The spine — Constitution §1

Every screen is one rung on a ladder. This is the mental model; if you can recite it, the
whole site explains itself.

```
What happened?          ->  Overview
What looks unusual?     ->  Investigation Queue
Why is it unusual?      ->  Case File
Is behaviour changing?  ->  Temporal · Agency Dossier
What may go wrong?      ->  Compliance & Early Warning
How much is at stake?   ->  Rs exposure (on every screen)
Investigate first?      ->  Audit Plan
Who goes, and when?     ->  Field Rota
What did we find?       ->  Field Scoreboard
Then what happens?      ->  Salesforce & Agentforce
Can I trust any of it?  ->  Data Transparency · Work Archetypes · How it works
```

The last four rungs are **new since Constitution v1** — v1's ladder stopped at "investigate
first" and never answered *"and then what?"*

---

# MONITOR

## 1 · Overview — the whole country on one screen

**Constitution:** §13 Screen 1 · UVP-3 (₹ exposure)

Four numbers, and one of them needs care.

| Figure | Value |
|---|---|
| Works monitored | **2,10,993** (85,773 done · 1,25,220 open) |
| Total recommended | **₹11,565 Cr** |
| **Exposure at risk** | **₹1,302 Cr** |
| Investigation leads | **37,705** — 4,478 HIGH · 33,227 MEDIUM |

### Say this, slowly

> "Exposure is **not** money lost. It is **not** money stolen. Nobody has alleged anything.
> It is the sanctioned amount multiplied by the probability the work does not finish in a
> year. If a ₹10 lakh work has a 30% chance of stalling, that is ₹3 lakh of exposure.
>
> It answers the question an auditor actually has: *if I can only chase some of these, where
> is the most public money hanging in the balance?*"

**Constitution §20-B** requires that qualification every time. Say "exposure", never "loss".

### The confidence-bands chart

Red / amber / green, **plus a distinct shape** (▲ ◆ ● ■) on every indicator.

> "Roughly one man in twelve is red-green colourblind, and this is a government tool. Severity
> is never carried by colour alone."

**HIGH** = three or more *independent* signal families agreed. **MEDIUM** = two. One signal
alone is usually noise, which is why a work is never surfaced on one.

---

## 2 · Investigation Queue — the screen an officer works from

**Constitution:** §13 Screen 3 · UVP-6 (evidence fusion)

Two lakh works became a ranked list. The ranking is **Audit-ROI**:

> **priority × ₹ exposure × corroboration** — *how odd is it, times how much money is at
> stake, times how many independent signals agree.*

Click any row: it expands in place and tells you **why it is there**. No black box.

---

## 3 · Audit Plan — ⭐ the strongest screen you have

**Constitution:** §13 Screen 7 · UVP-7 (audit-ROI optimisation under a capacity budget)

**This closes the biggest gap between claim and code.** v1 promised "optimisation under an
audit-capacity budget"; for a long time only the ranking existed. It exists now.

### The idea in one sentence

> "An inspector has a finite number of days. This decides **which works those days should be
> spent on** — and it beats simply working down the ranked list."

### The insight that makes it work

The first visit to an agency costs **1.0 day**. A second work at the *same* agency costs
**0.35 days** — because someone is already standing there.

> "So the plan deliberately clusters works by agency. It is not just picking the top N; it is
> picking the set that fits the budget and covers the most rupees."

### The result — at a 50-day budget

| Strategy | Works | Agencies | ₹ covered | Share of best |
|---|---|---|---|---|
| **Optimised plan** | **100** | **23** | **₹47.1 Cr** | **100%** |
| Audit-ROI ranking | 74 | 37 | ₹42.4 Cr | 90.1% |
| Biggest cheques first | 72 | 38 | ₹28.1 Cr | 59.7% |
| **Highest risk first** | 94 | 26 | **₹3.7 Cr** | **7.9%** |
| Random selection | 55 | 47 | ₹0.5 Cr | 1.0% |

### 🎯 The line that wins the room

> "**Highest risk first** is what a naive anomaly dashboard does. It covers **7.9%** of what
> we cover in the same fifty days — because the riskiest works are often small ones. And we
> are **94× better than random**.
>
> That gap is the entire argument for decision-support over detection."

### The coverage curve

| Budget | Optimised | Ranking |
|---|---|---|
| 10 days | ₹16.6 Cr (17 works) | ₹15.3 Cr (13) |
| 50 days | ₹47.1 Cr (100 works) | ₹42.4 Cr (74) |
| 250 days | ₹120.7 Cr (539 works) | ₹109.5 Cr (420) |

This is exactly **§10's "₹-exposure covered within top-K vs a baseline"** — the evaluation
metric the Constitution promised.

### The contract, shown on screen

> *"A recommended plan for a human to approve, amend or reject. It allocates attention; it
> does not allege anything about any work, agency or person."*

---

## 4 · Field Rota — who goes, and when

**Constitution:** extends UVP-7 into execution — **not in v1 at all**

Turns the plan into a **staffed schedule**: 4 auditors · 23 trips · 100 works · 49.95
auditor-days.

### Two things worth saying

**It is provably near-optimal.**

> "Balanced scheduling is NP-hard, so this is a heuristic — trips are dealt longest-first to
> whoever is least loaded. But its longest round is **provably within 1.25× the best rota that
> exists**. We are not claiming optimality; we are claiming a bound."

Result: busiest auditor 12.7 days, quietest 12.3 — a spread of **0.4 days**.

**An agency is never split between two auditors.**

> "The plan's saving depends on the second work at an agency costing 0.35 of a day *because
> someone is already standing there*. Send two people and you pay for that arrival twice, and
> the plan's arithmetic stops being true."

That constraint is the honest consequence of the cost model — a detail most teams would miss.

### The contract

> *"A draft rota for a supervisor to amend. It does not know who is on leave, which districts
> are neighbours, or who already knows an agency."*

**Constitution §12** — the system recommends, humans decide.

---

## 5 · Agency Dossier — the actor, not the row

**Constitution:** UVP-4 (entity behavioural fingerprint) · §19 Q19

Everything about one implementing agency: portfolio, what was surfaced, top leads, **internal
duplicates**, and its **field history**.

### Why this exists — §7 killed signals

> "We tested raw agency concentration and **killed it**. `IDA_NAME` is a District
> Magistrate's office — concentration there is administrative structure, not wrongdoing.
>
> So we do not rank agencies by volume. We give you one agency's whole picture and let you
> read it."

That answers §19 Q19 directly, and turns a rejected signal into a credibility point.

---

# CASEWORK & CRM

## 6 · Salesforce & Agentforce — and then what happens?

**Constitution v1 had no answer to this.** The lead becomes a managed case:
`Investigation_Case__c`, `Evidence__c`, a **5-stage Path** with written guidance, and an
Agentforce lookup topic.

> "Everything else produces a lead. This is where a lead becomes somebody's job, in a system
> government departments already run — with a stage, an owner and an audit trail."

The five stages read as a journey in colour: neutral (untouched) → brass (assigned) →
terracotta (in progress) → green (verified) → deep green (closed).

---

# INTELLIGENCE

## 7 · Temporal — has behaviour changed?

**Constitution:** §13 Screen 5 · UVP-5

**73 of 697** agencies show a measurable shift between how they behaved before and after.

> "Green means normal or stable. Amber is a drift. Red is a sudden break. **A break is not
> wrongdoing** — a new officer, a new scheme, a flood all produce one. It means *something
> changed, go and ask what.*"

⚠️ **Be precise here.** The Constitution specifies CUSUM / Jensen-Shannon change-point
detection. What is built is a **level-shift heuristic** — it detects *that* behaviour shifted,
not yet *when*. Your revised deck already says "change-date: planned", which is the right
posture. Do not claim more.

---

## 8 · Near-Duplicates — the screen that shows judgement

**Constitution:** §7 (killed: naive duplicate detection)

**2,23,407** similar pairs found → **47,709** kept as concerning.

> "Repeated descriptions are **normal** here. One MP recommending forty street lights writes
> the same sentence forty times. Flag all of those and you bury the officer in noise, and they
> stop using the tool by Tuesday.
>
> So a pair only counts when it is near-identical **and** from the same implementing agency
> **and** for a near-identical amount. That is the shape a repeated claim would take."

> "The most useful thing on this screen is the 1,75,698 pairs we threw away."

---

## 9 · Compliance & Early Warning — where authority is declared

**Constitution:** §3.3 rule 6 · §12

Eight lifecycle checks, plus early-warning levels over open works, plus a Health Index of
**62.9/100**.

### The Authority column is the point

> "Every check declares where its authority comes from: **Official rule**, **Observed
> baseline**, or **Statistical outlier**.
>
> We assert **no official rules at all** — because no statutory threshold ships with this
> public data. Calling a statistical outlier a legal breach would be inventing law. **There is
> an automated test that fails the build if anyone tries.**"

That single paragraph is the difference between a defensible system and one thrown out of court.

---

## 10 · Work Archetypes — what the machine taught itself

**Constitution:** UVP-1 · §10

50 work types, discovered from descriptions with no labels. **49 named, 1 honestly labelled
"uninterpretable."**

### Say the silhouette number before a judge finds it

> "Silhouette is **0.050**. That measures how *separated* clusters are — **it is not
> accuracy**. Real text clusters overlap: a 'community hall' and a 'community centre' genuinely
> are close. A high silhouette here would mean we cherry-picked easy clusters.
>
> Which is exactly why archetypes are our **secondary** peer axis. The primary one is the
> official government category — 118 of them, parsed out of `ACTIVITY_NAME`, covering 93% of
> works. Both the problem deck and the previous team called that field unusable. It is a
> composite string. Nobody split it."

---

# TRUST

## 11 · Data Transparency — ⭐ your strongest screen with sceptics

**Constitution:** §13 Screen 8 · §3.2

Green = measured from records. Amber = derived, with confidence stated. **Red = unavailable,
and we refuse to fake it.**

### The four honest limitations

1. **No expenditure analysis.** `ACTUAL_AMOUNT` equals the recommended amount on **98.35%** of
   completed works; not one exceeds 1.05×. **We measured that rather than assuming it.**
2. **No sanction date.** Sanction rows copy the recommendation date verbatim on **100.00%** of
   1,79,676 works. Presence is testable; timing is unknowable.
3. **No district column.** So we make no district-level claims.
4. **No cost estimate anywhere.** So no overrun detection is possible.

> "Every one of those is on screen with the measurement that proves it, and the code already
> has typed, empty interfaces ready if MoSPI grants the richer data."

---

## 12 · Field Scoreboard — ⭐ the answer to your own hardest problem

**Constitution:** §3.2 ("no fraud labels") — **absent from v1**

| | |
|---|---|
| Verifications recorded | **4** |
| Concerns confirmed on site | 4 |
| Still needed to fit weights | **496** |

### Why this is the most important screen in the product

> "The deepest problem with this problem statement is that **there are no fraud labels**.
> Nobody ever marked a row 'this one was a problem'. So no honest system can be trained to
> predict fraud, and no honest team can quote an accuracy figure.
>
> These verification records **are** those missing labels — accumulating one site visit at a
> time. At about 500, our scoring weights stop being reasoned defaults and start being fitted
> to what officers actually confirmed on the ground.
>
> **We have 4. And this screen says 4** — not 'coming soon'."

> "Everyone else's model is as good on day 1000 as on day one. Ours is built to improve, and
> it shows you exactly how far along that is."

Demo records are **excluded from the count**, so a walkthrough cannot inflate it.

---

## 13 · How it works — the method, illustrated

Learn → Compare → Predict → Explain → Prioritise, with the Lego analogy (sorting a mixed box
into piles nobody named) and the school-bag analogy (compare a bag to other bags in your town,
not to every object in the shop).

---

# The assistant — on every screen

15 read-only tools over all 2,10,993 works.

> "It has **no independent knowledge** of this data and **cannot do arithmetic**, so it cannot
> invent a figure. And it shows you **which tool produced every answer** — that trace is how
> you check it rather than take it on trust."

It is **page-aware**: on a case file it offers questions about that work.

**Constitution §19 Q14** asked why not an LLM at all. The answer: the model supplies language
and navigation; the pipeline supplies truth. A prompt is a request — the output filter is the
guarantee.

---

# Three questions you will definitely get

**"Can you call this fraud?"**
> "No. By design. There are no fraud labels in this data, so a supervised fraud model would be
> fabricated. Every output is an investigation lead with its evidence, and a human decides."

**"How do you know it works without labels?"**
> "Two ways. We plant anomalies we designed ourselves into the real data — **69.25% detection**
> over 904 planted, 96.1% on stalled works. And on the Audit Plan we measure ₹-coverage against
> four baselines: we are 94× better than random and 12× better than picking the highest-risk
> works first."

**"What if you flag an innocent agency?"**
> "It is a lead, shown with its peer context, for a human. Nothing is asserted. And the Field
> Scoreboard records what the officer actually found — including when they found nothing."

---

# Numbers to quote — never estimate

| Measure | Value |
|---|---|
| Works | 210,993 (85,773 done · 125,220 open) |
| Recommended / exposure | ₹11,565 Cr / ₹1,302 Cr |
| Leads | 37,705 — 4,478 HIGH · 33,227 MEDIUM |
| Coverage | 36 states · 545 constituencies · 778 agencies |
| Archetypes | 50, silhouette **0.050** *(separation, not accuracy)* |
| Completion risk | Cox PH held-out **C-index 0.6759** |
| Duplicates | 223,407 pairs → 47,709 concerning |
| Behaviour shifts | 73 of 697 agencies |
| Health Index | 62.9 / 100 |
| Synthetic detection | **69.25%** over 904 planted |
| Audit Plan @ 50 days | **₹47.1 Cr** vs ₹0.5 Cr random |
| Field verifications | **4** of ~500 |
| Tests | **247 passing** |

**Never claim:** fraud detected · a fraud percentage · **100% accurate** · cost-overrun on real
data · tamper-**proof** (it is tamper-**evident**) · that the AI decides audits · that we
invented any algorithm.

⚠️ **Deck correction:** slide 3 says C-index **0.743**. The trained model reports **0.6759**.
Fix the slide — 0.6759 is perfectly defensible.
