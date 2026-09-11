# Data Package Validation

Result of the post-build quality check. **27 checks run, 27 passed, 0 failed.**
The package was rebuilt from source immediately before this validation, and the full test
suite (`pytest -q`) passed: **12 passed**.

---

## 1. What was checked and the result

### File integrity

| Check | Result |
|---|---|
| All 13 exported files open and parse | **pass** |
| SHA-256 recorded for every exported file | **pass** (`package_manifest.json`) |
| SHA-256 recorded for every raw source file | **pass** (`raw_sources.json`) |
| Total exported volume | 330.6 MB across 13 files |

### Row counts

| Check | Expected | Measured | Result |
|---|---:|---:|---|
| Work-level rows | 210,987 | 210,987 | **pass** |
| Lifecycle event rows | 476,781 | 476,781 | **pass** |
| Raw row accounting (480,768 − 3,987 null-key) | 476,781 | 476,781 | **pass** |
| `work_ref` duplicates | 0 | 0 | **pass** |
| Archetype catalog clusters | 50 | 50 | **pass** |
| Works with an archetype | 209,958 | 209,958 | **pass** |
| Cox feature rows | 209,092 | 209,092 | **pass** |
| Audit plan works | 238 | 238 | **pass** |

**No source data was lost.** Every raw stage row is either present in
`processed/mplads_lifecycle_events.csv` or accounted for by the 3,987 null-key exclusions;
the 6 works dropped for non-positive amounts remain in both `raw/` and the events file.

### Joins

| Check | Result |
|---|---|
| `archetype_features` joins 1:1 to work-level | **pass** |
| `triage_features` joins 1:1 to work-level | **pass** |
| `triage_results` joins 1:1 to work-level | **pass** |
| `completion_risk_features` is a subset of work-level `work_ref` | **pass** (209,092 of 210,987) |
| `completion_risk_scores` is a subset of work-level `work_ref` | **pass** |
| `audit_plan` is a subset of work-level `work_ref` | **pass** |
| `behavioral_features_entity_quarter` agencies within work-level agencies | **pass** |
| `entity_change_points` agencies within work-level agencies | **pass** |

Every feature and output row traces back to a canonical work or agency. No orphans.

### Temporal leakage

| Check | Result |
|---|---|
| No `post_completion` column is marked `recommendation_time` | **pass** (empty intersection) |
| The Cox feature file contains no `post_completion` column | **pass** (empty intersection) |
| Every column carries a temporal-availability verdict | **pass** (enforced in `export_package._self_check`) |

The two leaks previously found in this codebase — the holdout fitted on post-cutoff
durations, and completion-derived features driving change-point detection — are both fixed
and carry regression tests. See `DATA_LINEAGE.md` stages 4 and 5.

### Documentation coverage

| Check | Result |
|---|---|
| Every exported column appears in the data dictionary | **pass** (empty difference) |
| Dictionary entry count | **pass** (104) |

This is enforced structurally, not merely verified: `export_package._write()` raises
`KeyError` and aborts the build if any emitted column lacks a dictionary entry.

### Claim discipline

| Check | Result |
|---|---|
| `triage_results.csv` carries the non-fraud contract on every row | **pass** (210,987 rows) |
| No column is named or described as a fraud score | **pass** |
| No synthetic work id appears in any real output | **pass** |

### Metrics reproduced against the Phase 1–7 runs

| Metric | Phase run | Package | Result |
|---|---|---|---|
| Holdout C-index | 0.742 | 0.7425 | **pass** |
| National exposure | ₹5,219 cr | ₹5,218.7 cr | **pass** |
| Audit plan | 238 works / 54 clusters | 238 / 54 | **pass** |
| Plan > largest-amount-first > random | yes | yes | **pass** |
| Confidence bands | 183,036 / 26,317 / 1,580 / 54 | identical | **pass** |

---

## 2. Discrepancies discovered

### 2.1 `ACTUAL_AMOUNT` identity figure in earlier project documents — **corrected here**

`docs/DATA_ACQUISITION_REPORT.md` §1/§1a and `docs/PROJECT_CONSTITUTION.md` §3.2 state that
`ACTUAL_AMOUNT` equals `RECOMMENDED_AMOUNT` for **85,524 of 85,525** completed works.

Measured on this extract:

| Measure | Value |
|---|---:|
| Completed works with both amounts | 85,525 |
| Exactly equal | **84,111** |
| Differing | **1,414** |
| Ratio range | **0.6798 – 1.00001** |
| Ratio above 1.05× | **0** |

The specific figure in those documents is wrong. **The conclusion is unchanged and slightly
stronger:** the ratio never meaningfully exceeds 1.0, so there is no cost-overrun signal at
all, and the modest downward variance in 416 works is not an independent measurement of
spending. `actual_amount` remains unused by every phase.

The earlier documents were **not edited** — they are dated narrative reports. The measured
version is in `data_quality_report.md` §3 and `../README.md` §9.5.

### 2.2 Back-dated row count differs from earlier documents

Earlier documents report **1,194** negative-delay rows; this package measures **1,191** at
the work level. The difference comes from the 6 non-positive-amount works dropped before
the flag is computed, and from counting distinct works rather than raw stage rows. Not a
defect; the handling (flag, null the delay, feed the conformance signal) is unchanged.

### 2.3 Stage row counts differ from earlier documents

Earlier documents report Recommended 211,784 / Sanctioned 181,846 / Completed 87,138. This
package reports 210,454 / 180,517 / 85,810. The difference is the **3,987 null-key rows**
excluded before stage counting. Both are correct for what they count; the package figures
are the ones that reconcile with the work-level table.

### 2.4 One test broke during the reorganisation — **fixed**

`load_real._self_check` wrote its fixture as `works_rs.csv`, which no longer matches
`config.RAW_STAGE_FILES` after the rename. The fixture now derives its filename from
`RAW_FILES[-1]`. Caught by `pytest`, fixed, re-run: **12 passed**.

---

## 3. Unresolved issues

Carried forward deliberately, not silently:

1. **Completion-risk is over-confident in its sparse top band** — predicted 0.41 vs actual
   0.27 on 561 works. The two large bands are well calibrated.
2. **Silhouette barely discriminates K** (~0.04–0.05 across the whole grid). K=50 is a weak
   optimum; cluster quality rests on manual coherence review.
3. **~4 of 50 archetypes are language/script artifacts** rather than work types.
4. **The proportional-hazards assumption is not formally tested** — no Schoenfeld residual check.
5. **Fusion weights are hand-set** and cannot be validated against real outcomes (no labels).
   Only the synthetic ablation in `validate.py` supports them.
6. **Cluster ids are not stable** across scikit-learn versions or thread counts — partitions
   are stable, integer labels may permute. Never hard-code an `archetype_id`.
7. **Exact leave-one-out MAD is not implemented** (O(n²) per group); the peer scale is
   whole-group, which makes an outlier's own z conservative.
8. **`docs/` narrative reports contain superseded figures** (§2.1–2.3). They are preserved
   as dated records; this package is the current source of truth.

---

## 4. What this validation does NOT establish

It verifies that the data package is internally consistent, traceable, leak-free by the
declared rules, and reproducible. It does **not** validate that any flagged work is
irregular — no fraud labels exist, so no such validation is possible. Every output remains
an **investigation lead**.
