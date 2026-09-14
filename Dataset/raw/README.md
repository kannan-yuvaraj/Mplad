# data/raw — REAL government data. Do not modify.

Everything in this directory is **REAL** public MPLADS data, preserved exactly as
downloaded: original column names, original values, original row order. Nothing here is
cleaned, deduplicated, internally renamed, or rewritten by any code in this repository.

The pipeline only ever **reads and hashes** these files. If you need a change, create a
derived file under `processed/` and document the transformation — never edit here.

| File | Rows | Cols | Sep | House | Read by the pipeline? |
|---|---:|---:|---|---|---|
| `esakshi_stagewise_works_ls17_raw.csv` | 242,358 | 31 | `,` | 17th Lok Sabha | **yes** |
| `esakshi_stagewise_works_ls18_raw.csv` | 179,415 | 31 | `,` | 18th Lok Sabha | **yes** |
| `esakshi_stagewise_works_rs_raw.csv` | 58,995 | 29 | `,` | Rajya Sabha | **yes** |
| `vonter_mplads_recommendations_raw.csv` | 60,359 | 15 | `;` | mixed | **no** |

Each `esakshi_*` file carries **one row per work-stage**, not per work. `tile_label` holds
the stage: `Works Recommended` / `Works Sanctioned` / `Works Completed`.

## Provenance

Full details — SHA-256 for every file, licences, upstream URLs, original upstream
filenames: **`../metadata/raw_sources.json`**.

- The three `esakshi_*` files come from [in-rolls/mplads](https://github.com/in-rolls/mplads),
  which scrapes the eSAKSHI portal (`mplads.mospi.gov.in`). **No licence is declared** in
  that repository — the safe reproduction path is to run its scraper against the official
  portal and attribute MPLADS/MoSPI.
- `vonter_mplads_recommendations_raw.csv` comes from
  [Vonter/india-mplads-works](https://github.com/Vonter/india-mplads-works) under **ODbL**,
  sourced from the MPLADS SBI public report.

Both are secondary mirrors of official portals. No authentication was used or bypassed.

## Why the Vonter file is present but unused

It carries only the recommendation stage — no sanction or completion rows — so it cannot
support the lifecycle join everything downstream depends on. It is preserved because it is
real, independently licensed, and may be useful for cross-validating recommendation records.

## `original_archives/`

The `.tar.gz` files exactly as downloaded, plus three `._works_*.csv` AppleDouble stubs the
archives contain (macOS resource forks, 163–319 bytes, no data). Nothing here is read by
the pipeline; it exists so the download can be verified against the extraction.

## Regenerating

```bash
python -m mplads_audit.fetch_raw
```

Files already present are skipped. Delete one to force a fresh download.
