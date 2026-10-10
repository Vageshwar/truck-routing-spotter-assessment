"""Small geometry helpers. Points are (lat, lon) tuples in degrees."""

import math

EARTH_RADIUS_MI = 3958.8

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two points, in miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode an encoded polyline (Google's format) into points.

    Valhalla uses 6 decimal places of precision, Google and OSRM use 5.
    Each value is stored as the difference from the previous point, packed
    into 5-bit chunks offset by 63 so they are printable characters.
    """
    factor = 10**precision
    points = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                chunk = ord(encoded[index]) - 63
                index += 1
                result |= (chunk & 0x1F) << shift
                shift += 5
                if chunk < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append((lat / factor, lon / factor))
    return points
