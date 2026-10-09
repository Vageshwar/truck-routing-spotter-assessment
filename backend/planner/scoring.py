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

The order is strict, as the brief gives it: one fewer Severe mile beats any
amount of saved time. Travel time only decides when everything above it ties.
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


CRITERIA = (
    Criterion("No Travel miles", lambda r: r.no_travel_mi),
    Criterion("Severe miles", lambda r: r.severe_mi),
    Criterion("High miles", lambda r: r.high_mi),
    Criterion("average risk", lambda r: r.avg_risk),
    Criterion("travel time (s)", lambda r: r.duration_s),
)


def _sort_key(route: RouteSummary) -> tuple[float, ...]:
    # Rounding keeps float noise (e.g. 12.500000001 vs 12.5) from deciding.
    return tuple(round(c.value(route), 6) for c in CRITERIA)


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


def recommend(routes: Sequence[RouteSummary]) -> Recommendation:
    if not routes:
        raise ValueError("no routes to recommend from")

    # sorted() is stable, so routes that tie on every criterion keep input order.
    ranked = sorted(routes, key=_sort_key)
    winner = ranked[0]
    winner_key = _sort_key(winner)

    eliminations = []
    for route in ranked[1:]:
        key = _sort_key(route)
        # The first criterion where a route differs from the winner is where it lost.
        for criterion, value, best in zip(CRITERIA, key, winner_key, strict=True):
            if value != best:
                eliminations.append(Elimination(route.route_id, criterion.name, value, best))
                break
        else:
            eliminations.append(
                Elimination(route.route_id, "tie (input order)", key[-1], winner_key[-1])
            )

    return Recommendation(
        ranking=[r.route_id for r in ranked],
        eliminations=eliminations,
        all_routes_no_travel=all(r.has_no_travel for r in routes),
    )
