"""Client for OSRM, used as a fallback when Valhalla returns fewer than 3 routes.

The public OSRM demo server only has a car profile, so these routes are marked
as car routes in the UI.
"""

import os

import httpx

from .cache import cached
from .geo import LatLon, decode_polyline
from .routes import Route, Step, accumulate_steps
from .valhalla import TIMEOUT_S, USER_AGENT, RoutingError

OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
METERS_PER_MILE = 1609.344
CACHE_TTL_S = 60 * 60


def build_url(origin: LatLon, destination: LatLon) -> str:
    # OSRM wants lon,lat order
    coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    return f"{OSRM_URL}/route/v1/driving/{coords}"


PARAMS = {
    "alternatives": 3,
    "overview": "full",
    "geometries": "polyline6",
    # per-segment distance and duration, so ETAs work the same way as Valhalla
    "annotations": "distance,duration",
    "steps": "false",
}


def parse_response(data: dict, source: str = "osrm") -> list[Route]:
    routes = []
    for n, raw in enumerate(data["routes"]):
        points = decode_polyline(raw["geometry"], precision=6)
        steps = []
        offset = 0
        for leg in raw["legs"]:
            ann = leg["annotation"]
            # each annotation entry is the segment from point i to i+1
            for i, (meters, seconds) in enumerate(
                zip(ann["distance"], ann["duration"], strict=True)
            ):
                steps.append(Step(offset + i, offset + i + 1, meters / METERS_PER_MILE, seconds))
            offset += len(ann["distance"])
        cum_mi, cum_s = accumulate_steps(points, steps)
        routes.append(Route(f"{source}-{n}", source, points, cum_mi, cum_s))
    return routes


def fetch_routes(origin: LatLon, destination: LatLon) -> list[Route]:
    def compute():
        try:
            response = httpx.get(
                build_url(origin, destination),
                params=PARAMS,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_S,
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RoutingError(f"OSRM request failed: {exc}") from exc
        if data.get("code") != "Ok":
            raise RoutingError(f"OSRM returned {data.get('code')}: {data.get('message', '')}")
        return parse_response(data)

    return cached("osrm", [origin, destination], CACHE_TTL_S, compute)
