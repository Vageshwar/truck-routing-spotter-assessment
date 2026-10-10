"""Place search for the origin and destination boxes, using Photon.

Photon is built for search-as-you-type and is free. (Nominatim's usage policy
does not allow autocomplete, so it is not used.) Calls go through the backend
so results can be cached and the browser only talks to our API.
"""

import os

import httpx

from .cache import cached
from .valhalla import USER_AGENT

PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
# Lower 48 states; the risk rules are in US units and the routing is US-tuned.
US_BBOX = "-125,24,-66,50"
CACHE_TTL_S = 24 * 60 * 60
TIMEOUT_S = 10


class GeocodeError(Exception):
    pass


def search(query: str, limit: int = 5) -> list[dict]:
    query = query.strip()
    return cached("photon", [query.lower(), limit], CACHE_TTL_S, lambda: _search(query, limit))


def _search(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.get(
            PHOTON_URL,
            params={"q": query, "limit": limit * 2, "lang": "en", "bbox": US_BBOX},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodeError(f"Place search failed: {exc}") from exc
    # ask for extra because non-US places are dropped
    return parse_response(data)[:limit]


def parse_response(data: dict) -> list[dict]:
    results = []
    seen = set()
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        # the bounding box also covers parts of Canada and Mexico
        if props.get("countrycode") != "US":
            continue
        name = label(props)
        if name in seen:
            continue
        seen.add(name)
        lon, lat = feature["geometry"]["coordinates"]
        results.append({"label": name, "lat": lat, "lon": lon})
    return results


def label(props: dict) -> str:
    """Readable name like "1600 Main St, Dallas, Texas" or "Denver, Colorado"."""
    street = " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
    parts = [props.get("name"), street, props.get("city"), props.get("state")]
    seen = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen) or "Unnamed place"
