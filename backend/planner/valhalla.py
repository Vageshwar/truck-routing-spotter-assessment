"""Client for the Valhalla routing engine (truck profile).

Uses the free public server run by FOSSGIS by default. It has no API key and
asks for fair use, so we send a User-Agent that says who we are and cache
results upstream.
"""

import os

import httpx

from .geo import LatLon, decode_polyline
from .routes import Route, Step, accumulate_steps

VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de")
USER_AGENT = "truck-routing-spotter-assessment (+https://github.com/Vageshwar/truck-routing-spotter-assessment)"
TIMEOUT_S = 30

# Valhalla wants the gross vehicle weight (it checks bridge and road limits),
# but the user enters the payload. We add a typical empty tractor + 53 ft
# trailer. The risk rules still use the payload only.
EMPTY_TRUCK_LB = 35_000
LB_PER_METRIC_TON = 2204.62


class RoutingError(Exception):
    pass


def build_request(
    origin: LatLon,
    destination: LatLon,
    load_lb: float,
    alternates: int = 2,
    via: LatLon | None = None,
) -> dict:
    stops = [origin, via, destination] if via else [origin, destination]
    locations = [{"lat": lat, "lon": lon} for lat, lon in stops]
    if via:
        # "through" means pass by this point without stopping there
        locations[1]["type"] = "through"

    gross_tons = (EMPTY_TRUCK_LB + load_lb) / LB_PER_METRIC_TON
    return {
        "locations": locations,
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(gross_tons, 2)}},
        "alternates": alternates,
        "units": "miles",
        # we only need lengths and times per maneuver, not instruction text
        "directions_type": "maneuvers",
    }


def parse_response(data: dict, source: str = "valhalla") -> list[Route]:
    """The main trip plus any alternates, each as a Route."""
    trips = [data["trip"]] + [alt["trip"] for alt in data.get("alternates", [])]
    return [_parse_trip(trip, f"{source}-{n}", source) for n, trip in enumerate(trips)]


def _parse_trip(trip: dict, route_id: str, source: str) -> Route:
    # A trip with a via point has one leg per part. Each leg's shape starts
    # where the previous one ended, so we drop that repeated first point and
    # shift the leg's maneuver indices to match the joined line.
    points: list[LatLon] = []
    steps: list[Step] = []
    for leg in trip["legs"]:
        shape = decode_polyline(leg["shape"], precision=6)
        offset = len(points) - 1 if points else 0
        points.extend(shape[1:] if points else shape)
        for m in leg["maneuvers"]:
            steps.append(
                Step(
                    begin=m["begin_shape_index"] + offset,
                    end=m["end_shape_index"] + offset,
                    length_mi=m["length"],
                    time_s=m["time"],
                )
            )

    cum_mi, cum_s = accumulate_steps(points, steps)
    return Route(route_id=route_id, source=source, points=points, cum_mi=cum_mi, cum_s=cum_s)


def fetch_routes(
    origin: LatLon,
    destination: LatLon,
    load_lb: float,
    alternates: int = 2,
    via: LatLon | None = None,
) -> list[Route]:
    body = build_request(origin, destination, load_lb, alternates=alternates, via=via)
    try:
        response = httpx.post(
            f"{VALHALLA_URL}/route",
            json=body,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise RoutingError(f"Valhalla request failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200:
        message = data.get("error", response.text[:200])
        raise RoutingError(f"Valhalla returned {response.status_code}: {message}")
    return parse_response(data)
