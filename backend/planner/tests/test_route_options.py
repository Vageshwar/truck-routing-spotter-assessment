"""Route fallbacks, using real responses recorded in fixtures/.

The network calls are replaced with functions that return parsed fixtures,
so these tests also check which fallbacks get called and when.
"""

import json
from pathlib import Path

import pytest

from planner import osrm, route_options, valhalla
from planner.geo import haversine_mi
from planner.route_options import get_route_options, overlap, via_points
from planner.routes import Route, Step, accumulate_steps
from planner.valhalla import RoutingError

FIXTURES = Path(__file__).parent / "fixtures"
DALLAS = (32.7767, -96.7970)
OKC = (35.4676, -97.5164)
CHICAGO = (41.8781, -87.6298)
DENVER = (39.7392, -104.9903)


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def valhalla_fixture(name):
    return valhalla.parse_response(load(f"valhalla_{name}"))


def osrm_fixture(name):
    return osrm.parse_response(load(f"osrm_{name}"))


def fail(*args, **kwargs):
    raise AssertionError("this fallback should not be called")


def straight_route(points, miles):
    steps = [Step(0, len(points) - 1, miles, miles * 60)]
    cum_mi, cum_s = accumulate_steps(points, steps)
    return Route("x", "test", points, cum_mi, cum_s)


def test_osrm_totals_match_its_summary():
    data = load("osrm_chicago_denver")
    for route, raw in zip(osrm.parse_response(data), data["routes"], strict=True):
        assert route.distance_mi == pytest.approx(raw["distance"] / osrm.METERS_PER_MILE, rel=0.005)
        assert route.duration_s == pytest.approx(raw["duration"], rel=0.005)


class TestOverlap:
    def test_route_overlaps_itself_fully(self):
        route = valhalla_fixture("dallas_okc")[0]
        assert overlap(route, route) == 1.0

    def test_same_road_from_another_engine_counts_as_duplicate(self):
        truck = valhalla_fixture("dallas_okc")[0]
        car = osrm_fixture("dallas_okc")[0]
        assert overlap(car, truck) >= route_options.MAX_OVERLAP

    def test_different_routes_overlap_little(self):
        a, _, c = valhalla_fixture("dallas_denver")
        assert overlap(c, a) < 0.2


class TestViaPoints:
    def test_heading_north_puts_points_west_and_east(self):
        route = straight_route([(0.0, 0.0), (2.0, 0.0)], miles=138)
        left, right = via_points(route, (0.0, 0.0), (2.0, 0.0))
        assert left[1] < 0 < right[1]  # west, then east
        assert left[0] == pytest.approx(1.0) and right[0] == pytest.approx(1.0)

    def test_offset_is_a_share_of_trip_length(self):
        route = straight_route([(0.0, 0.0), (0.0, 3.0)], miles=207)
        left, right = via_points(route, (0.0, 0.0), (0.0, 3.0))
        straight = haversine_mi((0.0, 0.0), (0.0, 3.0))
        mid = (0.0, 1.5)
        assert haversine_mi(mid, left) == pytest.approx(straight * 0.2, rel=0.01)
        assert left[0] > 0 > right[0]  # heading east, left is north


class TestGetRouteOptions:
    def test_three_valhalla_routes_need_no_fallback(self, monkeypatch):
        monkeypatch.setattr(
            valhalla, "fetch_routes", lambda *a, **k: valhalla_fixture("dallas_denver")
        )
        monkeypatch.setattr(osrm, "fetch_routes", fail)
        routes = get_route_options(DALLAS, DENVER, 20_000)
        assert [(r.route_id, r.source) for r in routes] == [
            ("A", "valhalla"),
            ("B", "valhalla"),
            ("C", "valhalla"),
        ]

    def test_osrm_fills_the_gap(self, monkeypatch):
        monkeypatch.setattr(
            valhalla, "fetch_routes", lambda *a, **k: valhalla_fixture("chicago_denver")
        )
        monkeypatch.setattr(osrm, "fetch_routes", lambda *a: osrm_fixture("chicago_denver"))
        routes = get_route_options(CHICAGO, DENVER, 20_000)
        assert [r.source for r in routes] == ["valhalla", "valhalla", "osrm"]

    def test_via_points_when_both_engines_give_one_route(self, monkeypatch):
        def fake_valhalla(origin, destination, load_lb, alternates=2, via=None):
            if via is None:
                return valhalla_fixture("dallas_okc")
            side = "left" if via[1] < -97.2 else "right"
            return valhalla_fixture(f"dallas_okc_via_{side}")

        monkeypatch.setattr(valhalla, "fetch_routes", fake_valhalla)
        monkeypatch.setattr(osrm, "fetch_routes", lambda *a: osrm_fixture("dallas_okc"))
        routes = get_route_options(DALLAS, OKC, 20_000)
        # OSRM's route is the same road as Valhalla's, so it is skipped
        assert [r.source for r in routes] == ["valhalla", "valhalla-via", "valhalla-via"]
        assert [r.route_id for r in routes] == ["A", "B", "C"]

    def test_failing_fallbacks_still_return_what_we_have(self, monkeypatch):
        def fake_valhalla(origin, destination, load_lb, alternates=2, via=None):
            if via is None:
                return valhalla_fixture("dallas_okc")
            raise RoutingError("no road near via point")

        def broken_osrm(*args):
            raise RoutingError("server down")

        monkeypatch.setattr(valhalla, "fetch_routes", fake_valhalla)
        monkeypatch.setattr(osrm, "fetch_routes", broken_osrm)
        routes = get_route_options(DALLAS, OKC, 20_000)
        assert [r.route_id for r in routes] == ["A"]

    def test_long_detours_are_skipped(self, monkeypatch):
        main = valhalla_fixture("dallas_okc")[0]
        # a real, different route, stretched to 1.65x the main route's length
        real = valhalla_fixture("dallas_okc_via_left")[0]
        detour = Route("d", "valhalla", real.points, [m * 1.3 for m in real.cum_mi], real.cum_s)
        assert detour.distance_mi > main.distance_mi * route_options.MAX_DETOUR_RATIO
        monkeypatch.setattr(
            valhalla,
            "fetch_routes",
            lambda *a, via=None, **k: [main] if via is None else [detour],
        )
        monkeypatch.setattr(osrm, "fetch_routes", lambda *a: [])
        assert len(get_route_options(DALLAS, OKC, 20_000)) == 1

    def test_main_route_error_is_raised(self, monkeypatch):
        def down(*args, **kwargs):
            raise RoutingError("Valhalla down")

        monkeypatch.setattr(valhalla, "fetch_routes", down)
        with pytest.raises(RoutingError):
            get_route_options(DALLAS, OKC, 20_000)
