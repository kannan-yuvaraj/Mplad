# Reverse-engineering findings

Measured against the live portal on **2026-09-10**. Each finding names the
evidence. Anything not measured is in `LIMITATIONS.md` instead.

---

## 1. The portal has a complete public JSON API, and we were not using it

The project's entire dataset comes from `in-rolls/mplads` and
`Vonter/india-mplads-works` — **secondary GitHub mirrors** of a scrape someone
else ran (`Dataset/README.md` §3). The portal exposes the same data directly,
unauthenticated, over a REST API, and exposes **more** of it.

Consequence for the project: we can refresh the snapshot ourselves, we stop
depending on a third party's scrape cadence, and the data provenance chain
shortens from *portal → unknown scraper → GitHub → us* to *portal → us*.

## 2. Three fields we did not have

The `Expenditure on Completed and On-going Works as on Date` key returns
**payment-grain** rows carrying `VENDOR_NAME`, `VENDOR_ID`, `IA_NAME`,
`EXPENDITURE_DATE`, `FUND_DISBURSED_AMT` and `WORK_STATUS`.

`docs/DATA_CONTRACT.md` lists no vendor column anywhere, and the "DO NOT USE"
list exists partly because expenditure could not be measured. It can be, at the
level of individual vendor payments, publicly.

For work 140096: vendor `GopiKrishana Majoor Sahakari Sanstha Ruikheda`,
`VENDOR_ID` 34176, `FUND_DISBURSED_AMT` ₹29,74,718 on 07-Oct-2024, status
`Payment Success`.

## 3. The 3,987 "corrupt rows" are the server's own subtotal

`docs/DATA_CONTRACT.md` §3 drops 3,987 rows with a null
`WORK_RECOMMENDATION_DTL_ID` and treats them as MP-level totals carrying
`Total_Amt`.

**Every `getTilesReportData` response ends with a row `{"Total_Amt": <number>}`.**
It is a per-response grand total, appended by the server for the footer the
DataTable renders. `len(rows) = distinct works + 1` held in every scope measured.

The upstream scraper concatenated one of these per request. The interpretation
in the data contract — "MP-level totals, usable as a reconciliation oracle" — is
functionally right and the reconciliation use is sound; the *origin* is a
response footer, not an MP summary record.

## 4. 17th Lok Sabha data is on the portal

`getTenureData` for the Lok Sabha returns both `17th Lok Sabha` (ID 5) and
`18th Lok Sabha` (ID 7), and `getTilesReportData` returns work rows for tenure 5.

Measured: RAVER constituency, tenure 5 → 96 works. Andaman & Nicobar, tenure 5 →
42 recommended, 20 completed. Arunachal Pradesh, tenure 7 → 298 recommended.

The dashboard's own notice says data for 2019-20 through 2022-23 is **not** on
eSAKSHI because the scheme was paper-based before 1 April 2023, so tenure 5 here
means "17th LS works recorded on eSAKSHI from 2023-24 onward", not the full
17th LS. That is a coverage boundary of the portal itself, and it is the reason
`CURRENT` and `HISTORICAL` must stay separated — see `LIMITATIONS.md` §5.

## 5. Every count reconciles exactly; one amount does not, and we know why

`ingestion.cli validate` over Andaman & Nicobar, Andhra Pradesh and Arunachal
Pradesh (18th LS), 12 checks:

- **Our row count == the published tile count: exact, every check.**
- **Our amount sum == the server's own grand total: exact, every check.**
- **Two mismatches, both on `Works Completed`**, where the published tile amount
  exceeds the drill-down sum.

Investigated rather than left open:

| State | Tile amount | Σ `ACTUAL_AMOUNT` | Σ `SANCTION_AMOUNT` of the same works |
|---|---:|---:|---:|
| Arunachal Pradesh | 179,756,360 | 178,703,990 | **179,756,360** |
| Andhra Pradesh | 624,068,315 | 614,963,823 | **624,068,315** |

**The dashboard's "Works Completed" money tile is the *sanctioned* value of
completed works; the drill-down report is the *actual* value.** The match is
exact to the rupee in both states. This is a definition difference, not an error
in either the portal or our collection — and it is exactly the kind of thing
Phase 10 exists to surface. It is recorded, not corrected.

## 6. `ACTUAL_AMOUNT` varies from sanctioned more than our snapshot suggests

`CLAUDE.md` constraint 4 states that in the CSV snapshot 98.35% of completed
works have `ACTUAL_AMOUNT` exactly equal to `RECOMMENDED_AMOUNT`, and concludes
that no overrun signal exists.

Live, comparing `ACTUAL_AMOUNT` against `SANCTION_AMOUNT` on the same works:

| State | `ACTUAL == SANCTION` |
|---|---|
| Arunachal Pradesh | 215 / 226 = **95.13%** |
| Andhra Pradesh | 972 / 1,195 = **81.34%** |

**This does not overturn constraint 4** and must not be quoted as if it did. It
is two states, a different comparison (sanctioned, not recommended) and the live
portal rather than the snapshot. What it does establish is that the question is
worth re-measuring nationally against fresh data before the "no overrun signal"
conclusion is carried into another release. Every difference observed was a
*saving* (actual below sanctioned), which is consistent with the constraint's
"zero exceed 1.05×" finding.

## 7. Enumeration is small

Measured with `ingestion.cli enumerate`, 0 failures:

| Dimension | Discovered |
|---|---:|
| States / UTs | **36** |
| Constituencies | **543** |
| MPs (distinct) | **1,380** |
| MP rows across state × house × tenure | 1,607 |

`docs/DATA_CONTRACT.md` records **545** constituencies from the snapshot against
543 live. Two constituencies in the snapshot are not currently returned by
`getConstituencyData`. Unexplained; recorded rather than reconciled away.

A full national work-grain crawl is 36 states × 2 houses × ~2 tenures × 5 keys ≈
**720 requests**, each under a second. At the module's default 1 req/s that is
roughly 12 minutes of extremely light load.

## 8. No district dimension exists for works

`getDistrictByState` exists on the citizen controller but returned an empty body
for every parameter shape tried, and **no work-grain endpoint accepts a
district**. `IDA_NAME` is a district *office* name, e.g.
`JALGAON(DISTRICT COLLECTOR JALGAON_IDA)`.

This confirms the existing note in `CLAUDE.md` — "No district column" — against
the live source rather than against the snapshot. The `districts` table in
`ingestion/schemas/schema.sql` is defined but deliberately left unpopulated.

## 9. Documents are real evidence, and richer than the structured data

The completion certificate retrieved for work 140096 is a scanned, signed
Government of Maharashtra handover certificate. Read directly, it carries fields
that appear **nowhere** in any API response:

- contractor: `चेअरमन, गोपीकृष्ण, मजुर सहकारी संस्था मर्या., मु. पो. रुईखेडा`
- work start date 29/02/2024, completion date 11/03/2024
- technical sanction order number and date (प्रशा-2/4972/2023, 09/11/2023)
- the officer who received the asset for maintenance

The API's `ACTUAL_END_DATE` for this work is 11-Sep-2024; the certificate says
the work was completed 11/03/2024. **These disagree.** One is the portal's
"marked complete" timestamp and the other is the physical completion date on the
certificate. Which is which cannot be settled from these two documents alone,
and is not settled here — it is exactly the sort of thing the project's
field-verification loop exists to resolve, and a good argument for extracting
document text with page-level provenance.
