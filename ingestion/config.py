"""Configuration for the eSAKSHI public-portal ingestion module.

Never hardcode a path, a rate or an endpoint anywhere else in this package —
import it from here. Mirrors the convention in `mplads.config`.

Every value in this file was measured against the live portal on 2026-09-10,
not assumed. See `ingestion/research/ENDPOINT_INVENTORY.md` for the evidence.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Target
# --------------------------------------------------------------------------

#: Official Ministry of Statistics and Programme Implementation MPLADS portal.
BASE_URL = os.environ.get("MPLADS_PORTAL_BASE", "https://mplads.mospi.gov.in")

#: The public dashboard page whose JavaScript drives the REST API below.
DASHBOARD_URL = f"{BASE_URL}/digigov/dashboard.html"

#: Public, unauthenticated REST controllers.
REST_DASHBOARD = "/rest/PreLoginDashboardData"
REST_CITIZEN = "/rest/PreLoginCitizenWorkRcmdRest"

# --------------------------------------------------------------------------
# Identifiers used by the portal (decoded from the frontend, then verified)
# --------------------------------------------------------------------------

#: `HOUSE_OF_PARLIAMENT` values. Recovered from `loksaba.js` / `rajyasaba.js`,
#: which call `sethouse(279935^279933)` = 2 and `sethouse(878755^878754)` = 1.
HOUSE_LOK_SABHA = 2
HOUSE_RAJYA_SABHA = 1
HOUSES = (HOUSE_LOK_SABHA, HOUSE_RAJYA_SABHA)

#: The five `getTilesReportData` keys that return work-grain or payment-grain
#: rows, mapped to the envelope key the server wraps the rows in. The server
#: returns `{<envelope>: "<json string>"}` — the rows are a *string*, not an
#: object, and must be parsed a second time.
TILE_KEYS: dict[str, str] = {
    "Works Recommended": "Total Works Recommended",
    "Works Sanctioned": "Total Sanction Work",
    "Works Completed": "Total Works Completed",
    "Expenditure on Completed and On-going Works as on Date": "Total Expenditure",
    "Allocated Limit for Hon'ble MPs": "Allocated Limit",
}

#: `getAttachIdsbyFlag` selects attachments by work stage. Only FLAG values that
#: returned content during characterisation are enumerated; 2 and 3 return the
#: sentinel `{"FILE_NAME": "N/A", "URL": "N/A"}` and 0/4/5/6 return `[]` for the
#: works measured so far. The stage->FLAG mapping is NOT fully characterised —
#: see ingestion/research/LIMITATIONS.md. We sweep the range and record what
#: comes back rather than assuming.
ATTACHMENT_FLAGS = (1, 2, 3)

#: Sentinel the server returns instead of an empty list when a stage exists but
#: carries no file. Must never be written to disk as if it were a file.
ATTACHMENT_ABSENT = "N/A"

# --------------------------------------------------------------------------
# Politeness. Phase 9: do not hammer a government server.
# --------------------------------------------------------------------------

#: Minimum seconds between requests. Single-threaded by design; there is no
#: concurrency knob because we do not want one against this host.
REQUEST_DELAY_SECONDS = float(os.environ.get("MPLADS_REQUEST_DELAY", "1.0"))

#: Extra delay after a large attachment download, which costs the server more.
ATTACHMENT_DELAY_SECONDS = float(os.environ.get("MPLADS_ATTACHMENT_DELAY", "1.5"))

REQUEST_TIMEOUT_SECONDS = float(os.environ.get("MPLADS_TIMEOUT", "180"))
MAX_RETRIES = int(os.environ.get("MPLADS_MAX_RETRIES", "4"))
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 120.0

#: Sent so the operator is identifiable to the portal's administrators rather
#: than anonymous. Do not disguise this as an ordinary browser.
USER_AGENT = os.environ.get(
    "MPLADS_USER_AGENT",
    "mplads-intel-research/1.0 (SIH 2026 PS 26102; public MPLADS dashboard data; "
    "contact via repository)",
)

# --------------------------------------------------------------------------
# Storage layout (Phase 5)
# --------------------------------------------------------------------------

INGESTION_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = INGESTION_ROOT.parent

DATA_ROOT = Path(os.environ.get("MPLADS_INGEST_DATA", PROJECT_ROOT / "data" / "portal"))

RAW_ROOT = DATA_ROOT / "raw"
RAW_API = RAW_ROOT / "api"
RAW_PAGES = RAW_ROOT / "pages"
RAW_DOCUMENTS = RAW_ROOT / "documents"
RAW_IMAGES = RAW_ROOT / "images"

NORMALIZED_ROOT = DATA_ROOT / "normalized"
MANIFEST_ROOT = DATA_ROOT / "manifests"
EXTRACTED_TEXT_ROOT = DATA_ROOT / "extracted_text"
CHECKPOINT_ROOT = DATA_ROOT / "checkpoints"
REPORT_ROOT = DATA_ROOT / "reports"
LOG_ROOT = DATA_ROOT / "logs"

#: The Phase 3 single-work proof lives here, deliberately outside `raw/` so a
#: crawl can never overwrite the worked example.
EXAMPLE_WORK_ROOT = PROJECT_ROOT / "data" / "raw" / "example_work"

ALL_DIRS = (
    RAW_API, RAW_PAGES, RAW_DOCUMENTS, RAW_IMAGES,
    NORMALIZED_ROOT, MANIFEST_ROOT, EXTRACTED_TEXT_ROOT,
    CHECKPOINT_ROOT, REPORT_ROOT, LOG_ROOT,
)


def ensure_dirs() -> None:
    """Create the storage tree. Idempotent."""
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Extensions we are willing to write to disk, by kind.
# --------------------------------------------------------------------------

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"})
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf", ".odt"})
