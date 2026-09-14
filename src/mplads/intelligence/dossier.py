"""The agency dossier: what an auditor should read on the way to a visit.

Every other screen in this product is organised around a *work*. An auditor's day is not.
They travel to an **implementing agency**, and once there they see whatever that agency is
building — which is exactly why the audit plan batches by agency and why a rota is dealt
out in whole agencies. The one thing missing was the page an officer reads on the journey:
who is this body, what does it hold, what did we find here last time.

**The comparison is the point, and it has to be a rate.** A district planning office with
four thousand works will surface more leads than one with forty, and reading the raw count
as a signal is how a large agency is punished for being large. So every figure that could
be read as an accusation is reported next to the national rate for the same measure, and
the dossier says in plain words when an agency's surfaced share is ordinary.

**What was found here before outranks what the model thinks.** If an officer has already
stood at this agency and recorded an outcome, that is the only ground truth this system
will ever have, and it goes above the model's own reasoning on the page. It also cuts both
ways: visits that cleared works are shown with the same weight as visits that did not.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

LOGGER = logging.getLogger(__name__)

#: Below this many works, a rate is arithmetic rather than evidence. The dossier still
#: prints the count; it declines to compare the rate against the national one.
MIN_WORKS_FOR_A_RATE = 20

#: How far above the national surfaced-lead rate counts as worth a sentence. Chosen to be
#: unmistakable rather than significant — no test is being run here, and calling a 1.1x
#: difference "elevated" would be dressing noise as a finding.
NOTABLE_RATE_MULTIPLE = 1.5


def _national(frame: pd.DataFrame) -> dict[str, float]:
    """The portfolio-wide baselines every agency figure is read against."""
    total = len(frame)
    surfaced = int(frame["band"].isin(["HIGH", "MEDIUM"]).sum())
    return {
        "works": total,
        "surfaced_rate": surfaced / total if total else 0.0,
        "median_amount": float(frame["recommended_amount"].median()) if total else 0.0,
        "open_rate": float(frame["is_open"].mean()) if total else 0.0,
    }


def agencies(frame: pd.DataFrame, limit: int = 40) -> list[dict[str, Any]]:
    """Agencies ranked by exposure carried, for a picker rather than for a verdict."""
    if frame.empty:
        return []
    grouped = (
        frame.groupby("implementing_agency", observed=True)
        .agg(works=("work_ref", "size"),
             exposure=("rs_exposure", "sum"),
             state=("state_name", "first"))
        .reset_index()
        .sort_values("exposure", ascending=False)
        .head(limit)
    )
    return [
        {"implementing_agency": str(row.implementing_agency), "state": str(row.state),
         "works": int(row.works), "exposure_rupees": float(row.exposure)}
        for row in grouped.itertuples()
    ]


def build(frame: pd.DataFrame, agency: str, *,
          cases_by_ref: dict[str, Any] | None = None,
          duplicate_pairs: "pd.DataFrame | Callable[[set], pd.DataFrame] | None" = None,
          verifications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Everything worth knowing about one implementing agency before going there.

    `frame` is the whole scored portfolio, not the leads — an agency is described by what
    it holds, and describing it only by the works that were flagged would make every
    agency in the dossier look like a problem by construction.
    """
    if frame.empty:
        return {"available": False, "note": "no scored works loaded"}

    mine = frame[frame["implementing_agency"] == agency]
    if mine.empty:
        return {"available": False, "implementing_agency": agency,
                "note": "no works recorded against this implementing agency"}

    national = _national(frame)
    works = len(mine)
    leads = mine[mine["band"].isin(["HIGH", "MEDIUM"])]
    surfaced_rate = len(leads) / works
    ratio = surfaced_rate / national["surfaced_rate"] if national["surfaced_rate"] else 0.0

    comparable = works >= MIN_WORKS_FOR_A_RATE
    if not comparable:
        reading = (
            f"{works} works is too few to read a rate from. The individual leads below are "
            "still worth reading; the proportion is not."
        )
    elif ratio >= NOTABLE_RATE_MULTIPLE:
        reading = (
            f"{surfaced_rate:.1%} of this agency's works were surfaced, against "
            f"{national['surfaced_rate']:.1%} across the portfolio — about {ratio:.1f} "
            "times the national rate. That is a reason to look, not a finding."
        )
    elif ratio <= 1 / NOTABLE_RATE_MULTIPLE:
        reading = (
            f"{surfaced_rate:.1%} of this agency's works were surfaced, against "
            f"{national['surfaced_rate']:.1%} nationally — below the ordinary rate."
        )
    else:
        reading = (
            f"{surfaced_rate:.1%} of this agency's works were surfaced, against "
            f"{national['surfaced_rate']:.1%} nationally. That is an ordinary rate: this "
            "agency appears here because of its size and the individual works below, not "
            "because it stands out as a body."
        )

    top = leads.sort_values("audit_roi", ascending=False).head(8)
    cases_by_ref = cases_by_ref or {}

    lead_rows = []
    for row in top.itertuples():
        case = cases_by_ref.get(row.work_ref) or {}
        lead_rows.append({
            "work_ref": str(row.work_ref),
            "description": str(row.work_description)[:160],
            "band": str(row.band),
            "exposure_rupees": float(row.rs_exposure),
            "recommended_amount": float(row.recommended_amount),
            "early_warning": str(row.early_warning_level),
            "signals": [e.get("signal") for e in (case.get("evidence") or [])][:4],
            "next_step": case.get("recommended_next_step", ""),
        })

    # Duplicates *within* this agency are the ones a single visit can settle: the officer
    # is already standing where both works are supposed to be.
    internal_duplicates = []
    if callable(duplicate_pairs):
        # The API passes a lookup rather than the whole table: 223,407 pairs are 248 MB and
        # this needs the handful that sit inside one agency.
        duplicate_pairs = duplicate_pairs(set(mine["work_ref"]))
    if duplicate_pairs is not None and not duplicate_pairs.empty:
        refs = set(mine["work_ref"])
        columns = set(duplicate_pairs.columns)
        if {"work_ref_a", "work_ref_b"} <= columns:
            pairs = duplicate_pairs[
                duplicate_pairs["work_ref_a"].isin(refs)
                & duplicate_pairs["work_ref_b"].isin(refs)
            ].sort_values("similarity", ascending=False).head(10)
            internal_duplicates = [
                {
                    "a": str(row.work_ref_a),
                    "b": str(row.work_ref_b),
                    "similarity": round(float(row.similarity), 3),
                    "classification": str(row.classification),
                    "description": str(row.description_a)[:120],
                }
                for row in pairs.itertuples()
            ]

    # What officers actually found here, which outranks anything the model says.
    #
    # Seeded walkthrough records are shown rather than hidden — an officer arriving at an
    # agency should see everything on the file — but they are marked, because the one thing
    # that must never happen is a demo record being quoted in a real briefing as though a
    # real person had stood there.
    history = [
        {"work_ref": v["work_ref"], "outcome": v["outcome"], "actor": v["actor"],
         "when": str(v.get("created_at", ""))[:10], "notes": v.get("notes", ""),
         "demo": bool(int(v.get("demo", 0) or 0))}
        for v in (verifications or [])
        if v.get("work_ref") in set(mine["work_ref"])
    ]

    open_rate = float(mine["is_open"].mean())
    median_duration = (
        float(mine.loc[mine["is_completed"] == 1, "duration_days"].median())
        if int(mine["is_completed"].sum()) else None
    )

    return {
        "available": True,
        "implementing_agency": agency,
        "states": sorted({str(s) for s in mine["state_name"].unique()}),
        "constituencies": sorted({str(c) for c in mine["constituency"].unique()})[:12],
        "portfolio": {
            "works": works,
            "recommended_rupees": float(mine["recommended_amount"].sum()),
            "median_work_rupees": float(mine["recommended_amount"].median()),
            "national_median_work_rupees": national["median_amount"],
            "open": int(mine["is_open"].sum()),
            "completed": int(mine["is_completed"].sum()),
            "open_rate": round(open_rate, 3),
            "national_open_rate": round(national["open_rate"], 3),
            "median_completed_days": median_duration,
            "categories": [
                {"category": str(name), "works": int(count)}
                for name, count in mine["activity_category"].value_counts().head(6).items()
            ],
        },
        "surfaced": {
            "leads": int(len(leads)),
            "high": int((mine["band"] == "HIGH").sum()),
            "medium": int((mine["band"] == "MEDIUM").sum()),
            "exposure_rupees": float(leads["rs_exposure"].sum()),
            "rate": round(surfaced_rate, 4),
            "national_rate": round(national["surfaced_rate"], 4),
            "rate_multiple": round(ratio, 2) if comparable else None,
            "comparable": comparable,
            "reading": reading,
            "compliance_flags": int(mine["compliance_flags"].sum()),
        },
        "top_leads": lead_rows,
        "internal_duplicates": internal_duplicates,
        "field_history": history,
        "field_history_note": (
            "What an officer recorded on site, including visits that found nothing wrong. "
            "These outrank the model: they are the only ground truth this system has."
            if history else
            "No one has recorded a site visit at this agency yet. The first officer who "
            "does creates the first ground truth this system has about it."
        ),
        "contract": (
            "A briefing on a body that implements public works. Nothing here is a finding "
            "against the agency or anyone in it; the individual works below are "
            "investigation leads that a human decides what to do with."
        ),
    }
