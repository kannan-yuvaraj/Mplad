# MPLADS Data Lineage

Complete trace from government source to audit plan. Every stage lists its input, output,
transformation, code file, assumptions, and the ways it can fail.

Failure modes marked **(HAPPENED)** are defects that actually occurred in this codebase and
were fixed — documented so the next engineer does not reintroduce them.

```
SOURCE (eSAKSHI / MPLADS portals)
  ↓  0. ACQUISITION                  fetch_raw.py
RAW DATA                             data/raw/*.csv                  REAL
  ↓  1. CLEANING + WORK-LEVEL JOIN   load_real.py
PROCESSED                            data/processed/*.csv            DERIVED FROM REAL
  ↓  2. ARCHETYPE DISCOVERY          archetypes.py
        →                            data/models/archetype/*         MODEL ARTIFACT
  ↓  3. FEATURE ENGINEERING          peer_anomaly.py
  ↓  4. SURVIVAL MODEL               survival.py
  ↓  5. BEHAVIOURAL ANALYSIS         entities.py
  ↓  6. RISK FUSION → TRIAGE         case_file.py
  ↓  7. AUDIT OPTIMIZATION           targeting.py
OUTPUTS                              data/outputs/*.csv              MODEL OUTPUT
```

The whole chain is re-executed by `python -m mplads_audit.export_package`.

---

## Stage 0 — Acquisition

| | |
|---|---|
| **Input** | Public GitHub mirrors of MPLADS/eSAKSHI reporting tables |
| **Output** | `data/raw/esakshi_stagewise_works_{ls17,ls18,rs}_raw.csv`, `data/raw/vonter_mplads_recommendations_raw.csv`, `data/raw/original_archives/*.tar.gz` |
| **Transformation** | Download, extract, rename to descriptive filenames. **No content change.** |
| **Code** | `mplads_audit/fetch_raw.py` |

**Assumptions**

- The mirrors faithfully reproduce the official portal tables (in-rolls publishes its scraper).
- Files are already public; no authentication is used or bypassed.

**Failure modes**

- Upstream repositories could move, change schema, or disappear — the SHA-256 of each file
  is recorded in `raw_sources.json`, so drift is detectable.
- in-rolls declares **no licence**. The safe reproduction path is running its scraper
  against the official portal and attributing MPLADS/MoSPI.
- The extract is a **point-in-time snapshot** (as-of 2026-05-26). Every censored duration
  and every "still open" statement is relative to that date.

---

## Stage 1 — Cleaning and work-level join

| | |
|---|---|
| **Input** | The three eSAKSHI stage files — 480,768 rows, one row per **work-stage** |
| **Output** | `data/processed/mplads_work_level.csv` (210,987 × 31), `mplads_lifecycle_events.csv` (476,781 × 7), `works_clean.parquet` (cache) |
| **Transformation** | Drop null-key rows → split by `tile_label` → dedupe per stage → outer-join on `(WORK_RECOMMENDATION_DTL_ID, mp_id)` → rename → coerce types → derive lifecycle flags, durations, censoring, `work_ref` |
| **Code** | `mplads_audit/load_real.py` (`build`), `export_package.py` (`work_level`, `lifecycle_events`) |

**Row accounting** — every row is accounted for, nothing silently disappears:

| Step | Rows |
|---|---:|
| Raw stage rows (3 files) | 480,768 |
| − null join key | −3,987 |
| = stage rows retained (`mplads_lifecycle_events.csv`) | 476,781 |
| Distinct works after pivot | 210,993 |
| − `recommended_amount <= 0` | −6 |
| **= canonical work-level rows** | **210,987** |

**Assumptions**

- `(WORK_RECOMMENDATION_DTL_ID, mp_id)` uniquely identifies a work. Verified: 0 duplicate
  `work_ref`.
- Where a stage repeats for one key, the **earliest recommendation row** is authoritative
  (`sort_values → drop_duplicates(keep="first")`).
- Absence of a `Works Sanctioned` row means "no sanction recorded", not "not sanctioned".
- The extract as-of date is the **maximum recommendation date**, not the maximum of all dates.

**Failure modes**

- **(HAPPENED) Censoring anchor poisoned by date typos.** The anchor was originally
  `max(all dates)`; nine completion dates typed 2034/2044 pushed it decades out and every
  open work's duration inflated to ~19 years. Fixed by anchoring on recommendation dates
  only. Regression-tested in `load_real._self_check`.
- **(HAPPENED) `WORK_ID` used as the identifier.** It is populated only on Completed rows,
  so it was 100% null for open works. Fixed by `work_ref`; asserted unique in the self-check.
- Deduplication `keep="first"` silently discards later stage rows for the same key — they
  survive in `mplads_lifecycle_events.csv`, which is why that file exists.
- 0.33% of amounts and dates are null; downstream code must not assume completeness.

---

## Stage 2 — Archetype discovery

| | |
|---|---|
| **Input** | 187,865 unique `work_description` strings |
| **Output** | `data/models/archetype/{desc_embeddings.npz, archetypes.parquet, archetypes_map.parquet, archetype_catalog.csv}`, `data/features/archetype_features.csv` |
| **Transformation** | MiniLM embeddings (384-d, `max_seq_length=64`) → `MiniBatchKMeans` over K ∈ {20,30,40,50,60,80} → silhouette selects **K=50** → labels from share × log-lift phrases |
| **Code** | `mplads_audit/archetypes.py` |

**Assumptions**

- Descriptions are informative enough to define work types.
- Cosine geometry over MiniLM embeddings approximates "same kind of work".
- Truncating at 64 tokens (p90 = 61) discards only trailing address text.

**Failure modes**

- **Silhouette is ~0.04–0.05 at every K** — the metric barely discriminates, so K=50 is a
  weak optimum and cluster quality genuinely rests on manual coherence review.
- **~4 of 50 clusters are language artifacts** (transliterated Hindi/Gujarati grouped by
  script rather than work type). They still form valid peer groups, just coarser ones.
- **(HAPPENED) Labels named villages, not work types.** Scoring purely by lift made rare
  proper nouns win (`hesarghatta / thanamakua / donekal`). Fixed by weighting by in-cluster
  share with a 3% floor.
- **Cluster ids are not stable** across scikit-learn versions or thread counts — partitions
  are stable, integer labels may permute. Never hard-code an `archetype_id`.
- 1,029 works have no usable description and remain unassigned (`archetype_id` null); they
  fall through to no peer group.

---

## Stage 3 — Peer-conditional features

| | |
|---|---|
| **Input** | Work-level table + `archetype_id` |
| **Output** | `data/features/triage_features.csv` (peer context + signal scores) |
| **Transformation** | Peer key `(archetype, state, scale_bucket)`, floor 30, backing off to `(archetype, state)` then `(archetype)` → leave-one-out median and percentile → robust z against `max(MAD, IQR/1.349)` → score = `min(z-ramp, percentile-ramp above 0.98)` |
| **Code** | `mplads_audit/peer_anomaly.py` |

Coverage: 209,929 of 210,987 works (99.5%) land in a peer group; 1,457 distinct groups,
median size 282.

**Assumptions**

- A work is only comparable to works of its own archetype, state, and scale band.
- 30 members is enough for a stable median/percentile.
- Only the **high side** is of interest (unusually large / slow, never small / fast).

**Failure modes**

- **(HAPPENED) MAD collapse under round-number bunching.** 194 of 479 works in one group
  sat at exactly ₹6.25L, driving MAD to ₹5,000 and giving a 79th-percentile work a z of 10.
  Fixed with the IQR floor plus the percentile gate; firings fell 7,619 → 1,010.
- Leave-one-out is exact for the median and percentile but the **scale is whole-group** — an
  outlier inflates its own scale, making its z conservative. Exact LOO MAD is O(n²) per group.
- Back-off means two works can be compared against different-sized peer sets; `peer_group`
  and `peer_n` record which was used.

---

## Stage 4 — Completion-risk (survival)

| | |
|---|---|
| **Input** | `duration_days`, `event_observed`, `entry_days`, `log_amount`, `is_sanctioned`, archetype/state dummies (209,092 rows) |
| **Output** | `data/features/completion_risk_features.csv`, `data/outputs/completion_risk_scores.csv`, `exposure_by_state.csv`, `data/metadata/completion_risk_calibration.csv` |
| **Transformation** | Cox PH (`penalizer=0.1`, 60k sample, `random_state=0`) with left-truncated entry → conditional survival `1 − S(t+365)/S(t)` → `rs_exposure = amount × (1 − p)` |
| **Code** | `mplads_audit/survival.py` |

Measured: C-index 0.6924 (full fit), 0.7425 (holdout training window, n=84,593).

**Assumptions**

- Proportional hazards holds well enough for ranking (this is **not** formally tested).
- eSAKSHI coverage starts 2023-04-01; earlier works enter the risk set then (left truncation).
- Completion is observed reliably when it happens.
- The baseline survival curve can be extrapolated 365 days beyond the observed duration.

**Failure modes**

- **(HAPPENED) Temporal holdout leaked the future** — fitted on durations observed through
  the end of the extract while claiming to stand at the 2024-07-01 cutoff; predicted 0.83 vs
  actual 0.13 in the top band. Now the data is rebuilt as it looked on the cutoff date.
- **Over-confidence in the sparse top band** (561 works, predicted 0.41 vs actual 0.27) —
  unresolved.
- **Collinear design matrices** cause `ConvergenceError` if a covariate is perfectly
  determined by another (seen on a fixture). The penalizer mitigates but does not eliminate it.
- `rs_exposure` is risk × amount by construction. It is **exposure, not loss**; presenting
  it as money lost would be a factual misstatement.

---

## Stage 5 — Behavioural fingerprint and change-point

| | |
|---|---|
| **Input** | Work-level rows grouped by `implementing_agency` × quarter |
| **Output** | `data/features/behavioral_features_entity_quarter.csv` (6,179 rows), `data/outputs/entity_change_points.csv` (448 agencies) |
| **Transformation** | Quarterly behaviour vector → drop partial final quarter → binary segmentation (max-t) → Jensen-Shannon divergence of archetype mix → `change_score = √(rank(t) × rank(JS))` |
| **Code** | `mplads_audit/entities.py` |

**Assumptions**

- The implementing district authority is the meaningful actor.
- A quarter with ≥5 works characterises behaviour; ≥6 quarters are needed for a split.
- Only recommendation-time features may drive detection.

**Failure modes**

- **(HAPPENED) The detector was reading the calendar.** With `completion_rate` and
  `median_delay` in the vector, every agency "shifted" at the recent edge purely because
  recent works had not had time to finish. Fixed by restricting the vector to
  recommendation-time features; regression-tested with a pure-censoring fixture.
- A change point has **innocent explanations** — a new officer, a revised guideline, a
  scheme-wide policy change. It is a lead, never a cause.
- `change_score` is a **within-cohort rank**: it says "changed more than other agencies",
  not "changed a lot in absolute terms".

---

## Stage 6 — Risk fusion and triage

| | |
|---|---|
| **Input** | All signal scores from stages 3–5 plus conformance rules and an IsolationForest cross-check |
| **Output** | `data/outputs/triage_results.csv` (210,987 × 18) |
| **Transformation** | `priority = 1 − Π(1 − wᵢ·sᵢ)`; confidence = count of independent signal **families** |
| **Code** | `mplads_audit/case_file.py` |

**Assumptions**

- The weights are transparent, hand-set knobs — **not learned** (there are no labels to
  learn them from).
- Signals within a family are not independent evidence (`peer_stall` and `completion_risk`
  read the same clock).
- Only tail behaviour is a signal.

**Failure modes**

- **(HAPPENED) Ungated signals flagged 92% of the portfolio.** `completion_risk` fired on
  any work below P=0.5 (the median is 0.30) and `change_point` on any positive score, making
  the confidence bands meaningless. Both are now tail-gated (bottom 5% / top decile),
  producing NONE 183,036 / LOW 26,317 / MEDIUM 1,580 / HIGH 54.
- Noisy-OR assumes conditional independence between families — only approximately true.
- Weight changes reorder the queue; there is no labelled set to validate them against, only
  the synthetic ablation in `validate.py`.
- **A high priority is not evidence of wrongdoing.** Every row carries `not_a_fraud_finding`.

---

## Stage 7 — Audit-ROI optimization

| | |
|---|---|
| **Input** | `priority`, `n_families`, `rs_exposure`, `state_name`, `constituency_name` |
| **Output** | `data/outputs/audit_plan.csv` (238 works), `audit_plan_baselines.csv` |
| **Transformation** | Greedy selection on value-per-marginal-cost under a 100 auditor-day budget; 1.0 day opens a travel cluster, 0.25 day per further work in it |
| **Code** | `mplads_audit/targeting.py` |

**Assumptions**

- **100 auditor-days** is a demo assumption, not an official capacity figure.
- The 1.0 / 0.25 cost split is a **modelling assumption** about travel, not measured.
- Greedy is good enough; an exact solver adds nothing a judge can read.

**Failure modes**

- **(HAPPENED) Rajya Sabha works merged into one travel cluster.** All RS works carry the
  constituency `"Sitting Rajya Sabha"`, so keying on constituency alone let an auditor hop
  from Andhra Pradesh to Punjab for a quarter-day. Fixed by keying on state + constituency.
- Greedy is not optimal; it can be beaten by a solver on a crafted instance.
- The plan inherits every upstream bias — if the peer groups or the survival model are
  wrong, the plan sends auditors to the wrong places.
- **The plan is a recommendation.** Humans approve audits.

---

## Cross-cutting: REAL vs DERIVED vs MODEL OUTPUT vs SYNTHETIC

| Layer | Classification | Rule |
|---|---|---|
| `data/raw/` | **REAL** | Never modified. |
| `data/processed/` | **DERIVED FROM REAL** | Deterministic cleaning + join only. |
| `data/features/` | **DERIVED FROM REAL** | Deterministic transformations of processed data. |
| `data/models/` | **MODEL ARTIFACT** | Fitted/cached; reproducible from features given seeds. |
| `data/outputs/` | **MODEL OUTPUT** | Predictions and rankings. Leads, never fraud findings. |
| `data/synthetic/` | **SYNTHETIC** | Generated. **Never** government data, never mixed into the real pipeline. |

The synthetic layer is used only by `generate_data.py`, `engine.py`, `photo_reuse.py` and
`validate.py`. No synthetic row enters any file under `processed/`, `features/`, or
`outputs/`.
