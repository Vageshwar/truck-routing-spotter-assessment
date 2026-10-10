"""Weather risk for a single checkpoint.

Thresholds come straight from the assessment brief. Each band is
[lower, upper): a value sitting exactly on a boundary belongs to the higher
band, so 25 mph wind is Moderate and 0.25 in/hr rain is High. The one
exception is the No Travel column for rain and snow, which the brief writes as
">1.00" and ">3.0", so exactly 1.00 in/hr rain or 3.0 in/hr snow is still
Severe.
"""

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Band:
    """The lowest value that puts a reading into `level`."""

    level: RiskLevel
    threshold: float
    strict: bool = False  # value must be > threshold instead of >=

    def matches(self, value: float) -> bool:
        return value > self.threshold if self.strict else value >= self.threshold


# Bands are listed from mildest to worst. Anything below the first band is Low.
WIND_MPH_BANDS = (
    Band(RiskLevel.MODERATE, 25),
    Band(RiskLevel.HIGH, 35),
    Band(RiskLevel.SEVERE, 45),
    Band(RiskLevel.NO_TRAVEL, 55),
)
RAIN_IN_HR_BANDS = (
    Band(RiskLevel.MODERATE, 0.10),
    Band(RiskLevel.HIGH, 0.25),
    Band(RiskLevel.SEVERE, 0.50),
    Band(RiskLevel.NO_TRAVEL, 1.00, strict=True),
)
SNOW_IN_HR_BANDS = (
    Band(RiskLevel.MODERATE, 0.5),
    Band(RiskLevel.HIGH, 1.0),
    Band(RiskLevel.SEVERE, 2.0),
    Band(RiskLevel.NO_TRAVEL, 3.0, strict=True),
)

# Load rules from the brief. Both compare with a strict ">".
# The third rule (>= 55 mph is No Travel for any load) is already the last
# wind band above, so it needs no extra code.
NO_TRAVEL_WIND_LOAD_LB = 30_000  # 45-54 mph + more than this -> No Travel
SEVERE_WIND_LOAD_LB = 40_000  # 35-44 mph + more than this -> Severe


def classify(value: float, bands: tuple[Band, ...]) -> RiskLevel:
    level = RiskLevel.LOW
    for band in bands:
        if band.matches(value):
            level = band.level
    return level


def wind_level_for_load(wind_mph: float, load_lb: float) -> RiskLevel:
    """Wind level after the load rules.

    "45-54 mph" and "35-44 mph" in the brief are exactly the Severe and High
    wind bands, so the rules are written against those levels instead of
    repeating the mph numbers.
    """
    level = classify(wind_mph, WIND_MPH_BANDS)
    if level == RiskLevel.SEVERE and load_lb > NO_TRAVEL_WIND_LOAD_LB:
        return RiskLevel.NO_TRAVEL
    if level == RiskLevel.HIGH and load_lb > SEVERE_WIND_LOAD_LB:
        return RiskLevel.SEVERE
    return level


@dataclass(frozen=True)
class Assessment:
    level: RiskLevel
    wind: RiskLevel  # after load rules
    rain: RiskLevel
    snow: RiskLevel
    reason: str


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Classify one checkpoint. The overall level is the worst of the three."""
    for name, value in (
        ("wind_mph", wind_mph),
        ("rain_in_hr", rain_in_hr),
        ("snow_in_hr", snow_in_hr),
        ("load_lb", load_lb),
    ):
        if value < 0:
            raise ValueError(f"{name} cannot be negative, got {value}")

    base_wind = classify(wind_mph, WIND_MPH_BANDS)
    wind = wind_level_for_load(wind_mph, load_lb)
    rain = classify(rain_in_hr, RAIN_IN_HR_BANDS)
    snow = classify(snow_in_hr, SNOW_IN_HR_BANDS)
    level = max(wind, rain, snow)

    if level == RiskLevel.LOW:
        reason = "All conditions Low"
    else:
        parts = []
        if wind == level:
            text = f"Wind {wind_mph:g} mph"
            if wind != base_wind:
                limit = (
                    NO_TRAVEL_WIND_LOAD_LB if wind == RiskLevel.NO_TRAVEL else SEVERE_WIND_LOAD_LB
                )
                text += f" with {load_lb:,.0f} lb load (over {limit:,} lb)"
            parts.append(text)
        if rain == level:
            parts.append(f"Rain {rain_in_hr:g} in/hr")
        if snow == level:
            parts.append(f"Snow {snow_in_hr:g} in/hr")
        reason = f"{' + '.join(parts)} -> {level.label}"

    return Assessment(level=level, wind=wind, rain=rain, snow=snow, reason=reason)


def _scale_position(value: float, bands: tuple[Band, ...]) -> float:
    """Where a value sits on the 0-4 scale, e.g. 30 mph wind is 1.5
    (Moderate starts at 25, High at 35, so 30 is halfway)."""
    edges = [0.0, *(band.threshold for band in bands)]
    for i in range(len(edges) - 1):
        if value < edges[i + 1]:
            return i + (value - edges[i]) / (edges[i + 1] - edges[i])
    return float(RiskLevel.NO_TRAVEL)


def risk_score(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> float:
    """A smooth 0-4 version of the risk level, used to shade the heatmap.

    The whole-number part is always the official level from assess(), so the
    heatmap never disagrees with the checkpoints. The fraction shows how close
    the worst condition is to the next level, so a calm day still shows where
    the wind is picking up.
    """
    level = assess(wind_mph, rain_in_hr, snow_in_hr, load_lb).level
    if level == RiskLevel.NO_TRAVEL:
        return float(level)
    position = max(
        _scale_position(wind_mph, WIND_MPH_BANDS),
        _scale_position(rain_in_hr, RAIN_IN_HR_BANDS),
        _scale_position(snow_in_hr, SNOW_IN_HR_BANDS),
    )
    # The load rules can raise the level above what the raw numbers say, and
    # exactly 1.00 in/hr rain is still Severe, so keep the score inside the level.
    return max(float(level), min(position, level + 0.99))
