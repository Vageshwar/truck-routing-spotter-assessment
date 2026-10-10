"""Routes, and checkpoints placed along them.

A Route keeps, for every point on its line, how far along the route that point
is (miles) and how long the truck takes to get there (seconds after
departure). With those two lists, finding where the truck is at mile 75 and
when it gets there is a lookup plus a linear interpolation.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from .geo import LatLon, haversine_mi

SAMPLING_INTERVALS_MI = (10, 25, 50)


@dataclass(frozen=True)
class Step:
    """A piece of the route as the routing engine reports it (one maneuver).

    It covers the line from points[begin] to points[end] and the engine tells
    us its length and travel time, but not how they split across the points
    in between.
    """

    begin: int
    end: int
    length_mi: float
    time_s: float


@dataclass(frozen=True)
class Route:
    route_id: str
    source: str
    points: list[LatLon]
    cum_mi: list[float]  # miles from the origin at each point
    cum_s: list[float]  # seconds after departure at each point

    @property
    def distance_mi(self) -> float:
        return self.cum_mi[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_s[-1]


def accumulate_steps(points: Sequence[LatLon], steps: Sequence[Step]) -> tuple[list, list]:
    """Spread each step's length and time over its points.

    The engine's per-step length and time already account for road type and
    speed limits, so we keep its totals and only use the geometry to share
    them out: a segment that is 30% of the step's straight-line length gets
    30% of its miles and 30% of its seconds. Speed is assumed constant inside
    one step, which is fine because steps are usually a single road.
    """
    cum_mi = [0.0] * len(points)
    cum_s = [0.0] * len(points)
    for step in steps:
        seg = [haversine_mi(points[i], points[i + 1]) for i in range(step.begin, step.end)]
        total = sum(seg)
        for k, i in enumerate(range(step.begin, step.end)):
            share = seg[k] / total if total > 0 else 1 / len(seg)
            cum_mi[i + 1] = cum_mi[i] + step.length_mi * share
            cum_s[i + 1] = cum_s[i] + step.time_s * share
    return cum_mi, cum_s


def default_interval_mi(distance_mi: float) -> int:
    """Pick the checkpoint spacing from the trip length (the user can change it)."""
    if distance_mi < 300:
        return 10
    if distance_mi <= 1000:
        return 25
    return 50


@dataclass(frozen=True)
class Checkpoint:
    mile: float
    lat: float
    lon: float
    offset_s: float  # seconds after departure


def place_checkpoints(route: Route, interval_mi: float) -> list[Checkpoint]:
    """A checkpoint at the origin, every interval_mi, and at the destination."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")

    # k * interval instead of adding up, so float error doesn't build up
    count = int(route.distance_mi // interval_mi)
    miles = [k * interval_mi for k in range(count + 1)]
    if miles[-1] < route.distance_mi:
        miles.append(route.distance_mi)

    return [_point_at(route, m) for m in miles]


def _point_at(route: Route, mile: float) -> Checkpoint:
    # Index of the last point at or before this mile, kept inside the line so
    # there is always a next point to interpolate towards.
    i = min(bisect_right(route.cum_mi, mile) - 1, len(route.points) - 2)
    i = max(i, 0)
    start, end = route.cum_mi[i], route.cum_mi[i + 1]
    t = (mile - start) / (end - start) if end > start else 0.0

    (lat1, lon1), (lat2, lon2) = route.points[i], route.points[i + 1]
    return Checkpoint(
        mile=mile,
        lat=lat1 + (lat2 - lat1) * t,
        lon=lon1 + (lon2 - lon1) * t,
        offset_s=route.cum_s[i] + (route.cum_s[i + 1] - route.cum_s[i]) * t,
    )
