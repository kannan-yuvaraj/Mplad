# Stage 0b — Portal acquisition posture (attachment study)

> **DRAFT — not yet merged into `DATA_LINEAGE.md`.** This entry is written per §8.2 of the
> Attachment Corpus Study spec. It is to be inserted into `Dataset/metadata/DATA_LINEAGE.md`
> between **Stage 0 — Acquisition** and **Stage 1 — Cleaning and work-level join** on the
> day the first attachment fetch runs — not before, because every field below is dated
> and the terms/robots position must be read fresh at run time, not pre-asserted.
>
> Status of the study itself: **not started.** Tasks 1 and 2 (DevTools captures) are
> unresolved; the resolver endpoint and FLAG 2 behaviour are still unknown (§2.3).
> This document records the posture, not a completed acquisition.

---

| | |
|---|---|
| **Input** | MPLADS/eSAKSHI portal — `https://mplads.mospi.gov.in`, endpoints under `/rest/PreLoginDashboardData/` |
| **Output** | `outputs/attachment_study/{sample_frame.csv, raw_jsonl_cache/, extracted.csv, bridge_validation.csv}` (gitignored; never under `Dataset/`) |
| **Transformation** | Structured field extraction from work-attachment documents (OCR per §25 of the spec). Page images are **discarded after extraction is confirmed** (§7 extract-and-discard). |
| **Code** | `in-rolls` fetcher extension (attachment module) — to be written; spec task 5 |
| **Volume** | n = 25 works, FLAGS 1–5 each, plus ~100 lookup calls (spec §4). No bulk corpus. |

**Endpoints used**

- `POST /rest/PreLoginDashboardData/getTilesReportData` — tabular tiles (6 keys; upstream implements 3–5 only)
- `POST /rest/PreLoginDashboardData/getAttachIdsbyFlag` — attachment metadata per `WORK_ID`
- The attachment resolver (`ATTACH_ID` → bytes) — **endpoint not yet captured** (spec task 1)

**Throttle**

2 s between calls plus jitter, per `in-rolls/_client.Throttle`. Rationale: ~100 lookups
plus document downloads stay well inside any reasonable rate expectation for a public,
credential-free dashboard endpoint; the throttle exists to be a good citizen, not to
evade detection. Resume from a JSONL cache so an interrupted run never re-fetches.

**Terms and robots position**

- **No credentials are used, bypassed, or simulated.** Every endpoint exercised sits under
  `PreLoginDashboardData`, i.e. it serves the public pre-login dashboard to any browser
  session. A `GET /digigov/dashboard.html` establishes the session, exactly as a browser
  visit would.
- robots.txt position as of this draft: **not yet read — must be recorded on the run date**
  by whoever executes task 6, with the date. If robots.txt disallows these paths, the fetch
  does not proceed and this entry is amended instead.
- No bulk mirroring. The fetch is scoped to a stratified sample of 25 works; the study
  extracts fields and discards images. It is not a crawl and must not become one.

**Retention and personal data (§7 of the spec, binding)**

- Attachments carry PII the tabular data never did: contractor names, tax identifiers,
  officer phone numbers, wet signatures, beneficiary names in some state forms.
- Persist structured fields only. Do not retain page images beyond confirmation; do not
  build a corpus of scans or signatures.
- All study outputs live under `outputs/attachment_study/`, which is **gitignored** —
  nothing enters `Dataset/` (read-only per the project constitution) or any commit.
- Any document shown in a walkthrough is redacted at the raster level first (contractor
  name, tax ID, phone).
- The source-tree guard gains `contractor_name`, `pan`, `phone` as banned identifiers,
  or all PII handling routes through a single redaction module.

**Attribution**

Data acquired from the MPLADS/eSAKSHI portal, Ministry of Statistics and Programme
Implementation (MoSPI), Government of India. Attribute MPLADS/MoSPI in any output that
derives from this study. Portal data © Government of India; used here for public-interest
audit research under the portal's public reporting terms.

**Relationship to Stage 0**

Stage 0 records the existing acquisition: secondary GitHub mirrors, point-in-time
snapshot, no portal contact. Stage 0b records the first direct portal contact. Together
they resolve the provenance ambiguity Stage 0 flags ("in-rolls declares no licence") for
the attachment study specifically — the tabular mirrors remain as they are, and defect 1
of the spec's §9 (nothing in `Dataset/` came from the portal) stays open for the tabular
corpus.
