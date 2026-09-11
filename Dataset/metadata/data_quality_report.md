# MPLADS Data Quality Report

Generated 2026-08-24T16:07:27+00:00 by `python -m mplads_audit.export_package`. Every number below is measured from the current real extract — none is copied from an earlier document.

## 1. Scale

| Measure | Value |
|---|---:|
| Raw stage rows (with a usable key) | 476,781 |
| Work-level rows | 210,987 |
| Unique `work_ref` | 210,987 |
| Duplicate `work_ref` | 0 |
| States / UTs | 36 |
| Constituencies | 545 |
| Implementing agencies | 778 |
| Distinct work descriptions | 187,865 |
| Distinct `activity_name` | 180,700 |
| Distinct `work_category` | 4 |

**There is no district column.** The source carries `CONSTITUENCY` and `IDA_NAME` (a district administration office) but no clean district field, so no district-level statistic is reported anywhere in this package.

## 2. Lifecycle and stage coverage

| Measure | Value |
|---|---:|
| RECOMMENDED stage rows | 210,454 |
| SANCTIONED stage rows | 180,517 |
| COMPLETED stage rows | 85,810 |
| SANCTIONED rows carrying a date | 180,517 |
| Works with a sanction record | 180,357 |
| Works completed | 85,767 |
| Works with amount **and** completion (full lifecycle) | 85,525 |
| Works completed with **no** sanction record | 70 |
| Open works | 125,220 |

The sanction stage has **no date at all** in the source. Any conformance check on sanction *timing* is therefore impossible; only sanction *presence* is testable.

## 3. Amounts

| Measure | Value |
|---|---:|
| `recommended_amount` null | 0.329% |
| Non-positive amounts dropped at load | 6 |
| Negative amounts remaining | 0 |
| Median | Rs 315,000 |
| 99th percentile | Rs 3,500,000 |
| Maximum | Rs 75,742,166 |

### `actual_amount` is NOT expenditure

| Measure | Value |
|---|---:|
| Completed works with both amounts | 85,525 |
| `actual_amount` exactly equal to `recommended_amount` | 84,111 |
| Works where the two differ | 1,414 |
| Ratio range | 0.679822 to 1.000011 |
| Ratio above 1.05x | 0 |
| Ratio above 1.5x | 0 |

**Correction to earlier project documents.** `docs/DATA_ACQUISITION_REPORT.md` and `docs/PROJECT_CONSTITUTION.md` state that the two amounts are identical for '85,524/85,525' completed works. Measured on this extract that is not exact: 84,111 of 85,525 are exactly equal and 1,414 differ. The conclusion is unchanged and if anything stronger: the ratio never exceeds 1.000011, so there is no cost-overrun signal whatsoever, and the small downward variance is not an independent measurement of spending.

There is **no independent expenditure figure** in public MPLADS data. Cost-overrun, payment-tranche and utilisation analyses are impossible here and are not attempted.

## 4. Dates

| Measure | Value |
|---|---:|
| Recommendation date parse failures | 0.329% |
| Earliest recommendation | 2019-05-23 |
| Extract as-of (max recommendation date) | 2026-05-26 |
| Back-dated rows (completion before recommendation) | 1,191 |
| Future/out-of-window dated rows | 9 |
| Completed works whose delay was nulled for bad dates | 1,442 |

## 5. Durations and censoring

| Measure | Value |
|---|---:|
| Rows usable for survival | 209,092 |
| Events observed (completions) | 84,325 |
| Right-censored (still open) | 124,767 |
| Median delay of completed works | 401 days |
| Longest open duration | 2,560 days |

## 6. Peer groups

| Measure | Value |
|---|---:|
| Works placed in a peer group | 209,929 (99.5%) |
| Distinct peer groups | 1,457 |
| Median peer group size | 282 |
| Archetypes | 50 |

## 7. Signal firing and triage bands

| Signal | Works fired |
|---|---:|
| `peer_amount` | 1,010 |
| `peer_delay` | 255 |
| `peer_stall` | 254 |
| `conformance` | 1,270 |
| `completion_risk` | 6,238 |
| `change_point` | 18,545 |
| `iforest` | 2,110 |

| Confidence band | Works |
|---|---:|
| NONE | 183,036 |
| LOW | 26,317 |
| MEDIUM | 1,580 |
| HIGH | 54 |

A band is **corroboration count, not certainty of wrongdoing**. HIGH means three or more independent signal families agree that the work is unusual.

## 8. Known defects found and handled

Each was measured on this extract, not assumed:

1. **`WORK_ID` is unusable as an identifier.** It is populated only on COMPLETED stage rows (0% on Recommended/Sanctioned), so it is null for every open work. The package keys on `work_ref` = `MP<mp_id>-W<rec_dtl_id>`, which is unique (0 duplicates).
2. **Non-positive amounts.** 6 rows with `RECOMMENDED_AMOUNT <= 0` are dropped at load. They remain present in `raw/` and in `processed/mplads_lifecycle_events.csv`, so nothing is lost.
3. **Back-dated lifecycle rows.** 1,191 works record a completion date before their recommendation date. They are flagged (`is_backdated`), their `delay_days` is nulled so they cannot corrupt the survival fit, and they raise the conformance signal as a data-quality lead.
4. **Out-of-window completion dates.** 9 rows carry completion dates after the extract (e.g. 2034, 2044). Because the censoring anchor was originally the maximum of *all* dates, these typos inflated every open work's duration to roughly 19 years. The anchor is now the maximum **recommendation** date (2026-05-26), and such rows are flagged `is_future_dated`.
5. **`ACTUAL_AMOUNT` is not expenditure** (section 3). Never compute overrun from it.
6. **Round-number bunching breaks a plain MAD.** In one 479-work peer group, 194 works share exactly Rs 6.25L, collapsing the MAD to Rs 5,000 and giving a 79th-percentile work a robust-z of 10. The peer scale is now `max(MAD, IQR/1.349)` plus a 98th-percentile gate.
7. **Change-point detection was reading the calendar.** Completion rate and delay are censoring-contaminated: recent quarters look 'changed' only because their works have not had time to finish. The change-point vector now uses only features fixed at recommendation time; the contaminated columns remain as reviewer context.
8. **The temporal holdout leaked the future.** It fitted on durations observed through the end of the extract while claiming to stand at the cutoff, producing predicted 0.83 vs actual 0.13 in the top band. It now rebuilds the data as it looked on the cutoff date; holdout C-index 0.742 on n=84,593.
9. **Signal gates.** Un-gated, `completion_risk` (P<0.5) and `change_point` (any positive score) fired on over 90% of the portfolio, making the confidence bands meaningless. Both are now tail-gated (bottom 5% / top decile).
10. **`vonter_mplads_recommendations_raw.csv` is unused** by every phase. It is preserved with full provenance but feeds nothing.

## 9. Missingness by column (work-level)

| Column | Null % |
|---|---:|
| `mp_tenure` | 87.255% |
| `attach_id` | 64.185% |
| `delay_days` | 60.033% |
| `work_id` | 59.35% |
| `actual_amount` | 59.35% |
| `average_rating` | 59.35% |
| `completion_date` | 59.35% |
| `duration_days` | 0.898% |
| `work_description` | 0.488% |
| `archetype_id` | 0.488% |
| `archetype_label` | 0.488% |
| `work_category` | 0.359% |
| `mp_name` | 0.329% |
| `house` | 0.329% |
| `state_name` | 0.329% |
| `constituency_name` | 0.329% |
| `implementing_agency` | 0.329% |
| `activity_name` | 0.329% |
| `recommended_amount` | 0.329% |
| `recommendation_date` | 0.329% |
| `financial_year` | 0.329% |
| `scale_bucket` | 0.329% |
| `work_ref` | 0.0% |
| `rec_dtl_id` | 0.0% |
| `mp_id` | 0.0% |
| `is_sanctioned` | 0.0% |
| `is_completed` | 0.0% |
| `event_observed` | 0.0% |
| `is_backdated` | 0.0% |
| `is_future_dated` | 0.0% |
| `work_status` | 0.0% |

## 10. What this report does NOT establish

No fraud labels exist in any public MPLADS source. Nothing here measures fraud prevalence, fraud accuracy, or the guilt of any state, constituency, agency or MP. Every flagged record is an **investigation lead**.

