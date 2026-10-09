import pytest

from planner.risk import RiskLevel
from planner.scoring import RouteSummary, allocate_miles, recommend, summarize_route

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel


def make_route(route_id, *, no_travel=0, severe=0, high=0, avg=0.0, hours=10.0):
    return RouteSummary(
        route_id=route_id,
        distance_mi=500,
        duration_s=hours * 3600,
        miles_by_level={
            LOW: 0,
            MODERATE: 0,
            HIGH: high,
            SEVERE: severe,
            NO_TRAVEL: no_travel,
        },
        avg_risk=avg,
    )


class TestAllocateMiles:
    def test_midpoint_split(self):
        # last stretch (50 -> 60) is shorter than the 25 mile spacing
        assert allocate_miles([0, 25, 50, 60]) == [12.5, 25, 17.5, 5]

    def test_miles_add_up_to_route_length(self):
        positions = [0, 10, 20, 30, 40, 47.3]
        assert sum(allocate_miles(positions)) == pytest.approx(47.3)

    def test_origin_and_destination_only(self):
        assert allocate_miles([0, 10]) == [5, 5]

    def test_single_point(self):
        assert allocate_miles([0]) == [0]

    def test_rejects_unordered_positions(self):
        with pytest.raises(ValueError):
            allocate_miles([0, 30, 20])


class TestSummarizeRoute:
    def test_miles_by_level_and_weighted_average(self):
        summary = summarize_route("a", [0, 25, 50, 60], [LOW, HIGH, HIGH, SEVERE], duration_s=3600)
        assert summary.distance_mi == 60
        assert summary.high_mi == 42.5
        assert summary.severe_mi == 5
        assert summary.no_travel_mi == 0
        # (0*12.5 + 2*25 + 2*17.5 + 3*5) / 60
        assert summary.avg_risk == pytest.approx(100 / 60)
        assert not summary.has_no_travel

    def test_average_is_weighted_by_miles_not_checkpoint_count(self):
        # three Severe checkpoints bunched near the end cover few miles
        summary = summarize_route("a", [0, 98, 99, 100], [LOW, SEVERE, SEVERE, SEVERE], 0)
        assert summary.avg_risk == pytest.approx(3 * 51 / 100)

    def test_levels_must_match_positions(self):
        with pytest.raises(ValueError):
            summarize_route("a", [0, 10], [LOW], 0)


class TestRecommend:
    def test_no_travel_miles_come_first(self):
        a = make_route("a", no_travel=1, hours=5)
        b = make_route("b", severe=100, hours=20)
        result = recommend([a, b])
        assert result.ranking == ["b", "a"]
        assert result.eliminations[0].criterion == "No Travel miles"

    def test_fewest_severe_miles_beats_fewer_high_miles(self):
        a = make_route("a", severe=20, high=0)
        b = make_route("b", severe=0, high=200)
        assert recommend([a, b]).ranking == ["b", "a"]

    def test_high_miles_decide_when_severe_ties(self):
        a = make_route("a", severe=10, high=60)
        b = make_route("b", severe=10, high=12)
        result = recommend([a, b])
        assert result.ranking == ["b", "a"]
        assert result.eliminations[0].criterion == "High miles"

    def test_average_risk_decides_next(self):
        a = make_route("a", avg=1.4, hours=8)
        b = make_route("b", avg=0.9, hours=12)
        assert recommend([a, b]).ranking == ["b", "a"]

    def test_travel_time_is_the_last_resort(self):
        a = make_route("a", avg=1.0, hours=12)
        b = make_route("b", avg=1.0, hours=9)
        result = recommend([a, b])
        assert result.ranking == ["b", "a"]
        assert result.eliminations[0].criterion == "travel time (s)"

    def test_strict_order_even_small_differences_count(self):
        # 3 extra Severe miles lose, even though that route is 3 hours faster
        a = make_route("a", severe=3, hours=8)
        b = make_route("b", severe=0, hours=11)
        result = recommend([a, b])
        assert result.ranking == ["b", "a"]
        assert result.eliminations[0].criterion == "Severe miles"

    def test_float_noise_is_not_a_difference(self):
        a = make_route("a", high=12.500000001, hours=8)
        b = make_route("b", high=12.5, hours=11)
        assert recommend([a, b]).ranking == ["a", "b"]

    def test_three_routes_full_ranking_and_reasons(self):
        a = make_route("a", severe=30, hours=7)
        b = make_route("b", high=40, hours=9)
        c = make_route("c", high=10, hours=10)
        result = recommend([a, b, c])
        assert result.ranking == ["c", "b", "a"]
        reasons = {e.route_id: e.criterion for e in result.eliminations}
        assert reasons == {"a": "Severe miles", "b": "High miles"}

    def test_flags_when_every_route_has_no_travel(self):
        a = make_route("a", no_travel=12)
        b = make_route("b", no_travel=3)
        result = recommend([a, b])
        assert result.ranking == ["b", "a"]
        assert result.all_routes_no_travel

    def test_not_flagged_when_one_route_is_clear(self):
        a = make_route("a", no_travel=12)
        b = make_route("b")
        assert not recommend([a, b]).all_routes_no_travel

    def test_exact_tie_keeps_input_order(self):
        a = make_route("a")
        b = make_route("b")
        result = recommend([a, b])
        assert result.ranking == ["a", "b"]
        assert result.eliminations[0].criterion == "tie (input order)"

    def test_needs_at_least_one_route(self):
        with pytest.raises(ValueError):
            recommend([])
