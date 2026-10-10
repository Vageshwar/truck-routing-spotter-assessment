"""Hourly forecasts from Open-Meteo, batched and cached.

Points are snapped to a 0.1 degree grid (about 7 miles), so nearby checkpoints
and repeat searches share cached forecasts instead of costing new calls.
"""

import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from django.core.cache import cache

from .geo import LatLon
from .valhalla import USER_AGENT

OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
GRID_DEG = 0.1
LOCATIONS_PER_REQUEST = 100
PARALLEL_REQUESTS = 4
CACHE_TTL_S = 30 * 60  # forecasts are updated about hourly
TIMEOUT_S = 30

HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"


class WeatherError(Exception):
    pass


@dataclass(frozen=True)
class Reading:
    wind_mph: float
    gust_mph: float | None
    rain_in_hr: float  # rain + showers
    snow_in_hr: float


def forecast_hour(eta: datetime) -> datetime:
    """The forecast record that covers the hour the truck is there.

    Open-Meteo stamps rain and snow with the end of the hour they add up
    (the 15:00 value is what fell from 14:00 to 15:00), so a 14:37 ETA uses
    the 15:00 record. Wind is an instant reading at that same time.
    """
    eta = eta.astimezone(UTC)
    return eta.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def snap(point: LatLon) -> LatLon:
    lat, lon = point
    return (round(round(lat / GRID_DEG) * GRID_DEG, 1), round(round(lon / GRID_DEG) * GRID_DEG, 1))


def _cache_key(cell: LatLon, hour: datetime) -> str:
    return f"wx:{cell[0]:.1f}:{cell[1]:.1f}:{hour:%Y%m%d%H}"


def get_readings(requests: Sequence[tuple[LatLon, datetime]]) -> list[Reading]:
    """Forecast for each (point, forecast hour) pair, in the same order.

    Hours must be whole UTC hours, as returned by forecast_hour().
    """
    wanted = [(snap(point), hour) for point, hour in requests]
    keys = [_cache_key(cell, hour) for cell, hour in wanted]
    found = cache.get_many(keys)

    missing = [
        (cell, hour) for (cell, hour), key in zip(wanted, keys, strict=True) if key not in found
    ]
    if missing:
        cells = sorted({cell for cell, _ in missing})
        start = min(hour for _, hour in missing)
        end = max(hour for _, hour in missing)
        fetched = fetch_hourly(cells, start, end)
        cache.set_many(fetched, CACHE_TTL_S)
        found.update(fetched)

    try:
        return [found[key] for key in keys]
    except KeyError as exc:
        raise WeatherError("forecast not available for every checkpoint") from exc


def fetch_hourly(cells: list[LatLon], start: datetime, end: datetime) -> dict[str, Reading]:
    """All hours from start to end (inclusive) for each cell, keyed for the cache."""
    chunks = [
        cells[i : i + LOCATIONS_PER_REQUEST] for i in range(0, len(cells), LOCATIONS_PER_REQUEST)
    ]
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        results = pool.map(lambda chunk: _fetch_chunk(chunk, start, end), chunks)

    readings = {}
    for chunk, data in zip(chunks, results, strict=True):
        readings.update(parse_response(chunk, data))
    return readings


def _fetch_chunk(cells: list[LatLon], start: datetime, end: datetime) -> list[dict]:
    params = {
        "latitude": ",".join(f"{lat:.1f}" for lat, _ in cells),
        "longitude": ",".join(f"{lon:.1f}" for _, lon in cells),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "start_hour": f"{start:%Y-%m-%dT%H:%M}",
        "end_hour": f"{end:%Y-%m-%dT%H:%M}",
    }
    try:
        response = httpx.get(
            OPEN_METEO_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
        )
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WeatherError(f"Open-Meteo request failed: {exc}") from exc
    if response.status_code != 200:
        reason = data.get("reason", "") if isinstance(data, dict) else ""
        raise WeatherError(f"Open-Meteo returned {response.status_code}: {reason}")
    # a single location comes back as an object instead of a list
    return data if isinstance(data, list) else [data]


def parse_response(cells: list[LatLon], data: list[dict]) -> dict[str, Reading]:
    """Results come back in the same order as the requested locations."""
    readings = {}
    for cell, location in zip(cells, data, strict=True):
        hourly = location["hourly"]
        for i, stamp in enumerate(hourly["time"]):
            wind = hourly["wind_speed_10m"][i]
            rain = hourly["rain"][i]
            showers = hourly["showers"][i]
            snow = hourly["snowfall"][i]
            if None in (wind, rain, showers, snow):
                continue  # no data for this hour, get_readings reports it if needed
            hour = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
            readings[_cache_key(cell, hour)] = Reading(
                wind_mph=wind,
                gust_mph=hourly["wind_gusts_10m"][i],
                rain_in_hr=rain + showers,
                snow_in_hr=snow,
            )
    return readings
