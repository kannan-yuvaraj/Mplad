"""Measure whether sweeping three attachment FLAGs is necessary.

`enumerate_attachments` asks `getAttachIdsbyFlag` once per FLAG in
`config.ATTACHMENT_FLAGS`. At ~72,000 works with attachments that is ~215,000
requests — about 60 hours at 1 req/s, and roughly 40 of those hours exist only
to confirm that FLAGs 2 and 3 return nothing new.

On the single work characterised so far (140096), FLAG 1 returned both files and
FLAGs 2 and 3 returned the `N/A` sentinel. One work is not evidence. This script
measures it across a real sample and prints what the sweep actually buys.

**It does not change the crawler.** If FLAGs 2/3 ever return a file that FLAG 1
did not, the sweep stays — losing a photograph to save a day would be a bad
trade, and the point of measuring is to find that out rather than assume it.

    ./.venv/Scripts/python.exe -m ingestion.research.flag_experiment --works 60
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from ingestion import api, config
from ingestion.client import PortalClient, PortalError
from ingestion.crawler.attachment_crawl import iter_crawled_works


def _files_for(client: PortalClient, work_id: str, flag: int) -> set[tuple[str, str]]:
    """(attach_id, file_name) pairs the portal lists for this work at this FLAG."""
    try:
        body, _ = api.list_attachments(client, work_id, flag)
    except PortalError:
        return set()
    found: set[tuple[str, str]] = set()
    for record in body if isinstance(body, list) else []:
        names, ids = record.get("FILE_NAME"), record.get("ATTACH_ID")
        if names == config.ATTACHMENT_ABSENT or not isinstance(names, list):
            continue
        if not isinstance(ids, list) or len(ids) != len(names):
            continue
        for name, attach_id in zip(names, ids):
            if name != "File not available.":
                found.add((str(attach_id), str(name)))
    return found


def run(sample_size: int, flags: tuple[int, ...]) -> dict[str, Any]:
    works = [str(r["WORK_RECOMMENDATION_DTL_ID"]) for r in iter_crawled_works()]
    # Spread the sample across the crawl order rather than taking the first N,
    # which would all come from whichever state was crawled first.
    step = max(len(works) // sample_size, 1)
    sample = works[::step][:sample_size]

    per_flag: dict[int, Counter] = {f: Counter() for f in flags}
    unique_to: Counter = Counter()
    works_where_flag1_was_enough = 0
    works_with_any_file = 0
    detail: list[dict[str, Any]] = []

    with PortalClient() as client:
        for work_id in sample:
            found = {f: _files_for(client, work_id, f) for f in flags}
            union = set().union(*found.values())
            if not union:
                continue
            works_with_any_file += 1

            for f in flags:
                per_flag[f]["works_with_files"] += bool(found[f])
                per_flag[f]["files"] += len(found[f])

            base = found.get(1, set())
            extra = union - base
            if not extra:
                works_where_flag1_was_enough += 1
            else:
                for f in flags:
                    if f == 1:
                        continue
                    for item in found[f] - base:
                        unique_to[f] += 1
                detail.append({
                    "work": work_id,
                    "flag1_files": sorted(n for _, n in base),
                    "extra_files": sorted(n for _, n in extra),
                })

    result = {
        "sample_requested": sample_size,
        "sample_taken": len(sample),
        "works_with_at_least_one_file": works_with_any_file,
        "per_flag": {str(f): dict(c) for f, c in per_flag.items()},
        "works_where_FLAG_1_alone_was_complete": works_where_flag1_was_enough,
        "files_found_only_under_flag_2_or_3": dict(unique_to),
        "works_where_the_sweep_mattered": detail,
    }
    if works_with_any_file:
        pct = 100 * works_where_flag1_was_enough / works_with_any_file
        result["flag_1_sufficiency_pct"] = round(pct, 2)
        result["verdict"] = (
            "FLAG 1 alone was complete on every sampled work — the sweep can be "
            "narrowed, saving ~2 requests per work."
            if not unique_to else
            "FLAGs 2/3 returned files FLAG 1 did not. KEEP THE SWEEP."
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--works", type=int, default=60)
    args = parser.parse_args()
    print(json.dumps(run(args.works, config.ATTACHMENT_FLAGS), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
