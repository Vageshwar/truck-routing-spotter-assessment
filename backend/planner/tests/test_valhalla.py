"""Tests against real Valhalla responses saved in fixtures/.

The fixtures were recorded from the public server for a 20,000 lb load, with
the instruction text stripped to keep them small.
"""

import json
from itertools import pairwise
from pathlib import Path

import pytest

from planner.geo import haversine_mi
from planner.routes import place_checkpoints
from planner.valhalla import build_request, parse_response

FIXTURES = Path(__file__).parent / "fixtures"
DALLAS = (32.7767, -96.7970)
DENVER = (39.7392, -104.9903)


def load(name):
    return json.loads((FIXTURES / f"valhalla_{name}.json").read_text())


def trips(data):
    return [data["trip"]] + [alt["trip"] for alt in data.get("alternates", [])]


def test_request_uses_truck_profile_and_gross_weight():
    body = build_request(DALLAS, DENVER, load_lb=20_000)
    assert body["costing"] == "truck"
    # (35,000 lb empty truck + 20,000 lb load) in metric tons
    assert body["costing_options"]["truck"]["weight"] == pytest.approx(24.95)
    assert body["alternates"] == 2
    assert body["units"] == "miles"
    assert len(body["locations"]) == 2


def test_request_with_via_point_passes_through_it():
    body = build_request(DALLAS, DENVER, load_lb=0, via=(36.0, -101.0))
    assert [loc.get("type") for loc in body["locations"]] == [None, "through", None]


@pytest.mark.parametrize(
    ("name", "count"), [("dallas_okc", 1), ("dallas_denver", 3), ("chicago_denver", 2)]
)
def test_parses_main_trip_and_alternates(name, count):
    assert len(parse_response(load(name))) == count


@pytest.mark.parametrize("name", ["dallas_okc", "dallas_denver", "chicago_denver"])
def test_totals_match_valhalla_summary(name):
    data = load(name)
    for route, trip in zip(parse_response(data), trips(data), strict=True):
        assert route.distance_mi == pytest.approx(trip["summary"]["length"], rel=0.005)
        assert route.duration_s == pytest.approx(trip["summary"]["time"], rel=0.005)
        assert all(b >= a for a, b in pairwise(route.cum_mi))
        assert all(b >= a for a, b in pairwise(route.cum_s))


def test_routes_start_and_end_at_the_requested_places():
    for route in parse_response(load("dallas_denver")):
        assert haversine_mi(route.points[0], DALLAS) < 2
        assert haversine_mi(route.points[-1], DENVER) < 2


def test_checkpoints_on_a_real_route():
    route = parse_response(load("dallas_denver"))[0]
    checkpoints = place_checkpoints(route, 25)

    assert checkpoints[0].mile == 0
    assert checkpoints[-1].mile == pytest.approx(route.distance_mi)
    assert len(checkpoints) == int(route.distance_mi // 25) + 2
    assert checkpoints[-1].offset_s == pytest.approx(route.duration_s)
    # ETAs only go forward
    offsets = [c.offset_s for c in checkpoints]
    assert offsets == sorted(offsets)
    # 25 road miles should never be more than 25 straight-line miles apart
    for a, b in pairwise(checkpoints):
        assert haversine_mi((a.lat, a.lon), (b.lat, b.lon)) <= 25.01
