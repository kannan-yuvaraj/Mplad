# Thadam - (mplads -intel) 

AI-assisted forensic monitoring and decision support over MPLADS / eSAKSHI work-lifecycle
data. It learns what normal work looks like across the national portfolio, compares each
work against its true peers, predicts completion risk, detects behavioural change, fuses
those signals into an explainable case file, and ranks case files by audit
return-on-investment.

**SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus**

> **This system produces investigation leads, never fraud verdicts.** There are no fraud
> labels in MPLADS public data. Nothing here is a supervised fraud model and no output is a
> fraud probability. Every case file ends in an action for a human to take.

## Status

Phase 0 of 11 complete: repository bootstrap and data contract. The full README — with the
architecture diagram, quickstart, and a results table drawn from real artifacts — is a
Phase 11 deliverable.

## Quickstart (development)

```bash
python -m uv venv --python 3.11 .venv
python -m uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python.exe -m mplads.cli paths
.venv/Scripts/python.exe -m pytest
```

## Data

The supplied data package lives in `Dataset/` and is **not** committed. Our pipeline reads
only the three eSAKSHI stage-wise CSVs in `Dataset/raw/`; everything else in that directory
is a previous pipeline's derived output, used to cross-check our numbers and never as an
input.

Start with **[docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md)** — what the data actually
contains, measured, including what must never be used and why.

## Documentation

| Document | Contents |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Standing context: constraints, conventions, layout, phase list |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Every column, the join key, orphan counts, the DO-NOT-USE list |
| `docs/data_profile.txt` | Generated profile of every raw file |
| [README_HF.md](README_HF.md) | HuggingFace Spaces version of this README |

## Setup (clone and run)

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git LFS (for large dataset files)

### 1. Install Git LFS and pull dataset

The dataset is committed via Git LFS (~500 MB download). After cloning:

```bash
git lfs install
git lfs pull
```

This pulls the large raw CSVs and the pre-computed embeddings cache (`desc_embeddings.npz`).
Without this step, the files will be empty pointer stubs.

#### Verifying dataset integrity (defect-3 note)

`Dataset/metadata/raw_sources.json` records the expected row count, byte size and
SHA-256 for every raw source. **A plain `git clone` cannot verify these hashes**:
until `git lfs pull` runs, the large files on disk are ~130-byte LFS pointer stubs,
not the real data, so any hash you compute from them is a hash of the stub.

After `git lfs pull` completes, verify with:

```bash
python - <<'EOF'
import hashlib, json, os
manifest = json.load(open("Dataset/metadata/raw_sources.json"))
for src in manifest:
    path = os.path.join("Dataset", src["file"])
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    status = "OK" if h == src["sha256"] else f"MISMATCH (expected {src['sha256']})"
    print(f"{status:10s} {src['file']}")
EOF
```

All four sources should print `OK`. A `MISMATCH` means the file on disk differs from
what the manifest declares — re-run `git lfs pull` before investigating anything else.
Note the manifest hash covers the *raw* file as published by the upstream mirror;
Git LFS stores the identical bytes, so the check works directly against the checked-out file.

### 2. Python environment

```bash
python -m venv .venv
# Windows
.venv/Scripts/activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
pip install fpdf2 python-multipart  # required for serving, not in pyproject.toml yet
```

### 3. Build artifacts

```bash
# Ingest the raw CSVs into a clean parquet
python -m mplads.cli ingest

# Train clustering / survival / anomaly models
python -m mplads.train

# Run the intelligence pipeline (case files, leads, audit plan)
python -m mplads.pipeline
```

### 4. Run the application

```bash
# Backend (FastAPI on port 8020)
python -m uvicorn mplads.api.app:app --host 0.0.0.0 --port 8020 --reload

# Frontend (Vite dev server on port 4300)
cd frontend && npm install && npm run dev
```

Open **http://localhost:4300** in your browser.

### Docker alternative

```bash
docker compose up --build
```

## Architecture

| Layer | Technology |
|---|---|
| Data ingestion | pandas + custom normalisation pipeline |
| Clustering | scikit-learn KMeans (8 archetypes) |
| Survival analysis | lifelines Cox proportional hazards |
| Anomaly detection | Isolation Forest |
| Intelligence | 7-engine fusion (duplicates, completion risk, change points, etc.) |
| Backend API | FastAPI + uvicorn |
| Frontend | React 18 + Vite 5 |
| Chat interface | Anthropic Claude (optional, requires API key) |

## Key Results (on real data)

| Metric | Value |
|---|---|
| Raw work records | 210,993 |
| Work stages (pre-norm) | 476,781 |
| Case files generated | 38,674 |
| HIGH audit leads | 4,524 |
| Anomaly-flagged works | 4,220 |
| Duplicate pairs flagged | 50,290 |
| Cox C-index | 0.6759 |
| KMeans silhouette | 0.0500 |

## Important Notes

- This system produces **investigation leads, never fraud verdicts**.
- There are no fraud labels in MPLADS public data — nothing here is a supervised fraud model.
- Every case file ends in an action for a human to take.

**SIH 2026 · PS 26102 (MoSPI) · Team Morior Invictus**
