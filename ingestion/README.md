# `ingestion/` — live eSAKSHI public-portal collector

A reproducible, auditable pipeline that collects publicly accessible MPLADS data
directly from the official portal, `https://mplads.mospi.gov.in`.

It is **additive**. Nothing under `src/mplads/` is modified, no existing artefact
is overwritten, and it writes to its own tree under `data/portal/`. The existing
CSV-snapshot pipeline keeps working exactly as before.

Read `research/ENDPOINT_INVENTORY.md` for what the portal exposes,
`research/FINDINGS.md` for what we learned, and `research/LIMITATIONS.md` for
what this does **not** do. Those three files carry the evidence; this one tells
you how to run it.

---

## The short version

The portal is a ZK/Java application whose public dashboard is driven entirely by
an **unauthenticated JSON REST API**. HTML scraping is unnecessary and would be
worse. Two controllers matter:

```
POST /rest/PreLoginDashboardData/getTilesReportData   -> work-grain rows
POST /rest/PreLoginDashboardData/getAttachIdsbyFlag   -> a work's file list
POST /rest/PreLoginCitizenWorkRcmdRest/getAttachmentById -> the file bytes (base64)
```

Everything else is enumeration around those three.

---

## Running it

Commands run in order. Each is resumable; re-running is safe and cheap.

```bash
.venv/Scripts/python.exe -m ingestion.cli proof
```

**Phase 3 gate.** Retrieves ONE complete work with every piece of public
evidence attached to it, into `data/raw/example_work/`. `works` and
`attachments` refuse to run until this has passed. ~20 requests, under a minute.

```bash
.venv/Scripts/python.exe -m ingestion.cli enumerate
```

States, tenures, constituencies, MPs. ~120 requests, ~2 minutes. Verified
output: 36 states, 543 constituencies, 1,380 distinct MPs, 0 failures.

```bash
.venv/Scripts/python.exe -m ingestion.cli works --state 35
.venv/Scripts/python.exe -m ingestion.cli works              # all states
```

The work-grain crawl. The unit is (state, house, tenure, tile key) — about 720
units nationally, roughly 12 minutes at the default 1 req/s.

```bash
.venv/Scripts/python.exe -m ingestion.cli attachments --limit-works 12
```

Documents and images for crawled works. Two requests per work minimum, plus one
per file, so this is the expensive stage — always bound it with `--limit-works`
before letting it run free.

```bash
.venv/Scripts/python.exe -m ingestion.cli normalize
.venv/Scripts/python.exe -m ingestion.cli validate
.venv/Scripts/python.exe -m ingestion.cli report
```

Normalized parquet tables, reconciliation against the portal's own published
aggregates, and the completeness report.

### Rate limiting

Default **1 request per second**, single-threaded, with exponential backoff and
jitter on 5xx/429. There is no concurrency setting and that is deliberate. To go
gentler:

```bash
MPLADS_REQUEST_DELAY=3 .venv/Scripts/python.exe -m ingestion.cli works
```

`MPLADS_ATTACHMENT_DELAY`, `MPLADS_TIMEOUT`, `MPLADS_MAX_RETRIES` and
`MPLADS_USER_AGENT` are the other knobs. All live in `ingestion/config.py`;
nothing is hardcoded elsewhere.

---

## Layout

```
ingestion/
  config.py                 paths, rates, identifiers — the only place they live
  client.py                 throttled, retrying HTTP client
  api.py                    typed wrapper per endpoint == the endpoint inventory
  cli.py                    the commands above
  research/                 ENDPOINT_INVENTORY · FINDINGS · LIMITATIONS
  crawler/
    proof.py                Phase 3 — one complete work, the gate
    enumerate_reference.py  states, tenures, constituencies, MPs
    works.py                work-grain crawl + scope-disjointness proof
    attachment_crawl.py     documents and images at scale
    checkpoint.py           atomic, resumable checkpoints
  storage/
    manifest.py             RawStore — the only writer of bytes; audit manifest
    attachments.py          base64 decode, magic-byte verification, storage
  documents/extract.py      PDF text extraction with page markers
  images/inspect.py         dimensions, MIME, EXIF — no stage inference
  normalizer/normalize.py   raw responses -> parquet, provenance in-band
  validation/
    reconcile.py            our sums vs the portal's published aggregates
    completeness.py         discovered vs retrieved, and every failure
  schemas/schema.sql        PostgreSQL DDL
```

### Data layout

```
data/portal/
  raw/api/          every response verbatim, by scope and key
  raw/documents/    <work_id>/<attach_id>__<filename>
  raw/images/       <work_id>/<attach_id>__<filename>
  raw/unknown/      files whose extension we do not classify — kept, not dropped
  normalized/       works.parquet · payments.parquet · mp_allocations.parquet
  manifests/        manifest.jsonl — one line per retrieved artefact
  extracted_text/   <work_id>/<attach_id>.txt
  checkpoints/      resume state
  reports/          reconciliation · completeness · crawl summaries
  logs/
data/raw/example_work/   the Phase 3 proof, kept out of reach of the crawler
```

---

## Provenance

`RawStore.write` is the only path bytes take to disk, and it always appends a
manifest line:

```json
{
  "stored_path": "raw/documents/140096/703161.801553__work cc.pdf",
  "source_url": "https://mplads.mospi.gov.in/rest/PreLoginCitizenWorkRcmdRest/getAttachmentById",
  "http_method": "POST",
  "request_body": "{\"id\": \"703161.801553\"}",
  "http_status": 200,
  "content_type": "application/pdf",
  "file_size": 264737,
  "sha256": "61016427b7f007d35dc8d223ead3559e83c9b4171070bbde8127410a9a2b915b",
  "retrieved_at": "2026-09-10T05:22:44.940502+00:00",
  "artefact_kind": "document",
  "identifiers": {
    "WORK_RECOMMENDATION_DTL_ID": "140096",
    "ATTACH_ID": "703161.801553",
    "FLAG": 1,
    "FILE_NAME": "work cc.pdf"
  }
}
```

Normalized rows additionally carry `source_stored_path` and `source_sha256`, so
the chain runs:

```
a field on a work  ->  source_stored_path  ->  the exact preserved response
                   ->  manifest row  ->  source_url + request_body + timestamp
```

and for document-derived facts, `extracted_text/` files carry `===== PAGE n =====`
markers so a claim can cite a page.

---

## Design decisions worth knowing before you change anything

**Scope narrowing is the pagination.** There is no page parameter anywhere. The
server returns a whole scope at once; national scope times out and state scope
returns in under a second. Do not add a `page` argument — there is nothing to
send it to.

**Strip the grand-total row.** Every report response ends with
`{"Total_Amt": n}`. It is not a work. `api.get_tile_report` separates it into
`TileReport.grand_total` and Phase 10 reconciles against it. Not stripping it is
how 3,987 phantom rows got into the project's CSV snapshot.

**The work key is `(WORK_RECOMMENDATION_DTL_ID, mp_id)`.** The portal's own
`WORK_ID` is issued at completion and absent on every open work. It is kept as
`portal_work_id` and never joined on, matching `docs/DATA_CONTRACT.md`.

**Failures are returned, not raised or swallowed.** `download_attachment`
returns an `AttachmentFailure` rather than throwing, checkpoints record every
one with URL, identifier, status and retry count, and the completeness report
lists them. Nothing is silently skipped.

**The completeness report never claims completeness.** It prints discovered vs
retrieved and `completeness_claim: NOT CLAIMED`, with the five conditions that
would have to hold. See `research/LIMITATIONS.md` §8.

---

## What this is not allowed to do

No login, no captcha, no OTP, no credential, no vulnerability, no rate-limit
evasion, no ID enumeration against an identity-gated endpoint. Restricted
resources are **recorded** — see the table in `research/LIMITATIONS.md` §2 — not
opened. `getCitizenRequestByPhNumber` returns a private citizen's submissions
against a phone number; it is publicly reachable and deliberately never called.
