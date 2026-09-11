# Limitations, boundaries and things not established

The point of this file is that the ingestion module never claims more than it
measured. If something below looks like a gap, it is a gap, stated on purpose.

---

## 1. Legal and access boundary

The data collected is **published by the Government of India on a public
dashboard with no authentication**. Nothing here bypasses a control:

- no login, no captcha solved, no OTP, no credential guessed
- no rate limit circumvented — we self-imposed 1 req/s where none was enforced
- no vulnerability probed, no parameter fuzzed for access, no ID enumerated
  against an endpoint that gates on identity
- `robots.txt` does not exist on this host (302 to the login page), so no crawl
  directive was overridden

**Content ownership:** "© Content Owned by Ministry of Statistics and Programme
Implementation, Government of India". No licence is declared on the portal. Most
GoI portal content falls under the **Government Open Data Licence – India** or
NDSAP, but **this portal does not say so**, and we should not assert a licence it
does not claim. For SIH use: attribute MPLADS / MoSPI, state the retrieval date,
and do not present the data as licensed for redistribution until MoSPI says it
is. `Dataset/README.md` already takes this posture for the mirrors.

**Personal data.** MP names, vendor names and implementing-agency names are
published by the government on a public dashboard and are collected.
`getCitizenRequestByPhNumber` returns a private citizen's submissions keyed by
phone number; it is publicly reachable and is **deliberately not called**.

## 2. What is restricted

| Resource | Access | Reason |
|---|---|---|
| `/digigov/Login.zul` and all stakeholder workflows | **RESTRICTED** | authentication required |
| `getCaptcha` | **RESTRICTED** | login captcha; not solved |
| `verifyOTPForCitizenLogin`, `updateWorkReviewByCitizen` | **RESTRICTED** | OTP-gated write path |
| PFMS / TSA transaction-level ledger | **NOT EXPOSED** | only `FUND_DISBURSED_AMT` is public |
| Sanction order *as a structured record* | **NOT EXPOSED** | it exists only as an uploaded file, if the agency uploaded one |

## 3. The FLAG → stage mapping is not characterised

`getAttachIdsbyFlag` takes a `FLAG`. On work 140096, `FLAG=1` returned both
files, `FLAG=2` and `3` returned the sentinel `[{"FILE_NAME":"N/A","URL":"N/A"}]`
and `0/4/5/6` returned `[]`. On work rows, `FLAG` is `1` on recommended and
sanctioned rows and `3` on completed rows.

That is not enough to say what FLAG *means*. `ingestion/config.ATTACHMENT_FLAGS`
sweeps `(1, 2, 3)` and records what comes back rather than assuming a mapping.
The `FLAG = 2` question in `CLAUDE.md` open item 3 is **not** answered by this
work.

## 4. Image stages are not available, and are not inferred

The brief asks for BEFORE / DURING / AFTER / COMPLETED "where available". **The
portal does not label them.** There is a numeric stage FLAG and a filename
chosen by the uploading agency, and nothing else.

Filename-based inference was tested and fails immediately: `wc.jpg` on the very
first work retrieved is not a photograph of an asset at all — it is a scanned
completion certificate. `images.source_declared_stage` is therefore `NULL` on
every row by design. Do not "improve" this by pattern-matching filenames.

## 5. Historical coverage is a boundary of the portal, not of this crawler

The dashboard states plainly that MPLADS was paper-based before **1 April 2023**
and that works recommended and sanctioned in 2019-20 through 2022-23 (17th LS)
and pre-2023-24 Rajya Sabha works are **not on eSAKSHI at all**. District
authorities held those records physically.

So `tenure_id = 5` ("17th Lok Sabha") returns *17th-LS works recorded on eSAKSHI
from 2023-24 onward*, not the 17th Lok Sabha. **No amount of crawling this portal
will recover 2019–2023.** Sources that might, and which this module does not
touch:

- MPLADS SBI public report at `164.100.68.116/mpladssbi` (the Vonter mirror's
  origin, ODbL) — recommendation stage only
- MoSPI annual reports and Lok Sabha / Rajya Sabha question answers (PDF)
- `data.gov.in` MPLADS resources

`CURRENT` (eSAKSHI, 2023-04 onward) and `HISTORICAL` (everything else) must stay
separated. This module collects `CURRENT` only.

## 6. Reconciliation is partial

`ingestion.cli validate` reconciled **3 states, 12 checks**, not the nation. All
counts matched; the two amount mismatches are explained in `FINDINGS.md` §5.
Running it nationally is one command and has not been run.

Reasons a portal aggregate and our sum can legitimately differ, none of which are
grounds for silently adjusting a number:

- **definitional** — confirmed for the `Works Completed` tile, which sums
  sanctioned value while the report sums actual value
- the portal updates in real time from stakeholder logins; a tile and a report
  fetched seconds apart can straddle a write
- a tile scoped to a tenure vs a report scoped to the same tenure can differ if
  a work changes tenure attribution
- cancelled or reverted works
- the `Amount consented for Calamity` tile is separate from the work tiles

## 7. Things not built

- **No OCR.** `documents/extract.py` extracts embedded PDF text only. The sample
  certificate is a photograph of a handwritten-annotated Marathi document;
  running OCR and storing the output as the document's contents would
  manufacture text nobody can trust. When added it must carry a confidence and
  be marked machine-read — the same posture `src/mplads/ocr.py` already takes.
- **`pypdf` is not installed** and is not in `pyproject.toml`, because this
  project requires asking before adding a dependency. Extraction reports
  `unavailable` rather than failing.
- **No PostgreSQL loader.** `schemas/schema.sql` is complete and the normalizer
  writes the same shapes as parquet, matching how the rest of the project
  stores data. A loader is a small script if a database is actually wanted.
- **No national crawl has been run.** The module is proven on Andaman & Nicobar
  (71 works, 20 attachments) and reconciled on three states. Scaling is a
  command, not more code — but it has not been executed, and no completeness
  claim is made.
- **`getFileData`** (scheme guideline PDFs) has its request shape from source
  reading, not from a successful call. The filenames from `get_fileNames` are
  verified; retrieving one of those PDFs is not.

## 8. What "complete" would require

`ingestion.cli report` deliberately prints `completeness_claim: NOT CLAIMED`.
Completeness would require, all together:

1. every planned (state, house, tenure, key) scope in the checkpoint completed
2. every failure in the checkpoint resolved, not merely recorded
3. attachments attempted for every work carrying an `ATTACH_ID`
4. reconciliation run nationally with every mismatch explained
5. `verify_scope_disjointness` showing state scopes partition the work-id space

Until all five hold, the report states what was discovered and what was
retrieved, and leaves the judgement to a person.
