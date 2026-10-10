import pytest

from planner.geo import decode_polyline, haversine_mi


def test_decode_google_example():
    # Example from Google's polyline format docs (5 digit precision)
    points = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert points == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_decode_empty():
    assert decode_polyline("") == []


def test_one_degree_of_latitude():
    assert haversine_mi((0, 0), (1, 0)) == pytest.approx(69.09, abs=0.01)


def test_dallas_to_denver_straight_line():
    assert haversine_mi((32.7767, -96.7970), (39.7392, -104.9903)) == pytest.approx(663, abs=2)
