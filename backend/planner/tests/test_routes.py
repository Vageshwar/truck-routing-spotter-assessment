import pytest

from planner.routes import (
    Route,
    Step,
    accumulate_steps,
    default_interval_mi,
    place_checkpoints,
)

# Three points along the equator, evenly spaced (about 34.5 straight-line
# miles apart). The engine's step lengths below are what we trust for miles.
POINTS = [(0.0, 0.0), (0.0, 0.5), (0.0, 1.0)]


def make_route(steps):
    cum_mi, cum_s = accumulate_steps(POINTS, steps)
    return Route("r", "test", POINTS, cum_mi, cum_s)


class TestAccumulateSteps:
    def test_one_step_is_shared_by_geometry(self):
        cum_mi, cum_s = accumulate_steps(POINTS, [Step(0, 2, length_mi=60, time_s=3600)])
        assert cum_mi == pytest.approx([0, 30, 60])
        assert cum_s == pytest.approx([0, 1800, 3600])

    def test_each_step_keeps_its_own_speed(self):
        # first half at 60 mph, second half at 30 mph
        steps = [Step(0, 1, 30, 1800), Step(1, 2, 30, 3600)]
        cum_mi, cum_s = accumulate_steps(POINTS, steps)
        assert cum_mi == pytest.approx([0, 30, 60])
        assert cum_s == pytest.approx([0, 1800, 5400])

    def test_zero_length_arrival_step_is_ignored(self):
        steps = [Step(0, 2, 60, 3600), Step(2, 2, 0, 0)]
        cum_mi, cum_s = accumulate_steps(POINTS, steps)
        assert cum_mi[-1] == 60
        assert cum_s[-1] == 3600


class TestPlaceCheckpoints:
    def test_origin_every_interval_and_destination(self):
        route = make_route([Step(0, 2, 60, 3600)])
        assert [c.mile for c in place_checkpoints(route, 25)] == [0, 25, 50, 60]

    def test_no_duplicate_when_length_is_a_multiple(self):
        route = make_route([Step(0, 2, 50, 3000)])
        assert [c.mile for c in place_checkpoints(route, 25)] == [0, 25, 50]

    def test_position_and_eta_are_interpolated(self):
        route = make_route([Step(0, 2, 60, 3600)])
        checkpoint = place_checkpoints(route, 25)[1]  # mile 25 of 30 on the first segment
        assert checkpoint.lat == pytest.approx(0)
        assert checkpoint.lon == pytest.approx(0.5 * 25 / 30)
        assert checkpoint.offset_s == pytest.approx(1500)

    def test_eta_follows_slower_step(self):
        steps = [Step(0, 1, 30, 1800), Step(1, 2, 30, 3600)]
        route = make_route(steps)
        checkpoints = place_checkpoints(route, 15)
        by_mile = {c.mile: c.offset_s for c in checkpoints}
        assert by_mile[15] == pytest.approx(900)  # 60 mph part
        assert by_mile[45] == pytest.approx(1800 + 1800)  # halfway through the 30 mph part
        assert by_mile[60] == pytest.approx(5400)

    def test_rejects_non_positive_interval(self):
        route = make_route([Step(0, 2, 60, 3600)])
        with pytest.raises(ValueError):
            place_checkpoints(route, 0)


@pytest.mark.parametrize(
    ("distance", "expected"),
    [(50, 10), (299.9, 10), (300, 25), (1000, 25), (1000.1, 50), (2800, 50)],
)
def test_default_interval(distance, expected):
    assert default_interval_mi(distance) == expected
