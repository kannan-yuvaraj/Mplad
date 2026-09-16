# THADAM — the complete technology stack

**SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus**
Working folder: `C:\Users\kanna\Downloads\MPLADS - Copy` · Repository:
[`kannan-yuvaraj/Mplad`](https://github.com/kannan-yuvaraj/Mplad) · Compiled **16 September 2026**

Every version in this document was **read out of the installed environment**, not from a
requirements file and not from memory. Where a thing is planned rather than built it says
so in the same sentence, because a stack list that quietly includes what you *meant* to
build is the fastest way to be caught out in a demo.

**Legend** — ✅ built and running · 🟡 partly built, stated honestly · ⬜ not built,
deliberately or not yet · ❌ considered and rejected, with the reason

---

## 1. The one-paragraph answer

Python 3.11 does the thinking, React 18 does the showing, and the two meet over one FastAPI
process that serves both. Three models are trained offline with scikit-learn and lifelines;
nothing trains at request time. All state is files — Parquet for tables, SQLite for records
that must not be edited, JSON for the case files. Photographs are read by a vision-language
model through llama.cpp; documents by Docling. The whole product ships as one Docker image.

---

## 2. Language and runtime

| Thing | Version | Where it matters |
|---|---|---|
| **Python** | **3.11.16** | pinned `>=3.11,<3.12` in `pyproject.toml` |
| **Node.js** | **24.19.0** | frontend build only — never at runtime |
| **npm** | **11.17.0** | `frontend/` |
| **uv** | system-wide | the venv **has no pip**; install with `uv pip install --python .venv/Scripts/python.exe` |
| OS developed on | Windows 11 Pro 26200 | the deployed container is Linux |

---

## 3. Python packages — exactly what is installed

### 3.1 Core data and numerics ✅

| Package | Installed | Role |
|---|---|---|
| **pandas** | 2.3.3 | every table in the system |
| **numpy** | 2.4.6 | under pandas; the scoring arithmetic |
| **scipy** | 1.17.1 | statistics; `ndimage` for the OCR benchmark's motion blur |
| **pyarrow** | 25.0.1 | Parquet read/write, **and the streaming reads that let the service fit in 512 MB** |

### 3.2 Machine learning and statistics ✅ *(build-time only — never imported by the API)*

| Package | Installed | Role |
|---|---|---|
| **scikit-learn** | 1.9.0 | MiniBatchKMeans, IsolationForest, TfidfVectorizer, NearestNeighbors |
| **lifelines** | 0.30.3 | Cox proportional hazards, right-censored |
| **joblib** | 1.5.3 | model persistence (`.joblib`) |
| **autograd**, **formulaic**, **threadpoolctl** | 1.9.1 / 1.2.2 / 3.6.0 | pulled in by lifelines and sklearn |

> The serving image installs **none of these**. `requirements-serve.txt` was verified line by
> line: no module in the API import chain references sklearn, lifelines, joblib or torch.
> That check takes the deployed image from well over a gigabyte to roughly 200 MB.

### 3.3 Web service ✅

| Package | Installed | Role |
|---|---|---|
| **FastAPI** | 0.141.1 | 56 routes |
| **Starlette** | 1.6.0 | underneath FastAPI. Server-Sent Events for the intake stream use its plain `StreamingResponse` — **no `sse-starlette` dependency** |
| **Uvicorn** | 0.52.4 | ASGI server, `[standard]` extras, **one worker always** |
| **Pydantic** | 2.13.4 | request bodies |
| **python-multipart** | 0.0.32 | photograph and document uploads |
| **PyJWT** | 2.13.0 | HS256 tokens, 12-hour expiry |

### 3.4 Reading photographs and documents ✅ / 🟡

| Package | Installed | Role |
|---|---|---|
| **surya-ocr** | 0.22.1 | primary reader for site boards — a vision-language model |
| **rapidocr-onnxruntime** | 1.4.4 | second reader and fallback (PP-OCRv4) |
| **onnxruntime** | 1.29.0 | runs the RapidOCR models on CPU |
| **docling** / **docling-core** | 2.126.0 / 2.96.0 | sanction orders, work orders, certificates → structured Markdown |
| **torch** / **torchvision** | **2.14.0+cpu** / 0.29.0+cpu | required by Docling. **CPU build deliberately** — the CUDA wheel is ~2.5 GB |
| **transformers**, **tokenizers**, **safetensors** | 5.17.0 / 0.23.2 / 0.8.0 | Docling's layout models |
| **pypdfium2** | 5.13.0 | PDF page rasterising |
| **opencv-python-headless** | 4.11.0.86 | image handling inside RapidOCR/Docling |
| **Pillow** | **10.4.0** | photo hashing and benchmark rendering. **Pinned down by surya** |
| **huggingface-hub** | 1.31.0 | model download (`scripts/fetch_ocr_models.py`) |

### 3.5 Output, language and utilities ✅

| Package | Installed | Role |
|---|---|---|
| **fpdf2** | 2.8.8 | the PDF case report and the field day pack |
| **anthropic** | 1.1.0 | written briefings — **key authenticates, billing empty, so every path uses its template** 🟡 |
| **httpx** | 0.28.1 | the live-portal crawler in `ingestion/` |
| **requests**, **beautifulsoup4**, **lxml** | 2.34.2 / 4.15.0 / 6.1.3 | portal scraping helpers |
| **psutil** | 7.2.2 | the memory profiling that produced §11 |
| **matplotlib** | 3.11.1 | offline figures for the deck — not used by the site |

### 3.6 Development and test ✅

| Package | Installed | Role |
|---|---|---|
| **pytest** | 9.1.1 | **300 passing, 1 skipped** across 17 files |
| **httpx** | 0.28.1 | FastAPI `TestClient` |
| **setuptools** | 84.0.0 | editable install (`pip install -e .`) |

### 3.7 Declared but **NOT installed** ⬜

| Package | Why it is absent |
|---|---|
| **sentence-transformers** | MiniLM embeddings were computed **once** and cached at `Dataset/models/archetype/desc_embeddings.npz` (307 MB, 187,865 × 384 float32). `train.py` loads the cache and never runs a neural network. **Consequence: a brand-new description cannot be embedded without installing it.** Say this proactively — it is why the pipeline runs in 90 seconds with no GPU. |

---

## 4. Frontend

| Thing | Locked version | Role |
|---|---|---|
| **React** | 18.3.1 | 19 pages, 11 components |
| **react-dom** | 18.3.1 | |
| **react-router-dom** | 6.30.6 | client-side routing; the API serves `index.html` for unknown paths |
| **Recharts** | 2.15.4 | every chart |
| **Vite** | 5.4.21 | dev server and production build |
| **@vitejs/plugin-react** | 4.7.0 | |
| **esbuild** / **rollup** | 0.21.5 / 4.63.0 | inside Vite |
| **d3-scale**, **d3-shape** | 4.0.2 / 3.2.0 | inside Recharts — not used directly |

153 packages in `frontend/package-lock.json`. **No CSS framework, no component library, no
state manager, no TypeScript** — plain CSS with custom properties, and React's own state.

**Pages** — Landing, Login, Overview, Worklist, AuditPlan, FieldRota, AgencyDossier,
Scoreboard, CaseFile, SalesforceHub, Trends, Duplicates, Compliance, Archetypes,
Transparency, HowItWorks, StateMap, Submit, Workflow.
**Components** — Bits, Chat, CaseworkStrip, Detection, DocumentReader, FieldVerify,
GovChrome, Insight, Logo, Reveal, icons.

### 4.1 Typography and colour

* **Fraunces** (serif display), **Noto Sans** + nine Indic subsets, **Roboto Mono** (figures)
  — loaded from Google Fonts.
* Light **parchment** `#f7f4ed`, ink text, **terracotta `#a8452a`**, forest green, aged brass.
  **No blue anywhere**, deliberately: the dark-blue dashboard look reads as an AI product.
* `frontend/src/severity.js` is the **single source** for every band and level colour, with
  measured contrast ratios in its header. Six pages each kept a private copy until HIGH and
  LOW came out the same terracotta in two of them.
* **Severity is never carried by colour alone** — red and amber are indistinguishable under
  deuteranopia, so every indicator also carries a glyph (■ ▲ ◆ ● ·) and its text label.

### 4.2 The map ✅

`StateMap.jsx` draws **hand-written inline SVG paths**. No Leaflet, no Mapbox, no
topojson, no tile server — nothing to load, nothing to pay for, nothing to break offline.

---

## 5. Data formats and storage

| Format | Where | Why that one |
|---|---|---|
| **Apache Parquet** | `works_scored`, `duplicate_pairs`, model outputs | columnar, so 22 of 82 columns can be read without touching the rest. **Written with `row_group_size` on purpose** — a single row group is read all-or-nothing and costs 250 MB to touch |
| **SQLite** | `case_files.sqlite`, `audit_log.sqlite`, `field_verifications.sqlite`, the crawler's store | a primary-key lookup with no server, and **triggers that block UPDATE and DELETE** |
| **JSON** | `case_files.json`, `stats.json`, `temporal.json`, `transparency.json` | the artifacts the pipeline hands to the API |
| **CSV** | `Dataset/`, `salesforce_export/` | what the source gives and what Salesforce Bulk API takes |
| **NPZ** | `desc_embeddings.npz` | the 307 MB embedding cache |
| **joblib** | the three trained models | scikit-learn and lifelines objects |
| **Git LFS** | 5 files, 542 MB | `desc_embeddings.npz` (307 MB) and `esakshi_..._ls17_raw.csv` (113 MB) are **over GitHub's 100 MB hard limit** — LFS is not a preference here, it is the only option |

> **GitHub free LFS is 1 GB of storage and 1 GB of bandwidth a month.** 542 MB is used.
> Roughly one full clone a month before downloads are blocked.

---

## 6. The models

Three models are trained; one pretrained model is used as a frozen feature extractor.
**Every figure below is read from `data/artifacts/models/metrics.json`.**

| # | Model | Library | Measured | Honest limit |
|---|---|---|---|---|
| 1 | **MiniBatchKMeans**, k = 50 | scikit-learn | **silhouette 0.050** over 187,865 descriptions, k chosen by sweep (20/30/40/50/60) | **Silhouette is not accuracy.** 0.05 is weak separation. The clusters rest on manual coherence — 49 named, 1 honestly "uninterpretable" |
| 2 | **Cox proportional hazards**, right-censored | lifelines | **C-index 0.6759** held out, n=60,000 fit, 84,311 events, 125,896 censored, 365-day horizon | It ranks *which works finish sooner*. It is **never** a probability of wrongdoing |
| 3 | **IsolationForest**, contamination 0.02 | scikit-learn | **4,220 flagged** over standardised `[log_amount, age_days]` | A multivariate outlier flag that corroborates other signals — never a verdict |
| — | **all-MiniLM-L6-v2**, 384-d | sentence-transformers *(cached, not installed)* | pretrained, **not trained by us** | a feature extractor reused as a cache |

**There is no fraud classifier and there will not be one.** There are no fraud labels in
this data; any supervised model claiming to predict fraud would be fabricated. Scoring is
transparent, weighted and rule-based, and a test greps the whole `src/` tree to make sure no
field is ever named `fraud_probability`, `is_fraud`, `fraud_score` or `fraudulent`.

---

## 7. Algorithms written by hand, not imported

The part of the stack that is not a package. These exist because no library does the job.

| Algorithm | Where | What it is |
|---|---|---|
| **Greedy with bundle lookahead** | `intelligence/targeting.py` | the audit plan. Set-up costs make this a knapsack variant — **NP-hard** — so it is a heuristic, and `test_the_planner_is_greedy_and_does_not_pretend_otherwise` pins a case where it loses to the clustered optimum |
| **LPT (longest processing time first)** | `intelligence/assignment.py` | dealing trips to auditors. Carries **Graham's proved bound of (4/3 − 1/3m)**, and both the bound and the achieved spread are printed |
| **Wilson score interval** | `intelligence/calibration.py` | every rate on the scoreboard. The normal approximation returns bounds outside [0, 1] at these counts |
| **Herfindahl–Hirschman Index** | `intelligence/vendors.py` | vendor concentration from the live portal — who actually gets paid, and how narrowly |
| **pHash + dHash** | `photohash.py` | catches a resized, re-compressed, brightened copy of a photograph that a checksum misses |
| **SHA-256 hash chain** | `api/audit.py` | over `(ts, actor, role, action, resource, detail, prev_hash)`; `verify_chain()` detects tampering |
| **Blocked cosine k-NN over the 384-d embeddings** | `intelligence/duplicates.py` | neighbours found inside blocks against the cached MiniLM vectors (**not** TF-IDF): 223,407 candidate pairs → **47,709 concerning** |
| **Streaming JSON decode** | `api/stores.py` | `raw_decode` in a loop, so 37,705 case files are never all in memory at once |
| **Greedy heap + lazy upper bounds** | `intelligence/targeting.py` | what took the planner from 35 s to ~1.3 s, and the slider from 1.6 s to 0.005 s |

---

## 8. OCR stack in detail

| Layer | Technology | Status |
|---|---|---|
| **Primary photo reader** | **Surya OCR 2**, a vision-language model, GGUF quantised | ✅ on the laptop |
| **Inference engine** | **llama.cpp** (`llama-server`), installed via `winget install ggml.llamacpp` | ✅ |
| **GPU backend** | **Vulkan** on an NVIDIA Quadro T1000 (`MPLADS_LLAMA_DEVICE=Vulkan1`) | ✅ |
| **Second reader** | **RapidOCR** / PP-OCRv4 on **onnxruntime**, CPU | ✅ |
| **Document reader** | **Docling** with the **PP-OCRv6** models bundled in the rapidocr wheel | ✅ locally, ⬜ **off on Render** |
| **Model weights** | 1.5 GB in `data/models/ocr/` — **gitignored** | fetched by `scripts/fetch_ocr_models.py` |

**Measured on 44 synthetic boards, T1000** (`docs/OCR_BENCHMARK.md`):

| Reader | Exact reference | Amount | Speed |
|---|---|---|---|
| Surya | **93%** | **93%** | ~20 s a board |
| RapidOCR | 91% | 73% | ~2 s a board |
| *Motion blur* | Surya 50% | RapidOCR **0%** | |

Three rules hold the OCR loop together, and they are product decisions, not code style:

1. **A match is never settled by the machine.** MPLADS references run in sequence, so a
   weathered board can read one digit wrong at 99.6% confidence and land on a *different
   real work*. `match_to_work` returns every real reference one character away, cross-checks
   the amount painted on the board, and refuses to save until a human ticks the box.
2. **Two readers that disagree is information.** Surya once read a wrong but plausible
   reference on heavy JPEG; RapidOCR was right, and the disagreement held the match. The two
   never agreed on the same wrong number.
3. **A re-used photograph is a question, not a finding.** Two phases of one road legitimately
   look identical from the roadside.

**A downloaded-but-incomplete model is treated as absent.** `scripts/fetch_ocr_models.py`
writes `manifest.json` only when size *and* SHA-256 match Hugging Face, because a
half-downloaded GGUF has a valid header and would crash llama-server 40 seconds into startup.

---

## 9. Language model use

| Thing | Detail |
|---|---|
| Provider | **Anthropic**, SDK 1.1.0 |
| Used for | written portfolio briefings and translation |
| Status | 🟡 **the key authenticates but billing is empty**, so every path serves its committed template |
| Circuit breaker | `llm._HALTED` — the first permanent failure is logged **once**; every later call returns instantly. This was **~2 seconds a page** before |
| Honesty rule | `llm.available()` reports `False` once halted. A screen claiming "live" while serving templates would be lying about whether the Tamil text was generated |
| **Never** | nothing is machine-translated at runtime. With no credits the fallback would silently be English — the exact failure the design exists to prevent |

**Languages: 10 at 100%** — `en hi bn ta te mr gu kn ml pa`, across both the UI bundles and
the Agentforce phrase set (47 keys). **Translated:** headings, labels, and above all the
non-fraud contract. **Never translated:** work references, agency names, MP names, rupee
figures — a work reference is an identifier, not a word.

---

## 10. Security stack

| Control | Technology | Status |
|---|---|---|
| Authentication | **PyJWT**, HS256, 12-hour expiry | ✅ |
| Authorisation | RBAC, 5 roles, `auth.require_scope` enforces jurisdiction **server-side** | ✅ tested on the failure path |
| Tamper-evident log | SHA-256 hash chain + **SQLite triggers blocking UPDATE/DELETE** | ✅ |
| Immutable field records | same trigger pattern — a correction is a new record | ✅ |
| Upload safety | 12 MB cap, extension allowlist, content-addressed storage, `Path(name).name` traversal guard | ✅ |
| Read-only chat tools | a test **greps their source** for `write_text`, `to_parquet`, `open(`, `os.remove`, `setattr` | ✅ |
| **Rate limiting** | on the architecture diagram | ⬜ **NOT IMPLEMENTED — do not claim it** |

**Weak by design, and say so before a judge finds it:** `JWT_SECRET` defaults to
`dev-only-not-a-production-secret` (Render generates a real one), `REQUIRE_AUTH=0`,
`CORS allow_origins=["*"]`, demo passwords in plaintext in `app.py` and listed openly at
`/api/auth/accounts`. Demo accounts: `ministry` / `auditor` / `bihar` / `saran`, all
`mplads2026`.

---

## 11. Memory and performance engineering

Not a library — a set of measured decisions that decide whether this runs on a free host.

| Measure | Before | After |
|---|---|---|
| `Store()` — case files + worklist + pairs | **+658 MB** | **+66 MB** |
| Whole warmed process | **~900 MB** | **~430 MB** |
| Page load | 10–12 s | **< 45 ms** |
| Audit planner | 35 s | ~1.3 s |
| Budget slider | 1.6 s a move | **0.005 s** |

How: SQLite for case files instead of 37,705 Python dicts · Parquet scans instead of a
223,407-row frame · **Arrow read-ahead turned off** (150 MB by itself) · row groups on both
Parquet files · dictionary-encoded corpus columns · `sys.intern` on repeating identity
fields · per-jurisdiction caches keyed so a Bihar officer **cannot** receive a national plan
· `lru_cache` on the plan, rota and curve · `useDebounced` on the sliders.

---

## 12. Salesforce and Agentforce

| Thing | Version / detail | Status |
|---|---|---|
| **Salesforce CLI (`sf`)** | 2.149.9 | ✅ |
| Org | Agentforce **Developer Edition**, alias `mplads`, `00Daj0000143kQ5EAI` | ✅ |
| Metadata | SFDX package, **4 custom objects, 65 fields**, Path, compact layout, list views, tabs, Lightning app, permission set | ✅ |
| `Investigation_Case__c` | **500** records, ₹97.5 Cr exposure | ✅ loaded |
| `Evidence__c` | **1,586** records | ✅ loaded |
| `Site_Verification__c` | 4 records | ✅ loaded |
| `Audit_Assignment__c` | metadata and CSV both built and reproducible | 🟡 **not deployed to the org — do not claim it exists there** |
| **Agentforce agent inside the org** | ~15 minutes of clicking, `SETUP.md` §7 | ⬜ **NOT BUILT.** What runs in the app is our own Agentforce-branded topic router (`salesforce.py::query_agentforce`) over the same data. **Do not claim the org agent exists** |
| Reports / dashboards | do not deploy as metadata for custom objects | ⬜ build in the UI |
| Public Sector Solutions | a licensed managed package | ❌ unavailable in a DE org |

**Why a DE org holds only 500 cases:** it caps at ~2,500 records at 2 KB each; 210,993 works
would be ~420 MB. Loading the top 500 leads is both the only option **and** the correct
architecture — Salesforce holds the cases that need a human, not the two lakh that do not.

---

## 13. Live-portal ingestion (`ingestion/`)

A second data path beside the CSV snapshot. Standard library plus **httpx**, **pandas**,
**sqlite3** — no framework, no scrapy, no celery.

| Piece | What it does | Status |
|---|---|---|
| `crawler/`, `client.py` | polite paged crawl of the live eSAKSHI API | ✅ **100,364 IDs across 16 states** |
| `normalizer/` | live rows → the same schema the pipeline uses | ✅ |
| `storage/` | SQLite, checkpointed and resumable | ✅ |
| `documents/`, `images/` | attachment fetching | 🟡 tiny subset only — see below |
| `api/live.py` | freshness, change feed, live figures — **additive**, reports plainly when the live DB has never been written | ✅ |
| Vendor + payment data | **68,568 works** | ✅ local |

**The attachment corpus is not downloaded and the numbers say why:** the full corpus is
≈ **96 GB** against **6.3 GB free**. The committed plan tier is **15 works / 0.02 GB**.
(There is no "84 GB corpus" anywhere in this project — that figure was measured and found
not to exist.)

---

## 14. Deployment

| Surface | Technology | Status |
|---|---|---|
| **Docker** | multi-stage: `node:20-slim` builds the frontend → `python:3.11-slim` runs it | ✅ |
| **Render** | free plan, 512 MB, Singapore, blueprint in `render.yaml` | ✅ **ready — one click from live** |
| **Hugging Face Spaces** | Docker SDK, uploaded by `scripts/deploy_hf_space.py` | 🟡 **PAUSED: `Quota exceeded for flavor cpu-basic: limit=0`** — an account restriction, not a code problem |
| **Google Colab** | `notebooks/MPLADS_run_in_colab.ipynb` | ✅ free, public link, dies with the tab |
| **Cloudflare quick tunnel** | `cloudflared` | ✅ a public link to the laptop, no account |
| **LAN demo** | Vite `host: true` + proxy | ✅ phone on the same wifi |
| **Google Cloud Run** | `Dockerfile.gcp`, `.gcloudignore` | ⬜ leftovers from an earlier attempt — **not in use** |
| **Kubernetes / AWS / GCP** | — | ❌ never attempted; no budget, no need |

Runtime switches that decide what a deployment can do:

| Variable | Effect |
|---|---|
| `MPLADS_LOW_MEMORY=1` | smaller plan cache; the budget slider warms as used; **warm-up runs behind the open port** so a sleeping container wakes fast. Changes no answer |
| `MPLADS_OCR_ENGINES=rapidocr` | photographs read by RapidOCR, and the screen says so |
| `MPLADS_DOCUMENT_OCR=0` | Documents panel reports itself unavailable rather than loading PyTorch and being killed. **Doubles as a Docker build arg of the same name**, so the image does not carry 2 GB it will never import |
| `MPLADS_JWT_SECRET` | Render generates one |
| `MPLADS_REQUIRE_AUTH` | reading open, **writing always needs a name** regardless |

**What the free tier costs, plainly:** it sleeps after 15 idle minutes (~1 minute to wake);
it has **no disk**, so verifications recorded through the live site do not survive a restart;
Surya and document reading are both off.

---

## 15. Development tooling

| Tool | Version | Use |
|---|---|---|
| **uv** | system | the only way to install into the venv — **it has no pip** |
| **pytest** | 9.1.1 | 300 passing, 1 skipped (`MPLADS_TEST_SURYA=1` opts the real Surya test in) |
| **Git** + **Git LFS** | — | `origin` = `kannan-yuvaraj/Mplad`; the old `SomeNobody21112/Thadam` is kept as remote `thadam` |
| **Vite** | 5.4.21 | `npm run dev` / `npm run demo` |
| **Salesforce CLI** | 2.149.9 | deploy and bulk import |
| **winget** | — | installed llama.cpp |
| **PowerShell** | `scripts/ports.ps1` | port hygiene |
| **`.claude/launch.json`** | — | API on 8020, frontend on 4300, `autoPort: false` |
| **CI** | — | ⬜ **no GitHub Actions.** Tests run locally |

**Ports: API 8010, web 3000** (launch.json uses 8020/4300 for the in-editor preview).
Both moved off 8000/5173 because those are the two most contended ports on a developer
machine, and `strictPort: true` makes a taken port an **error** rather than a silent slide to
the next one — a second server on a second port is how half a team ends up looking at a stale
build and calling it a bug.

---

## 16. Considered and rejected ❌

Worth as much as the list of what was used, because a judge will ask.

| Not used | Why |
|---|---|
| **HDBSCAN** | the density assumption does not hold on these embeddings |
| **Graph neural networks** | no graph structure worth the dependency |
| **LLM-based anomaly detection** | unexplainable, and the key has no credits |
| **Blockchain** | a SHA-256 hash chain in SQLite gives tamper-evidence without the theatre |
| **Deep tabular models** | 0.6759 C-index from an interpretable Cox model beats an unexplainable point of AUC in an audit context |
| **A fraud classifier** | **there are no fraud labels.** Any such model would be fabricated |
| **Leaflet / Mapbox** | inline SVG paths, nothing to load |
| **CSS framework / component library** | plain CSS with custom properties |
| **TypeScript** | not for this scope |
| **Redis / Postgres / message queue** | Parquet + SQLite + `lru_cache` do the job at this size |
| **Multiple uvicorn workers** | the corpus is in memory and the audit chain is append-only — a second worker doubles the memory and can interleave writes into the chain |

---

## 17. To be used — what is planned, and what it would take

| # | Thing | Effort | Blocked by |
|---|---|---|---|
| 1 | **Deploy `Audit_Assignment__c`** to the live org | `sf project deploy` + `sf data import` — minutes | nothing; just not run |
| 2 | **Build the real Agentforce agent** in the org | ~15 min of clicking, SETUP.md §7 | nothing; the org is Agentforce-enabled |
| 3 | **Reports and dashboards** for the ministry POV | ~2 min each in the UI | metadata deploy does not work for custom objects |
| 4 | **Rate limiting** | middleware | not started — **and not claimed** |
| 5 | **UVP-4 behavioural fingerprint**, full 8-dimension + change-point | rewrite | 🟡 30% built (volume only). **The finding worth keeping:** a global FDR correction across ~4,000 change-point tests is *unachievable* on 6–11 quarters — a permutation test on 6 periods has 720 orderings, so its smallest possible p-value is 1/720 whatever the effect size. Correct within-entity, or test agreement across dimensions |
| 6 | **sentence-transformers** back in | `uv pip install` + ~2 GB | only needed to embed a *brand-new* description |
| 7 | **Persistent disk on Render** | a paid setting | free tier has none; verifications do not survive a restart today |
| 8 | **Surya + documents in the cloud** | a 2 GB host | 512 MB free tier |
| 9 | **CI (GitHub Actions)** | one workflow file | nothing |
| 10 | **Real MoSPI cost figures** (1.0 / 0.35 auditor-days) | a conversation, not code | the assumption is printed on screen and in the API response so a reviewer can disagree |
| 11 | **Attachment corpus at scale** | 96 GB vs 6.3 GB free | disk |
| 12 | **`FLAG = 2`** (957 works) meaning | ask MoSPI | DATA_CONTRACT §13 Q1 |

---

## 18. Housekeeping the stack should not carry

* **Rotate the Anthropic API key** — it was pasted in plaintext in chat.
* **Root strays** — `App.py`, `Chat.jsx`, `Chat.css`, `Dockerfile.gcp`, `.gcloudignore`,
  `run.cmd` look like leftovers from earlier attempts and should be checked for imports,
  then cleared.
* **`CLAUDE.md` says 47 API routes; the running app has 56.** The count in this document was
  read from `app.routes`.
* **The older `MPLADS` folder is stale.** `MPLADS - Copy` is the project.

---

## 19. How to regenerate every number in this file

```bash
# installed Python versions
.venv/Scripts/python.exe -m pip list        # (no pip in the venv — use importlib.metadata)
.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('pandas'))"

# frontend locked versions
node -e "const d=require('./frontend/package-lock.json');console.log(d.packages['node_modules/react'].version)"

# API route count
.venv/Scripts/python.exe -c "from mplads.api.app import app; print(len([r for r in app.routes if hasattr(r,'methods')]))"

# model metrics
cat data/artifacts/models/metrics.json

# tests
.venv/Scripts/python.exe -m pytest
```

**Scale of the codebase:** 14,256 lines of Python across 41 modules · 9,346 lines of
JSX/JS · 17 test files · 15 scripts · 18 documents.

---

> **The contract this whole stack exists to keep:** every output is an *investigation lead
> with evidence*, never a fraud verdict, and a human decides every action. No technology on
> this page is allowed to break that.
