"""Put it all together: routes, checkpoints, weather, risk and the recommendation.

plan_trip() returns the JSON the frontend draws, so this module is also where
numbers get rounded and route lines get simplified for the map.
"""

from datetime import datetime, timedelta

from . import weather
from .geo import LatLon, simplify
from .risk import Assessment, RiskLevel, assess
from .route_options import get_route_options
from .routes import Checkpoint, Route, default_interval_mi, place_checkpoints, point_at
from .scoring import allocate_miles, recommend, summarize_route
from .valhalla import EMPTY_TRUCK_LB

US_LEGAL_GROSS_LB = 80_000
# about 30 m; a 9,000 point route line becomes about 700 points
SIMPLIFY_TOLERANCE_DEG = 0.0003


def plan_trip(
    origin: LatLon,
    destination: LatLon,
    depart_at: datetime,
    load_lb: float,
    interval_mi: int | None = None,
) -> dict:
    routes = get_route_options(origin, destination, load_lb)
    # One spacing for every route, based on the main route, so the routes
    # are compared on the same terms.
    interval = interval_mi or default_interval_mi(routes[0].distance_mi)

    checkpoints = {r.route_id: place_checkpoints(r, interval) for r in routes}
    etas = {
        r.route_id: [depart_at + timedelta(seconds=c.offset_s) for c in checkpoints[r.route_id]]
        for r in routes
    }

    # One batched weather lookup for every checkpoint of every route.
    requests = [
        ((c.lat, c.lon), weather.forecast_hour(eta))
        for r in routes
        for c, eta in zip(checkpoints[r.route_id], etas[r.route_id], strict=True)
    ]
    readings = iter(weather.get_readings(requests))

    route_data = []
    summaries = []
    for route in routes:
        cps = checkpoints[route.route_id]
        cp_readings = [next(readings) for _ in cps]
        assessments = [assess(w.wind_mph, w.rain_in_hr, w.snow_in_hr, load_lb) for w in cp_readings]
        summary = summarize_route(
            route.route_id,
            [c.mile for c in cps],
            [a.level for a in assessments],
            route.duration_s,
        )
        summaries.append(summary)
        route_data.append((route, cps, etas[route.route_id], cp_readings, assessments, summary))

    rec = recommend(summaries)
    lost_on = {e.route_id: e for e in rec.eliminations}
    gross_lb = EMPTY_TRUCK_LB + load_lb

    return {
        "depart_at": depart_at.isoformat(),
        "load_lb": load_lb,
        "interval_mi": interval,
        "gross_weight_lb": gross_lb,
        "over_legal_weight": gross_lb > US_LEGAL_GROSS_LB,
        "recommended_route_id": rec.ranking[0],
        "all_routes_no_travel": rec.all_routes_no_travel,
        "routes": [
            {
                "id": route.route_id,
                "source": route.source,
                "rank": rec.ranking.index(route.route_id) + 1,
                "distance_mi": round(summary.distance_mi, 1),
                "duration_s": round(summary.duration_s),
                "arrive_at": (depart_at + timedelta(seconds=route.duration_s)).isoformat(),
                "miles_by_level": {
                    level.name.lower(): round(mi, 1) for level, mi in summary.miles_by_level.items()
                },
                "avg_risk": round(summary.avg_risk, 3),
                "worst_level": max(a.level for a in assessments).name.lower(),
                "lost_on": _lost_on(lost_on.get(route.route_id)),
                "segments": risk_segments(route, cps, [a.level for a in assessments]),
                "checkpoints": [
                    _checkpoint_json(c, eta, w, a)
                    for c, eta, w, a in zip(cps, cp_etas, cp_readings, assessments, strict=True)
                ],
            }
            for route, cps, cp_etas, cp_readings, assessments, summary in route_data
        ],
    }


def _lost_on(elimination) -> dict | None:
    if elimination is None:
        return None
    return {
        "criterion": elimination.criterion,
        "value": round(elimination.value, 3),
        "best": round(elimination.best, 3),
    }


def _checkpoint_json(c: Checkpoint, eta: datetime, w: weather.Reading, a: Assessment) -> dict:
    return {
        "mile": round(c.mile, 1),
        "lat": round(c.lat, 5),
        "lon": round(c.lon, 5),
        "eta": eta.isoformat(),
        "level": a.level.name.lower(),
        "reason": a.reason,
        "wind_mph": w.wind_mph,
        "gust_mph": w.gust_mph,
        "rain_in_hr": round(w.rain_in_hr, 3),
        "snow_in_hr": round(w.snow_in_hr, 3),
    }


def risk_segments(route: Route, cps: list[Checkpoint], levels: list[RiskLevel]) -> list[dict]:
    """The route line cut into pieces colored by risk, ready to draw.

    Each checkpoint's stretch uses the same midpoint split as the mile totals,
    so what the map shows matches the numbers on the route card. Neighbouring
    stretches with the same level are merged into one piece.
    """
    miles = allocate_miles([c.mile for c in cps])
    kept = simplify(route.points, SIMPLIFY_TOLERANCE_DEG)

    segments: list[dict] = []
    start = 0.0
    for level, length in zip(levels, miles, strict=True):
        end = start + length
        if end <= start:
            continue
        inner = [route.points[k] for k in kept if start < route.cum_mi[k] < end]
        a, b = point_at(route, start), point_at(route, end)
        coords = [(a.lat, a.lon), *inner, (b.lat, b.lon)]
        name = level.name.lower()
        if segments and segments[-1]["level"] == name:
            segments[-1]["coordinates"].extend(_lon_lat(coords[1:]))
        else:
            segments.append({"level": name, "coordinates": _lon_lat(coords)})
        start = end
    return segments


def _lon_lat(points: list[LatLon]) -> list[list[float]]:
    # GeoJSON order is [lon, lat]
    return [[round(lon, 5), round(lat, 5)] for lat, lon in points]
