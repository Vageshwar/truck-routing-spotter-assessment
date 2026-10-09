import pytest

from planner.risk import (
    RAIN_IN_HR_BANDS,
    SNOW_IN_HR_BANDS,
    WIND_MPH_BANDS,
    RiskLevel,
    assess,
    classify,
    wind_level_for_load,
)

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, LOW),
        (24.9, LOW),
        (25, MODERATE),
        (34.9, MODERATE),
        (35, HIGH),
        (44.9, HIGH),
        (45, SEVERE),
        (54.9, SEVERE),
        (55, NO_TRAVEL),
        (90, NO_TRAVEL),
    ],
)
def test_wind_bands(mph, expected):
    assert classify(mph, WIND_MPH_BANDS) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0, LOW),
        (0.099, LOW),
        (0.10, MODERATE),
        (0.249, MODERATE),
        (0.25, HIGH),
        (0.499, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),  # brief says ">1.00" for No Travel
        (1.001, NO_TRAVEL),
    ],
)
def test_rain_bands(in_hr, expected):
    assert classify(in_hr, RAIN_IN_HR_BANDS) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (0.99, MODERATE),
        (1.0, HIGH),
        (1.99, HIGH),
        (2.0, SEVERE),
        (3.0, SEVERE),  # brief says ">3.0" for No Travel
        (3.01, NO_TRAVEL),
    ],
)
def test_snow_bands(in_hr, expected):
    assert classify(in_hr, SNOW_IN_HR_BANDS) == expected


@pytest.mark.parametrize(
    ("mph", "load_lb", "expected"),
    [
        # >= 55 mph is No Travel for any load
        (55, 0, NO_TRAVEL),
        # 45-54 mph + more than 30,000 lb -> No Travel
        (45, 30_001, NO_TRAVEL),
        (54.9, 30_001, NO_TRAVEL),
        (50, 30_000, SEVERE),  # exactly 30,000 is not "more than"
        (50, 45_000, NO_TRAVEL),  # heavier loads still hit the 30,000 rule
        # 35-44 mph + more than 40,000 lb -> Severe
        (35, 40_001, SEVERE),
        (44.9, 40_001, SEVERE),
        (40, 40_000, HIGH),  # exactly 40,000 is not "more than"
        (44.9, 30_001, HIGH),  # the 30,000 rule only applies from 45 mph
        # below 35 mph, load does not matter
        (34.9, 80_000, MODERATE),
        (10, 80_000, LOW),
    ],
)
def test_load_rules(mph, load_lb, expected):
    assert wind_level_for_load(mph, load_lb) == expected


def test_overall_level_is_worst_condition():
    result = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6, load_lb=20_000)
    assert (result.wind, result.rain, result.snow) == (LOW, HIGH, MODERATE)
    assert result.level == HIGH
    assert result.reason == "Rain 0.3 in/hr -> High"


def test_load_rule_can_override_milder_precipitation():
    result = assess(wind_mph=47, rain_in_hr=0.3, snow_in_hr=0, load_lb=38_000)
    assert result.level == NO_TRAVEL
    assert result.reason == "Wind 47 mph with 38,000 lb load (over 30,000 lb) -> No Travel"


def test_reason_lists_every_condition_at_the_worst_level():
    result = assess(wind_mph=36, rain_in_hr=0.3, snow_in_hr=1.5, load_lb=10_000)
    assert result.level == HIGH
    assert result.reason == "Wind 36 mph + Rain 0.3 in/hr + Snow 1.5 in/hr -> High"


def test_calm_weather_is_low():
    result = assess(wind_mph=5, rain_in_hr=0, snow_in_hr=0, load_lb=80_000)
    assert result.level == LOW
    assert result.reason == "All conditions Low"


def test_negative_values_are_rejected():
    with pytest.raises(ValueError, match="load_lb"):
        assess(wind_mph=5, rain_in_hr=0, snow_in_hr=0, load_lb=-1)


def test_level_labels():
    assert [level.label for level in RiskLevel] == [
        "Low",
        "Moderate",
        "High",
        "Severe",
        "No Travel",
    ]
