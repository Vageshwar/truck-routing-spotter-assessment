"""The whole pipeline with recorded routes and made-up weather.

The three Dallas to Denver fixture routes take different roads:
  A: I-35 through Oklahoma City and Wichita
  B: through western Oklahoma and Kansas
  C: through Amarillo and down I-25
so weather placed in a box along one road affects only that route.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from planner import plan as plan_module
from planner import weather
from planner.plan import plan_trip
from planner.valhalla import parse_response
from planner.weather import Reading

FIXTURES = Path(__file__).parent / "fixtures"
DALLAS = (32.7767, -96.7970)
DENVER = (39.7392, -104.9903)
DEPART = datetime(2026, 10, 11, 14, 37, tzinfo=UTC)


def fixture_routes():
    routes = parse_response(json.loads((FIXTURES / "valhalla_dallas_denver.json").read_text()))
    return [replace(r, route_id=rid) for r, rid in zip(routes, "ABC", strict=True)]


def in_box(point, lat_range, lon_range):
    return lat_range[0] <= point[0] <= lat_range[1] and lon_range[0] <= point[1] <= lon_range[1]


def stormy_weather(requests):
    readings = []
    for point, _hour in requests:
        if in_box(point, (35, 37), (-98, -96.5)):  # on route A only
            readings.append(Reading(wind_mph=48, gust_mph=60, rain_in_hr=0, snow_in_hr=0))
        elif in_box(point, (35.5, 37.5), (-105, -102.5)):  # on route C only
            readings.append(Reading(wind_mph=10, gust_mph=15, rain_in_hr=0.3, snow_in_hr=0))
        else:
            readings.append(Reading(wind_mph=8, gust_mph=12, rain_in_hr=0, snow_in_hr=0))
    return readings


@pytest.fixture
def fake_services(monkeypatch):
    seen = []

    def fake_readings(requests):
        seen.extend(requests)
        return stormy_weather(requests)

    monkeypatch.setattr(plan_module, "get_route_options", lambda *a: fixture_routes())
    monkeypatch.setattr(weather, "get_readings", fake_readings)
    return seen


def by_id(result):
    return {r["id"]: r for r in result["routes"]}


def test_heavy_load_turns_wind_into_no_travel(fake_services):
    result = plan_trip(DALLAS, DENVER, DEPART, load_lb=42_000)
    routes = by_id(result)

    assert routes["A"]["worst_level"] == "no_travel"
    assert routes["A"]["miles_by_level"]["no_travel"] > 0
    assert any("42,000 lb" in c["reason"] for c in routes["A"]["checkpoints"])
    assert routes["C"]["worst_level"] == "high"
    assert routes["B"]["worst_level"] == "low"

    assert result["recommended_route_id"] == "B"
    assert [routes[i]["rank"] for i in "ABC"] == [3, 1, 2]
    assert routes["A"]["lost_on"]["criterion"] == "No Travel miles"
    assert routes["C"]["lost_on"]["criterion"] == "High miles"
    assert routes["B"]["lost_on"] is None
    assert not result["all_routes_no_travel"]


def test_lighter_load_makes_the_same_wind_severe(fake_services):
    routes = by_id(plan_trip(DALLAS, DENVER, DEPART, load_lb=20_000))
    assert routes["A"]["worst_level"] == "severe"
    assert routes["A"]["lost_on"]["criterion"] == "Severe miles"


def test_miles_by_level_add_up_to_route_distance(fake_services):
    for route in plan_trip(DALLAS, DENVER, DEPART, load_lb=42_000)["routes"]:
        assert sum(route["miles_by_level"].values()) == pytest.approx(route["distance_mi"], abs=0.5)


def test_checkpoint_etas_start_at_departure_and_use_forecast_hours(fake_services):
    result = plan_trip(DALLAS, DENVER, DEPART, load_lb=42_000)
    checkpoints = by_id(result)["A"]["checkpoints"]
    assert checkpoints[0]["eta"] == DEPART.isoformat()
    etas = [c["eta"] for c in checkpoints]
    assert etas == sorted(etas)
    # every weather lookup asks for a whole hour after the ETA
    assert all(hour.minute == 0 for _, hour in fake_services)
    assert fake_services[0][1] == datetime(2026, 10, 11, 15, tzinfo=UTC)


def test_default_and_chosen_interval(fake_services):
    assert plan_trip(DALLAS, DENVER, DEPART, 42_000)["interval_mi"] == 25
    result = plan_trip(DALLAS, DENVER, DEPART, 42_000, interval_mi=10)
    assert result["interval_mi"] == 10
    assert by_id(result)["A"]["checkpoints"][1]["mile"] == 10


def test_segments_follow_the_risk_and_the_road(fake_services):
    route = by_id(plan_trip(DALLAS, DENVER, DEPART, load_lb=42_000))["A"]
    levels = [s["level"] for s in route["segments"]]
    assert "no_travel" in levels
    # neighbouring stretches with the same level are merged
    assert all(a != b for a, b in zip(levels, levels[1:], strict=False))
    first = route["segments"][0]["coordinates"][0]
    assert first == pytest.approx([DALLAS[1], DALLAS[0]], abs=0.01)  # [lon, lat]
    total_points = sum(len(s["coordinates"]) for s in route["segments"])
    assert total_points < 1500  # simplified from about 9,000


def test_weight_warning(fake_services):
    assert plan_trip(DALLAS, DENVER, DEPART, 42_000)["gross_weight_lb"] == 77_000
    assert not plan_trip(DALLAS, DENVER, DEPART, 42_000)["over_legal_weight"]
    assert plan_trip(DALLAS, DENVER, DEPART, 50_000)["over_legal_weight"]
