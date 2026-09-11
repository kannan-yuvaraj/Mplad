# CLAUDE.md — mplads-intel

**Read this first, every session. Do not re-read the whole repo.**

This is the complete working context. If you are a fresh session with no history, everything
you need is here.

---

## ⚠️ READ THIS BEFORE ANYTHING ELSE

**The working directory is `C:\Users\kanna\Downloads\MPLADS - Copy`.**

There is an older folder at `C:\Users\kanna\Downloads\MPLADS` that is **behind** and missing
the audit planner, PDF reports, multilingual Agentforce, the casework strip and the camera
evidence. Do not work in it. Commands run from the wrong folder is the single most common
mistake in this project's history.

**The user runs Windows CMD with the venv already activated** (prompt shows `(.venv)`).
In CMD, `.venv/Scripts/python.exe` fails — forward slashes. Give them **`python`** on its
own, or `.venv\Scripts\python.exe` with backslashes. You, in Bash, use
`./.venv/Scripts/python.exe`.

---

## What this is

An AI-assisted monitoring layer over MPLADS/eSAKSHI work-lifecycle data. It learns what
normal work looks like nationally, compares each work against its true peers, predicts
completion risk, detects duplicates and behavioural change, fuses those signals into an
explainable case file, ranks by audit return-on-investment, **plans a budgeted audit**, and
hands the case to Salesforce for the human casework that follows.

**SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus.**

**Status: feature-complete and demoable.** 245 tests passing, 2 skipped.

---

## The six hard constraints

Product constraints, not style preferences. They must survive into code and UI copy.

1. **No fraud verdicts.** Output is an *investigation lead* with evidence. No field,
   variable, column or label may be named `fraud_probability`, `is_fraud`, `fraud_score` or
   `fraudulent`. Enforced by `test_no_fraud_language_in_the_source_tree`, which greps the
   whole `src/` tree — it has caught real violations twice, including inside our own safety
   filters. **Rephrase, never exempt.**
2. **No fraud classifier.** There are no fraud labels in the data. Any supervised model
   claiming to predict fraud is fabricated. Scoring is transparent, weighted, rule-based.
3. **Silhouette is not accuracy.** Ours is 0.050. Say so, in code comments, docs and UI.
4. **`ACTUAL_AMOUNT` is not expenditure.** 98.35% of completed works have it exactly equal
   to `RECOMMENDED_AMOUNT`; zero exceed 1.05×. No overrun signal exists. DATA_CONTRACT §6.
5. **Human-in-the-loop.** Every recommendation ends in "a human should check X".
6. **Field verification is the only ground truth there will ever be.** No dataset says which
   works were problems. What an officer found on site is the sole exception, which is why
   those records are immutable, attributed, and counted honestly: `field.label_readiness()`
   reports the gap to 500 rather than implying it is closed, and demo-seeded records are
   excluded.

---

## Verified numbers — quote these, never estimate

| Measure | Value |
|---|---|
| Works | **210,993** (210,987 after dropping 6 with amount ≤ 0) |
| Raw stage rows | 480,768 = 3,987 MP-summary + 476,781 work-stage |
| Completed / open | 85,773 / 125,220 |
| Recommended / exposure | ₹11,565 Cr / ₹1,302 Cr |
| Leads | 37,705 (**4,478 HIGH**, 33,227 MEDIUM) |
| States / constituencies / agencies | 36 / 545 / 778 |
| Archetypes | 50 (49 named, 1 honestly "uninterpretable"), K by sweep, silhouette **0.050** |
| Cox C-index (held out) | **0.6759** |
| IsolationForest flagged | 4,220 |
| Duplicate pairs | 223,407 → **47,709 concerning** |
| Compliance-flagged works | 5,946 |
| Agencies changed | 73 of 697 |
| Health Index | 62.9 / 100 |
| Synthetic validation | **69.2%** overall (stalled 96.1%, inflated 83.2%, break 58.0%, cloned 50.0%) |
| **Tests** | **300 passing**, 1 skipped (Surya real test is opt-in: `MPLADS_TEST_SURYA=1`) |
| **API routes** | **47** (+ `/api/ocr/document`, `/api/document/{name}`, `/api/ocr/status`) |
| **Chat tools** | **15** read-only |
| **Languages** | **10** (UI + Agentforce, all 100%) |

### Audit plan @ 50 auditor-days (regenerate if the pipeline reruns)

| Strategy | Works | Agency visits | Exposure |
|---|---|---|---|
| **Optimised plan** | **100** | **23** | **₹47.1 Cr** (100%) |
| Audit-ROI ranking | 74 | 37 | ₹42.4 Cr (90%) |
| Biggest cheques first | 72 | 38 | ₹28.1 Cr (60%) |
| Highest risk first | 94 | 26 | ₹3.7 Cr (8%) |
| Random selection | 55 | 47 | ₹0.5 Cr (1%) |

---

## Stack

Python 3.11 (`.venv/`, uv) · pandas 2.3.3 · numpy 2.4.6 · scipy 1.17.1 · scikit-learn 1.9.0
· lifelines 0.30.3 · pyarrow · FastAPI 0.141 · uvicorn · PyJWT · anthropic 1.1.0 ·
rapidocr-onnxruntime 1.4.4 · onnxruntime · **Pillow 10.4** (pinned down by surya) · **fpdf2 2.8.8** ·
pytest 9.1.1 · **OCR: surya-ocr 0.22.1 · docling 2.126 · torch 2.14 CPU build**
React 18 + Vite 5 + Recharts + react-router-dom. Salesforce CLI (`sf`) installed.
**llama.cpp** (`winget install ggml.llamacpp`, Vulkan build) runs Surya on the Quadro T1000.

**`sentence-transformers` is NOT installed** (torch now is, for Surya/Docling only). MiniLM
embeddings were computed once and cached at `Dataset/models/archetype/desc_embeddings.npz`
(307 MB, 187,865 × 384 float32). `train.py` loads the cache and never runs a neural network.
Consequence: a brand-new description cannot be embedded without installing
sentence-transformers. Say this proactively — it is why the pipeline runs in 90 seconds.

**The venv has no pip.** Install with the system uv:
`/c/Users/kanna/AppData/Local/Python/pythoncore-3.14-64/Scripts/uv.exe pip install --python .venv/Scripts/python.exe <pkg>`.
**Hugging Face's Xet downloader stalls at 0 bytes on this network** — set `HF_HUB_DISABLE_XET=1`.
The connection runs at ~240 KB/s; a 1.5 GB model takes ~25 minutes.

**Docker: NOT installed.** Node: installed.

---

## Layout

```
src/mplads/
  config.py            paths, seeds, SNAPSHOT_DATE=2026-05-26, weights, .env loader
  cli.py               mplads <paths|profile|ingest|pipeline|api|train|validate|tokens|audit>
  ingest/              loader.py (typed load) · normalise.py · schema.py
  train.py             3 trained models -> data/artifacts/models/
  pipeline.py          Learn->Compare->Predict->Explain->Prioritise
  intelligence/        duplicates · temporal · compliance · early_warning · transparency
                       · labels · targeting.py     audit plan optimiser
                       · assignment.py  ← the plan dealt out to auditors   (NEW)
                       · dossier.py     ← the agency briefing              (NEW)
                       · calibration.py ← model vs what officers found     (NEW)
  validation/synthetic.py   plant known anomalies, measure detection
  llm.py               Claude briefings + translation, template fallback
  chat.py              15 read-only tools over ALL 210,993 works + offline router
  ocr.py               Surya reads board photos, RapidOCR checks it, Docling reads documents;
                       refuses to settle an ambiguous reference — see docs/OCR.md
  photohash.py         pHash + dHash — the same *picture*, not the same file
  field.py             immutable, attributed site-verification records + camera evidence
  casereport.py        PDF case report (fpdf2)                          ← NEW
  salesforce.py        Salesforce CRM mirror + Agentforce topic router  ← NEW
  agentforce_i18n.py   Agentforce phrases in 10 languages               ← NEW
  api/                 app.py · auth.py (JWT/RBAC) · audit.py (hash chain) · strings/translations

frontend/src/
  pages/     Landing · Login · Overview · Worklist · AuditPlan · FieldRota(NEW) ·
             AgencyDossier(NEW) · Scoreboard(NEW) · CaseFile · SalesforceHub ·
             Trends · Duplicates · Compliance · Archetypes · Transparency · HowItWorks
  components/ Bits · Chat · CaseworkStrip(NEW) · FieldVerify · Insight · Logo · Reveal
  severity.js  THE single source for band/level colours + glyphs

salesforce_package/   deployable SFDX metadata (4 objects, 65 fields) + SETUP.md
salesforce_extras/    Path + compact layout (deployed separately)
salesforce_export/    investigation_cases.csv · evidence.csv · site_verifications.csv
                      · audit_assignments.csv
demo/                 WALKTHROUGH.md + 5 generated work-board photographs
docs/                 see below
scripts/              profile_data · make_demo_data · export_for_salesforce ·
                      build_salesforce_package · build_salesforce_extras ·
                      import_salesforce_findings · sync_verifications_to_salesforce ·
                      export_audit_plan (NEW — the rota into the CRM)
```

---

## Commands

```bash
# from "MPLADS - Copy". In the user's CMD, use plain `python`.
.venv/Scripts/python.exe -m pytest                      # 245 tests, ~85s
.venv/Scripts/python.exe -m mplads.cli ingest           # raw -> data/interim (~40s)
.venv/Scripts/python.exe -m mplads.cli train            # 3 models (~90s)
.venv/Scripts/python.exe -m mplads.cli pipeline         # artifacts (~50s)
.venv/Scripts/python.exe -m mplads.cli validate         # synthetic harness (~35s)
.venv/Scripts/python.exe scripts/make_demo_data.py      # demo boards + seeded records
.venv/Scripts/python.exe -m uvicorn mplads.api.app:app --host 0.0.0.0 --port 8010

cd frontend && npm run dev                              # PATH="/c/Program Files/nodejs:$PATH"
cd frontend && npm run demo                             # built bundle — use this over wifi
```

Add a dependency: `python -m uv pip install --python .venv/Scripts/python.exe <pkg>`, then
add it to `pyproject.toml`. **Do not add dependencies without asking.**

---

## Conventions

- Type hints everywhere. `pathlib`, never string paths. No notebooks in `src/`.
- **Never hardcode a path, seed or date.** Import from `mplads.config`.
- Every transform logs row count at entry and exit. `_log_counts()` **raises** if a count
  changes without a stated reason — a silent drop is impossible, not merely discouraged.
- Deterministic: dedup sorts on `(recommendation_date, work_ref, source_file, raw_row_index)`.
- `Dataset/` is read-only. Never write into it.
- Expensive work is cached and skipped on rerun.

---

## Data facts you must not get wrong

Full detail in `docs/DATA_CONTRACT.md`. The ones that bite:

- **Join key is `(WORK_RECOMMENDATION_DTL_ID, mp_id)` → `work_ref`.** Never `WORK_ID`
  (82% null, issued only at completion — renamed `portal_work_id` as a guard rail).
- **No sanction date exists.** Sanction rows copy `RECOMMENDATION_DATE` verbatim on 100.00%
  of 179,676 works. Presence is testable; timing is unknowable.
- **Censoring anchor = `max(RECOMMENDATION_DATE)` = 2026-05-26.** `max(all dates)` lands in
  2044 and inflates every open duration by ~18 years.
- **`ACTIVITY_NAME` is a composite**: `WS/MP<code>/<FY>/<serial>-<official category>`.
  Parsing yields **118 official categories at 93% coverage**. Both the deck and the previous
  team called this field unusable; they never split it.
- **The 3,987 "corrupt" rows are MP-level totals.** They carry `Total_Amt`, null on all
  476,781 work rows. Used as a reconciliation oracle — median ratio exactly 1.0000.
- **695 orphans**, **70** completed-without-sanction, **1,194** back-dated, **9**
  out-of-window dates. Carry and flag; several are conformance signals.
- **No district column.** `IDA_NAME` is a district *office*; `CONSTITUENCY` is a
  constituency. All Rajya Sabha works share `CONSTITUENCY = "Sitting Rajya Sabha"`.
- **DO NOT USE:** `ACTUAL_AMOUNT`, `WORK_ID`, `AVERAGE_RATING`, `FILE_STATUS`, `Sno`,
  `MP_NAME`, `Total_Amt` at work grain.

---

## Design system

Light **parchment** ground `#f7f4ed`, ink text, **terracotta `#a8452a`** primary, forest
green secondary, aged brass for figures. **No blue anywhere** — a deliberate move away from
the dark-blue dashboard look, which reads as an AI product. Fraunces (serif display) + Noto
Sans (body, all Indic subsets) + Roboto Mono (figures).

**Severity is not a palette choice.** `frontend/src/severity.js` is the single source for
every band, level and classification colour, with measured contrast ratios in its header —
six pages each kept their own copy until HIGH and LOW ended up the same terracotta in two of
them. Red and amber cannot be separated under deuteranopia, so severity is never carried by
colour alone: every indicator also has a `glyph` (■ ▲ ◆ ● ·) and its text label.

---

## The audit plan (`intelligence/targeting.py`)

**The strongest new thing. It did not exist before and BUILD_STATUS marked it ❌.**

Ranking answers *"what is worst?"*. An official asks *"I have twenty auditor-days, where do
I send them?"* — different, because cases do not cost the same to check:

- first work at an implementing agency: **`FIRST_VISIT_DAYS = 1.0`** (travel, visit, write-up)
- every further work there: **`SAME_AGENCY_DAYS = 0.35`** — the auditor is already standing there

That one dependency is why this is a plan and not a sort.

**Algorithm.** Greedy with **bundle lookahead**. A purely myopic greedy compares one work
against one work and never notices that opening a cluster buys six mediocre works for barely
more than the trip. `_best_bundle()` judges an agency by the best exposure-per-day of taking
its top *k* works together (capped at `BUNDLE_LOOKAHEAD = 40`). Once open, an agency's
remaining works compete individually at the cheaper repeat cost via a heap.

**It is a heuristic and the tests say so.** With set-up costs this is a knapsack variant,
NP-hard. `test_the_planner_is_greedy_and_does_not_pretend_otherwise` pins a case where it
trails the clustered optimum. The comparison table is built to be able to report that we
lost — a table hard-wired to crown our own strategy would be decoration, not evidence.

**Performance:** was 35s (O(n²) rescan), now ~1.3s (heaps + vectorised baselines).

API: `GET /api/audit-plan?budget_days=50`. Screen: `/audit-plan`. Scoped officers get their
own jurisdiction only.

---

## Ports and network access

**API `8010`, web `3000`.** Both moved off 8000/5173 because those are the two most
contended ports on a developer machine, and a stale process holding one is how "the site
is slow" turns out to mean "you are looking at a dead tab" — which has cost real time on
this project more than once.

`frontend/vite.config.js` is the single source: `WEB_PORT` and `API_PORT`, overridable
with the `PORT` / `API_PORT` environment variables. `strictPort: true` makes a taken port
an **error** rather than a silent slide to the next one, and `.claude/launch.json` has
`autoPort: false` to match. A second server on a second port is how half a team ends up
looking at a stale build and calling it a bug.

`host: true` binds every interface, so a phone on the same wifi opens
`http://<lan-ip>:3000`. **Only the web server is exposed** — the browser calls `/api/...`
relatively and Vite proxies it to the API over loopback, so no visitor needs the API's
address and nothing is reconfigured per device. The proxy also returns a readable 502 when
uvicorn is down, instead of hanging forever and looking like slowness.

For a demo over wifi use `npm run demo` (build + preview). A dev server streams hundreds of
separate modules to the browser, which is free on loopback and slow on a phone.

---

## Performance — why the service is fast, and what not to undo

The site was taking 10-12 seconds a page. Four causes, all fixed; **do not remove these
without measuring first.**

1. **The audit plan was rebuilt on every request.** It is deterministic — same works, same
   budget, same plan — and it was running the optimiser **seven times** per call (once for
   the plan, once inside `compare_strategies`, five more for the coverage curve). Now
   `_plan_cached` / `_rota_cached` / `_curve_cached` in `app.py`, keyed on
   `(_scope_key(principal), budget)`. **The jurisdiction must stay in the key** — dropping
   it would serve a Bihar officer a national plan, which is a data leak dressed as a
   speed-up.
2. **`targeting.build` recomputed what it was handed.** It now takes `plan=` and `curve=`.
   The curve does not depend on the budget at all, so it is cached once per jurisdiction
   rather than redrawn for every position of a slider.
3. **The dead API key cost ~2s per page.** `llm._ask` called the live model on every
   insight, failed with `BadRequestError` (key authenticates, billing is empty), retried
   with backoff, then rendered the template it could have rendered instantly.
   `llm._HALTED` is now a circuit breaker: the first permanent failure is logged **once**
   and every later call returns immediately. `llm.available()` reports `False` once
   halted — a screen claiming "live" while serving templates is lying about whether the
   Tamil text was generated. `llm.resume()` re-arms it after fixing billing.
4. **The sliders fired a request per pixel of drag.** `useDebounced` in `hooks.js`; the
   figure under the thumb still tracks instantly, only the fetch waits.

Also fixed: **`AuditPlan.jsx`'s `Figure` counter showed ₹0 forever in a background tab.**
`requestAnimationFrame` does not tick in a hidden document, and it counted up from zero.
`useCountUp` already had this fix; the page's private copy did not. Any new counter must
land on the value when `document.hidden`.

Startup warms the chat index, the default plan and rota, the LLM probe, and the concerning-
duplicate filter, so **no user request ever pays a cold cost**. Measured after: every
endpoint under 45 ms from the first request, worst case, through the Vite proxy.

---

## The four auditor tools built on top of the plan

The plan says where the days should go. These four answer what a supervising officer and a
field auditor actually do next.

### 1. The field rota (`intelligence/assignment.py`) — `/rota`

The plan with names against it. **One hard rule: an implementing agency is never split
between two auditors.** The plan's entire saving is that the second work at an agency costs
0.35 of a day *because someone is already standing there* — send two people and that
arrival is paid for twice while being earned once, and every figure downstream stops
describing the plan anyone is executing. So the unit of assignment is the **trip**, not the
work, priced exactly as the plan priced it.

Trips are dealt **longest-first to whoever is least loaded** (LPT). Also NP-hard, so also a
heuristic — but LPT carries Graham's proved bound of (4/3 − 1/3m) of the best possible
longest round, and the bound *and* the achieved spread are both printed. At 50 days across
4 auditors: **23 trips, 100 works, 49.95 days used, spread 0.4 days.**

More auditors than trips leaves people idle, and that is reported. The tempting fix —
splitting an agency so every name has a line against it — produces a rota that looks
complete and costs more than the plan allowed. `test_idle_auditors_are_reported_rather_than_given_half_an_agency` pins it.

**`GET /api/audit-plan/assignments?budget_days=&auditors=`**

### 2. The field day pack (`casereport.build_day_pack`)

`GET /api/audit-plan/assignments/{auditor}/pack.pdf` → one auditor's round as a document
they carry: where to be on which day, a **tick box against every work**, what to record
(including "nothing wrong"), and the cost model printed on the page so an officer who finds
it wrong in the field can say so. Same page furniture as the case file on purpose — nobody
should have to learn a second document — and the non-fraud contract on every page.

### 3. The agency dossier (`intelligence/dossier.py`) — `/agency`

An auditor travels to a **body**, not a work. This is the page for the journey.

**The comparison must be a rate, and this is the safety-critical part of the whole
feature.** A district office with four thousand works surfaces more leads than one with
forty; reading the raw count as a signal is the single most likely way this product gets
somebody unfairly investigated. So every figure is printed beside the national rate, and
where an agency is ordinary the page **says so in words** rather than letting a bar imply
otherwise. Under `MIN_WORKS_FOR_A_RATE = 20` no rate is computed at all.

Field findings outrank the model and sit above it on the page. Seeded demo records are
shown (an officer should see the whole file) but **marked**.

**`GET /api/agencies`** · **`GET /api/agency/{name}`**

### 4. The field scoreboard (`intelligence/calibration.py`) — `/scoreboard`

**The screen this system is allowed to lose on.** Did the works we called HIGH turn out
worse than the ones we called MEDIUM, on the works someone actually visited?

Three disciplines, each of which costs us a number we would rather print:

1. **No rate below `MIN_VISITS_FOR_A_RATE = 10`.** Three visits and two confirmations is
   three visits, not 67%. The bar is left *empty*, never drawn short — a short bar reads as
   a low rate.
2. **Every rate carries a Wilson interval**, not the normal approximation, which at these
   counts returns bounds outside [0, 1]. Where two bands' intervals overlap, the ordering
   between them is **not claimed**.
3. **The sample is not random and never will be.** Officers go where this model sends them,
   so the never-surfaced negative class is barely represented. Stated *with* the result.

One work, one verdict: the newest record supersedes earlier ones, so a revisited work votes
once. Nothing is refitted — `field.label_readiness()` still counts the gap to 500.

**`GET /api/calibration`**

### And the queue nobody screens: case ageing (`salesforce.case_ageing`)

A lead that was surfaced, assigned and then left for four months has not been monitored, it
has been *filed*, and the exposure is still out there. **Two silences counted apart**:
*late* means somebody committed to a date and the date passed; *never picked up* means the
case is still on the stage it was loaded on — a different failure, usually a supervisor's.
Merging them hides whichever is smaller.

The review clock is now set by the **escalation tier** and stretched by the band
(`TIER_REVIEW_DAYS` × `BAND_REVIEW_MULTIPLE` in `export_for_salesforce.py`). It was
band-only, and since every loaded case is HIGH that gave all 500 the same date — an ageing
report that could not tell a slipping ministry case from a routine district one.

**`GET /api/salesforce/ageing`** · strip at the top of `/salesforce`.

---

## The PDF case report (`casereport.py`)

`GET /api/case/{work_ref}/report.pdf` → real PDF, opens in a browser tab.

Sections: title + band → three headline figures → the work → why it was surfaced (evidence
with families) → peer context → lifecycle checks → early warning → recommended next step +
checkboxes → field verification history → how to read this document.

**The footer is not decoration.** A PDF outlives the screen it came from — it gets emailed,
printed and read months later by someone who never saw the caveat. The non-fraud contract is
stamped on **every page**.

**fpdf2 gotchas that cost an hour, do not rediscover them:**
- Core fonts are **Latin-1 only**. `_fold()` maps ₹ → "Rs ", em-dashes, ellipsis, glyphs,
  then `.encode("latin-1", "replace")`. Without it the export dies halfway down page two.
- **`multi_cell` defaults to `new_x=RIGHT`**, parking the cursor at the right margin so the
  next cell gets zero width → *"Not enough horizontal space to render a single character"*.
  **Every `multi_cell` needs an explicit `new_x="LMARGIN", new_y="NEXT"`.**
- A **zero-width `cell(0, ...)`** means "run to the right margin". Two in a row = the second
  has no room. The header uses explicit widths (100 + 74).

---

## Salesforce & Agentforce

### The framing that wins

> Our engine reads 210,993 works and decides **where an officer should look**. Salesforce
> decides **what happens after they decide to look** — assignment, approval, mobile, audit
> trail. Agentforce connects an officer to both, in their own language. The models stay in
> Python because there is no Cox regression in Apex, and Salesforce holds the 500 cases that
> need a human rather than the two lakh works that do not. **That split is the design.**

### The live org

- Alias **`mplads`** · `ropheangel1312.287b095150cb@agentforce.com` · Org `00Daj0000143kQ5EAI`
- It is an **Agentforce Developer Edition** (`orgfarm-a17c494943-dev-ed.develop.my.salesforce.com`)

| Object | Records | Purpose |
|---|---|---|
| `Investigation_Case__c` | **500** | top Audit-ROI leads, ₹97.5 Cr exposure |
| `Evidence__c` | **1,586** | all linked to their case |
| `Site_Verification__c` | **4** | what the officer AND the camera found |
| `Audit_Assignment__c` | **built, not yet loaded** | the rota: who visits what, on which day |

Plus: 5-stage **Path**, compact layout, 3 case list views, 2 verification list views
(including **"Camera Raised A Question"**), tabs, Lightning app, permission set.

### Deploy / reload commands

```bash
cd salesforce_package
sf project deploy start --source-dir force-app --target-org mplads
sf org assign permset --name MPLADS_Investigator --target-org mplads

cd ..
.venv/Scripts/python.exe scripts/export_for_salesforce.py
sf data import bulk --sobject Investigation_Case__c --file salesforce_export/investigation_cases.csv --target-org mplads --wait 10
sf data import bulk --sobject Evidence__c --file salesforce_export/evidence.csv --target-org mplads --wait 10

.venv/Scripts/python.exe scripts/sync_verifications_to_salesforce.py
sf data import bulk --sobject Site_Verification__c --file salesforce_export/site_verifications.csv --target-org mplads --wait 10

# the rota into the CRM, so an auditor opens their round on their phone
.venv/Scripts/python.exe scripts/export_audit_plan.py --budget-days 50 --auditors 4
sf data import bulk --sobject Audit_Assignment__c --file salesforce_export/audit_assignments.csv --target-org mplads --wait 10
```

`Assignment_Key__c` is `{budget}d-{team}a-{work_ref}` and is the External ID, so re-running
the *same* budget and team updates in place. A different budget is a different fortnight,
so it deliberately writes different rows rather than editing last quarter's.

### Salesforce lessons that cost real time — do not rediscover

1. **Base Edition orgs allow ZERO custom objects.** The first signup produced one
   (`OrganizationType: Base Edition`) and nothing would deploy. A **Developer Edition** from
   `developer.salesforce.com/signup` is required. Verify with:
   `sf data query --query "SELECT OrganizationType FROM Organization" --target-org mplads`
2. **A DE org holds ~2,500 records** (2 KB each regardless of size). 210,993 works ≈ 420 MB.
   This is *why* only the top 500 leads are loaded — and it is the correct architecture
   anyway.
3. **Field tuples are `(api_name, label, kind, spec)`.** Writing them `(label, api, ...)`
   makes Salesforce read the label as the field name → *"Cannot specify label on standard
   field"*.
4. **`precision` in metadata is TOTAL digits including decimals.** Currency(16,2) is
   `precision 18, scale 2`.
5. **PermissionSet requires all `fieldPermissions` grouped, then all `objectPermissions`.**
   Interleaving → *"Element objectPermissions is duplicated at this location"*.
6. **Required fields cannot appear in `fieldPermissions`** — always visible by definition.
7. **List-view checkbox filters take `1`/`0`, not `true`/`false`.**
8. **Formula fields must be `Readonly` on the layout** (`READONLY_FIELDS` in the generator).
9. **Salesforce will not convert a stored field to a formula in place** — delete it first:
   `sf project delete source --metadata "CustomField:Obj__c.Field__c" --target-org mplads --no-prompt`
10. **Bulk API rejects a UTF-8 BOM** with a misleading *"Found unescaped quote"* hundreds of
    rows away. Export plain UTF-8.
11. **Bulk API rejects LF line endings on Windows** — the CLI declares CRLF. Write CRLF.
12. **Reports do not deploy as metadata** for custom objects (the auto report type will not
    resolve by API name). Build them in the UI — 2 minutes.
13. **Public Sector Solutions** (Inspections, Data 360) is a **licensed managed package**,
    not available in a DE org. Plain custom objects tell the same story and actually run.

### Agentforce

**⚠️ THE AGENT INSIDE THE ORG IS NOT BUILT.** What runs in the app is our own
Agentforce-branded topic router (`salesforce.py::query_agentforce`) over the same data.
Building the real one is ~15 minutes of clicking — `salesforce_package/SETUP.md` §7 — and
the org is Agentforce-enabled. **Do not claim the org agent exists.**

Ten topics, all answering from real data:

| Topic | Example |
|---|---|
| Investigation Lookup | *"Tell me about MP3018356-W86316"* |
| State Brief | *"Show me HIGH priority cases in Bihar"* |
| Escalation Tier | *"What does escalation tier mean?"* |
| Top Exposure | *"Which case has the highest exposure?"* |
| **Audit Planning** | *"What should I investigate first?"* / *"plan 100 auditor-days"* |
| **Casework Status** | *"How many cases are open?"* |
| **Overdue Casework** | *"What has gone quiet?"* |
| **Field Rota** | *"Split 50 days across 4 auditors"* |
| **Field Scoreboard** | *"Has the model been right so far?"* |
| **Agency Dossier** | *"Brief me on SARAN before I visit"* |

Audit Planning parses a budget out of the question and calls the **same** optimiser the
screen uses. One source of truth.

### Multilingual Agentforce (`agentforce_i18n.py`)

**10 languages at 100%** of the phrase set (**47 keys**): en hi bn ta te mr gu kn ml pa.

**A trap the four new topics fell into first.** They were written closing on an English
contract line built in Python (`ageing['contract']`, `rota['contract']`), which produced a
Tamil answer ending in an English disclaimer — the exact failure this design exists to
prevent. Every topic now closes on the committed `t['contract']` or `t['plan_contract']`,
and any English *sentence* poured in as data is marked with `_note(t)`.

The architecture is the honest part. Answers are **templates**, so the *structure* is
translated from committed strings while the data poured in is not:

- **Translated:** headings, field labels, and above all **the non-fraud contract**
- **Never translated:** work references, agency names, MP names, rupee figures

A work reference is an identifier, not a word. An agency's name is how it appears on its own
letterhead. Translating either produces something an officer cannot search for or quote back.

**Nothing is machine-translated at runtime.** That would need the live model, and with no
API credits the fallback would silently be English — which is the failure this design exists
to avoid. A Tamil reader shown a list of flagged works and an English disclaimer has, in
practice, been shown a list of flagged works.

`POST /api/agentforce/query` takes `{question, lang}`. The hub follows the site language via
`useI18n()` — one language for the whole product, never a second picker.

---

## OCR — Surya, RapidOCR, Docling (`ocr.py`, `docs/OCR.md`)

- **Photographs → Surya OCR 2** (vision-language model, GGUF, run by `llama-server` on the
  GPU via Vulkan; `MPLADS_LLAMA_DEVICE=Vulkan1` in `.env`). **RapidOCR reads the same photo
  as a second reader**; `cross_check.agrees` false → `match_to_work` forces confirmation and
  offers the other reading. Surya missing / not started / failing → RapidOCR alone, and the
  result says so (`engine`, `fell_back_from`).
- **Documents → Docling** (`POST /api/ocr/document`): Markdown with tables, **every** work
  ref (each checked against all 210,993), amounts, `mentions_this_work`. Uses the PP-OCRv6
  models bundled in the `rapidocr` wheel for scanned pages.
- **The model is 1.5 GB in `data/models/ocr/` (gitignored).** `scripts/fetch_ocr_models.py`
  downloads resumably and writes `manifest.json` only when size + SHA-256 match Hugging Face.
  **Surya counts as available only if the manifest matches** — a half-downloaded GGUF has a
  valid header and would crash llama-server 40 s into startup.
- The API warms Surya in a background thread at startup and stops it on shutdown.
- **Amounts on boards are printed with "₹", which RapidOCR drops or reads as "?"** — it lost
  the amount on half the benchmark. `LABELLED_AMOUNT` finds it by the "Sanctioned Amount"
  label instead. Surya reads the ₹ sign.
- `scripts/benchmark_ocr.py` → `docs/OCR_BENCHMARK.md`: boards drawn from real works, 11
  photograph conditions, exact-reference accuracy per reader. **Synthetic, and says so.**
  **Measured (44 boards, T1000):** Surya 93% exact ref / 93% amount / ~20 s a board;
  RapidOCR 91% / 73% / 2 s. Motion blur: Surya 50%, RapidOCR 0%. Surya once read a wrong
  *plausible* ref on heavy JPEG; RapidOCR was right and the disagreement held the match —
  the two never agreed on the same wrong number.
- Windows: Surya logs `Failed to stop llamacpp … WinError 87` at shutdown. Harmless — the
  process is killed; Surya's liveness check misreads Windows' "no such process".
- Tests: `test_ocr_engines.py` (stand-ins, fast) · `test_ocr_real.py` (Docling when cached;
  Surya only with `MPLADS_TEST_SURYA=1`).
- Verification records gained `ocr_engine`, `readers_agree`, `document` (MIGRATIONS).

## The field-verification loop (and the camera evidence)

The one place in this product that creates data.

`POST /api/ocr` reads a photographed work board, matches it against **all 210,993 works**
(not just leads), and fingerprints it against every photograph submitted before.
`POST /api/verify/{work_ref}` appends what the officer found.

**Three rules hold it together:**

- **A match is never settled by the machine.** OCR confidence is confidence in the *pixels*.
  A weathered board reads one digit wrong at 99.6% and lands on a **different real work** —
  MPLADS references run in sequence. `ocr.match_to_work` returns every real reference one
  character away, cross-checks the amount painted on the board, and sets
  `needs_confirmation`; the UI will not save until a human ticks the box.
- **A re-used photograph is a question, not a finding.** `photohash` catches a resized,
  re-compressed, brightened copy that a checksum misses — but two phases of one road
  legitimately look identical from the roadside. Report, never conclude.
- **Writing requires a name.** Reading is open (`REQUIRE_AUTH=0`); `auth.require_identity`
  refuses an unattributed verification. A presented token is honoured **even when auth is
  optional** — the flag says whether a badge is *required*, not whether we read the one given.
  (Getting this backwards attributed every verification to "anonymous".)

**Camera evidence columns** on `verification` (added by `MIGRATIONS`): `board_ref`,
`board_amount`, `ocr_confidence`, `needed_confirmation`, `photo_reuse_count`, `reused_from`.
Kept **apart from the outcome** on purpose — the outcome is the officer's judgement, the
board reference is what the camera saw, and the two disagreeing is the most useful thing a
photograph can report.

`field.photo_forensics_summary()` counts *questions raised by photographs*, not findings.

Works never surfaced return a **"clear record"** case file rather than 404. Not cosmetic: if
only flagged works can be visited, every label ever collected is a positive and the weights
can never be corrected.

**"False Positive" maps to `VERIFIED_COMPLETE`**, not its own outcome. An officer saying "we
looked, nothing wrong" is a **negative label**, and negatives are half of what makes a label
set usable. Giving them their own name is how they quietly stop being counted.

---

## Security

- **JWT** (HS256, 12h) + **RBAC** with 5 roles; `auth.require_scope` enforces jurisdiction
  **server-side**, tested on the failure path.
- **Hash-chained audit log** — SHA-256 over `(ts, actor, role, action, resource, detail,
  prev_hash)`; SQLite triggers block UPDATE/DELETE. `verify_chain()` detects tampering.
- **Immutable field records** — same trigger pattern. A correction is a new record.
- Upload: 12 MB cap, extension allowlist, content-addressed storage, path-traversal guard
  (`Path(name).name`).
- Chat tools **provably read-only** — a test greps their source for `write_text`,
  `to_parquet`, `open(`, `os.remove`, `setattr`.

**Weak by design, say so before a judge finds it:** `JWT_SECRET` defaults to
`"dev-only-not-a-production-secret"`; `REQUIRE_AUTH=0`; `CORS allow_origins=["*"]`; demo
passwords plaintext in `app.py` and listed at `/api/auth/accounts`. **Rate limiting is on the
architecture diagram and is NOT implemented — do not claim it.**

Demo accounts: `ministry` / `auditor` / `bihar` / `saran`, all password `mplads2026`.

---

## Docs

| File | What it is |
|---|---|
| `docs/MODELS_IN_PLAIN_ENGLISH.md` | read-aloud script explaining the 3 models, no jargon |
| `docs/DEMO_WALKTHROUGH_SCRIPT.md` | 14-step localhost walkthrough, ⭐ = the 4-minute cut |
| `docs/SALESFORCE_AND_AGENTFORCE_REPORT.md` | what SF/AF add, which of the 9 features shipped |
| `docs/JUDGE_SCRIPT.md` | earlier judge script (some sections superseded) |
| `docs/DATA_CONTRACT.md` | 14 sections, all 106 columns, DO-NOT-USE list |
| `docs/BUILD_STATUS.md` | audit vs the PROJECT CONSTITUTION (in the older folder only) |

---

## Which of the 9 proposed functionalities shipped

| # | Functionality | Status |
|---|---|---|
| 1 | AI audit prioritisation | ✅ already the core |
| 2 | Explainable case files | ✅ + **PDF export built** |
| 3 | Investigation workflow | ✅ **built** |
| 4 | **Audit-ROI optimisation** | ✅ **built — was missing entirely** |
| 5 | Salesforce case management | ✅ **built and deployed** |
| 6 | **Evidence + resolution loop** | ✅ **built** |
| 7 | Behaviour / change-point | 🟡 pre-existing, not extended |
| 8 | Semantic duplication | ✅ pre-existing |
| 9 | Agentforce copilot | ✅ **extended + multilingual** |

Built on top of that list this session, none of which was in the original nine:

| Capability | Where |
|---|---|
| **Field rota** — the plan dealt out to named auditors | `/rota` · `assignment.py` |
| **Field day pack** — one auditor's round as a carryable PDF | `pack.pdf` · `casereport.py` |
| **Agency dossier** — the briefing for the journey, rate not count | `/agency` · `dossier.py` |
| **Field scoreboard** — has the model been right | `/scoreboard` · `calibration.py` |
| **Case ageing** — the queue that fails invisibly | `/salesforce` · `case_ageing()` |
| **`Audit_Assignment__c`** — the rota as CRM records | `salesforce_package/` |

Nothing from the ❌ list was touched — no HDBSCAN, no GNN, no LLM anomaly detection, no
blockchain, no deep tabular models.

---

## Open items / known gaps

0. **`Audit_Assignment__c` is built but not deployed.** The metadata and the CSV both
   exist and are reproducible; the `sf project deploy` and `sf data import` above have not
   been run against the live org. **Do not claim the object exists in the org until they
   have.**
1. **The Agentforce agent inside the org is not built.** ~15 min of clicking, SETUP.md §7.
2. **Ministry POV is thinner than the auditor POV.** Reports/dashboard metadata exists in
   `salesforce_package/` but did not deploy (see lesson 12) — build in the UI.
3. **API key has no credits.** The key in `.env` authenticates but billing is empty, so every
   LLM path uses its fallback. **The key was pasted in plaintext in chat — it should be
   rotated.**
4. **Docker not installed** — packaging is the only FRD phase not attempted.
5. **`FLAG = 2`** (957 works) meaning still UNVERIFIED. DATA_CONTRACT §13 Q1.
6. **The audit cost model is an assumption** (1.0 / 0.35 auditor-days). Stated on screen and
   in the API response so a reviewer can disagree. Real MoSPI figures would replace it with
   no code change.
7. **UVP-4 behavioural fingerprint is 30% built** (volume only). An earlier attempt at the
   full 8-dimension version plus CUSUM/Jensen-Shannon change-point was written and lost
   before commit. **The finding worth keeping:** a global FDR correction across ~4,000
   change-point tests is *unachievable* on 6–11 quarters of history — a permutation test on
   6 periods has 720 orderings, so its smallest possible p-value is 1/720, whatever the
   effect size. Correct within-entity, or test agreement across dimensions instead.
8. **The older `MPLADS` folder is stale.** Consider deleting or renaming it.

---

## Session history (what happened, in order)

1. Phase 0/1: data contract, ingestion, 3 trained models, 7 intelligence engines
2. React app, 10 languages, data-grounded chatbot, RBAC + hash-chained audit log
3. Field verification: OCR, perceptual hashing, immutable attributed records
4. Salesforce: metadata package, DE org, 500 cases + 1,586 evidence deployed
5. Audit planner, PDF reports, multilingual Agentforce, casework strip, camera evidence
   → Salesforce
6. **This session:** the four auditor tools built on top of the plan — field rota + day
   pack, agency dossier, field scoreboard, case ageing — four new Agentforce topics in all
   ten languages, and `Audit_Assignment__c` in the SFDX package

Recent commits (branch `main`, remote `SomeNobody21112/Thadam`):

```
7d651ba Carry the camera evidence into Salesforce
776de5e Report what Salesforce and Agentforce actually add
3e1240a Make the assistant multilingual and link casework back to the case file
a7b8f9b Plan the audit under a budget, and give every case a document
abcd2e8 Explain the models in plain English, and restore the bundles two screens need
```

**Concurrent-session hazard:** other Claude/Antigravity sessions have edited this repo
mid-work and reverted files (`chat.py`, `strings.py`, `translations.py` were all lost once
to a merge). **Check `git status` and `git log` before assuming your last change survived.**

---

## The closing line for any demo

> "Other teams will tell you how late the finished works were. That number is a lie — it
> ignores every work that never finished. We corrected it with survival analysis, turned the
> risk into a rupee figure, tested the obvious fraud signals and **rejected** them in public,
> and we refuse to output a fraud score because there are no fraud labels in this data.
>
> It gives investigators evidence and priorities — not accusations. An AI that knows what it
> doesn't know."
