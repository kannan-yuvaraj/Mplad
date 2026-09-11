"""Typed wrappers for every public eSAKSHI endpoint we found.

This module *is* the endpoint inventory. Each function documents the request
shape, the response shape and the date the shape was verified against the live
portal. If a shape here disagrees with the portal, this module is wrong — fix
it here rather than working around it at the call site.

Nothing in this module is speculative. An endpoint that we found referenced in
the frontend but could not get useful data from is recorded in
`ingestion/research/LIMITATIONS.md`, not guessed at here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ingestion import config
from ingestion.client import PortalClient, RawResponse

log = logging.getLogger(__name__)

D = config.REST_DASHBOARD
C = config.REST_CITIZEN


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Scope:
    """The `combo` parameter, decoded from the dashboard's search handler.

    The frontend builds an array `e` where::

        e[0] = state id        (0 = all)
        e[1] = constituency id (0 = all)
        e[2] = mp id           (0 = all)
        e[3] = house           (2 = Lok Sabha, 1 = Rajya Sabha)
        e[4] = tenure id       (omitted when no tenure is selected)

    and sends `e.toString()`, i.e. a comma-joined string.
    """

    state_id: int = 0
    constituency_id: int = 0
    mp_id: int = 0
    house: int = config.HOUSE_LOK_SABHA
    tenure_id: int | None = None

    def to_combo(self) -> str:
        parts = [self.state_id, self.constituency_id, self.mp_id, self.house]
        if self.tenure_id is not None:
            parts.append(self.tenure_id)
        return ",".join(str(p) for p in parts)

    def slug(self) -> str:
        """Filesystem-safe identity for this scope, used for raw paths."""
        return "s{}_c{}_m{}_h{}_t{}".format(
            self.state_id, self.constituency_id, self.mp_id,
            self.house, self.tenure_id if self.tenure_id is not None else "any",
        )


# --------------------------------------------------------------------------
# Reference / enumeration endpoints
# --------------------------------------------------------------------------

def get_states(client: PortalClient) -> tuple[list[dict[str, Any]], RawResponse]:
    """All states/UTs. Verified 2026-09-10: 36 rows.

    Request  ``POST /rest/PreLoginDashboardData/getStateData {}``
    Response ``[{"STATE_NAME": "Bihar", "STATE_ID": 6}, ...]``
    """
    raw = client.post_json(f"{D}/getStateData", {})
    return raw.json(), raw


def get_tenures(client: PortalClient, house: int) -> tuple[list[dict[str, Any]], RawResponse]:
    """Tenures available for a house.

    Verified 2026-09-10 — Lok Sabha: ``17th Lok Sabha`` (5), ``18th Lok Sabha``
    (7). Rajya Sabha: ``Retired`` (2), ``Sitting`` (1).

    Note the parameter is `uname`, not `combo`, and an empty body returns `[]`.
    """
    raw = client.post_json(f"{D}/getTenureData", {"uname": f"0,0,0,{house}"})
    return raw.json(), raw


def get_constituencies(client: PortalClient, state_id: int) -> tuple[list[dict[str, Any]], RawResponse]:
    """Constituencies in a state.

    Request  ``POST .../getConstituencyData {"id": "21"}``
    Response ``[{"ID": 245, "CAPTION": "RAVER"}, ...]``
    """
    raw = client.post_json(f"{D}/getConstituencyData", {"id": str(state_id)})
    return raw.json(), raw


def get_mps_by_state(
    client: PortalClient, state_id: int, house: int, tenure_id: int
) -> tuple[list[dict[str, Any]], RawResponse]:
    """MPs for a (state, house, tenure).

    Request  ``POST .../getMpNamesData {"state_combo": "21,2,7"}``
              — note the order is state, house, tenure, which is NOT the
              `combo` order used by the report endpoint.
    Response ``[{"ID": 3042393, "CAPTION": "NILESH DNYANDEV LANKE"}, ...]``
    """
    raw = client.post_json(
        f"{D}/getMpNamesData", {"state_combo": f"{state_id},{house},{tenure_id}"}
    )
    return raw.json(), raw


def get_mps_by_constituency(
    client: PortalClient, constituency_id: int, house: int, tenure_id: int
) -> tuple[list[dict[str, Any]], RawResponse]:
    """MPs for a (constituency, house, tenure).

    Request  ``POST .../getMpAndConstCombo {"const_combo": "245,2,7"}``
    """
    raw = client.post_json(
        f"{D}/getMpAndConstCombo", {"const_combo": f"{constituency_id},{house},{tenure_id}"}
    )
    return raw.json(), raw


# --------------------------------------------------------------------------
# Aggregates (the numbers the public dashboard shows — Phase 10 oracle)
# --------------------------------------------------------------------------

def get_tiles(client: PortalClient, scope: Scope) -> tuple[dict[str, Any], RawResponse]:
    """Dashboard tile aggregates for a scope.

    Request  ``POST .../getTilesData {"uname": "0,0,0,2"}``
    Response keys observed at national LS scope: ``Allocated Limit for Hon'ble
    MPs``, ``Expenditure on Completed and On-going Works as on Date``, ``Works
    Recommended``, ``Works Completed``, ``Works Sanctioned``, ``Amount consented
    for Calamity``, ``Current Tenure``.

    Values are ``[count, rupees_formatted, crore_formatted]`` for work tiles and
    ``[rupees_formatted, crore_formatted]`` for money tiles. The rupee strings
    carry a literal ``Rs`` prefix that the frontend strips.
    """
    raw = client.post_json(f"{D}/getTilesData", {"uname": scope.to_combo()})
    return raw.json(), raw


def get_total_tiles(client: PortalClient, scope: Scope) -> tuple[dict[str, Any], RawResponse]:
    """All-tenure totals for a scope (the "Total" row of the dashboard)."""
    raw = client.post_json(f"{D}/getTotalTilesData", {"uname": scope.to_combo()})
    return raw.json(), raw


# --------------------------------------------------------------------------
# Work-grain data
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TileReport:
    """Rows for one (scope, key), with the server's grand-total row separated."""

    key: str
    envelope: str
    scope: Scope
    rows: list[dict[str, Any]]
    #: The trailing ``{"Total_Amt": ...}`` row the server appends to every
    #: response. This is the origin of the "3,987 corrupt rows" in our CSV
    #: snapshot: the upstream scraper concatenated it with the work rows.
    grand_total: float | None
    raw: RawResponse


def get_tile_report(client: PortalClient, scope: Scope, key: str) -> TileReport:
    """Work-grain (or payment-grain) rows for a scope and tile key.

    Request  ``POST .../getTilesReportData
              {"combo": "21,245,3019105,2,7", "key": "Works Recommended"}``

    Response is double-encoded: ``{"<envelope>": "<a JSON string of rows>"}``.
    The last element of the parsed array is a grand-total row, not a work.

    There is no pagination parameter. The server returns the entire scope in one
    response and the frontend chunks it client-side, so *scope narrowing is the
    pagination mechanism*. National scope (`0,0,0,2`) times out; state scope
    returns in well under a second.
    """
    if key not in config.TILE_KEYS:
        raise ValueError(f"unknown tile key {key!r}; expected one of {sorted(config.TILE_KEYS)}")

    raw = client.post_json(f"{D}/getTilesReportData", {"combo": scope.to_combo(), "key": key})
    body = raw.json()

    envelope = config.TILE_KEYS[key]
    if envelope not in body:
        # The server names the envelope itself; trust what it sent over our map.
        if len(body) != 1:
            raise PortalShapeError(f"{key}: expected one envelope, got {sorted(body)}")
        envelope = next(iter(body))

    payload = body[envelope]
    rows = json.loads(payload) if isinstance(payload, str) else payload

    grand_total: float | None = None
    if rows and set(rows[-1]) == {"Total_Amt"}:
        grand_total = rows[-1]["Total_Amt"]
        rows = rows[:-1]

    return TileReport(
        key=key, envelope=envelope, scope=scope,
        rows=rows, grand_total=grand_total, raw=raw,
    )


class PortalShapeError(RuntimeError):
    """The portal returned a shape this module does not model."""


# --------------------------------------------------------------------------
# Attachments — documents and images (Phase 6 / Phase 7)
# --------------------------------------------------------------------------

def list_attachments(
    client: PortalClient, work_recommendation_dtl_id: int | str, flag: int
) -> tuple[list[dict[str, Any]], RawResponse]:
    """Filenames and attachment ids for a work at one stage FLAG.

    Request  ``POST .../getAttachIdsbyFlag
              {"json": {"FLAG": 1, "WORK_ID": "140096"}}``
              — the frontend reads WORK_ID from a `wrk_rec_id` DOM attribute, so
              despite the name this is `WORK_RECOMMENDATION_DTL_ID`, not the
              portal's own `WORK_ID`.
    Response ``[{"FILE_NAME": ["wc.jpg", "work cc.pdf"],
                 "ATTACH_ID": ["703161.725942", "703161.801553"]}]``
              or ``[]``, or the sentinel
              ``[{"FILE_NAME": "N/A", "URL": "N/A"}]`` when the stage carries no
              file. `ATTACH_ID` is `<parent>.<child>` — the parent matches the
              `ATTACH_ID` on the work row.
    """
    raw = client.post_json(
        f"{D}/getAttachIdsbyFlag",
        {"json": {"FLAG": flag, "WORK_ID": str(work_recommendation_dtl_id)}},
    )
    return raw.json(), raw


def get_attachment(client: PortalClient, attach_id: str) -> tuple[dict[str, Any], RawResponse]:
    """Retrieve one attachment's bytes.

    Request  ``POST /rest/PreLoginCitizenWorkRcmdRest/getAttachmentById
              {"id": "703161.725942"}``
    Response ``[{"FILE_NAME": "wc.jpg", "URL": "<base64>"}]``

    The compound `<parent>.<child>` id is required; the bare parent id returns
    ``[{}]``. The `URL` field is not a URL — it is the base64 file body. The
    server sets no content-type for it, so the MIME type must be taken from the
    filename extension and confirmed against the magic bytes.
    """
    raw = client.post_json(f"{C}/getAttachmentById", {"id": str(attach_id)}, extra_delay=config.ATTACHMENT_DELAY_SECONDS)
    body = raw.json()
    record = body[0] if isinstance(body, list) and body else {}
    return record, raw


# --------------------------------------------------------------------------
# Scheme documents and citizen feedback
# --------------------------------------------------------------------------

def list_scheme_documents(client: PortalClient, content: str) -> tuple[list[str], RawResponse]:
    """Guideline / manual / form filenames. `content` is ENGLISH, HINDI or FORMS."""
    raw = client.post_json(f"{D}/get_fileNames", {"content": content})
    return raw.json(), raw


def get_scheme_document(client: PortalClient, name: str, content: str) -> tuple[dict[str, Any], RawResponse]:
    """One scheme document. Response ``{"FileUrl": "<base64>"}``."""
    raw = client.post_json(
        f"{D}/getFileData", {"json": {"name": name, "content": content}},
        extra_delay=config.ATTACHMENT_DELAY_SECONDS,
    )
    return raw.json(), raw


def get_citizen_reviews(client: PortalClient) -> tuple[list[dict[str, Any]], RawResponse]:
    """Citizen star ratings and review text.

    Request  ``POST /rest/PreLoginCitizenWorkRcmdRest/getReviewDetailsByWork
              {"json": {"WORK_ID": "140096"}}``

    **The work id is ignored.** Verified 2026-09-10: passing a specific work and
    passing a bare string both return the same global list, keyed by
    `WORK_RECOM_DTL_ID`. Treat this as "fetch all reviews once", not as a
    per-work lookup.
    """
    raw = client.post_json(f"{C}/getReviewDetailsByWork", {"json": {"WORK_ID": "0"}})
    return raw.json(), raw
