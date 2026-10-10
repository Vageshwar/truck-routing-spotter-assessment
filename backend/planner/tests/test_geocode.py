import json
from pathlib import Path

from rest_framework.test import APIClient

from planner import geocode
from planner.geocode import label, parse_response

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_real_photon_response():
    data = json.loads((FIXTURES / "photon_main_st_dallas.json").read_text())
    results = parse_response(data)
    assert results
    assert set(results[0]) == {"label", "lat", "lon"}
    assert results[0]["label"] == "1600 South Main Street, Duncanville, Texas"


def test_label_skips_repeats_and_blanks():
    assert label({"name": "Denver", "city": "Denver", "state": "Colorado"}) == "Denver, Colorado"
    assert (
        label({"housenumber": "1600", "street": "Main St", "city": "Dallas", "state": "Texas"})
        == "1600 Main St, Dallas, Texas"
    )
    assert label({}) == "Unnamed place"


def test_endpoint_ignores_short_queries(monkeypatch):
    monkeypatch.setattr(geocode, "_search", lambda q, limit: 1 / 0)
    assert APIClient().get("/api/geocode", {"q": "de"}).json() == []


def test_endpoint_returns_results(monkeypatch):
    result = [{"label": "Denver, Colorado", "lat": 39.7, "lon": -105.0}]
    monkeypatch.setattr(geocode, "_search", lambda q, limit: result)
    assert APIClient().get("/api/geocode", {"q": "denver"}).json() == result


def test_endpoint_reports_service_failure(monkeypatch):
    def broken(q, limit):
        raise geocode.GeocodeError("Place search failed: timeout")

    monkeypatch.setattr(geocode, "_search", broken)
    assert APIClient().get("/api/geocode", {"q": "denver"}).status_code == 502
