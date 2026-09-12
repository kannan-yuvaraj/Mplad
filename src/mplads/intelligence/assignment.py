"""Turning a budgeted audit plan into people's working weeks.

`targeting.py` answers *"where should the auditor-days go?"*. It stops one step short of
what a supervising officer actually has to produce on a Monday morning, which is a name
against every trip:

    "I have four auditors and a fortnight. Who goes where, and on which day?"

That is a different problem again, and it has one constraint that makes it interesting.

**An agency is never split between two auditors.** The entire saving the plan is built on
is that the second work at an agency costs a fraction of a day because someone is already
standing there. Send two auditors to the same agency and that discount is paid twice and
earned once — the plan's arithmetic quietly stops being true. So the unit of assignment is
the *trip*, not the work: an agency and everything the plan chose there, priced exactly as
the plan priced it.

**How the trips are dealt out.** Longest-processing-time first: sort the trips by length,
hand each in turn to whoever is currently least loaded. LPT is not optimal — multiprocessor
scheduling is NP-hard, like the selection problem it follows — but it carries a proved
worst-case bound of (4/3 - 1/(3m)) of the best possible longest day, so the imbalance is
bounded rather than merely hoped for. The bound and the achieved spread are both reported,
because a rota that claims to be balanced and is not will be found out in week one.

**What this does not do.** It does not know who is on leave, who has a car, which two
districts are actually adjacent, or which officer already has a relationship with an
agency. It produces a draft rota for a supervisor to amend. The one thing it is careful
about is not proposing something that silently costs more than the plan said it would.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from mplads.intelligence import targeting

LOGGER = logging.getLogger(__name__)

#: The most auditors a rota is offered for. Beyond this the trips run out before the people
#: do, and the answer stops being a rota and starts being a list of idle names.
MAX_AUDITORS = 24


def trips(plan: pd.DataFrame) -> list[dict]:
    """The plan regrouped into indivisible visits, priced exactly as the plan priced them.

    A trip is one implementing agency and every work the plan chose there. Its cost is the
    sum of the costs already assigned — a full day for the arrival and the stated fraction
    for each further work — so a rota built from trips spends precisely the budget the plan
    spent, and no assignment can accidentally re-buy travel the plan had already paid for.
    """
    if plan.empty:
        return []

    grouped = []
    for agency, rows in plan.groupby("implementing_agency", sort=False, observed=True):
        rows = rows.sort_values("plan_order")
        grouped.append({
            "implementing_agency": str(agency),
            "state": str(rows["state_name"].iloc[0]),
            "works": [
                {
                    "work_ref": str(r.work_ref),
                    "band": str(r.band),
                    "exposure_rupees": float(r.rs_exposure),
                    "cost_days": float(r.plan_cost_days),
                }
                for r in rows.itertuples()
            ],
            "work_count": int(len(rows)),
            "cost_days": round(float(rows["plan_cost_days"].sum()), 2),
            "exposure_rupees": float(rows["rs_exposure"].sum()),
            "first_order": int(rows["plan_order"].min()),
        })

    grouped.sort(key=lambda t: (-t["cost_days"], -t["exposure_rupees"],
                                t["implementing_agency"]))
    return grouped


def _days(trip_list: list[dict]) -> list[dict]:
    """Lay one auditor's trips out against calendar days.

    A trip costing 2.4 days spans three of them; the next trip starts the morning after,
    because an auditor does not begin a second agency at four in the afternoon in a
    district they still have to reach. That rounding is why an auditor's calendar is longer
    than the auditor-days they spend, and both numbers are reported rather than the
    flattering one.
    """
    schedule = []
    day = 1
    for trip in trip_list:
        span = max(1, math.ceil(trip["cost_days"] - 1e-9))
        schedule.append({
            "day_from": day,
            "day_to": day + span - 1,
            "implementing_agency": trip["implementing_agency"],
            "state": trip["state"],
            "works": trip["works"],
            "work_count": trip["work_count"],
            "cost_days": trip["cost_days"],
            "exposure_rupees": trip["exposure_rupees"],
        })
        day += span
    return schedule


def assign(plan: pd.DataFrame, auditors: int = 4) -> dict:
    """Deal a plan's trips out to a team, keeping every agency whole.

    Longest trip first, to whoever is least loaded. Placing the long trips while there is
    still room for them is what stops the last auditor being handed a three-day visit on
    top of a full week; dealing them in arrival order is the classic way to produce a rota
    where one person carries a fortnight and everyone else carries three days.
    """
    auditors = max(1, min(int(auditors), MAX_AUDITORS))
    all_trips = trips(plan)

    if not all_trips:
        return {"available": False, "auditors": auditors,
                "note": "the plan is empty, so there is nothing to allocate"}

    rota: list[dict] = [
        {"auditor": index + 1, "trips": [], "days": 0.0, "works": 0, "exposure": 0.0}
        for index in range(auditors)
    ]

    for trip in all_trips:
        # Least-loaded first; the auditor number breaks ties, so the rota is reproducible.
        target = min(rota, key=lambda a: (a["days"], a["auditor"]))
        target["trips"].append(trip)
        target["days"] = round(target["days"] + trip["cost_days"], 2)
        target["works"] += trip["work_count"]
        target["exposure"] += trip["exposure_rupees"]

    loads = [entry["days"] for entry in rota]
    busiest, quietest = max(loads), min(loads)

    #: Graham's bound for LPT on identical machines. Printed because "balanced" is a claim,
    #: and this is the only honest version of it: the longest round cannot be worse than
    #: this multiple of the best rota anyone could have written.
    bound = round(4 / 3 - 1 / (3 * auditors), 3)

    people = []
    for entry in rota:
        # Highest exposure first inside an auditor's own week: if a fortnight is cut short,
        # what falls off the end should be the least consequential thing on it.
        ordered = sorted(entry["trips"],
                         key=lambda t: (-t["exposure_rupees"], t["implementing_agency"]))
        schedule = _days(ordered)
        people.append({
            "auditor": entry["auditor"],
            "label": f"Auditor {entry['auditor']}",
            "auditor_days": round(entry["days"], 2),
            "calendar_days": schedule[-1]["day_to"] if schedule else 0,
            "agency_visits": len(ordered),
            "works": entry["works"],
            "states": sorted({trip["state"] for trip in ordered}),
            "exposure_rupees": entry["exposure"],
            "schedule": schedule,
        })

    LOGGER.info(
        "assignment: %s trips across %s auditors, busiest %.2f / quietest %.2f days",
        len(all_trips), auditors, busiest, quietest,
    )

    return {
        "available": True,
        "auditors": auditors,
        "trips": len(all_trips),
        "works": int(sum(person["works"] for person in people)),
        "auditor_days": round(sum(loads), 2),
        "exposure_rupees": float(sum(person["exposure_rupees"] for person in people)),
        "balance": {
            "busiest_days": round(busiest, 2),
            "quietest_days": round(quietest, 2),
            "spread_days": round(busiest - quietest, 2),
            "longest_round_days": max((p["calendar_days"] for p in people), default=0),
            "lpt_bound": bound,
            "note": (
                "Trips are dealt longest-first to whoever is least loaded. Balanced "
                "scheduling is NP-hard, so this is a heuristic: its longest round is "
                f"provably within {bound}x the best rota that exists, and the spread it "
                "actually achieved is printed above rather than assumed."
            ),
        },
        "idle": [person["label"] for person in people if person["works"] == 0],
        "people": people,
        "constraint": (
            "An implementing agency is never split between two auditors. The plan's saving "
            f"depends on the second work at an agency costing {targeting.SAME_AGENCY_DAYS} "
            "of a day because someone is already standing there; sending two people would "
            "pay for that arrival twice and the plan's arithmetic would stop being true."
        ),
        "contract": (
            "A draft rota for a supervisor to amend. It does not know who is on leave, "
            "which districts are neighbours, or who already knows an agency — and it "
            "alleges nothing about any work, agency or person."
        ),
    }


def build(works: pd.DataFrame, budget_days: float = targeting.DEFAULT_BUDGET,
          auditors: int = 4, plan: pd.DataFrame | None = None) -> dict:
    """Plan under the budget, then deal the resulting trips out to a team.

    `plan` is accepted because the plan does not depend on the team size at all — dealing
    23 trips to 4 auditors or to 12 uses the same 23 trips. Re-planning per team size cost
    a fresh run of the optimiser on every move of the auditors dial, which is the whole
    wait on this screen; the caller passes the plan it already holds.
    """
    leads = works[works["band"].isin(["HIGH", "MEDIUM"])].copy()
    if leads.empty:
        return {"available": False, "note": "no leads to plan against"}

    if plan is None:
        plan = targeting.optimise(leads, budget_days=budget_days)
    result = assign(plan, auditors=auditors)
    result["budget_days"] = budget_days
    result["per_auditor_days"] = round(budget_days / max(1, auditors), 2)
    return result
