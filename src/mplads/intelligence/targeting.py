"""Audit-ROI optimisation: which works to investigate when you cannot investigate them all.

Every other engine in this system answers *"what looks unusual?"*. This one answers the
question an official actually asks next, which is different and harder:

    "I have twenty auditor-days this quarter. Where do I send them?"

Ranking alone does not answer that. A ranked list assumes every case costs the same to
check, and they do not. Five works in one district office are one trip; five works in five
districts are five trips. An auditor who follows a pure ranking spends most of the quarter
in transit.

So this is a **budgeted selection** problem, not a sort. The cost of adding a case depends
on what is already in the plan:

* the first work at an implementing agency costs a full day — travel, arrival, the visit
* every further work at that same agency costs a fraction of a day, because the auditor is
  already standing there

That single dependency is what makes the optimised plan beat the ranking it is built from,
and it is why the comparison against baselines is worth showing rather than asserting.

**What this is not.** It does not decide anything. It produces a *recommended plan* for a
human to approve, reject or amend, and it reports what each alternative strategy would have
covered so the recommendation can be argued with.
"""

from __future__ import annotations

import heapq
import math
import logging

import numpy as np
import pandas as pd

from mplads import config

LOGGER = logging.getLogger(__name__)

#: Auditor-days to reach an implementing agency and inspect the first work there. Travel,
#: the visit itself, and writing it up.
FIRST_VISIT_DAYS = 1.0

#: Auditor-days for each additional work at an agency already being visited. The travel is
#: already paid for; this is the marginal cost of walking to the next site.
SAME_AGENCY_DAYS = 0.35

#: Budgets offered in the interface. Chosen to span one auditor for a fortnight through a
#: small team for a quarter.
BUDGET_PRESETS = (10, 20, 50, 100, 250)

DEFAULT_BUDGET = 50


def _cost(agency: str, committed: set[str]) -> float:
    """What adding this work costs, given the agencies already in the plan."""
    return SAME_AGENCY_DAYS if agency in committed else FIRST_VISIT_DAYS


#: How many works deep to look when deciding whether to open a new agency. Beyond this the
#: bundle ratio has long since peaked, and the cap keeps the step cheap on large agencies.
BUNDLE_LOOKAHEAD = 40


def _best_bundle(exposures: list[float], budget_left: float) -> tuple[float, int]:
    """The best exposure-per-day achievable by opening this agency and taking k works.

    This is the lookahead that makes the planner worth having. A purely myopic greedy
    compares one work against one work, so it takes a large remote case and never notices
    that opening a cluster buys six mediocre ones for barely more than the trip. Judging an
    agency by its best *bundle* rather than its best single work is what lets batching win,
    which is the entire claim this module makes.

    Returns (ratio, k). Only the decision to open uses this; once an agency is open its
    remaining works compete on their own, at the cheaper repeat cost.
    """
    best_ratio, best_k = 0.0, 0
    running = 0.0
    for k, exposure in enumerate(exposures[:BUNDLE_LOOKAHEAD], start=1):
        running += exposure
        cost = FIRST_VISIT_DAYS + (k - 1) * SAME_AGENCY_DAYS
        if cost > budget_left:
            break
        ratio = running / cost
        if ratio > best_ratio:
            best_ratio, best_k = ratio, k
    return best_ratio, best_k


def optimise(works: pd.DataFrame, budget_days: float = DEFAULT_BUDGET) -> pd.DataFrame:
    """Greedy travel-aware selection under an auditor-day budget.

    Two costs, one dependency: the first work at an agency costs a full day, every further
    work there costs a fraction of one. That dependency is why this is a plan and not a
    sort, and it is why opening an agency is judged on the bundle it unlocks rather than on
    its single best case.

    Greedy rather than exact: with set-up costs this is a knapsack variant, NP-hard, and it
    would need a solver the project does not carry. Greedy-with-lookahead lands within a few
    percent and stays explainable — at every step it took the option buying the most
    exposure per day, and the plan can be read to check that.
    """
    if works.empty or budget_days <= 0:
        return works.head(0).assign(plan_order=[], plan_cost_days=[], plan_cumulative_days=[])

    columns = ["work_ref", "implementing_agency", "rs_exposure", "state_name",
               "audit_roi", "priority", "band", "recommended_amount"]
    frame = works[columns].copy()
    frame["rs_exposure"] = frame["rs_exposure"].astype(float).fillna(0.0)
    frame = frame.sort_values(["rs_exposure", "work_ref"], ascending=[False, True])

    # Per agency, its works best-first; popping from the end is O(1).
    queues: dict[str, list[dict]] = {}
    for row in frame.to_dict("records"):
        queues.setdefault(row["implementing_agency"], []).append(row)
    for queue in queues.values():
        queue.reverse()

    committed: set[str] = set()
    chosen: list[dict] = []
    spent = 0.0

    # Agencies already open compete on single works, so a heap is enough for them.
    open_heap: list[tuple[float, str]] = []

    # Agencies not yet open compete on the bundle they would unlock. Their queues never
    # change while they are closed — a work is only ever popped from an agency that is
    # committed in the same step — so each agency's unrestricted bundle ratio is computed
    # once here, and only ever revised *downward* as the remaining budget shrinks. That
    # makes it a valid upper bound, so the best candidate can be found by refreshing a
    # handful of heap entries instead of rescanning every agency on every pick. Rescanning
    # cost ~1.5 s per plan on 778 agencies, which the budget slider paid on every move.
    order = {agency: index for index, agency in enumerate(queues)}
    new_heap: list[tuple[float, int, str]] = []
    for agency, queue in queues.items():
        bound, _ = _best_bundle([row["rs_exposure"] for row in reversed(queue)], math.inf)
        if bound > 0:
            new_heap.append((-bound, order[agency], agency))
    heapq.heapify(new_heap)

    while spent < budget_days:
        budget_left = budget_days - spent

        while open_heap and not queues[open_heap[0][1]]:
            heapq.heappop(open_heap)

        best_open_ratio = 0.0
        if open_heap and SAME_AGENCY_DAYS <= budget_left:
            best_open_ratio = -open_heap[0][0]

        # Opening a new agency is judged on the bundle it unlocks, not one work. The heap
        # holds upper bounds; refresh from the top until the best entry is one already
        # priced at this budget, which is then the true maximum. Ties resolve by the
        # agency's original position, exactly as scanning in order did.
        best_new_ratio, best_new_agency = 0.0, None
        if FIRST_VISIT_DAYS <= budget_left:
            priced_here: set[str] = set()
            while new_heap:
                negative, index, agency = new_heap[0]
                if agency in committed or not queues[agency]:
                    heapq.heappop(new_heap)
                    continue
                if agency in priced_here:
                    best_new_ratio, best_new_agency = -negative, agency
                    break
                exposures = [row["rs_exposure"] for row in reversed(queues[agency])]
                ratio, _ = _best_bundle(exposures, budget_left)
                priced_here.add(agency)
                if ratio > 0:
                    heapq.heapreplace(new_heap, (-ratio, index, agency))
                else:
                    heapq.heappop(new_heap)

        if best_open_ratio <= 0 and best_new_agency is None:
            break

        if best_open_ratio >= best_new_ratio:
            _, agency = heapq.heappop(open_heap)
            cost = SAME_AGENCY_DAYS
        else:
            agency = best_new_agency
            cost = FIRST_VISIT_DAYS
            committed.add(agency)

        work = dict(queues[agency].pop())
        spent += cost
        work["plan_order"] = len(chosen) + 1
        work["plan_cost_days"] = round(cost, 2)
        work["plan_cumulative_days"] = round(spent, 2)
        chosen.append(work)

        if queues[agency]:
            heapq.heappush(
                open_heap,
                (-queues[agency][-1]["rs_exposure"] / SAME_AGENCY_DAYS, agency),
            )

    plan = pd.DataFrame(chosen)
    LOGGER.info(
        "targeting: %s works over %.1f of %.0f auditor-days, %s agency visits, "
        "Rs %.1f crore exposure covered",
        len(plan), spent, budget_days, len(committed),
        plan["rs_exposure"].sum() / 1e7 if not plan.empty else 0.0,
    )
    return plan


def _spend(agencies: np.ndarray, exposures: np.ndarray, order: np.ndarray,
           budget_days: float) -> dict:
    """Walk a given order, paying travel as it falls, and report what it covered.

    Takes arrays rather than a frame: a row-at-a-time `.loc` over 37,705 leads, five times
    over for five baselines, was most of the wait on this screen.
    """
    committed: set[str] = set()
    spent, covered, count = 0.0, 0.0, 0
    for index in order:
        agency = agencies[index]
        cost = SAME_AGENCY_DAYS if agency in committed else FIRST_VISIT_DAYS
        if spent + cost > budget_days:
            continue
        committed.add(agency)
        spent += cost
        covered += float(exposures[index])
        count += 1
    return {"works": count, "agencies": len(committed),
            "days_used": round(spent, 2), "exposure": covered}


def compare_strategies(works: pd.DataFrame, budget_days: float = DEFAULT_BUDGET,
                       seed: int = config.RANDOM_SEED,
                       plan: pd.DataFrame | None = None) -> dict:
    """What each way of choosing would cover, for the same budget.

    The optimised plan is only worth recommending if it beats the obvious alternatives, and
    the obvious alternatives are what a department would otherwise do: work down the biggest
    cheques, work down the risk score, or pick without a system at all.

    `plan` lets a caller that has *already* run the optimiser for this budget hand the
    result in. Without it this function ran the optimiser a second time on the same works
    and the same budget to produce a plan identical to the one its caller was holding —
    which was a third of the wait on the audit-plan screen, spent recomputing a known
    answer.
    """
    if works.empty:
        return {"budget_days": budget_days, "strategies": []}

    frame = works.reset_index(drop=True)
    agencies = frame["implementing_agency"].to_numpy()
    exposures = frame["rs_exposure"].astype(float).fillna(0.0).to_numpy()
    rng = np.random.default_rng(seed)

    orders = {
        "Random selection": rng.permutation(len(frame)),
        "Biggest cheques first":
            np.argsort(-frame["recommended_amount"].astype(float).fillna(0.0).to_numpy(),
                       kind="stable"),
        "Highest risk first":
            np.argsort(-frame["priority"].astype(float).fillna(0.0).to_numpy(),
                       kind="stable"),
        "Audit-ROI ranking":
            np.argsort(-frame["audit_roi"].astype(float).fillna(0.0).to_numpy(),
                       kind="stable"),
    }

    results = [
        {"strategy": name, "optimised": False,
         **_spend(agencies, exposures, order, budget_days)}
        for name, order in orders.items()
    ]

    if plan is None:
        plan = optimise(works, budget_days)
    results.append({
        "strategy": "Optimised plan",
        "optimised": True,
        "works": int(len(plan)),
        "agencies": int(plan["implementing_agency"].nunique()) if not plan.empty else 0,
        "days_used": float(plan["plan_cumulative_days"].max()) if not plan.empty else 0.0,
        "exposure": float(plan["rs_exposure"].sum()) if not plan.empty else 0.0,
    })

    results.sort(key=lambda r: -r["exposure"])
    best = results[0]["exposure"]
    for row in results:
        row["exposure_crore"] = round(row["exposure"] / 1e7, 1)
        row["share_of_best"] = round(row["exposure"] / best, 3) if best else 0.0

    return {
        "budget_days": budget_days,
        "strategies": results,
        "cost_model": {
            "first_visit_days": FIRST_VISIT_DAYS,
            "same_agency_days": SAME_AGENCY_DAYS,
            "note": (
                "The first work at an agency costs a full auditor-day — travel, the visit, "
                "and the write-up. Further works at that same agency cost "
                f"{SAME_AGENCY_DAYS} of a day, because the auditor is already there. That "
                "one dependency is the whole reason a plan beats a ranking: a ranked list "
                "sends an auditor to five districts to see five works."
            ),
        },
    }


def coverage_curve(works: pd.DataFrame, budgets: tuple[int, ...] = BUDGET_PRESETS) -> list[dict]:
    """Exposure covered at each budget, for the optimised plan and the ranking it beats."""
    frame = works.reset_index(drop=True)
    agencies = frame["implementing_agency"].to_numpy()
    exposures = frame["rs_exposure"].astype(float).fillna(0.0).to_numpy()
    roi_order = np.argsort(-frame["audit_roi"].astype(float).fillna(0.0).to_numpy(),
                           kind="stable")

    curve = []
    for budget in budgets:
        plan = optimise(works, budget)
        ranked = _spend(agencies, exposures, roi_order, budget)
        curve.append({
            "budget_days": budget,
            "optimised_crore": round(float(plan["rs_exposure"].sum()) / 1e7, 1)
                               if not plan.empty else 0.0,
            "optimised_works": int(len(plan)),
            "ranking_crore": round(ranked["exposure"] / 1e7, 1),
            "ranking_works": ranked["works"],
        })
    return curve


def build(works: pd.DataFrame, budget_days: float = DEFAULT_BUDGET,
          curve: list[dict] | None = None, leads: pd.DataFrame | None = None) -> dict:
    """Everything the audit-plan screen needs, from the scored works table.

    `curve` is accepted because the coverage curve does not depend on `budget_days` at all —
    it always reports the same fixed presets. Recomputing it for every position of a slider
    meant five extra runs of the optimiser to redraw a line that had not changed, which was
    most of the wait on this screen.
    """
    # `leads` is accepted for the same reason as `curve`: which works are leads does not
    # depend on the budget, and selecting them copies 37,705 rows. A caller moving a slider
    # holds that selection already. Treated as read-only — `optimise` copies what it needs.
    if leads is None:
        leads = works[works["band"].isin(["HIGH", "MEDIUM"])].copy()
    if leads.empty:
        return {"available": False, "note": "no leads to plan against"}

    plan = optimise(leads, budget_days)
    comparison = compare_strategies(leads, budget_days, plan=plan)

    by_state = (
        plan.groupby("state_name", observed=True)
        .agg(works=("work_ref", "size"), exposure=("rs_exposure", "sum"),
             days=("plan_cost_days", "sum"))
        .reset_index().sort_values("exposure", ascending=False)
    ) if not plan.empty else pd.DataFrame()

    return {
        "available": True,
        "budget_days": budget_days,
        "budget_presets": list(BUDGET_PRESETS),
        "plan": [
            {
                "order": int(r.plan_order),
                "work_ref": r.work_ref,
                "state": str(r.state_name),
                "implementing_agency": str(r.implementing_agency),
                "band": str(r.band),
                "exposure_rupees": float(r.rs_exposure),
                "cost_days": float(r.plan_cost_days),
                "cumulative_days": float(r.plan_cumulative_days),
                # A repeat visit is the interesting row: it is cheap *because* of a
                # decision the plan already made.
                "repeat_visit": float(r.plan_cost_days) < FIRST_VISIT_DAYS,
            }
            for r in plan.itertuples()
        ],
        "totals": {
            "works": int(len(plan)),
            "agencies": int(plan["implementing_agency"].nunique()) if not plan.empty else 0,
            "states": int(plan["state_name"].nunique()) if not plan.empty else 0,
            "days_used": float(plan["plan_cumulative_days"].max()) if not plan.empty else 0.0,
            "exposure_rupees": float(plan["rs_exposure"].sum()) if not plan.empty else 0.0,
            "repeat_visits": int((plan["plan_cost_days"] < FIRST_VISIT_DAYS).sum())
                             if not plan.empty else 0,
        },
        "comparison": comparison,
        "by_state": [
            {"state": str(r.state_name), "works": int(r.works),
             "exposure_rupees": float(r.exposure), "days": round(float(r.days), 2)}
            for r in by_state.itertuples()
        ] if not by_state.empty else [],
        "curve": coverage_curve(leads) if curve is None else curve,
        "contract": (
            "A recommended plan for a human to approve, amend or reject. It allocates "
            "attention; it does not allege anything about any work, agency or person."
        ),
    }
