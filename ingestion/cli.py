"""Command line for the eSAKSHI public-portal ingestion module.

    .venv/Scripts/python.exe -m ingestion.cli <command>

Commands:
    proof       Phase 3 gate — retrieve ONE complete work with all its evidence.
    enumerate   Phase 8 — states, tenures, constituencies, MPs. Reference data only.
    works       Phase 8 — work-grain crawl. Resumable. Requires `proof` to have passed.
    attachments Phase 6/7 — documents and images for crawled works. Resumable.
    normalize   Phase 4 — raw responses to normalized tables.
    validate    Phase 10 — reconcile our sums against the portal's own aggregates.
    report      Completeness report over whatever has been collected so far.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ingestion import config


def _setup_logging(verbose: bool) -> None:
    config.ensure_dirs()
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(config.LOG_ROOT / "ingestion.log", encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingestion", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_proof = sub.add_parser("proof", help="Phase 3 gate: one complete work")
    p_proof.add_argument("--state", default=None)
    p_proof.add_argument("--constituency", default=None)
    p_proof.add_argument("--tenure", default=None)
    p_proof.add_argument("--work-id", default=None)

    p_enum = sub.add_parser("enumerate", help="states, tenures, constituencies, MPs")
    p_enum.add_argument("--house", type=int, choices=list(config.HOUSES), default=None)

    p_works = sub.add_parser("works", help="work-grain crawl (resumable)")
    p_works.add_argument("--house", type=int, choices=list(config.HOUSES), default=None)
    p_works.add_argument("--state", type=int, default=None, help="restrict to one STATE_ID")
    p_works.add_argument("--limit-scopes", type=int, default=None)

    p_att = sub.add_parser("attachments", help="documents and images (resumable)")
    p_att.add_argument("--limit-works", type=int, default=None)

    sub.add_parser("normalize", help="raw -> normalized tables")
    sub.add_parser("validate", help="reconcile against the portal's own aggregates")
    sub.add_parser("report", help="completeness report")
    sub.add_parser("dataset", help="package everything collected as a distributable dataset")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "proof":
        from ingestion.crawler.proof import run_proof
        kwargs = {}
        if args.state:
            kwargs["state_name"] = args.state
        if args.constituency:
            kwargs["constituency_name"] = args.constituency
        if args.tenure:
            kwargs["tenure_caption"] = args.tenure
        if args.work_id:
            kwargs["work_id"] = args.work_id
        summary = run_proof(**kwargs)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("proof_passed") else 1

    if args.command == "enumerate":
        from ingestion.crawler.enumerate_reference import run_enumeration
        result = run_enumeration(house=args.house)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "works":
        from ingestion.crawler.works import run_work_crawl
        if not _proof_passed():
            print("Refusing to crawl: `ingestion.cli proof` has not passed. "
                  "Phase 3 gates Phase 8.", file=sys.stderr)
            return 2
        result = run_work_crawl(house=args.house, only_state=args.state,
                                limit_scopes=args.limit_scopes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "attachments":
        from ingestion.crawler.attachment_crawl import run_attachment_crawl
        if not _proof_passed():
            print("Refusing to crawl: `ingestion.cli proof` has not passed.", file=sys.stderr)
            return 2
        result = run_attachment_crawl(limit_works=args.limit_works)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "normalize":
        from ingestion.normalizer.normalize import run_normalize
        print(json.dumps(run_normalize(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate":
        from ingestion.validation.reconcile import run_reconciliation
        result = run_reconciliation()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "dataset":
        from ingestion.dataset.build import run_build_dataset
        print(json.dumps(run_build_dataset(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "report":
        from ingestion.validation.completeness import run_completeness_report
        print(json.dumps(run_completeness_report(), ensure_ascii=False, indent=2))
        return 0

    parser.error(f"unhandled command {args.command}")
    return 2


def _proof_passed() -> bool:
    """Phase 3 gates Phase 8: refuse to scale until one work has been proven."""
    summary = Path(config.EXAMPLE_WORK_ROOT) / "proof_summary.json"
    if not summary.exists():
        return False
    try:
        return bool(json.loads(summary.read_text(encoding="utf-8")).get("proof_passed"))
    except (json.JSONDecodeError, OSError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
