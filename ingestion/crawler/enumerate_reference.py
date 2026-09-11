"""Phase 8 step 1 — enumerate the reference dimensions.

states x houses x tenures -> constituencies -> MPs.

This is the map the work crawl walks. It is cheap (a few hundred requests) and
is re-run to detect new MPs or tenures appearing on the portal. Every response
is preserved raw before anything is derived from it.

There is no district dimension in the works data. `getDistrictByState` exists on
the citizen controller but returned an empty body for every parameter shape we
tried, and no work-grain endpoint accepts a district. `IDA_NAME` — a district
*office* — is the only district-level attribute the portal exposes on a work.
"""

from __future__ import annotations

import logging
from typing import Any

from ingestion import api, config
from ingestion.client import PortalClient, PortalError
from ingestion.crawler.checkpoint import Checkpoint
from ingestion.storage.manifest import RawStore

log = logging.getLogger(__name__)

HOUSE_NAMES = {config.HOUSE_LOK_SABHA: "Lok Sabha", config.HOUSE_RAJYA_SABHA: "Rajya Sabha"}


def run_enumeration(*, house: int | None = None) -> dict[str, Any]:
    """Build the reference map. Resumable; cheap enough to just re-run."""
    store = RawStore()
    ckpt = Checkpoint.load("enumerate")
    houses = (house,) if house is not None else config.HOUSES

    result: dict[str, Any] = {
        "states": [], "tenures": {}, "constituencies": {}, "mps": {},
        "counts": {}, "failures": ckpt.failures,
    }

    with PortalClient() as client:
        states, raw = api.get_states(client)
        store.write(payload=raw.content, destination=config.RAW_API / "reference" / "states.json",
                    source_url=raw.url, request_body=raw.request_body, artefact_kind="api",
                    http_status=raw.status_code, content_type=raw.content_type)
        result["states"] = states
        log.info("states discovered: %d", len(states))

        for h in houses:
            try:
                tenures, raw = api.get_tenures(client, h)
            except PortalError as exc:
                ckpt.fail(f"tenures:{h}", url=exc.path, error=exc.detail, http_status=exc.status)
                continue
            store.write(payload=raw.content,
                        destination=config.RAW_API / "reference" / f"tenures_house{h}.json",
                        source_url=raw.url, request_body=raw.request_body, artefact_kind="api",
                        http_status=raw.status_code, content_type=raw.content_type,
                        identifiers={"house": h})
            result["tenures"][str(h)] = tenures
            log.info("house %s (%s) tenures: %s", h, HOUSE_NAMES.get(h),
                     [t["CAPTION"] for t in tenures])

        for state in states:
            sid = int(state["STATE_ID"])
            key = f"constituencies:{sid}"
            if not ckpt.done(key):
                try:
                    consts, raw = api.get_constituencies(client, sid)
                except PortalError as exc:
                    ckpt.fail(key, url=exc.path, error=exc.detail, http_status=exc.status,
                              identifier=str(sid))
                    continue
                store.write(payload=raw.content,
                            destination=config.RAW_API / "reference" / "constituencies"
                            / f"state_{sid}.json",
                            source_url=raw.url, request_body=raw.request_body,
                            artefact_kind="api", http_status=raw.status_code,
                            content_type=raw.content_type,
                            identifiers={"STATE_ID": sid, "STATE_NAME": state["STATE_NAME"]})
                result["constituencies"][str(sid)] = consts
                ckpt.mark(key)

            for h in houses:
                for tenure in result["tenures"].get(str(h), []):
                    tid = int(tenure["ID"])
                    mkey = f"mps:{sid}:{h}:{tid}"
                    if ckpt.done(mkey):
                        continue
                    try:
                        mps, raw = api.get_mps_by_state(client, sid, h, tid)
                    except PortalError as exc:
                        ckpt.fail(mkey, url=exc.path, error=exc.detail, http_status=exc.status,
                                  identifier=f"state={sid} house={h} tenure={tid}")
                        continue
                    store.write(payload=raw.content,
                                destination=config.RAW_API / "reference" / "mps"
                                / f"state_{sid}_house_{h}_tenure_{tid}.json",
                                source_url=raw.url, request_body=raw.request_body,
                                artefact_kind="api", http_status=raw.status_code,
                                content_type=raw.content_type,
                                identifiers={"STATE_ID": sid, "house": h, "tenure_id": tid})
                    result["mps"][mkey] = mps
                    ckpt.mark(mkey)

    ckpt.close()

    result["counts"] = {
        "states_discovered": len(result["states"]),
        "constituencies_discovered": sum(len(v) for v in result["constituencies"].values()),
        "mps_discovered": sum(len(v) for v in result["mps"].values()),
        "mps_distinct": len({m["ID"] for v in result["mps"].values() for m in v}),
        "failures": len(ckpt.failures),
    }
    store.write_json(obj=result["counts"],
                     destination=config.REPORT_ROOT / "enumeration_counts.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    log.info("enumeration counts: %s", result["counts"])
    return {"counts": result["counts"], "failures": ckpt.failures}
