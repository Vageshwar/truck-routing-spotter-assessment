import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from planner import heatmap as heatmap_module
from planner import views, weather
from planner.geo import haversine_mi
from planner.heatmap import CORRIDOR_MI, build_grid, corridor_cells, heatmap
from planner.risk import assess, risk_score
from planner.routes import place_checkpoints
from planner.valhalla import parse_response
from planner.weather import Reading

FIXTURES = Path(__file__).parent / "fixtures"
DEPART = datetime(2026, 10, 11, 14, 30, tzinfo=UTC)


def dallas_denver():
    return parse_response(json.loads((FIXTURES / "valhalla_dallas_denver.json").read_text()))


class TestRiskScore:
    def test_halfway_between_levels(self):
        assert risk_score(30, 0, 0, 0) == pytest.approx(1.5)  # Moderate 25, High 35

    def test_calm_is_near_zero(self):
        assert risk_score(5, 0, 0, 0) == pytest.approx(0.2)

    def test_load_rule_lifts_the_score_to_the_level(self):
        assert risk_score(47, 0, 0, 42_000) == 4.0  # No Travel
        assert risk_score(40, 0, 0, 45_000) == 3.0  # Severe, though 40 mph alone is 2.5

    def test_stays_inside_severe_at_the_strict_boundary(self):
        assert 3 <= risk_score(0, 1.00, 0, 0) < 4  # exactly 1.00 in/hr is Severe

    def test_whole_number_part_always_matches_the_level(self):
        rng = random.Random(7)
        for _ in range(2000):
            wind, rain = rng.uniform(0, 70), rng.uniform(0, 1.5)
            snow, load = rng.uniform(0, 4), rng.uniform(0, 80_000)
            level = assess(wind, rain, snow, load).level
            assert math.floor(risk_score(wind, rain, snow, load)) == level


class TestGrid:
    def test_points_are_on_the_lattice_and_near_a_route(self):
        routes = dallas_denver()
        cells = corridor_cells(routes, 0.25)
        assert cells
        assert all(abs(lat / 0.25 - round(lat / 0.25)) < 1e-6 for lat, _ in cells)
        route_points = [(c.lat, c.lon) for r in routes for c in place_checkpoints(r, 5)]
        for cell in cells[::10]:
            nearest = min(haversine_mi(cell, p) for p in route_points)
            assert nearest <= CORRIDOR_MI + 1

    def test_grid_gets_coarser_when_there_are_too_many_points(self, monkeypatch):
        routes = dallas_denver()
        fine = len(corridor_cells(routes, 0.25))
        monkeypatch.setattr(heatmap_module, "MAX_POINTS", fine - 1)
        step, cells = build_grid(routes)
        assert step == 0.5
        assert len(cells) < fine


class TestHeatmap:
    @pytest.fixture
    def fake_weather(self, monkeypatch):
        seen = []

        def fake(requests):
            seen.extend(requests)
            # wind grows with latitude so rows differ
            return [
                Reading(wind_mph=lat, gust_mph=None, rain_in_hr=0, snow_in_hr=0)
                for (lat, _), _ in requests
            ]

        monkeypatch.setattr(weather, "get_readings", fake)
        return seen

    def test_shape_and_hours(self, fake_weather):
        result = heatmap(dallas_denver(), DEPART, load_lb=20_000)
        assert len(result["times"]) == 49
        assert result["times"][0] == DEPART.isoformat()
        assert len(result["scores"]) == len(result["points"])
        assert all(len(row) == 49 for row in result["scores"])
        # every lookup uses a forecast hour: 14:30 departure reads the 15:00 record first
        assert fake_weather[0][1] == datetime(2026, 10, 11, 15, tzinfo=UTC)

    def test_scores_are_tenths_of_the_risk_score(self, fake_weather):
        result = heatmap(dallas_denver(), DEPART, load_lb=20_000)
        lon, lat = result["points"][0]
        assert result["scores"][0][0] == round(10 * risk_score(lat, 0, 0, 20_000))


def test_endpoint_takes_the_plan_body(monkeypatch):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"points": []}

    monkeypatch.setattr(views, "heatmap_for_trip", fake)
    body = {
        "origin": {"lat": 32.7767, "lon": -96.797},
        "destination": {"lat": 39.7392, "lon": -104.9903},
        "depart_at": datetime.now(UTC).isoformat(),
        "load_lb": 38_000,
        "interval_mi": 25,
    }
    response = APIClient().post("/api/heatmap", body, format="json")
    assert response.status_code == 200
    assert "interval_mi" not in calls[0]
    assert calls[0]["load_lb"] == 38_000
