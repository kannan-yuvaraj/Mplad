# data_real/ — real public MPLADS data

Run `python fetch_real.py` to download (files are gitignored; regenerate anytime).

| File | Source | Rows | Stage/fields |
|---|---|---|---|
| `MPLADS.csv` | [Vonter/india-mplads-works](https://github.com/Vonter/india-mplads-works) (ODbL) | ~60k | recommendation-stage: MP, work, category, state, constituency, IDA, allocation amount, status |
| `works_ls17/ls18/rs.csv` | [in-rolls/mplads](https://github.com/in-rolls/mplads) (from eSAKSHI) | ~300k | stage-wise lifecycle: RECOMMENDATION_DATE, RECOMMENDED_AMOUNT, ACTUAL_AMOUNT, ACTUAL_END_DATE, WORK_RECOMMENDATION_DTL_ID, IDA_NAME, tile_label (Recommended/Sanctioned/Completed) |

Both trace to the official MPLADS reporting portal (attribute the MPLADS site). See `../docs/DATA_ACQUISITION_REPORT.md`.
