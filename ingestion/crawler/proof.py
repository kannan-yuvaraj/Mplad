"""Phase 3 — prove the pipeline with ONE complete work before scaling.

This is not a demo of the architecture; it is the gate. It walks the full public
user journey against the live portal, retrieves everything the portal exposes
for a single work, and writes it to `data/raw/example_work/`. If it fails, the
scaled collector must not run.

Journey:
    states -> tenures -> constituencies -> MPs -> works (5 tile keys)
           -> attachment listing per FLAG -> attachment bytes

Run it with::

    .venv/Scripts/python.exe -m ingestion.cli proof
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ingestion import api, config
from ingestion.api import Scope
from ingestion.client import PortalClient
from ingestion.storage import attachments
from ingestion.storage.manifest import RawStore, utc_now_iso

log = logging.getLogger(__name__)

#: The work the proof targets by default. Chosen because it is completed, has
#: both an image and a PDF attached, and has a vendor payment record — so it
#: exercises every branch. Any other completed work would do.
DEFAULT_STATE = "Maharashtra"
DEFAULT_CONSTITUENCY = "RAVER"
DEFAULT_HOUSE = config.HOUSE_LOK_SABHA
DEFAULT_TENURE_CAPTION = "18th Lok Sabha"


def _dump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_proof(
    *,
    state_name: str = DEFAULT_STATE,
    constituency_name: str = DEFAULT_CONSTITUENCY,
    house: int = DEFAULT_HOUSE,
    tenure_caption: str = DEFAULT_TENURE_CAPTION,
    work_id: str | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Retrieve one complete work with all its public evidence.

    Returns a summary dict. Raises if any stage of the journey fails — a
    half-successful proof is a failed proof.
    """
    root = output_root or config.EXAMPLE_WORK_ROOT
    root.mkdir(parents=True, exist_ok=True)
    store = RawStore(manifest_name="proof_manifest.jsonl")

    summary: dict[str, Any] = {
        "retrieved_at": utc_now_iso(),
        "portal": config.BASE_URL,
        "journey": [],
        "restricted": [],
    }

    with PortalClient() as client:
        # -- 1. states ----------------------------------------------------
        states, raw = api.get_states(client)
        _dump(states, root / "api_response" / "01_states.json")
        summary["journey"].append({"step": "states", "count": len(states), "url": raw.url})

        match = [s for s in states if s["STATE_NAME"].lower() == state_name.lower()]
        if not match:
            raise RuntimeError(f"state {state_name!r} not present in {len(states)} states")
        state_id = int(match[0]["STATE_ID"])

        # -- 2. tenures ---------------------------------------------------
        tenures, raw = api.get_tenures(client, house)
        _dump(tenures, root / "api_response" / "02_tenures.json")
        summary["journey"].append({"step": "tenures", "count": len(tenures), "url": raw.url})

        tmatch = [t for t in tenures if t["CAPTION"].lower() == tenure_caption.lower()]
        if not tmatch:
            raise RuntimeError(
                f"tenure {tenure_caption!r} not in {[t['CAPTION'] for t in tenures]}"
            )
        tenure_id = int(tmatch[0]["ID"])

        # -- 3. constituencies --------------------------------------------
        constituencies, raw = api.get_constituencies(client, state_id)
        _dump(constituencies, root / "api_response" / "03_constituencies.json")
        summary["journey"].append(
            {"step": "constituencies", "count": len(constituencies), "url": raw.url}
        )

        cmatch = [c for c in constituencies if c["CAPTION"].upper() == constituency_name.upper()]
        if not cmatch:
            raise RuntimeError(f"constituency {constituency_name!r} not found in state {state_id}")
        constituency_id = int(cmatch[0]["ID"])

        # -- 4. MPs -------------------------------------------------------
        mps, raw = api.get_mps_by_constituency(client, constituency_id, house, tenure_id)
        _dump(mps, root / "api_response" / "04_mps.json")
        summary["journey"].append({"step": "mps", "count": len(mps), "url": raw.url})
        if not mps:
            raise RuntimeError(f"no MP for constituency {constituency_id}")
        mp_id = int(mps[0]["ID"])
        mp_name = mps[0]["CAPTION"]

        scope = Scope(state_id, constituency_id, mp_id, house, tenure_id)

        # -- 5. aggregates for this scope (the Phase 10 reconciliation oracle)
        tiles, raw = api.get_tiles(client, scope)
        _dump(tiles, root / "api_response" / "05_tiles.json")
        summary["journey"].append({"step": "tiles", "keys": sorted(tiles), "url": raw.url})

        # -- 6. every tile key at work grain -------------------------------
        reports: dict[str, list[dict[str, Any]]] = {}
        totals: dict[str, float | None] = {}
        for key in config.TILE_KEYS:
            report = api.get_tile_report(client, scope, key)
            reports[key] = report.rows
            totals[key] = report.grand_total
            store.write(
                payload=report.raw.content,
                destination=config.RAW_API / "tile_report" / scope.slug()
                / f"{key.replace(' ', '_').replace('/', '_')[:60]}.json",
                source_url=report.raw.url,
                request_body=report.raw.request_body,
                artefact_kind="api",
                http_status=report.raw.status_code,
                content_type=report.raw.content_type,
                identifiers={"combo": scope.to_combo(), "key": key},
                note=f"grand_total row separated: {report.grand_total}",
            )
            summary["journey"].append(
                {"step": f"report[{key}]", "rows": len(report.rows),
                 "grand_total": report.grand_total}
            )

        _dump(reports, root / "api_response" / "06_tile_reports.json")

        # -- 7. pick the work ---------------------------------------------
        recommended = reports["Works Recommended"]
        if not recommended:
            raise RuntimeError("scope returned no recommended works")

        if work_id is None:
            completed_ids = {
                str(r["WORK_RECOMMENDATION_DTL_ID"]) for r in reports["Works Completed"]
            }
            with_files = [
                r for r in recommended
                if str(r["WORK_RECOMMENDATION_DTL_ID"]) in completed_ids and r.get("ATTACH_ID")
            ]
            chosen = (with_files or recommended)[0]
        else:
            chosen = next(
                (r for r in recommended if str(r["WORK_RECOMMENDATION_DTL_ID"]) == str(work_id)),
                None,
            )
            if chosen is None:
                raise RuntimeError(f"work {work_id} not present in this scope")

        wid = str(chosen["WORK_RECOMMENDATION_DTL_ID"])

        # Assemble the work's full record across all five keys.
        def rows_for(key: str) -> list[dict[str, Any]]:
            return [
                r for r in reports[key]
                if str(r.get("WORK_RECOMMENDATION_DTL_ID", "")) == wid
            ]

        metadata = {
            "work_recommendation_dtl_id": wid,
            "work_ref": f"MP{mp_id}-W{wid}",
            "mp_id": mp_id,
            "mp_name": mp_name,
            "state": state_name,
            "state_id": state_id,
            "constituency": constituency_name,
            "constituency_id": constituency_id,
            "house": house,
            "tenure": tenure_caption,
            "tenure_id": tenure_id,
            "scope_combo": scope.to_combo(),
            "recommended": rows_for("Works Recommended"),
            "sanctioned": rows_for("Works Sanctioned"),
            "completed": rows_for("Works Completed"),
            "expenditure": rows_for("Expenditure on Completed and On-going Works as on Date"),
            "mp_allocated_limit": reports["Allocated Limit for Hon'ble MPs"],
            "scope_grand_totals": totals,
            "retrieved_at": utc_now_iso(),
        }
        _dump(metadata, root / "metadata.json")

        # -- 8. attachments ------------------------------------------------
        refs = attachments.enumerate_attachments(client, wid, store=store)
        _dump([asdict(r) for r in refs], root / "attachments_listing.json")
        summary["journey"].append({"step": "attachment_listing", "count": len(refs)})

        stored: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        known: set[str] = set()

        for ref in refs:
            result = attachments.download_attachment(client, ref, store, known_hashes=known)
            if isinstance(result, attachments.AttachmentFailure):
                failures.append({"attach_id": ref.attach_id, "file_name": ref.file_name,
                                 "http_status": result.http_status, "error": result.error})
                continue

            target_dir = root / ("images" if ref.kind == "image" else "documents")
            target_dir.mkdir(parents=True, exist_ok=True)
            source = config.DATA_ROOT / result.stored_path
            (target_dir / Path(result.stored_path).name).write_bytes(source.read_bytes())

            stored.append({
                "attach_id": ref.attach_id, "file_name": ref.file_name, "kind": ref.kind,
                "flag": ref.flag, "bytes": result.file_size, "sha256": result.sha256,
                "content_type": result.content_type, "note": result.note,
            })

        _dump({"stored": stored, "failed": failures}, root / "attachment_manifest.json")
        summary["attachments"] = {"listed": len(refs), "stored": len(stored), "failed": len(failures)}
        summary["failures"] = failures

    # -- what we deliberately did not touch --------------------------------
    summary["restricted"] = [
        {"resource": f"{config.BASE_URL}/digigov/Login.zul",
         "access": "RESTRICTED", "reason": "authentication required; not probed"},
        {"resource": f"{config.REST_CITIZEN}/verifyOTPForCitizenLogin",
         "access": "RESTRICTED", "reason": "OTP required to submit a citizen review; "
                                           "reading reviews is public, writing is not"},
    ]
    summary["work"] = {
        "work_recommendation_dtl_id": metadata["work_recommendation_dtl_id"],
        "work_ref": metadata["work_ref"],
        "mp_name": mp_name,
    }
    summary["output_root"] = str(root)

    _dump(summary, root / "proof_summary.json")

    ok = bool(stored) and not failures
    summary["proof_passed"] = ok
    _dump(summary, root / "proof_summary.json")
    return summary
