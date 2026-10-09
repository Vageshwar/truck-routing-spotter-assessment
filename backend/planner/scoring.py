"""Route totals and the route recommendation.

Each checkpoint stands for the stretch of road halfway back to the previous
checkpoint and halfway on to the next one (midpoint split). That way every
mile of the route is counted exactly once, and a shorter last stretch to the
destination is handled for free.

Routes are ranked with the order from the brief, plus No Travel miles first:

    0. fewest No Travel miles
    1. fewest Severe miles
    2. fewest High miles
    3. lowest average risk (mile weighted, Low=0 ... No Travel=4)
    4. shortest travel time

Values within a criterion's tolerance count as a tie and fall through to the
next criterion. The tolerances absorb noise from checkpoint spacing, so a
route that is 2 Severe miles "worse" but 3 hours faster can still win.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from .risk import RiskLevel


def allocate_miles(positions_mi: Sequence[float]) -> list[float]:
    """Miles each checkpoint covers, given its distance from the origin.

    positions_mi must be ascending, starting at the origin (0) and ending at
    the destination.
    """
    if any(b < a for a, b in pairwise(positions_mi)):
        raise ValueError("checkpoint positions must be in ascending order")

    last = len(positions_mi) - 1
    miles = []
    for i, pos in enumerate(positions_mi):
        start = positions_mi[0] if i == 0 else (positions_mi[i - 1] + pos) / 2
        end = positions_mi[-1] if i == last else (pos + positions_mi[i + 1]) / 2
        miles.append(end - start)
    return miles


@dataclass(frozen=True)
class RouteSummary:
    route_id: str
    distance_mi: float
    duration_s: float
    miles_by_level: dict[RiskLevel, float]
    avg_risk: float

    @property
    def no_travel_mi(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL]

    @property
    def severe_mi(self) -> float:
        return self.miles_by_level[RiskLevel.SEVERE]

    @property
    def high_mi(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH]

    @property
    def has_no_travel(self) -> bool:
        return self.no_travel_mi > 0


def summarize_route(
    route_id: str,
    positions_mi: Sequence[float],
    levels: Sequence[RiskLevel],
    duration_s: float,
) -> RouteSummary:
    if len(positions_mi) != len(levels):
        raise ValueError("need exactly one risk level per checkpoint")
    if not levels:
        raise ValueError("a route needs at least one checkpoint")

    miles = allocate_miles(positions_mi)
    miles_by_level = dict.fromkeys(RiskLevel, 0.0)
    for level, mi in zip(levels, miles, strict=True):
        miles_by_level[level] += mi

    total = sum(miles)
    if total > 0:
        avg_risk = sum(level * mi for level, mi in zip(levels, miles, strict=True)) / total
    else:
        avg_risk = float(max(levels))

    return RouteSummary(
        route_id=route_id,
        distance_mi=total,
        duration_s=duration_s,
        miles_by_level=miles_by_level,
        avg_risk=avg_risk,
    )


@dataclass(frozen=True)
class Criterion:
    name: str
    value: Callable[[RouteSummary], float]
    tolerance: float


CRITERIA = (
    Criterion("No Travel miles", lambda r: r.no_travel_mi, tolerance=0.0),
    Criterion("Severe miles", lambda r: r.severe_mi, tolerance=5.0),
    Criterion("High miles", lambda r: r.high_mi, tolerance=5.0),
    Criterion("average risk", lambda r: r.avg_risk, tolerance=0.1),
    Criterion("travel time (s)", lambda r: r.duration_s, tolerance=0.0),
)

# Guards against float noise when a tolerance is 0.
_EPSILON = 1e-9


@dataclass(frozen=True)
class Elimination:
    """Why a route lost to the recommended one."""

    route_id: str
    criterion: str
    value: float
    best: float


@dataclass(frozen=True)
class Recommendation:
    ranking: list[str]  # route ids, best first
    eliminations: list[Elimination]  # one per route that is not the winner
    all_routes_no_travel: bool


def _pick_best(routes: Sequence[RouteSummary]) -> tuple[RouteSummary, list[Elimination]]:
    """Filter routes criterion by criterion until one is left.

    At each step, keep only routes within tolerance of the best value among
    the routes still in the running. Filtering (instead of sorting with a
    fuzzy compare) keeps the result consistent: a fuzzy "equal" is not
    transitive, so a sort could give different answers for the same input.
    If routes are still tied at the end, the earliest one in the input wins.
    """
    remaining = list(routes)
    eliminated = []
    for criterion in CRITERIA:
        best = min(criterion.value(r) for r in remaining)
        limit = best + criterion.tolerance + _EPSILON
        kept = []
        for route in remaining:
            value = criterion.value(route)
            if value <= limit:
                kept.append(route)
            else:
                eliminated.append(Elimination(route.route_id, criterion.name, value, best))
        remaining = kept
        if len(remaining) == 1:
            break
    return remaining[0], eliminated


def recommend(routes: Sequence[RouteSummary]) -> Recommendation:
    if not routes:
        raise ValueError("no routes to recommend from")

    winner, eliminations = _pick_best(routes)

    # Rank the rest by running the same selection on what is left.
    ranking = [winner.route_id]
    remaining = [r for r in routes if r is not winner]
    while remaining:
        best, _ = _pick_best(remaining)
        ranking.append(best.route_id)
        remaining = [r for r in remaining if r is not best]

    # A route that was still tied with the winner when the criteria ran out
    # never gets an elimination record, so note that it lost on input order.
    explained = {e.route_id for e in eliminations}
    for route in routes:
        if route is not winner and route.route_id not in explained:
            eliminations.append(
                Elimination(
                    route.route_id, "tie (input order)", route.duration_s, winner.duration_s
                )
            )

    return Recommendation(
        ranking=ranking,
        eliminations=eliminations,
        all_routes_no_travel=all(r.has_no_travel for r in routes),
    )
