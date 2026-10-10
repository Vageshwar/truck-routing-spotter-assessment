from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from planner import views
from planner.valhalla import RoutingError


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_plan_trip(**kwargs):
        calls.append(kwargs)
        return {"routes": []}

    monkeypatch.setattr(views, "plan_trip", fake_plan_trip)
    return calls


def body(**overrides):
    data = {
        "origin": {"lat": 32.7767, "lon": -96.7970},
        "destination": {"lat": 39.7392, "lon": -104.9903},
        "depart_at": (timezone.now() + timedelta(hours=2)).isoformat(),
        "load_lb": 42_000,
    }
    data.update(overrides)
    return data


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_request_is_passed_to_the_planner(client, captured):
    response = client.post("/api/plan", body(interval_mi=10), format="json")
    assert response.status_code == 200
    call = captured[0]
    assert call["origin"] == (32.7767, -96.7970)
    assert call["load_lb"] == 42_000
    assert call["interval_mi"] == 10


def test_interval_is_optional(client, captured):
    assert client.post("/api/plan", body(), format="json").status_code == 200
    assert captured[0]["interval_mi"] is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"depart_at": (timezone.now() - timedelta(hours=1)).isoformat()}, "depart_at"),
        ({"depart_at": (timezone.now() + timedelta(days=8)).isoformat()}, "depart_at"),
        ({"load_lb": -5}, "load_lb"),
        ({"interval_mi": 30}, "interval_mi"),
        ({"origin": {"lat": 95, "lon": 0}}, "origin"),
        ({"destination": {"lat": 32.7768, "lon": -96.7971}}, "non_field_errors"),
    ],
)
def test_invalid_requests(client, captured, overrides, field):
    response = client.post("/api/plan", body(**overrides), format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert captured == []


def test_outside_service_failure_is_502(client, monkeypatch):
    def broken(**kwargs):
        raise RoutingError("Valhalla returned 503")

    monkeypatch.setattr(views, "plan_trip", broken)
    response = client.post("/api/plan", body(), format="json")
    assert response.status_code == 502
    assert response.json() == {"detail": "Valhalla returned 503"}
