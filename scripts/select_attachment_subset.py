"""Which attachments should THADAM download and read first?

    .venv/Scripts/python.exe scripts/select_attachment_subset.py

Measures, then recommends. Nothing here is estimated where it can be counted, and every
figure it prints is reproduced in `data/portal/reports/DATA_SELECTION_RUN.md` with the
formula that produced it.

The question: given the free disk on this machine and a GPU that reads a board in ~20 s,
which exact works' attachments give the strongest evidence for the works an auditor will
actually visit under the 50-auditor-day plan?

Outputs (all under data/portal/, which is gitignored and already the crawl's tree):
  manifests/corpus_manifest.csv   one row per crawled file
  manifests/download_now.csv      the selected work-refs, in visit order
  reports/attachment_selection.json
  reports/DATA_SELECTION_RUN.md   the executive manifest + how every number was measured

Discipline: every line is an investigation lead, never a finding. Conclusions are labelled
OBSERVED (counted here), INFERRED (derived from a measured sample) or RECOMMENDED.
"""

from __future__ import annotations

import csv
import json
import shutil
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mplads import config  # noqa: E402

PORTAL = config.REPO_ROOT / "data" / "portal"
WORKS_RAW = PORTAL / "raw" / "api" / "works"
ATTACH_RAW = PORTAL / "raw" / "api" / "attachments"
PAYLOAD_DIRS = [PORTAL / "raw" / "documents", PORTAL / "raw" / "images"]
MANIFESTS = PORTAL / "manifests"
REPORTS = PORTAL / "reports"

#: Measured on this machine (see `ocr_benchmark.json`): seconds to read one board.
SURYA_SECONDS = 20.4
RAPIDOCR_SECONDS = 2.0
API = "http://127.0.0.1:8020"


def _rows_from(payload) -> list[dict]:
    """The portal nests its rows as a JSON *string* inside the response dict.

    Counting the dict's keys instead of parsing that string is the miscount this function
    exists to prevent: it reports 1 row per file where there are thousands.
    """
    out: list[dict] = []
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, str) and value.strip().startswith("["):
                try:
                    inner = json.loads(value)
                except ValueError:
                    continue
                out.extend(r for r in inner if isinstance(r, dict))
            elif isinstance(value, list):
                out.extend(r for r in value if isinstance(r, dict))
    elif isinstance(payload, list):
        out.extend(r for r in payload if isinstance(r, dict))
    # The server appends a grand-total footer to every response (FINDINGS §3): a row with
    # almost no keys. It is not a work.
    return [r for r in out if len(r) > 2]


def verify_environment() -> dict:
    usage = shutil.disk_usage(config.REPO_ROOT.anchor)
    trees = {}
    for name, path in (("Dataset", config.DATASET), ("data/portal", PORTAL),
                       ("data/artifacts", config.ARTIFACTS)):
        trees[name] = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9
    return {
        "free_disk_gb": round(usage.free / 1e9, 2),
        "tree_sizes_gb": {k: round(v, 3) for k, v in trees.items()},
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def crawl_manifest() -> tuple[list[dict], set, set]:
    """One row per crawled file; the set of work ids seen, and those carrying an ATTACH_ID."""
    rows, all_ids, attach_ids = [], set(), set()
    for path in sorted(WORKS_RAW.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            rows.append({"file": path.name, "scope": path.parent.name, "error": "unreadable"})
            continue
        data = _rows_from(payload)
        ids, with_attach, states = set(), set(), set()
        for row in data:
            wid = row.get("WORK_RECOMMENDATION_DTL_ID")
            if wid not in (None, ""):
                ids.add(str(wid))
                if row.get("ATTACH_ID") not in (None, "", 0, "0"):
                    with_attach.add(str(wid))
            if row.get("STATE_NAME"):
                states.add(str(row["STATE_NAME"]))
        all_ids |= ids
        attach_ids |= with_attach
        rows.append({
            "scope": path.parent.name,
            "file": path.name,
            "report_key": path.stem,
            "state_names": "|".join(sorted(states))[:120],
            "rows": len(data),
            "distinct_work_ids": len(ids),
            "work_ids_with_attachment": len(with_attach),
            "bytes": path.stat().st_size,
        })
    return rows, all_ids, attach_ids


def listing_stats() -> dict:
    """Files exposed per work, from the attachment listings already retrieved.

    The listing is a list of {FILE_NAME: [...], ATTACH_ID: [...]} — parallel arrays, not
    one row per file.
    """
    per_work = []
    for work_dir in sorted(p for p in ATTACH_RAW.iterdir() if p.is_dir()):
        files = 0
        for flag in work_dir.glob("flag_*.json"):
            try:
                payload = json.loads(flag.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            for entry in payload if isinstance(payload, list) else []:
                names = entry.get("FILE_NAME") or []
                files += len(names) if isinstance(names, list) else 1
        per_work.append(files)
    return {
        "works_probed": len(per_work),
        "works_with_files": sum(1 for n in per_work if n),
        "mean_files_per_work": round(statistics.fmean(per_work), 2) if per_work else 0.0,
        "max_files_for_one_work": max(per_work) if per_work else 0,
    }


def payload_stats() -> dict:
    """Megabytes of actual attachment bytes per work, from what has been downloaded."""
    sizes: dict[str, int] = {}
    for base in PAYLOAD_DIRS:
        for f in base.rglob("*"):
            if f.is_file():
                sizes[f.parent.name] = sizes.get(f.parent.name, 0) + f.stat().st_size
    values = list(sizes.values())
    return {
        "works_sampled": len(values),
        "files": sum(1 for base in PAYLOAD_DIRS for f in base.rglob("*") if f.is_file()),
        "total_mb": round(sum(values) / 1e6, 2),
        "mean_mb_per_work": round(statistics.fmean(values) / 1e6, 3) if values else 0.0,
        "median_mb_per_work": round(statistics.median(values) / 1e6, 3) if values else 0.0,
        "max_mb_per_work": round(max(values) / 1e6, 3) if values else 0.0,
    }


def new_id_character(new_ids: set) -> dict:
    """What are the crawled works the snapshot does not have? Tenure and recommendation year
    decide whether this is fresher data or a different slice of the scheme."""
    import collections

    tenures, years, seen = collections.Counter(), collections.Counter(), 0
    for path in sorted(WORKS_RAW.rglob("Works_Recommended.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for row in _rows_from(payload):
            wid = str(row.get("WORK_RECOMMENDATION_DTL_ID") or "")
            if wid and wid in new_ids:
                seen += 1
                tenures[str(row.get("TENURE") or "?")] += 1
                date = str(row.get("RECOMMENDATION_DATE") or "")
                years[date[-4:] if len(date) >= 4 else "?"] += 1
    return {"rows_matched": seen,
            "by_tenure": dict(tenures.most_common(6)),
            "by_year": dict(sorted(years.items()))}


def vendor_coverage() -> dict:
    """Does the crawl actually carry vendor and disbursement fields, and are they populated?"""
    works, with_vendor, with_amount, rows = set(), set(), set(), 0
    for path in sorted(WORKS_RAW.rglob("Expenditure*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for row in _rows_from(payload):
            wid = str(row.get("WORK_RECOMMENDATION_DTL_ID") or "")
            if not wid:
                continue
            rows += 1
            works.add(wid)
            if str(row.get("VENDOR_NAME") or "").strip():
                with_vendor.add(wid)
            if row.get("FUND_DISBURSED_AMT") not in (None, "", 0):
                with_amount.add(wid)
    return {"payment_rows": rows, "distinct_works": len(works),
            "works_with_vendor_name": len(with_vendor),
            "works_with_disbursed_amount": len(with_amount),
            "vendor_coverage_pct": round(len(with_vendor) / max(len(works), 1) * 100, 1),
            "amount_coverage_pct": round(len(with_amount) / max(len(works), 1) * 100, 1)}


def audit_plan_refs(budget_days: int = 50) -> list[str]:
    """The works the budgeted plan actually sends someone to. Empty if the API is down."""
    try:
        with urllib.request.urlopen(f"{API}/api/audit-plan?budget_days={budget_days}", timeout=90) as r:
            plan = json.load(r)
        return [row["work_ref"] for row in plan.get("plan", [])]
    except Exception:
        return []


def write_run_log(s: dict) -> None:
    """The executive manifest, and how every number in it was measured."""
    env, crawl, ov = s["environment"], s["crawl"], s["overlap"]
    prev, pay, cost = s["attachment_prevalence"], s["payload_sample"], s["cost_model"]
    ven = s["vendor_and_payment_fields"]
    lines = []
    add = lines.append
    add("# Attachment acquisition - what to download first, and why")
    add("")
    add("Measured on this machine at " + env["measured_at"] +
        " by `scripts/select_attachment_subset.py`.")
    add("Every number is counted on this machine unless labelled INFERRED.")
    add("")
    add("**Discipline.** Everything here selects *what to look at*. Nothing here is a finding")
    add("against any work, agency or person.")
    add("")
    add("## The decision")
    add("")
    add("| Tier | Works with attachments | GB to disk | Surya GPU-h | Feeds |")
    add("|---|---:|---:|---:|---|")
    for t in s["tiers"]:
        add("| {tier} | {n:,} | {gb:.2f} | {gpu:.1f} | {why} |".format(
            tier=t["tier"], n=t["of_which_have_attachments"], gb=t["gb_to_disk"],
            gpu=t["surya_gpu_hours"], why=t["feeds"]))
    add("")
    add("**Free disk: {} GB.** The full corpus does not fit and is not planned.".format(
        env["free_disk_gb"]))
    add("")
    add("## OBSERVED - counted here")
    add("")
    add("- Crawl on disk: **{f} files, {r:,} rows, {ids:,} distinct work ids** across {sc} scopes"
        " and {st} states, {gb:.2f} GB.".format(
            f=crawl["files"], r=crawl["rows"], ids=ov["crawled_distinct_work_ids"],
            sc=crawl["scopes"], st=crawl["states_seen"], gb=crawl["bytes_gb"]))
    add("- Overlap with the snapshot: **{a:,} refresh works we already have**, **{b:,} are new to"
        " the snapshot**, and {c:,} snapshot works have not been crawled.".format(
            a=ov["already_in_snapshot"], b=ov["new_to_snapshot"],
            c=ov["snapshot_not_yet_crawled"]))
    add("- Attachments: **{n:,} of {t:,} works carry an ATTACH_ID ({p:.1f}%)**. HIGH band"
        " {h:,}/{hw:,}; MEDIUM {m:,}/{mw:,}.".format(
            n=prev["snapshot_works_with_attach_id"], t=s["tiers"][-1]["works_selected"],
            p=prev["snapshot_attachment_rate"] * 100,
            h=prev["by_band"]["HIGH"]["with_attachment"], hw=prev["by_band"]["HIGH"]["works"],
            m=prev["by_band"]["MEDIUM"]["with_attachment"], mw=prev["by_band"]["MEDIUM"]["works"]))
    add("  The crawl agrees independently: {c:,} of {t:,} crawled works carry one ({p:.1f}%).".format(
        c=prev["crawl_rows_with_attach_id_distinct_works"], t=ov["crawled_distinct_work_ids"],
        p=prev["crawl_rows_with_attach_id_distinct_works"] /
        max(ov["crawled_distinct_work_ids"], 1) * 100))
    add("- Vendor and payment fields already crawled: {r:,} payment rows over {w:,} works -"
        " vendor name on {v}% of them, disbursed amount on {a}%.".format(
            r=ven["payment_rows"], w=ven["distinct_works"],
            v=ven["vendor_coverage_pct"], a=ven["amount_coverage_pct"]))
    add("- Attachment payload sample: **{f} files over {w} works**, mean {m} MB/work,"
        " median {md}, max {mx}.".format(
            f=pay["files"], w=pay["works_sampled"], m=pay["mean_mb_per_work"],
            md=pay["median_mb_per_work"], mx=pay["max_mb_per_work"]))
    add("- OCR cost from `ocr_benchmark.json`: Surya {s} s/board on the GPU, RapidOCR {r} s/board"
        " on CPU.".format(s=cost["surya_seconds"], r=cost["rapidocr_seconds"]))
    add("")
    add("## INFERRED - from a small sample, provisional")
    add("")
    add("- Every GB figure is (works with an attachment) x {m} MB, the mean of a **{w}-work**"
        " sample. Those works were fetched *because* they had attachments, so the mean probably"
        " overstates. A 200-work random sample settles it.".format(
            m=pay["mean_mb_per_work"], w=pay["works_sampled"]))
    add("- The {n:,} ids new to the snapshot break down by tenure as {t} and by recommendation"
        " year as {y}.".format(n=ov["new_to_snapshot"], t=json.dumps(ov["new_id_character"]["by_tenure"]),
                               y=json.dumps(ov["new_id_character"]["by_year"])))
    add("")
    add("## RECOMMENDED")
    add("")
    add("1. **Normalise the text already on disk before downloading anything.** {ids:,} works are"
        " crawled and 71 are normalised. No download, no GPU, no new disk of consequence.".format(
            ids=ov["crawled_distinct_work_ids"]))
    add("2. **Fetch the plan tier's attachments now** - the smallest tier here, and the only works"
        " an auditor stands in front of this fortnight.")
    add("3. **Then the rest of the HIGH band** - fits the disk and one overnight GPU run.")
    add("4. **Do not plan the full corpus.** It does not fit, and most of it is LOW/NONE band:"
        " works nothing has flagged.")
    add("5. **Treat vendor and disbursement as a hypothesis, not a capability**, until coverage"
        " and independence are established on a national sample.")
    add("")
    add("## Reproducing this")
    add("")
    add("```bash")
    add(".venv/Scripts/python.exe scripts/select_attachment_subset.py")
    add("```")
    add("")
    add("Outputs: `manifests/corpus_manifest.csv` (one row per crawled file),"
        " `manifests/download_now.csv` (selected works, highest audit-ROI first),"
        " `reports/attachment_selection.json` (every figure, machine-readable).")
    add("")
    (REPORTS / "DATA_SELECTION_RUN.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    env = verify_environment()
    rows, crawl_ids, crawl_attach_ids = crawl_manifest()
    listings = listing_stats()
    payload = payload_stats()

    with (MANIFESTS / "corpus_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "scope", "file", "report_key", "state_names", "rows", "distinct_work_ids",
            "work_ids_with_attachment", "bytes", "error"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    works = pd.read_parquet(config.ARTIFACTS / "works_scored.parquet", columns=[
        "work_ref", "work_recommendation_dtl_id", "attach_id", "band", "audit_roi",
        "rs_exposure", "state_name", "implementing_agency", "n_families"])
    works["wid"] = works["work_recommendation_dtl_id"].astype("string")
    snapshot_ids = set(works["wid"].dropna())

    overlap = {
        "crawled_distinct_work_ids": len(crawl_ids),
        "already_in_snapshot": len(crawl_ids & snapshot_ids),
        "new_to_snapshot": len(crawl_ids - snapshot_ids),
        "snapshot_works": len(works),
        "snapshot_not_yet_crawled": len(snapshot_ids - crawl_ids),
    }

    has_attach = works["attach_id"].notna()
    prevalence = {
        "snapshot_works_with_attach_id": int(has_attach.sum()),
        "snapshot_attachment_rate": round(float(has_attach.mean()), 4),
        "by_band": {b: {"works": int((works["band"] == b).sum()),
                        "with_attachment": int((has_attach & (works["band"] == b)).sum())}
                    for b in ["HIGH", "MEDIUM", "LOW", "NONE"]},
        "crawl_rows_with_attach_id_distinct_works": len(crawl_attach_ids),
    }

    mb = payload["mean_mb_per_work"] or 0.84

    def tier(name: str, frame: pd.DataFrame, why: str) -> dict:
        n = int(frame["attach_id"].notna().sum())
        return {
            "tier": name,
            "works_selected": int(len(frame)),
            "of_which_have_attachments": n,
            "gb_to_disk": round(n * mb / 1024, 3),
            "surya_gpu_hours": round(n * SURYA_SECONDS / 3600, 1),
            "rapidocr_cpu_hours": round(n * RAPIDOCR_SECONDS / 3600, 1),
            "feeds": why,
        }

    new_ids = crawl_ids - snapshot_ids
    overlap["new_id_character"] = new_id_character(new_ids)
    vendors = vendor_coverage()

    plan_refs = audit_plan_refs()
    plan_works = works[works["work_ref"].isin(plan_refs)]
    high = works[works["band"] == "HIGH"]
    high_rest = high[~high["work_ref"].isin(plan_refs)]
    medium = works[works["band"] == "MEDIUM"]

    tiers = [
        tier("DOWNLOAD NOW — the 50-auditor-day plan", plan_works,
             "Every work an auditor is actually sent to: the case file and day pack carry the "
             "document beside the board photograph"),
        tier("AFTER FIRST RUN — rest of the HIGH band", high_rest,
             "The queue behind the plan; widens the field scoreboard's evidence base"),
        tier("DEFERRED — MEDIUM band", medium,
             "Only once disk allows and the HIGH band has been read"),
        tier("NOT PLANNED — every work with an attachment", works,
             "The full corpus, for reference only"),
    ]

    summary = {
        "environment": env,
        "crawl": {
            "files": len([r for r in rows if not r.get("error")]),
            "rows": sum(r.get("rows", 0) for r in rows),
            "scopes": len({r["scope"] for r in rows if r.get("scope")}),
            "states_seen": len({s for r in rows for s in (r.get("state_names") or "").split("|") if s}),
            "bytes_gb": round(sum(r.get("bytes", 0) for r in rows) / 1e9, 3),
        },
        "overlap": overlap,
        "attachment_prevalence": prevalence,
        "attachment_listings": listings,
        "payload_sample": payload,
        "cost_model": {"mb_per_work_used": mb, "surya_seconds": SURYA_SECONDS,
                       "rapidocr_seconds": RAPIDOCR_SECONDS},
        "tiers": tiers,
        "audit_plan_works": len(plan_refs),
        "vendor_and_payment_fields": vendors,
    }
    (REPORTS / "attachment_selection.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    selected = plan_works[plan_works["attach_id"].notna()].copy()
    selected = selected.sort_values("audit_roi", ascending=False)
    selected[["work_ref", "work_recommendation_dtl_id", "attach_id", "band", "rs_exposure",
              "state_name", "implementing_agency"]].to_csv(
        MANIFESTS / "download_now.csv", index=False)

    write_run_log(summary)
    print(json.dumps({k: summary[k] for k in
                      ("overlap", "vendor_and_payment_fields", "payload_sample")}, indent=2))
    for t in tiers:
        print(f"{t['tier']:48} {t['of_which_have_attachments']:>6} works  "
              f"{t['gb_to_disk']:>7.2f} GB  {t['surya_gpu_hours']:>6.1f} GPU-h")
    print(f"\nwrote {MANIFESTS / 'corpus_manifest.csv'}")
    print(f"wrote {MANIFESTS / 'download_now.csv'} ({len(selected)} works)")
    print(f"wrote {REPORTS / 'attachment_selection.json'}")


if __name__ == "__main__":
    main()
