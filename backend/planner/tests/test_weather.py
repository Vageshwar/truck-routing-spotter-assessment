import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from planner import weather
from planner.weather import WeatherError, forecast_hour, get_readings, parse_response, snap

FIXTURES = Path(__file__).parent / "fixtures"
HOUR = datetime(2026, 10, 11, 10, tzinfo=UTC)


def fake_location(start, end, wind=10.0, rain=0.0, showers=0.0, snow=0.0):
    hours = int((end - start).total_seconds() // 3600) + 1
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {
        "hourly": {
            "time": times,
            "wind_speed_10m": [wind] * hours,
            "wind_gusts_10m": [wind + 10] * hours,
            "rain": [rain] * hours,
            "showers": [showers] * hours,
            "snowfall": [snow] * hours,
        }
    }


class FakeOpenMeteo:
    def __init__(self):
        self.calls = []

    def __call__(self, cells, start, end):
        self.calls.append((list(cells), start, end))
        # wind speed = cell latitude, so results are easy to tell apart
        return [fake_location(start, end, wind=lat) for lat, _ in cells]


@pytest.fixture
def fake_api(monkeypatch):
    fake = FakeOpenMeteo()
    monkeypatch.setattr(weather, "_fetch_chunk", fake)
    return fake


class TestForecastHour:
    def test_uses_the_record_at_the_end_of_the_hour(self):
        assert forecast_hour(datetime(2026, 10, 11, 14, 37, tzinfo=UTC)) == datetime(
            2026, 10, 11, 15, tzinfo=UTC
        )

    def test_exact_hour_belongs_to_the_hour_after_it(self):
        # 14:00 to 15:00 is [inclusive, exclusive), so it is the 15:00 record
        assert forecast_hour(datetime(2026, 10, 11, 14, 0, tzinfo=UTC)).hour == 15

    def test_converts_to_utc(self):
        central = timezone(timedelta(hours=-5))
        eta = datetime(2026, 10, 11, 9, 37, tzinfo=central)
        assert forecast_hour(eta) == datetime(2026, 10, 11, 15, tzinfo=UTC)


def test_snap_to_tenth_of_a_degree():
    assert snap((32.7767, -96.7970)) == (32.8, -96.8)
    assert snap((39.7392, -104.9903)) == (39.7, -105.0)


class TestParseResponse:
    def test_real_open_meteo_response(self):
        data = json.loads((FIXTURES / "open_meteo_two_points.json").read_text())
        readings = parse_response([(32.8, -96.8), (39.7, -105.0)], data)
        assert len(readings) == 6  # 2 points x 3 hours
        first = readings["wx:32.8:-96.8:2026101110"]
        assert first.wind_mph == 5.4
        assert first.gust_mph == 16.6

    def test_rain_includes_showers(self):
        data = [fake_location(HOUR, HOUR, rain=0.1, showers=0.2)]
        reading = parse_response([(1.0, 2.0)], data)["wx:1.0:2.0:2026101110"]
        assert reading.rain_in_hr == pytest.approx(0.3)

    def test_hours_without_data_are_skipped(self):
        data = [fake_location(HOUR, HOUR)]
        data[0]["hourly"]["rain"] = [None]
        assert parse_response([(1.0, 2.0)], data) == {}


class TestGetReadings:
    def test_one_value_per_request_in_order(self, fake_api):
        readings = get_readings([((40.0, -100.0), HOUR), ((35.0, -100.0), HOUR)])
        assert [r.wind_mph for r in readings] == [40.0, 35.0]

    def test_nearby_points_share_one_grid_cell(self, fake_api):
        get_readings([((40.01, -100.01), HOUR), ((39.98, -99.97), HOUR)])
        cells, _, _ = fake_api.calls[0]
        assert cells == [(40.0, -100.0)]

    def test_one_time_window_covers_every_hour_needed(self, fake_api):
        later = HOUR + timedelta(hours=5)
        get_readings([((40.0, -100.0), HOUR), ((35.0, -100.0), later)])
        assert len(fake_api.calls) == 1
        _, start, end = fake_api.calls[0]
        assert (start, end) == (HOUR, later)

    def test_second_lookup_comes_from_cache(self, fake_api):
        get_readings([((40.0, -100.0), HOUR)])
        get_readings([((40.0, -100.0), HOUR)])
        assert len(fake_api.calls) == 1

    def test_large_batches_are_split(self, fake_api, monkeypatch):
        monkeypatch.setattr(weather, "LOCATIONS_PER_REQUEST", 2)
        get_readings([((float(lat), -100.0), HOUR) for lat in range(30, 35)])
        assert sorted(len(cells) for cells, _, _ in fake_api.calls) == [1, 2, 2]

    def test_missing_forecast_is_an_error(self, monkeypatch):
        monkeypatch.setattr(weather, "_fetch_chunk", lambda cells, start, end: [])
        monkeypatch.setattr(weather, "parse_response", lambda cells, data: {})
        with pytest.raises(WeatherError):
            get_readings([((40.0, -100.0), HOUR)])
