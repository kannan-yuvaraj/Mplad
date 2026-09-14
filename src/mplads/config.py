"""Single source of paths, seeds and the snapshot date.

Nothing in this repo may hardcode a path, a seed, or a date. Import it from here.
"""

from __future__ import annotations

from pathlib import Path

# --- Paths ----------------------------------------------------------------
#
# The supplied data package lives in `Dataset/`, not `data/raw/` as sketched in
# the FRD section 1.5. `Dataset/` is treated as READ-ONLY: we never write into
# it. Our own outputs go to `data/interim/` and `data/artifacts/`.

REPO_ROOT = Path(__file__).resolve().parents[2]

DATASET = REPO_ROOT / "Dataset"

#: The three eSAKSHI stage-wise exports. These are the ONLY inputs our pipeline
#: reads. Everything else under `Dataset/` is a previous team's derived output
#: and is used for cross-checking, never as an input.
DATA_RAW = DATASET / "raw"

#: A previous pipeline's processed tables, features, model artifacts and
#: outputs. Read-only reference used to validate our own numbers. Nothing here
#: may be consumed by our pipeline as an input.
REFERENCE = DATASET

DATA_INTERIM = REPO_ROOT / "data" / "interim"
ARTIFACTS = REPO_ROOT / "data" / "artifacts"
DOCS = REPO_ROOT / "docs"

#: The raw stage-wise files, by house. All three share a common column core;
#: the Rajya Sabha file has 29 columns to the Lok Sabha files' 31.
RAW_STAGE_FILES: dict[str, Path] = {
    "ls17": DATA_RAW / "esakshi_stagewise_works_ls17_raw.csv",
    "ls18": DATA_RAW / "esakshi_stagewise_works_ls18_raw.csv",
    "rs": DATA_RAW / "esakshi_stagewise_works_rs_raw.csv",
}

#: Present in `Dataset/raw/` but NOT read by the pipeline: it carries only the
#: recommendation stage, so it cannot support the lifecycle join. Kept for
#: provenance and possible cross-validation of recommendation records.
UNUSED_RAW_FILES: dict[str, Path] = {
    "vonter": DATA_RAW / "vonter_mplads_recommendations_raw.csv",
}

# --- Determinism ----------------------------------------------------------

RANDOM_SEED = 42

#: Which recommendation row wins when a work has more than one (156 works do).
#: "last" keeps the most recent by `recommendation_date`; "first" keeps the earliest.
#:
#: The supplied data package used "first". We use "last": where the portal has recorded a
#: work twice, the later record is the more current statement of what was recommended.
#: The choice changes 156 of 210,993 works, so it is nearly immaterial — but it must be
#: made once, here, rather than implied in two places.
#:
#: Determinism does not depend on this value. The sort is always tie-broken on
#: `(work_ref, source_file, raw_row_index)`, so the winner never depends on the order the
#: files happened to be concatenated in. See DATA_CONTRACT section 11.4.
DEDUP_KEEP: str = "last"

# --- Snapshot -------------------------------------------------------------
#
# Set in Phase 2 from the data, not guessed. Every censoring decision and every
# "as of" statement in the product resolves to this one value.

#: Censoring anchor = max(RECOMMENDATION_DATE), measured in Phase 0. Every "as of" and
#: every survival duration resolves to this one date. Anchoring on max(all dates) would
#: land in 2044 (out-of-window completion typos) and inflate open durations by ~18 years.
import datetime as _dt

SNAPSHOT_DATE: _dt.date = _dt.date(2026, 5, 26)

# --- Modelling constants --------------------------------------------------

#: Peer group must have at least this many works before it yields a percentile; else the
#: group backs off to a broader level. Groups below it at the global level never fire.
MIN_PEERS: int = 30

#: A peer group must have at least this many observed completions before its survival
#: curve is trusted; else it backs off to the parent level.
MIN_EVENTS: int = 30

#: Completion-risk horizon in days.
RISK_HORIZON_DAYS: int = 365

#: Amount / duration is only "unusual" above this within-peer percentile.
PEER_PERCENTILE_GATE: float = 0.90

#: Transparent fusion weights — NOT a learned model. Each maps a normalised signal in
#: [0,1] to its contribution. A work is only surfaced when >= 2 independent signal
#: *families* fire (the corroboration rule), never on one signal alone.
SIGNAL_WEIGHTS: dict[str, float] = {
    "peer_amount": 0.60,      # family: amount
    "peer_duration": 0.55,    # family: duration
    "completion_risk": 0.60,  # family: duration
    "conformance": 0.75,      # family: lifecycle
    "change_point": 0.50,     # family: behaviour
    "anomaly": 0.40,          # family: multivariate
    "duplicate": 0.65,        # family: duplication
}

#: Near-duplicate similarity at or above which the duplication signal fires.
DUPLICATE_SIGNAL_THRESHOLD: float = 0.97

#: Which family each signal belongs to. Confidence counts distinct families, not signals,
#: so two signals reading the same clock cannot manufacture corroboration.
SIGNAL_FAMILY: dict[str, str] = {
    "peer_amount": "amount",
    "peer_duration": "duration",
    "completion_risk": "duration",
    "conformance": "lifecycle",
    "change_point": "behaviour",
    "anomaly": "multivariate",
    "duplicate": "duplication",
}


def ensure_dirs() -> None:
    """Create the output directories this pipeline writes to."""
    for path in (DATA_INTERIM, ARTIFACTS, DOCS):
        path.mkdir(parents=True, exist_ok=True)

# --- API security -----------------------------------------------------------
#
# Prototype settings. REQUIRE_AUTH is off by default so the demo runs without a token;
# turn it on to exercise the RBAC failure paths. The secret is a development value and is
# not a production key — a real deployment injects it from the environment.

import os as _os


def _load_dotenv() -> None:
    """Read REPO_ROOT/.env into the environment if present.

    Kept dependency-free and non-overriding: a variable already exported in the shell
    always wins, so `.env` is a convenience for local runs, never a way to silently
    override a deliberately-set production value. The file is gitignored.
    """
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        _os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()

JWT_SECRET: str = _os.environ.get("MPLADS_JWT_SECRET", "dev-only-not-a-production-secret")
REQUIRE_AUTH: bool = _os.environ.get("MPLADS_REQUIRE_AUTH", "0") == "1"

#: Set on a host with little memory — a free container is typically 512 MB. It does not
#: change a single answer the service gives; it trades the pre-warmed budget slider and a
#: large plan cache for about 150 MB, so the first move of the slider costs a quarter of a
#: second instead of nothing.
LOW_MEMORY: bool = _os.environ.get("MPLADS_LOW_MEMORY", "0") == "1"

#: Document reading (Docling) loads PyTorch, which is ~300 MB of resident memory the first
#: time a document is uploaded. On a 512 MB host that is not a slow feature, it is a killed
#: process — and a container that dies when someone uploads a PDF is worse than one that
#: says it cannot read PDFs. Set to 0 there; the screen then reports documents as
#: unavailable instead of accepting one and falling over.
DOCUMENT_OCR: bool = _os.environ.get("MPLADS_DOCUMENT_OCR", "1") != "0"

#: Append-only, hash-chained audit log location.
AUDIT_LOG_PATH = REPO_ROOT / "data" / "artifacts" / "audit_log.sqlite"

# --- OCR ----------------------------------------------------------------------
#
# Two jobs, two engines. A *photograph* of a site board is read by Surya (a vision-language
# OCR model served by llama.cpp), with RapidOCR as a second, independent reader and as the
# fallback. A *document* — a sanction order, work order or completion certificate, as a PDF
# or a scan — is read by Docling, which keeps the page's structure (headings, tables).
# Every value below can be overridden from the environment; nothing is required, and a
# machine with none of it installed still records verifications by hand.

#: Model weights we fetch ourselves live here, not in a per-user cache, so a deployment can
#: ship them alongside the code. Gitignored with the rest of data/.
OCR_MODELS = REPO_ROOT / "data" / "models" / "ocr"

#: Readers tried for a photograph, in order. The first that is available is the primary;
#: the next available one reads the same image again as a cross-check.
OCR_IMAGE_ENGINES: tuple[str, ...] = tuple(
    e.strip() for e in _os.environ.get("MPLADS_OCR_ENGINES", "surya,rapidocr").split(",")
    if e.strip()
)

#: Surya's model, as the two GGUF files llama-server loads (model + vision projector).
SURYA_GGUF_DIR = Path(_os.environ.get("MPLADS_SURYA_GGUF_DIR", OCR_MODELS / "surya-ocr-2-gguf"))
SURYA_GGUF_MODEL = SURYA_GGUF_DIR / "surya-2.gguf"
SURYA_GGUF_MMPROJ = SURYA_GGUF_DIR / "surya-2-mmproj.gguf"

#: The llama-server binary. Empty means "find it on PATH, then in the winget install".
LLAMA_SERVER: str = _os.environ.get("MPLADS_LLAMA_SERVER", "")

#: Which llama.cpp device runs Surya ("Vulkan1" is a discrete GPU on a machine that also has
#: integrated graphics). Empty lets llama.cpp choose. `llama-server --list-devices` lists them.
LLAMA_DEVICE: str = _os.environ.get("MPLADS_LLAMA_DEVICE", "")

#: Seconds allowed for llama-server to load the model before Surya is declared unavailable.
SURYA_STARTUP_TIMEOUT: int = int(_os.environ.get("MPLADS_SURYA_STARTUP_TIMEOUT", "300"))

#: Documents Docling accepts from an upload. Images are accepted too (a phone photo of a
#: sanction order is a document, not a site board).
DOCUMENT_SUFFIXES: frozenset[str] = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif",
                                               ".tiff", ".bmp", ".webp"})
