# data/models — what is actually a model, and what is not

Be precise about this when presenting the system. It is **not one AI model**; it is a
composition, and most of it is statistics or transparent rules rather than machine learning.

## What is persisted here

```
models/
└── archetype/                          the only fitted artifact on disk
    ├── desc_embeddings.npz             187,865 texts x 384 float32 MiniLM vectors (cache)
    ├── archetypes.parquet              archetype_id, label, n_unique_descriptions, n_works
    ├── archetypes_map.parquet          work_description -> archetype_id
    └── archetype_catalog.csv           50 x 5, with three example descriptions per cluster
```

`desc_embeddings.npz` is a **cache, not a trained model** — the MiniLM weights come from
Hugging Face and are not modified. Regenerating it costs ~45 minutes of CPU. It is
resumable: the file holds however many vectors are complete, and the next run continues
from there.

## What is trained, computed, or hard-coded

| Stage | Kind | Fitted? | Persisted? |
|---|---|---|---|
| Description embedding | **ML — pretrained, frozen** | no (downloaded) | vectors cached |
| Archetype clustering | **ML — unsupervised** | yes, `MiniBatchKMeans(K=50, seed 0)` | **yes** |
| Peer-conditional anomaly | **Statistics** (robust z, LOO percentile) | no — recomputed | no |
| Completion risk | **Statistical modelling** — Cox PH, censored | yes, at runtime | **no — refitted each run** |
| Entity fingerprint | **Data engineering** (group-by aggregates) | no | no |
| Change-point | **Statistics** (binary segmentation, Jensen-Shannon) | no | no |
| IsolationForest cross-check | **ML — unsupervised** | yes, at runtime | **no — refitted each run** |
| Evidence fusion | **Rules + probability** (noisy-OR, hand-set weights) | **no — weights are knobs, not learned** | weights live in `case_file.WEIGHTS` |
| Audit-ROI targeting | **Optimization** (greedy under a budget) | no | no |

**Only the stages marked ML are ML.** Fusion weights and conformance rules are hand-set and
transparent by design; calling them "AI" would be inaccurate.

## What is NOT trained, and cannot be

There is **no supervised model anywhere in this project**, because there are **no fraud
labels in any public MPLADS source**. No classifier is trained to predict fraud, and none
can be until labelled investigation outcomes exist. Fusion weights are therefore chosen for
interpretability, not learned — a deployment with investigator feedback could learn them.

## Why the Cox model and IsolationForest are not persisted

Both are cheap to refit (seconds to a couple of minutes) and depend on the full current
extract, so a stale pickle would be a liability rather than an asset. They are refitted on
every run with fixed seeds. Their **outputs** are persisted in `../outputs/`, and their
metrics and hyperparameters in `../metadata/run_environment.json`.

If you need a frozen Cox model for serving, add explicit persistence to
`mplads_audit/survival.py` — do not assume one exists.

## Reproducibility notes

- Seeds: archetype clustering `0`, IsolationForest `0`, Cox fit sample `0`.
- **`MiniBatchKMeans` cluster ids are not stable** across scikit-learn versions or thread
  counts. The partitions are stable; the integer labels may permute. Never hard-code an
  `archetype_id` — join through `archetype_catalog.csv` or `archetypes_map.parquet`.
- Versions actually used are recorded in `../metadata/run_environment.json`.
