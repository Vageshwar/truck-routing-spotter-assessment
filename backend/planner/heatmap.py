"""Forecast risk on a grid around the routes, for every hour from departure
to 48 hours after.

The grid is a fixed lattice (0.25 degrees, about 17 miles), keeping only the
points within 20 miles of a route. A full bounding box would be thousands of
points on a long trip, and Open-Meteo's free tier counts every point as a
call. A fixed lattice also means the same points come back for similar trips,
so the cache gets reused.
"""

import math
from datetime import datetime, timedelta

from . import weather
from .geo import LatLon, haversine_mi
from .risk import risk_score
from .route_options import get_route_options
from .routes import Route, point_at

CORRIDOR_MI = 20
MAX_POINTS = 400
# Tried in order until the grid fits under MAX_POINTS.
GRID_STEPS_DEG = (0.25, 0.5, 1.0)
SAMPLE_EVERY_MI = 5
HOURS_AHEAD = 48


def _lattice(low: float, high: float, step: float) -> list[float]:
    return [round(k * step, 4) for k in range(math.ceil(low / step), math.floor(high / step) + 1)]


def corridor_cells(routes: list[Route], step_deg: float) -> list[LatLon]:
    """Lattice points within CORRIDOR_MI of any route."""
    cells = set()
    for route in routes:
        samples = int(route.distance_mi // SAMPLE_EVERY_MI) + 1
        for k in range(samples + 1):
            p = point_at(route, min(k * SAMPLE_EVERY_MI, route.distance_mi))
            dlat = CORRIDOR_MI / 69.0
            dlon = CORRIDOR_MI / (69.0 * math.cos(math.radians(p.lat)))
            for lat in _lattice(p.lat - dlat, p.lat + dlat, step_deg):
                for lon in _lattice(p.lon - dlon, p.lon + dlon, step_deg):
                    if (lat, lon) not in cells and haversine_mi(
                        (p.lat, p.lon), (lat, lon)
                    ) <= CORRIDOR_MI:
                        cells.add((lat, lon))
    return sorted(cells)


def build_grid(routes: list[Route]) -> tuple[float, list[LatLon]]:
    for step in GRID_STEPS_DEG:
        cells = corridor_cells(routes, step)
        if len(cells) <= MAX_POINTS:
            return step, cells
    return step, cells


def heatmap(routes: list[Route], depart_at: datetime, load_lb: float) -> dict:
    step, cells = build_grid(routes)
    times = [depart_at + timedelta(hours=h) for h in range(HOURS_AHEAD + 1)]
    hours = [weather.forecast_hour(t) for t in times]

    readings = weather.get_readings([(cell, hour) for cell in cells for hour in hours])

    scores = []
    for i in range(len(cells)):
        row = readings[i * len(hours) : (i + 1) * len(hours)]
        # scores are sent as whole numbers 0-40 (score x 10) to keep the JSON small
        scores.append(
            [round(10 * risk_score(r.wind_mph, r.rain_in_hr, r.snow_in_hr, load_lb)) for r in row]
        )

    return {
        "step_deg": step,
        "times": [t.isoformat() for t in times],
        "points": [[lon, lat] for lat, lon in cells],
        "scores": scores,
    }


def heatmap_for_trip(
    origin: LatLon, destination: LatLon, depart_at: datetime, load_lb: float
) -> dict:
    # Same routes as /api/plan; they come from the cache when the plan ran first.
    return heatmap(get_route_options(origin, destination, load_lb), depart_at, load_lb)
