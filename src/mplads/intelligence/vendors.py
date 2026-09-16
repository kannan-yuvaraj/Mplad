"""Vendor concentration — who actually gets paid, and how narrowly.

The live portal gives us something the CSV snapshot never had: the **vendor** on
each disbursement. That opens the one question a public-money auditor always
asks and this system could not previously answer — *is one district paying the
same handful of firms for everything?*

The measure is the **Herfindahl-Hirschman Index**, the standard used by
competition regulators worldwide: sum the squared share of each vendor in an
authority's disbursed money. One vendor taking everything gives 1.0; a hundred
equal vendors give 0.01. It is preferred here over "count the vendors" because
a district with fifty vendors where one takes 90% of the money is concentrated,
and a count would call it diverse.

**Three rails, and they are the whole safety case.**

1. **Concentration is not wrongdoing.** A rural district may have four firms
   capable of building a school. Reporting a high HHI as a finding would
   accuse every remote district in India of something. Every figure here is a
   *question*, and the API says so on every row.
2. **No index below `MIN_PAYMENTS_FOR_AN_INDEX`.** Three payments to one vendor
   is an HHI of 1.0 and means nothing at all. Under the floor we return the
   counts and no index — the same discipline `calibration.py` applies to rates.
3. **Always against the distribution, never against a threshold we invented.**
   An authority is reported at its percentile among comparable authorities.
   The regulator's 0.25 "highly concentrated" line is shown for reference and
   labelled as what it is — a competition-law benchmark, not an MPLADS rule.

Coverage is whatever the live feed has synced. `concentration_report` states it
rather than implying national coverage.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field as dataclass_field
from typing import Any

LOGGER = logging.getLogger(__name__)

#: Below this many payments an index is noise. Three payments to one vendor is
#: a perfect 1.0 and says nothing about how an authority buys.
MIN_PAYMENTS_FOR_AN_INDEX = 20

#: Competition-law reference points (US DOJ / FTC merger guidelines), shown for
#: orientation only. MPLADS publishes no concentration rule of its own, and we
#: do not invent one.
HHI_MODERATE = 0.15
HHI_HIGH = 0.25

#: How the index is described in words. Colour is never the only channel — the
#: frontend pairs each with its glyph, the same rule `severity.js` enforces.
BANDS = (
    (HHI_HIGH, "CONCENTRATED", "A few vendors take most of the money here."),
    (HHI_MODERATE, "MODERATE", "Somewhat concentrated among a smaller set of vendors."),
    (0.0, "SPREAD", "Money is spread across many vendors."),
)


@dataclass(frozen=True, slots=True)
class AuthorityConcentration:
    """One implementing authority's vendor profile."""

    authority: str
    state: str | None
    payments: int
    vendors: int
    total_disbursed: float
    hhi: float | None
    top_vendor_share: float | None
    top_vendor: str | None
    top3_share: float | None
    band: str | None
    percentile: float | None
    #: The vendors themselves, largest share first. An index is a summary; an
    #: officer about to ring a district authority needs the names.
    vendor_rows: list[dict[str, Any]] = dataclass_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "state": self.state,
            "payments": self.payments,
            "vendors": self.vendors,
            "total_disbursed": round(self.total_disbursed, 2),
            "top_vendors": self.vendor_rows,
            "hhi": None if self.hhi is None else round(self.hhi, 4),
            "effective_vendors": (
                None if not self.hhi else round(1.0 / self.hhi, 1)
            ),
            "top_vendor": self.top_vendor,
            "top_vendor_share": (
                None if self.top_vendor_share is None else round(self.top_vendor_share, 4)
            ),
            "top3_share": None if self.top3_share is None else round(self.top3_share, 4),
            "band": self.band,
            "percentile_among_comparable": (
                None if self.percentile is None else round(self.percentile, 3)
            ),
            "index_withheld": self.hhi is None,
            "withheld_reason": (
                None if self.hhi is not None else
                f"only {self.payments} payments — under {MIN_PAYMENTS_FOR_AN_INDEX} "
                f"an index is arithmetic, not evidence"
            ),
        }


def hhi(shares: list[float]) -> float:
    """Herfindahl-Hirschman Index over shares that sum to 1."""
    return float(sum(s * s for s in shares))


def band_for(index: float) -> tuple[str, str]:
    for floor, name, note in BANDS:
        if index >= floor:
            return name, note
    return "SPREAD", BANDS[-1][2]


def _percentile(value: float, population: list[float]) -> float:
    """Where `value` sits in `population`, 0-1. Ties count as half."""
    if not population:
        return 0.0
    below = sum(1 for p in population if p < value)
    equal = sum(1 for p in population if p == value)
    return (below + equal / 2) / len(population)


def concentration_report(
    rows: list[dict[str, Any]],
    *,
    by: str = "ida_name",
    min_payments: int = MIN_PAYMENTS_FOR_AN_INDEX,
) -> dict[str, Any]:
    """Vendor concentration per authority, from payment rows.

    `rows` need `vendor_id`/`vendor_name`, `fund_disbursed_amount`, the grouping
    column named by `by`, and optionally `state_name`. Rows missing a vendor or
    an amount are counted and reported, never silently dropped — the count of
    what we could not use is part of the answer.
    """
    grouped: dict[str, dict[str, Any]] = {}
    unusable = 0

    for row in rows:
        authority = (row.get(by) or "").strip()
        vendor = row.get("vendor_id") or row.get("vendor_name")
        amount = row.get("fund_disbursed_amount")
        if not authority or vendor in (None, "") or not isinstance(amount, (int, float)):
            unusable += 1
            continue
        if amount <= 0:
            unusable += 1
            continue

        bucket = grouped.setdefault(authority, {
            "state": row.get("state_name"),
            "payments": 0,
            "by_vendor": {},
            "names": {},
            "total": 0.0,
        })
        key = str(vendor)
        bucket["payments"] += 1
        bucket["total"] += float(amount)
        bucket["by_vendor"][key] = bucket["by_vendor"].get(key, 0.0) + float(amount)
        if row.get("vendor_name"):
            bucket["names"].setdefault(key, row["vendor_name"])

    # First pass: the indices, so the second pass can place each in the spread.
    indices: list[float] = []
    staged: list[tuple[str, dict[str, Any], float | None]] = []
    for authority, bucket in grouped.items():
        total = bucket["total"]
        if bucket["payments"] < min_payments or total <= 0:
            staged.append((authority, bucket, None))
            continue
        shares = sorted((v / total for v in bucket["by_vendor"].values()), reverse=True)
        index = hhi(shares)
        indices.append(index)
        staged.append((authority, bucket, index))

    results: list[AuthorityConcentration] = []
    for authority, bucket, index in staged:
        total = bucket["total"]
        shares = sorted((v / total for v in bucket["by_vendor"].values()), reverse=True) \
            if total > 0 else []
        top_key = max(bucket["by_vendor"], key=bucket["by_vendor"].get) \
            if bucket["by_vendor"] else None

        # The names behind the index, largest share first. Capped at ten: an
        # officer ringing a district authority needs the firms that matter, not
        # a directory of every payee.
        ranked = sorted(bucket["by_vendor"].items(), key=lambda kv: -kv[1])[:10]
        vendor_rows = [{
            "vendor_id": key,
            "vendor_name": bucket["names"].get(key, key),
            "disbursed": round(amount, 2),
            "share": round(amount / total, 4) if total else None,
        } for key, amount in ranked]

        results.append(AuthorityConcentration(
            vendor_rows=vendor_rows,
            authority=authority,
            state=bucket["state"],
            payments=bucket["payments"],
            vendors=len(bucket["by_vendor"]),
            total_disbursed=total,
            hhi=index,
            top_vendor_share=shares[0] if shares else None,
            top_vendor=bucket["names"].get(top_key, top_key) if top_key else None,
            top3_share=sum(shares[:3]) if shares else None,
            band=band_for(index)[0] if index is not None else None,
            percentile=_percentile(index, indices) if index is not None else None,
        ))

    results.sort(key=lambda r: (r.hhi if r.hhi is not None else -1), reverse=True)
    scored = [r for r in results if r.hhi is not None]

    return {
        "grouped_by": by,
        "authorities": [r.to_dict() for r in results],
        "coverage": {
            "payment_rows_read": len(rows),
            "rows_unusable": unusable,
            "authorities_seen": len(results),
            "authorities_with_an_index": len(scored),
            "authorities_below_floor": len(results) - len(scored),
            "min_payments_for_an_index": min_payments,
            "states_covered": sorted({r.state for r in results if r.state}),
        },
        "distribution": _distribution(scored),
        "contract": (
            "Concentration is a question, not a finding. A district with four firms "
            "able to build a school will concentrate for reasons that have nothing to "
            "do with wrongdoing. Every figure here is the start of a conversation with "
            "the District Authority, and a human should ask before anyone concludes."
        ),
        "benchmark_note": (
            f"The {HHI_MODERATE:.2f} and {HHI_HIGH:.2f} lines are competition-law "
            "reference points from merger-review guidelines, shown for orientation. "
            "MPLADS publishes no concentration rule, and we have not invented one."
        ),
    }


def _distribution(scored: list[AuthorityConcentration]) -> dict[str, Any]:
    """The shape of the national spread, so one authority can be placed in it."""
    if not scored:
        return {"count": 0, "note": "no authority cleared the payment floor"}
    values = sorted(r.hhi for r in scored if r.hhi is not None)

    def at(q: float) -> float:
        if not values:
            return 0.0
        pos = q * (len(values) - 1)
        low, high = math.floor(pos), math.ceil(pos)
        if low == high:
            return values[int(pos)]
        return values[low] + (values[high] - values[low]) * (pos - low)

    bands: dict[str, int] = {}
    for r in scored:
        if r.band:
            bands[r.band] = bands.get(r.band, 0) + 1

    return {
        "count": len(values),
        "median": round(at(0.5), 4),
        "p25": round(at(0.25), 4),
        "p75": round(at(0.75), 4),
        "p90": round(at(0.9), 4),
        "max": round(values[-1], 4),
        "min": round(values[0], 4),
        "bands": bands,
    }


def for_authority(report: dict[str, Any], authority: str) -> dict[str, Any] | None:
    """One authority's row out of a report, with its place in the spread."""
    target = (authority or "").strip().lower()
    for row in report.get("authorities", []):
        if row["authority"].strip().lower() == target:
            return row | {
                "distribution": report.get("distribution"),
                "contract": report.get("contract"),
            }
    return None
