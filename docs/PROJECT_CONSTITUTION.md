# PROJECT CONSTITUTION — FINAL (v4)

**SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus · St. Joseph's Institute of Technology, Chennai**
**v1 authored 2026-08-24 · v2 re-audited 2026-08-27 · v3 re-audited 2026-09-12 · v4 FINAL 2026-09-12**

> **What this is.** The authoritative reference for the project: what we are building, what
> is true, what is forbidden, and what is not built. Where any other document conflicts,
> resolve by: (1) prefer the latest validated real-data audit; (2) prefer actual computation
> over assumption; (3) preserve uncertainty when unresolved; (4) document conflicts, never
> silently pick the convenient answer.
>
> **Provenance of v4.** Two sources, both read on 2026-09-12:
> 1. **The working tree** at `C:\Users\kanna\Downloads\MPLADS - Copy` — `data/artifacts/*.json`,
>    `models/metrics.json`, `ocr_benchmark.json`, a full `pytest` run, the route tables, and
>    `ingestion/research/*`.
> 2. **Every session transcript of this project** — 37 transcripts, 25 August to 12 September,
>    920 human messages. That is where the mandates in §1 come from: they exist in no file.
>
> v1 and v2 are in the older, stale `MPLADS` folder. **This file supersedes both, and the v3
> written earlier today.** It ships with the code.

---

## 1. The mandates — requirements that came from people, not from the data

These are binding, and none of them is discoverable by reading the repository.

| # | Mandate | Who and when | How it is satisfied |
|---|---|---|---|
| M1 | **"AI-powered monitoring and analytics platform… detect trends, anomalies, irregularities and potential fraud"** | The official PS 26102 text | §3 — reframed as leads, never verdicts (§4.1) |
| M2 | **Use Salesforce for the auditor and ministry point of view, and Agentforce as the chat agent** | Round-1 judge, 2026-08-27 | §12 — 500 cases, 1,586 evidence rows, 5-stage Path, 10-language topic router |
| M3 | **"The data should be dynamic, and show the workflow of how the entire app works line by line. It shouldn't look like a prototype — it should look like a deployable app"** | SIH evaluator, 2026-09-11 | Step-by-Step screen (10 stages, live figures, one real work traced end to end); every page stamps when it computed and in how long |
| M4 | **Make the AI anomaly detection the visual and conceptual centrepiece; auditor tools are supporting layers, not equal focal points** | Design audit, 2026-09-11 | Detection Centre; the Find → Act → Check information architecture (§9) |
| M5 | **Make it look like an authentic Government of India portal — not a SaaS dashboard, not an AI startup page. Change the frontend only; break nothing** | 2026-09-10 | §9 visual system; every feature, route, API call and auth path preserved |
| M6 | **"Everything must be understandable by a layman or even a school child — change nothing but the way you portray the details"** | 2026-09-11 | §10 plain-language discipline |
| M7 | **Read site photographs and case documents; use Surya OCR and Docling, implemented fully** | 2026-09-11 | §11 |
| M8 | **The real system must take live data from eSAKSHI, not a third party's scrape** | 2026-09-06 | §13 live-portal ingestion, measured against the portal on 2026-09-10 |
| M9 | **Deploy it publicly** | 2026-09-11/12 | §15 — one working public route today, one blocked on account quota |

**A tenth, standing mandate:** never fabricate government data that does not exist. Where the
PS asks for something the data cannot support, say so and substitute a defensible alternative.

---

## 2. What we are building (one breath)

An **AI-assisted monitoring and decision-support system for MPLADS** that learns what "normal"
work looks like from the national portfolio, flags statistically and behaviourally unusual
activity **relative to genuine peers**, estimates **completion risk** and the **₹ exposure**
attached to it, detects **when an agency's behaviour changes**, **plans where a finite number
of auditor-days should go**, and **records what an officer found when they went and looked** —
producing **investigation leads with evidence, never fraud verdicts.**

It is **not** "an AI dashboard that gives every work a fraud score."

---

## 3. The ladder — the conceptual spine

```
What happened?          -> ingest + normalise the real MPLADS lifecycle
What looks unusual?     -> archetype-conditional anomaly (peer-relative, not global)
Why is it unusual?      -> evidence fusion + explainable case file
Is behaviour changing?  -> agency trend + level-shift detection
What may go wrong?      -> completion-risk / time-to-event model
How much is at stake?   -> Rs exposure-at-risk quantification
Investigate first?      -> Audit-ROI ranking
What did we find?       -> field verification: the officer's own observation, recorded
Who may see it?         -> RBAC scope + hash-chained audit log
Who acts on it?         -> Salesforce case management, 5-stage path
Where do the days go?   -> budgeted audit plan (travel-aware, not a sort)
Who goes where?         -> field rota, whole agencies per auditor
What do I read first?   -> agency dossier, rate not count
Were we right?          -> field scoreboard, the screen allowed to say no
```

Every screen is one rung. If you can recite the ladder, you can defend the product.

---

## 4. The seven hard constraints

Product constraints, not style preferences. They must survive into code **and** interface copy.

1. **No fraud verdicts, ever.** Output is a lead with evidence and a human decision. No field,
   variable, column or label may be named `fraud_probability`, `is_fraud`, `fraud_score` or
   `fraudulent`. `test_no_fraud_language_in_the_source_tree` greps the whole `src/` tree.
   **Rephrase, never exempt.**
2. **No fraud classifier.** No fraud labels exist in any public MPLADS source, so any
   supervised fraud model is fabricated. Scoring is transparent, weighted, rule-based.
3. **Silhouette 0.050 is separation, not accuracy.** Say so wherever it appears.
4. **`ACTUAL_AMOUNT` is not expenditure — in this snapshot.** 98.35% of completed works have it
   exactly equal to `RECOMMENDED_AMOUNT`; none exceeds 1.05×. **No cost-overrun claim is
   permitted.** Live portal measurement (§13) shows actual differs from *sanctioned* more often
   (81–95% equal in two states, every difference a saving). That **does not overturn** the
   constraint and must never be quoted as if it did; it means the question deserves a national
   re-measurement on fresh data before the conclusion is carried into another release.
5. **Human-in-the-loop.** Every recommendation ends in "a person should check X".
6. **Field verification is the only ground truth there will ever be.** Records are immutable,
   attributed, and counted honestly — `field.label_readiness()` reports the gap to 500 rather
   than implying it is closed, and demo-seeded records are excluded from the count.
7. **Two independent readers, two independent signal families.** A work becomes a lead only
   when ≥2 signal families agree; a photographed board reference is accepted only when two OCR
   engines agree, and even then the officer confirms.

---

## 5. Verified numbers — quote these, never estimate

Read from `data/artifacts/` on 2026-09-12.

| Measure | Value |
|---|---|
| Works | **210,993** (210,987 after dropping 6 with amount ≤ 0) |
| Completed / open | 85,773 / 125,220 |
| Recommended / exposure | **₹11,565 Cr / ₹1,302 Cr** |
| Leads | **37,705** — 4,478 HIGH · 33,227 MEDIUM (LOW 107,978 and NONE 65,310 carry no lead) |
| States / constituencies / agencies | 36 / 545 / 778 |
| Archetypes | **50** (49 named, 1 honestly "uninterpretable") from 187,865 descriptions |
| Compliance-flagged works | 5,946 |
| Duplicate pairs | 223,407 → **47,709 worth a look** |
| Agencies analysed / changed | 697 / **73** |
| Early warning (open works) | HIGH 292 · MEDIUM 18,157 · LOW 106,771 · CRITICAL 0 |
| Health Index | **62.9 / 100** |
| Cox C-index (held out) | **0.6759** (84,311 events, 125,896 censored) |
| Silhouette at K=50 | **0.050** — separation, never accuracy |
| IsolationForest flagged | 4,220 |
| Synthetic validation | **69.25%** of 904 planted anomalies surfaced |
| Tests | **300 passing, 1 skipped** (the skip starts Surya's GPU server: `MPLADS_TEST_SURYA=1`) |
| API routes / screens / languages | **47 / 17 / 10** |

### 5.1 What the data does NOT contain

No fraud labels · no independent expenditure in the snapshot · no sanction *date* (sanction
rows copy the recommendation date on 100.00% of 179,676 works) · no cost estimate · no payment
tranches · no physical progress % · no district column · no downloadable attachments.
**Several of these exist on the live portal — see §13.**

### 5.2 Data facts that bite

- Join key is `(WORK_RECOMMENDATION_DTL_ID, mp_id)` → `work_ref`. **Never `WORK_ID`** (82% null).
- Censoring anchor = `max(RECOMMENDATION_DATE)` = **2026-05-26**. Using `max(all dates)` lands
  in 2044 and inflates every open duration by ~18 years.
- `ACTIVITY_NAME` is a composite; parsing yields **118 official categories at 93% coverage**.
  Two previous teams called this field unusable — they never split it.
- The 3,987 "corrupt" rows are **the portal's own response footer** (`Total_Amt`), one appended
  per API response by the server (§13). Using them as a reconciliation oracle is sound; calling
  them MP-level summary records is not.

---

## 6. Architecture as built

```
ingest/       typed load -> normalise -> canonical parquet (row counts logged; a drop must be stated)
train.py      3 models -> data/artifacts/models/
pipeline.py   Learn -> Compare -> Predict -> Explain -> Prioritise
intelligence/ duplicates · temporal · compliance · early_warning · transparency · labels
              targeting (audit plan) · assignment (rota) · dossier (agency) · calibration (scoreboard)
ocr.py        Surya + RapidOCR (photographs) · Docling (documents)
field.py      immutable attributed site-verification records + camera evidence
salesforce.py CRM mirror + Agentforce topic router    casereport.py  PDF case report + day pack
chat.py       15 read-only tools over all 210,993 works    llm.py  briefings, template fallback
api/          app.py (47 routes) · auth.py (JWT/RBAC) · audit.py (hash chain) · strings/translations
ingestion/    live eSAKSHI portal collector -> data/portal/ (checkpoints, manifest, normaliser)
frontend/     React 18 + Vite 5, Government of India visual system, plain-language layer
```

**The audit plan is the strongest single piece.** Ranking answers *"what is worst?"*; an
official asks *"I have 50 auditor-days, where do I send them?"* — a different question, because
the first work at an agency costs a full day (travel, visit, write-up) and every further work
there costs 0.35 of a day. That one dependency makes it a route, not a sort. It is a greedy
optimiser with bundle look-ahead, it is a heuristic, and the tests say so; the comparison table
is built so it *can* report that we lost.

At 50 auditor-days: **100 works · 23 agency visits · ₹47.1 Cr** — against ₹42.4 Cr for our own
ranking, ₹28.1 Cr for biggest-cheques-first, ₹3.7 Cr for highest-risk-first, ₹0.5 Cr for random.

## 7. Models, and what their numbers actually mean

| Model | What it is | Honest metric |
|---|---|---|
| Archetype clustering | MiniBatchKMeans over cached MiniLM embeddings (384-d) | K=50 by sweep, **silhouette 0.050 — separation, never accuracy**; clusters rest on manual coherence |
| Completion risk | Cox proportional hazards, right-censored at the snapshot | **C-index 0.6759** — ranks which works finish sooner, never a probability of wrongdoing |
| Anomaly detection | IsolationForest over standardised `[log_amount, age_days]` | **4,220 flagged**, a corroborating signal only |

`sentence-transformers` and a GPU are **not** needed to run: embeddings were computed once and
cached, so the pipeline runs in ~90 seconds on CPU.

## 8. Killed approaches — keep these, they are a credibility weapon

Cost overrun (no expenditure in the snapshot) · payment-pattern anomalies (no tranches) ·
estimate-vs-actual (no estimate) · a fraud classifier (no labels) · district-level claims (no
district column) · verification of portal attachments (login-gated) · global anomaly scoring
without peers (a big road is not an anomaly) · blockchain (asked and rejected: an append-only
hash chain gives the same tamper-evidence without the theatre).

## 9. The product — 17 routes in three steps

**1 · Find** — Detection Centre (`/overview`) · Works to Check (`/worklist`) · Possible
Duplicates · Record Checks · Changes Over Time · Work Types · Case File (`/case/:ref`)
**2 · Act** — Visit Plan (`/audit-plan`) · Who Goes Where (`/rota`) · Agency Profile
(`/agency`) · Case Tracking (`/salesforce`)
**3 · Check** — Step by Step (`/workflow`) · Was It Right? (`/scoreboard`) · About the Data
(`/transparency`) · How It Works (`/how`)
Plus the landing page and sign-in.

Visual system: Government of India portal conventions — identity strip, masthead with the
ministry lockup, primary navigation numbered 1 · 2 · 3. **Severity is never carried by colour
alone**: `frontend/src/severity.js` is the single source, and every indicator also has a glyph
and a text label (red and amber cannot be separated under deuteranopia).

**The screen the system is allowed to lose on** is Was It Right? — no rate below 10 visits,
Wilson intervals, and the sampling bias printed beside the result.

## 10. Language discipline

- **Plain words everywhere**: "money at risk", not "exposure"; "works to check", not
  "investigation queue"; "how strong the clues are", not "confidence bands".
- **The engine's stored sentences are re-worded only at display time**
  (`frontend/src/plain.js`), with the original kept as a tooltip. Stored results never change.
- **Interface strings changed English values only** — no keys added, so all ten languages keep
  working (`src/mplads/api/strings.py`).
- Technical names survive in small print where a judge needs them (Cox, IsolationForest,
  MiniLM, silhouette) — never as the primary wording.
- Banned in output: fraud, guilty, corrupt, verdict. Permitted: unusual, worth checking,
  a person should check.

## 11. OCR — two readers for photographs, one for paper

| Job | Engine | Why |
|---|---|---|
| Photograph of a site board | **Surya OCR 2** (vision-language model, GGUF, run locally by `llama-server` on the GPU) | Reads a whole board, keeps a label beside its value, reads the ₹ sign |
| The same photograph again | **RapidOCR** (PP-OCRv4, CPU) | An independent second reader. Two readers agreeing is evidence; one reader at "99%" is not |
| Documents (PDF or scan) | **Docling** | Keeps tables and reading order; lists **every** work number, each checked against all 210,993 |

**Measured on 44 synthetic boards across 11 photograph conditions (Quadro T1000):**

| | Surya | RapidOCR |
|---|---|---|
| Work number exactly right | **93.2%** | 90.9% |
| Amount within 1% | **93.2%** | 72.7% |
| Motion blur | **50%** | 0% |
| Heavy JPEG | 75% | **100%** |
| Seconds per board | 20.4 | 2.0 |

On the 40 boards where both readers found a number they agreed 39 times and **never agreed on
the same wrong number**. The one disagreement was Surya misreading a compressed board — the
cross-check held it for the officer. At least one reader was exactly right on 95.5% of boards.

Rules: a match is never settled by the machine; Surya counts as available only after
`scripts/fetch_ocr_models.py` verifies the model against Hugging Face (size + SHA-256), because
a half-downloaded model has a valid header and would crash the server 40 s into startup; a
missing or failed Surya falls back to RapidOCR and the screen says so.
**The benchmark is synthetic and says so** — a real labelled sample replaces it the day one exists.

## 12. Salesforce + Agentforce (mandate M2)

The engine decides **where to look**; Salesforce carries **what happens next** — assignment,
review stages, approval, audit trail. Agentforce answers in the officer's language. The models
stay in Python because there is no Cox regression in Apex, and Salesforce holds the 500 cases
that need a human rather than the two lakh works that do not. **That split is the design.**

Live org: 500 `Investigation_Case__c`, 1,586 `Evidence__c`, 4 `Site_Verification__c`, a 5-stage
Path, case ageing, and ten Agentforce topics in ten languages.

**Two honest gaps: the Agentforce agent inside the org is NOT built** (what runs is our own
topic router over the same data — never claim otherwise), and `Audit_Assignment__c` is built and
exportable but not loaded into the org.

## 13. Live data from the portal (mandate M8)

Measured against `https://mplads.mospi.gov.in` on **2026-09-10**, recorded in
`ingestion/research/`.

- **The portal has a complete public JSON API.** Its dashboard is driven by unauthenticated
  REST endpoints; HTML scraping is unnecessary. Provenance shortens from
  *portal → unknown scraper → GitHub → us* to **portal → us**.
- **Three fields we do not currently have are public**: `VENDOR_NAME`, `VENDOR_ID` and
  payment-grain `FUND_DISBURSED_AMT` with dates. This is the single biggest unlock available —
  it would revive cost-overrun and payment-pattern analysis, both currently in §8.
- **Every count reconciles exactly** with the portal's own tiles across 12 checks; the two
  amount mismatches were explained, not smoothed: the "Works Completed" tile is the *sanctioned*
  value, the drill-down is the *actual* value. Recorded, not corrected.
- **Enumeration**: 36 states · 543 constituencies · 1,380 MPs. A full national work-grain crawl
  is ≈720 requests, ~12 minutes at the self-imposed 1 request/second.
- **Collected so far: 71 works, 66 payment rows, 13 attachment sets** — proof scale, not a
  re-ingest. The CSV-snapshot pipeline remains the source of every number in §5.
- **Legal boundary**: public dashboard, no authentication; no login, captcha, rate limit or
  access control was bypassed; 1 req/s self-imposed where none was enforced. The portal declares
  no licence, so we attribute MoSPI, state the retrieval date, and do **not** assert
  redistribution rights it never granted.

## 14. Security and governance

JWT (HS256, 12h) + RBAC with 5 roles, jurisdiction enforced **server-side** and tested on the
failure path · hash-chained audit log (SQLite triggers block UPDATE and DELETE) · immutable
field records · upload caps (12 MB photographs, 20 MB documents), extension allowlist,
content-addressed storage, path-traversal guard · chat tools provably read-only by test.

**Weak by design — say it before a judge finds it:** `JWT_SECRET` defaults to a development
value locally, `REQUIRE_AUTH=0`, CORS `*`, demo passwords listed on the sign-in page.
**Rate limiting is on the architecture diagram and is NOT implemented.**

**Secret hygiene — outstanding.** Over the project's life, two Anthropic API keys, one Hugging
Face write token and an AWS access-key file were pasted into chat or committed to a local
`.env`. **All of them must be rotated or revoked.** Rule from here: secrets go into `.env`
(gitignored) or a platform secret store, never into a message, a commit, or a command line.

## 15. Deployment status

| Where | How | State on 2026-09-12 |
|---|---|---|
| Laptop | `uvicorn mplads.api.app:app --port 8020`, serving the built frontend | **Working** — Surya OCR active on the GPU |
| Same Wi-Fi | Same server on `--host 0.0.0.0` + one inbound firewall rule | **Working** |
| Public, free | Cloudflare quick tunnel to the laptop | **Working** — the link lives only while the laptop runs |
| Hugging Face Space | `Dockerfile` + `scripts/deploy_hf_space.py`; 113 files / 154 MB uploaded to `kannanyuvaraj/Mplads`, Docker SDK, secret set | **Paused** — free accounts get zero CPU-Basic quota; a compute Space requires PRO ($9/month) |
| GitHub `main` | 6 commits ready locally, merged with origin | **Not pushed** — awaiting a working credential |

The deploy uploads only what the image needs, and never `.env`, `Dataset/`, the OCR weights, the
portal crawl, or the local verification and audit databases. On free CPU hardware photographs
fall back to RapidOCR — no GPU. Hosted storage is ephemeral: field records reset on restart.

## 16. Engineering conventions (load-bearing)

Type hints everywhere · `pathlib`, never string paths · **never hardcode a path, seed or date**
(import from `mplads.config`) · every transform logs row counts and `_log_counts()` **raises**
on an unexplained change · deterministic dedup · `Dataset/` is read-only · expensive work is
cached · caches keyed on jurisdiction, so a scoped officer can never be served national data ·
**the working directory is `MPLADS - Copy`; the `MPLADS` folder is stale.**

## 17. What is NOT built — ranked

1. **Rate limiting.** Claimed nowhere, missing everywhere.
2. **The Agentforce agent inside the org** (~15 minutes of clicking) and `Audit_Assignment__c`
   loaded into it.
3. **A national live re-ingest**, and with it vendor/payment analysis — the single largest
   capability increase available (§13).
4. **UVP-4 full 8-dimension entity fingerprint; UVP-5 real change-point detection.** The finding
   worth keeping: a global FDR correction across ~4,000 change-point tests is unachievable on
   6–11 quarters — a permutation test on 6 periods bottoms out at p = 1/720. Correct
   within-entity, or test agreement across dimensions instead.
5. **Money-gap funnel; Screen-2 choropleth.**
6. **Persistent storage on any hosted deployment.**
7. **A real labelled sample of board photographs** to replace the synthetic OCR benchmark.

## 18. Decision log — how the project got here

| Date | Decision or event |
|---|---|
| 08-24 | v1 constitution authored; ladder and non-fraud stance fixed |
| 08-25 | Data contract, ingestion, three trained models |
| 08-26 | React app, 10 languages, data-grounded chatbot, RBAC, hash-chained audit log |
| 08-27 | Field verification, OCR, perceptual hashing; **judge mandates Salesforce + Agentforce**; v2 constitution |
| 08-28 | Salesforce DE org, 500 cases + 1,586 evidence deployed; performance work (pages 10–12 s → under 45 ms) |
| 09-06 | PPT-vs-implementation gap review; **live-data direction set**; first deployment attempts (Vercel, AWS, GCP, HF static) |
| 09-06/09 | Audit plan, field rota, agency dossier, field scoreboard, day-pack PDF, case ageing |
| 09-10 | **Government of India frontend redesign**; live-portal ingestion module and its research |
| 09-11 | **Evaluator feedback** → Step-by-Step screen and live stamps; detection-first redesign; **plain-language rewrite**; Surya + Docling OCR |
| 09-12 | Deployment: Docker image, HF Space upload (paused on quota), Cloudflare tunnel; v3 then **v4 FINAL** constitution |

## 19. CONSTITUTION CARD — the one page to memorise

> **210,993 works · 37,705 leads · 4,478 HIGH · ₹1,302 Cr money at risk · 50 work types
> (silhouette 0.050 — separation, not accuracy) · Cox C-index 0.6759 · 69.25% synthetic
> detection · 300 tests · 47 API routes · 17 screens · 10 languages.**
>
> Two independent signal families must agree before a work is flagged. Two independent OCR
> readers must agree before a board reference is accepted. A person decides every action.
> Field verification is the only ground truth. We never say fraud.
>
> **"Other teams will tell you how late the finished works were. That number is a lie — it
> ignores every work that never finished. We corrected it with survival analysis, turned the
> risk into a rupee figure, tested the obvious fraud signals and rejected them in public, and
> we refuse to output a fraud score because there are no fraud labels in this data.
> It gives investigators evidence and priorities — not accusations. An AI that knows what it
> doesn't know."**
