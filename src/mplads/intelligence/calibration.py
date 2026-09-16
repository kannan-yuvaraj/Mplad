"""Has the model been right? The scoreboard that is allowed to say no.

Everything else here explains *why* a work was surfaced. This asks the only question that
ever settles it: when an officer actually went, what did they find — and did the works we
called HIGH turn out worse than the ones we called MEDIUM?

That is a scoreboard the system can lose on, which is the entire reason it exists. A
monitoring product with no way of being wrong is a product that will be wrong quietly.

**Three disciplines, all of which cost us numbers we would rather have printed.**

1. **A rate needs a denominator worth dividing by.** Below `MIN_VISITS_FOR_A_RATE` the
   count is reported and the percentage is refused. Three visits and two confirmations is
   not "67% precision"; it is three visits.
2. **Every rate carries an interval.** A Wilson score interval, which behaves at small n
   and near 0 and 1 where the textbook normal interval produces bounds outside [0, 1].
   Where the intervals for two bands overlap, the ordering between them is not evidence,
   and this module says so rather than letting a bar chart imply it.
3. **The sample is not random and never will be.** Officers go where they are sent, and
   they are sent by this model. So the works that were never surfaced are barely visited
   at all, and precision measured on a set the model chose is not precision on the
   portfolio. This is why a work that was never surfaced still returns a case file and can
   still be verified — without those visits there is no negative class, and a scoreboard
   without a negative class can only ever agree with itself.

Nothing here refits anything. `field.label_readiness()` counts how far the record still is
from the point where the fusion weights could honestly be fitted; until then these are
observations, not a correction.
"""

from __future__ import annotations

import logging
import math
from typing import Any

LOGGER = logging.getLogger(__name__)

#: Below this many visits in a band, the count stands on its own and no rate is computed.
#: Small enough to say something during a pilot; large enough that one officer's fortnight
#: cannot set the headline.
MIN_VISITS_FOR_A_RATE = 10

#: Bands in the order the model claims they should rank. The claim being tested is that
#: this order survives contact with what officers found.
BAND_ORDER = ["HIGH", "MEDIUM", "NOT SURFACED"]


def _wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Used rather than the normal approximation because the counts here are small and the
    proportions sit near the ends, which is exactly where the normal interval returns
    bounds below zero or above one and stops being a statement about anything.
    """
    if trials <= 0:
        return (0.0, 1.0)
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = phat + z * z / (2 * trials)
    spread = z * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials))
    return (max(0.0, (centre - spread) / denominator),
            min(1.0, (centre + spread) / denominator))


#: Public alias. The map compares each state's rate against the national one and
#: must use the same interval this screen does — a second implementation would
#: eventually disagree with this one, and then two screens would be making
#: different claims from the same counts.
wilson = _wilson


def build(verifications: list[dict[str, Any]],
          bands: dict[str, str],
          confirms_concern: set[str],
          include_demo: bool = False) -> dict[str, Any]:
    """Compare what officers found against the band each work was surfaced with.

    `bands` maps work reference to the band the model gave it; a work absent from that map
    was never surfaced, and is counted under "NOT SURFACED" — the negative class, and the
    half of this table that is hardest to collect.
    """
    real = [
        v for v in verifications
        if include_demo or not int(v.get("demo", 0) or 0)
    ]
    seeded = len(verifications) - len(real)

    # One work, one verdict: the newest verification supersedes the earlier ones, because a
    # correction here is a new record rather than an edit. Counting both would let a single
    # revisited work vote twice.
    latest: dict[str, dict[str, Any]] = {}
    for record in sorted(real, key=lambda v: (str(v.get("created_at", "")), v.get("id", 0))):
        latest[record["work_ref"]] = record

    rows = []
    for band in BAND_ORDER:
        visited = [
            record for ref, record in latest.items()
            if (bands.get(ref) or "NOT SURFACED").upper() == band
        ]
        confirmed = sum(1 for r in visited if r["outcome"] in confirms_concern)
        cleared = len(visited) - confirmed
        enough = len(visited) >= MIN_VISITS_FOR_A_RATE
        low, high = _wilson(confirmed, len(visited)) if enough else (None, None)
        rows.append({
            "band": band,
            "visits": len(visited),
            "concerns_confirmed": confirmed,
            "cleared": cleared,
            "rate": round(confirmed / len(visited), 3) if enough else None,
            "interval": [round(low, 3), round(high, 3)] if enough else None,
            "reportable": enough,
            "note": (
                None if enough else
                f"{len(visited)} visit(s). A rate is not reported below "
                f"{MIN_VISITS_FOR_A_RATE}; the count is the honest figure."
            ),
        })

    reportable = [row for row in rows if row["reportable"]]
    ordering = _ordering(reportable)

    total = len(latest)
    return {
        "available": True,
        "visits": total,
        "works_visited": total,
        "demo_records_excluded": seeded,
        "superseded_records_excluded": len(real) - total,
        "min_visits_for_a_rate": MIN_VISITS_FOR_A_RATE,
        "bands": rows,
        "ordering": ordering,
        "outcomes": _outcomes(latest.values()),
        "sampling_caveat": (
            "Officers go where this model sends them, so these visits are not a random "
            "sample of the portfolio. Works that were never surfaced are the negative "
            "class and are barely represented — which is why a work with a clear record "
            "still gets a case file and can still be verified. Until that column fills "
            "in, this table shows how the surfaced works behaved, not how well the model "
            "separates the portfolio."
        ),
        "contract": (
            "Observations from completed site visits. Nothing is refitted from them: the "
            "fusion weights stay at the reasoned defaults until there are enough records "
            "to fit honestly, and no accuracy is claimed before then."
        ),
    }


def _ordering(reportable: list[dict[str, Any]]) -> dict[str, Any]:
    """Does the band order survive what officers found — and is the gap real?

    Two bands whose intervals overlap are not ranked by this evidence, however different
    their point estimates look on a chart. Saying that out loud is the difference between
    a scoreboard and a decoration.
    """
    if len(reportable) < 2:
        return {
            "testable": False,
            "holds": None,
            "note": (
                "At least two bands need enough visits before their order can be checked. "
                "Nothing is claimed about the ranking yet."
            ),
        }

    ranked = sorted(reportable, key=lambda r: BAND_ORDER.index(r["band"]))
    holds = all(
        ranked[i]["rate"] >= ranked[i + 1]["rate"] for i in range(len(ranked) - 1)
    )
    separated = all(
        ranked[i]["interval"][0] > ranked[i + 1]["interval"][1]
        for i in range(len(ranked) - 1)
    )
    if holds and separated:
        note = ("The bands rank in the order the model claims, and their intervals do not "
                "overlap. On the works visited so far, the ranking is doing real work.")
    elif holds:
        note = ("The point estimates rank in the claimed order, but the intervals overlap. "
                "That is consistent with the ranking working and also with it not working; "
                "more visits would separate them.")
    else:
        note = ("The bands did not rank in the claimed order on the works visited so far. "
                "That is a finding about this system, and it is reported rather than "
                "smoothed over.")

    return {"testable": True, "holds": holds, "separated": separated,
            "order": [row["band"] for row in ranked], "note": note}


def _outcomes(records) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["outcome"]] = counts.get(record["outcome"], 0) + 1
    return [{"outcome": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda kv: -kv[1])]
