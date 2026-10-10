"""Always try to end up with 3 different routes.

1. Valhalla truck routing with 2 alternates (the best source, truck aware).
2. If that gives fewer than 3, add OSRM car routes that are actually different.
3. If still short, ask Valhalla for a truck route forced through a point off
   to the left or right of the main route's midpoint.

In testing, short trips (Dallas to Oklahoma City) get only 1 route from both
engines, so step 3 is what gives those trips real options.
"""

import math
from dataclasses import replace

from . import osrm, valhalla
from .geo import LatLon, haversine_mi
from .routes import Route, point_at
from .valhalla import RoutingError

TARGET_ROUTES = 3
ROUTE_IDS = "ABC"

# Two routes that share this much of their path count as the same route.
MAX_OVERLAP = 0.85
# A point of one route within this distance of the other counts as shared.
SHARED_WITHIN_MI = 1.0
# Skip detours that are much longer than the main route.
MAX_DETOUR_RATIO = 1.5
# How far the via point sits from the main route, as a share of the
# straight-line trip length, kept between a minimum and maximum.
VIA_OFFSET_SHARE = 0.2
VIA_OFFSET_MIN_MI = 15
VIA_OFFSET_MAX_MI = 120


def get_route_options(origin: LatLon, destination: LatLon, load_lb: float) -> list[Route]:
    routes = valhalla.fetch_routes(origin, destination, load_lb)
    main = routes[0]

    if len(routes) < TARGET_ROUTES:
        try:
            _add_if_different(routes, osrm.fetch_routes(origin, destination), main)
        except RoutingError:
            pass  # a fallback failing is not fatal, we try the via points next

    for via in via_points(main, origin, destination):
        if len(routes) >= TARGET_ROUTES:
            break
        try:
            detour = valhalla.fetch_routes(origin, destination, load_lb, alternates=0, via=via)
        except RoutingError:
            continue  # e.g. the via point is not near any road
        _add_if_different(routes, [replace(r, source="valhalla-via") for r in detour], main)

    return [replace(r, route_id=ROUTE_IDS[i]) for i, r in enumerate(routes[:TARGET_ROUTES])]


def _add_if_different(routes: list[Route], candidates: list[Route], main: Route) -> None:
    for candidate in candidates:
        if len(routes) >= TARGET_ROUTES:
            return
        if candidate.distance_mi > main.distance_mi * MAX_DETOUR_RATIO:
            continue
        if all(overlap(candidate, existing) < MAX_OVERLAP for existing in routes):
            routes.append(candidate)


def overlap(a: Route, b: Route, samples: int = 50) -> float:
    """Share of route a (by sampled points) that runs along route b."""
    b_points = _every_mile(b)
    hits = 0
    for k in range(samples):
        p = point_at(a, a.distance_mi * k / (samples - 1))
        if any(haversine_mi((p.lat, p.lon), q) <= SHARED_WITHIN_MI for q in b_points):
            hits += 1
    return hits / samples


def _every_mile(route: Route) -> list[LatLon]:
    # Route lines have thousands of points; one per mile is enough to compare.
    count = max(int(route.distance_mi), 1)
    return [
        (c.lat, c.lon)
        for c in (point_at(route, route.distance_mi * k / count) for k in range(count + 1))
    ]


def via_points(main: Route, origin: LatLon, destination: LatLon) -> list[LatLon]:
    """Two points beside the middle of the main route, one on each side.

    "Sideways" means perpendicular to the straight line from origin to
    destination. Over a few hundred miles a flat-earth approximation
    (69 miles per degree of latitude) is accurate enough for this.
    """
    mid = point_at(main, main.distance_mi / 2)
    straight = haversine_mi(origin, destination)
    offset = min(max(straight * VIA_OFFSET_SHARE, VIA_OFFSET_MIN_MI), VIA_OFFSET_MAX_MI)

    miles_per_lon = 69.0 * math.cos(math.radians(mid.lat))
    north = (destination[0] - origin[0]) * 69.0
    east = (destination[1] - origin[1]) * miles_per_lon
    length = math.hypot(north, east) or 1.0
    # rotate the trip direction 90 degrees to the left
    left_north, left_east = east / length, -north / length

    return [
        (
            mid.lat + side * left_north * offset / 69.0,
            mid.lon + side * left_east * offset / miles_per_lon,
        )
        for side in (1, -1)
    ]
