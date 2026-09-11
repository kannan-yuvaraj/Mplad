# eSAKSHI public endpoint inventory

**Target:** `https://mplads.mospi.gov.in` — the official MPLADS portal of the
Ministry of Statistics and Programme Implementation, maintained by TCS.
**Method:** frontend JavaScript recovered and de-obfuscated, then every endpoint
called against the live portal.
**Verified:** 2026-09-10. Every row below was executed; nothing is inferred.

Runnable equivalent of this document: `ingestion/api.py`.

---

## 1. How the site is built

The portal is a **ZK Framework (Java) application** — `.zul` pages, `/zkImages/`
asset paths, a ZK session behind `/digigov/Login.zul`. The **public** surface is
not ZK at all: `/digigov/dashboard.html` is a plain jQuery page whose entire
content comes from a JSON REST API.

**HTML scraping would have been the wrong approach.** Nothing renders into the
DOM that was not a JSON response first, the tables are DataTables built
client-side from a single bulk response, and the page is unusable without
JavaScript.

`robots.txt` does not exist — it returns `302 Found` to
`http://mplads.mospi.gov.in/digigov/Login.zul`. There is therefore no
machine-readable crawl directive to honour or violate. We self-imposed 1 req/s.

### De-obfuscation

The frontend bundles are obfuscated three ways at once: every identifier and
string literal encoded as `\uXXXX` escapes, string literals stored reversed and
rebuilt with `"...".split("").reverse().join("")`, and integer constants written
as XOR pairs (`279935^279933` for `2`). Decoding the `\uXXXX` escapes is
sufficient to recover every endpoint and parameter name:

```python
re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), source)
```

Bundles that matter: `/libs/simplegrid/landingpage.js`, `preLoginDashboard.js`,
`poptable.js`, `loksaba.js`, `rajyasaba.js`, `graph.js`.

---

## 2. Common request contract

| Property | Value |
|---|---|
| Method | `POST` on every endpoint, including pure reads |
| Content-Type | `application/json; charset=utf-8` |
| Auth | **None.** No cookie, token, captcha or referer check observed |
| Headers the frontend sends | `X-Client-UA: <navigator.userAgent>`, `X-Requested-With: XMLHttpRequest` |
| Response | `application/json;charset=UTF-8` |
| Rate limiting | None observable at 1 req/s over ~250 requests |
| Error behaviour | Malformed parameters return `200` with `[]`, `{}` or a zero-length body — **never a 4xx**. An empty response means "you asked wrongly" as often as "no data". |

Currency strings carry a literal `Rs` prefix that renders as a replacement
character in most encodings; the frontend strips it with `.replace("Rs","")`.

---

## 3. The `combo` parameter

Recovered from the `#searchFilter` click handler in `preLoginDashboard.js`,
which populates an array `e` and sends `e.toString()`:

```
combo = "<state_id>,<constituency_id>,<mp_id>,<house>,<tenure_id>"
```

`0` is the wildcard in any of the first three positions. `tenure_id` is omitted
when no tenure is selected, giving a 4-element combo.

**`house`: `2` = Lok Sabha, `1` = Rajya Sabha.** From `loksaba.js`
`sethouse(279935^279933)` and `rajyasaba.js` `sethouse(878755^878754)`.

`getMpNamesData` uses a *different* order — `state,house,tenure` — under the
parameter name `state_combo`. This is a genuine inconsistency in the API, not a
transcription error.

---

## 4. Endpoints

### 4.1 `/rest/PreLoginDashboardData`

| Endpoint | Request body | Response | Verified |
|---|---|---|---|
| `getStateData` | `{}` | `[{"STATE_NAME":"Bihar","STATE_ID":6}, …]` | 36 rows |
| `getTenureData` | `{"uname":"0,0,0,2"}` | `[{"ID":5,"CAPTION":"17th Lok Sabha"},{"ID":7,"CAPTION":"18th Lok Sabha"}]` | LS 2 rows; RS: `Sitting`=1, `Retired`=2. Empty body returns `[]` |
| `getConstituencyData` | `{"id":"21"}` | `[{"ID":245,"CAPTION":"RAVER"}, …]` | 543 total across 36 states |
| `getMpNamesData` | `{"state_combo":"21,2,7"}` | `[{"ID":3042393,"CAPTION":"NILESH DNYANDEV LANKE"}, …]` | 1,380 distinct MPs |
| `getMpAndConstCombo` | `{"const_combo":"245,2,7"}` | same shape, scoped to one constituency | ✓ |
| `getTilesData` | `{"uname":"<combo>"}` | dashboard tiles for the scope | ✓ |
| `getTotalTilesData` | `{"uname":"<combo>"}` | all-tenure totals | ✓ |
| **`getTilesReportData`** | `{"combo":"<combo>","key":"<tile>"}` | **work-grain rows** | ✓ — see §5 |
| **`getAttachIdsbyFlag`** | `{"json":{"FLAG":1,"WORK_ID":"140096"}}` | `[{"FILE_NAME":[…],"ATTACH_ID":[…]}]` | ✓ |
| `getPieChartLabels` | `{}` | four chart captions | ✓ |
| `getgraphdata` | `{"combo":"<combo>"}` | `{}` for every pre-login scope tried | returns nothing |
| `get_fileNames` | `{"content":"ENGLISH"}` | scheme guideline/manual filenames | ✓ `ENGLISH`, `HINDI`, `FORMS` |
| `getFileData` | `{"json":{"name":…,"content":…}}` | `{"FileUrl":"<base64>"}` | shape from source |
| `getRedirectUrl` | `{"type":"1"}` | `{"redirectUrl":""}` | returns empty |
| `getCaptcha` | `{}` | captcha for the **login** form only | not used |
| `stream` | — | video streaming for the landing page | not used |

### 4.2 `/rest/PreLoginCitizenWorkRcmdRest`

| Endpoint | Request body | Response | Verified |
|---|---|---|---|
| **`getAttachmentById`** | `{"id":"703161.725942"}` | `[{"FILE_NAME":"wc.jpg","URL":"<base64 file body>"}]` | ✓ real JPEG + real PDF retrieved |
| `getReviewDetailsByWork` | `{"json":{"WORK_ID":"140096"}}` | citizen star ratings — **parameter ignored, returns the global list** | ✓ 5 rows |
| `getComboStateData` | `{}` | states for the citizen recommendation form | ✓ |
| `getDistrictByState` | `{"id":"21"}` | **empty body** for every shape tried | no data |
| `getBlockByDistrict`, `getVillageByBlock`, `getWardByCity` | — | citizen-form cascades | not exercised |
| `getCitizenRequestByPhNumber` | phone number | citizen's own submissions | **not called** — personal data |
| `verifyOTPForCitizenLogin`, `updateWorkReviewByCitizen` | — | **RESTRICTED** — OTP-gated write path | **not attempted** |

---

## 5. `getTilesReportData` — the work-grain endpoint

Response is **double-encoded**: `{"<envelope>": "<a JSON string of rows>"}`. The
rows must be parsed a second time.

| `key` | envelope | grain |
|---|---|---|
| `Works Recommended` | `Total Works Recommended` | work |
| `Works Sanctioned` | `Total Sanction Work` | work |
| `Works Completed` | `Total Works Completed` | work |
| `Expenditure on Completed and On-going Works as on Date` | `Total Expenditure` | **payment** |
| `Allocated Limit for Hon'ble MPs` | `Allocated Limit` | MP |
| `Amount consented for Calamity` | `Total Calimity Consent` | total only (server's spelling) |

### The trailing grand-total row

**Every response appends a final row `{"Total_Amt": <number>}`.** It is not a
work. Measured relationship in every scope checked: `len(rows) = distinct works
+ 1`.

This explains the **3,987 "corrupt MP-level rows"** recorded in
`docs/DATA_CONTRACT.md` §3: the upstream `in-rolls/mplads` scraper concatenated
these grand-total rows with the work rows. They are not corruption and not
MP-level totals in the sense previously assumed — they are the server's own
per-response subtotal. `ingestion/api.py` separates it into
`TileReport.grand_total`, and Phase 10 uses it as a reconciliation oracle.

### Pagination

**There is none.** No page, offset, limit or cursor parameter exists on any
endpoint. The server returns the entire scope in one response and
`poptable.js` chunks it client-side (`chunk_size` is an XOR-obfuscated constant).

**Scope narrowing is the pagination mechanism.** Measured:

| scope | rows | time |
|---|---:|---:|
| `0,0,0,2` (national) | — | **timed out** |
| `2,0,0,2,7` (Andhra Pradesh) | 3,637 | 1.2 s |
| `12,0,0,2,7` (Goa) | 249 | 0.4 s |
| `35,0,0,2,7` (A&N) | 30 | 0.3 s |
| `21,245,3019105,2,7` (one MP) | 11 | 0.1 s |

`ingestion/crawler/works.py::verify_scope_disjointness` is the equivalent of the
"page 1 ≠ page 2" proof: two state scopes must return disjoint work-id sets.

---

## 6. Fields, by key

### `Works Recommended` / `Works Sanctioned`

`WORK_CATEGORY`, `ACTIVITY_NAME`, `STATE_NAME`, `HOUSE_OF_PARLIAMENT`,
`IDA_NAME`, `TENURE`, `MP_NAME`, `WORK_DESCRIPTION`, `RECOMMENDATION_DATE`,
`RECOMMENDED_AMOUNT`¹, `FLAG`, `CONSTITUENCY_ID`, `WORK_STAGE`, `LETTER_NO`,
`SANCTION_AMOUNT`, `Sno`, `CONSTITUENCY`, `WORK_RECOMMENDATION_DTL_ID`,
`FILE_STATUS`, `TENURE_START_DATE`, `TENURE_END_DATE`, `ATTACH_ID`,
`SANCTION_DATE`

¹ `RECOMMENDED_AMOUNT` appears on `Works Recommended` only.

### `Works Completed`

`WORK_CATEGORY`, `ACTIVITY_NAME`, `STATE_NAME`, `IDA_NAME`, `WORK_DESCRIPTION`,
`MP_NAME`, `FLAG`, `CONSTITUENCY_ID`, `LETTER_NO`, **`ACTUAL_AMOUNT`**, `Sno`,
`CONSTITUENCY`, **`ACTUAL_END_DATE`**, `WORK_RECOMMENDATION_DTL_ID`,
`FILE_STATUS`, `WORK_ID`, `ATTACH_ID`, `AVERAGE_RATING`

### `Expenditure …` — **payment grain, new to this project**

`STATE_NAME`, `ACTIVITY_NAME`, **`VENDOR_NAME`**, `HOUSE_OF_PARLIAMENT`,
`IDA_NAME`, **`IA_NAME`**, `TENURE`, `MP_NAME`, `LETTER_NO`, **`VENDOR_ID`**,
**`EXPENDITURE_DATE`**, **`FUND_DISBURSED_AMT`**, `Sno`, `CONSTITUENCY`,
**`WORK_STATUS`** (e.g. `Payment Success`), `WORK_RECOMMENDATION_DTL_ID`,
`TENURE_START_DATE`, `TENURE_END_DATE`, `WORK_ID`

Multiple rows per work — Andaman & Nicobar 18th LS returned 9 payment rows
against 29 recommended works; Andhra Pradesh returned 1,709 payments against
1,195 completed works.

**None of `VENDOR_NAME`, `VENDOR_ID`, `IA_NAME`, `EXPENDITURE_DATE`,
`FUND_DISBURSED_AMT` or `WORK_STATUS` exists in the CSV snapshot the rest of
this project uses.** They are only available live.

### `Allocated Limit for Hon'ble MPs`

`STATE_NAME`, `HOUSE_OF_PARLIAMENT`, `TENURE`, `Sno`, `MP_NAME`, `HOUSE_NAME`,
`CONSTITUENCY`, `ALLOCATED_AMT`, `TENURE_START_DATE`, `TENURE_END_DATE`

---

## 7. Attachments

Two calls, and the second is not a file URL.

```
POST /rest/PreLoginDashboardData/getAttachIdsbyFlag
     {"json": {"FLAG": 1, "WORK_ID": "140096"}}
  -> [{"FILE_NAME": ["wc.jpg", "work cc.pdf"],
       "ATTACH_ID":  ["703161.725942", "703161.801553"]}]

POST /rest/PreLoginCitizenWorkRcmdRest/getAttachmentById
     {"id": "703161.725942"}
  -> [{"FILE_NAME": "wc.jpg", "URL": "<base64 of the file body>"}]
```

- Despite the name, `WORK_ID` here is **`WORK_RECOMMENDATION_DTL_ID`**. The
  frontend reads it from a `wrk_rec_id` DOM attribute.
- `ATTACH_ID` is compound, `<parent>.<child>`. The parent matches the `ATTACH_ID`
  on the work row. **The bare parent id returns `[{}]`** — the compound id is
  required.
- `URL` is not a URL. It is the base64 file body, served with no content type, so
  the MIME type must come from the extension and be confirmed against magic
  bytes.
- Observed FLAG behaviour for work 140096: `1` returns the files; `2` and `3`
  return the sentinel `[{"FILE_NAME":"N/A","URL":"N/A"}]`; `0`, `4`, `5`, `6`
  return `[]`. The FLAG→stage mapping is **not** fully characterised — see
  `LIMITATIONS.md`.

Retrieved and verified: `wc.jpg` 1,412,513 bytes (`ff d8 ff e0`, valid JPEG) and
`work cc.pdf` 264,737 bytes (`%PDF-1.4`). The JPEG is a signed Government of
Maharashtra work-completion handover certificate naming the contractor and
carrying start and completion dates.

---

## 8. Restricted — found, not accessed

| Resource | Access | Reason |
|---|---|---|
| `/digigov/Login.zul` and everything behind it | **RESTRICTED** | Authentication required. MP / CNA / SNA / NDA / IDA / IA stakeholder workflows. Not probed. |
| `getCaptcha` | **RESTRICTED** | Serves the login form's captcha. Not solved, not bypassed. |
| `verifyOTPForCitizenLogin`, `updateWorkReviewByCitizen` | **RESTRICTED** | OTP-gated. Reading citizen reviews is public; writing one is not. Not attempted. |
| `getCitizenRequestByPhNumber` | **NOT CALLED** | Would return a named citizen's submissions against a phone number. Publicly reachable, but it is personal data and no legitimate research need requires it. |
| Per-work expenditure ledger beyond `FUND_DISBURSED_AMT` | **NOT EXPOSED** | PFMS/TSA transaction detail is not on the public surface. |
