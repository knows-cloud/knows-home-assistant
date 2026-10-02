"""Constants for the Klima @ Home integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "klima_at_home"

CONF_LOCATION: Final = "location"
CONF_STATION_COUNT: Final = "station_count"

DEFAULT_STATION_COUNT: Final = 3
MAX_STATION_COUNT: Final = 5

WEATHER_UPDATE_INTERVAL: Final = timedelta(minutes=30)
GROUNDWATER_UPDATE_INTERVAL: Final = timedelta(hours=12)

# WMO climate normal period. The WMO reference period for climate-change anomalies
# is 1961-1990; do not "modernise" this without also relabelling the sensor, or the
# number stops meaning what it says.
BASELINE_START: Final = "1961-01-01"
BASELINE_END: Final = "1990-12-31"

# Years of overlap used to derive the ERA5 <-> high-res-model bias offset.
BIAS_YEARS: Final = 5

# Smoothing half-window (days) applied to the day-of-year normals. Without it the
# normal jumps a degree between neighbouring calendar days and the anomaly is noise.
NORMALS_SMOOTHING_WINDOW: Final = 7

# A dry day per the ETCCDI definition of "consecutive dry days" — not 0.0 mm, or a
# single drizzle reading resets the streak.
DRY_DAY_THRESHOLD_MM: Final = 1.0

# Days of recent history pulled for the drought windows (90 days) plus slack.
#
# This deliberately does NOT come from the forecast endpoint's `past_days`: that only
# carries real values ~67 days back and returns null before then, which silently emptied
# the 90-day window. The historical-forecast archive covers 150+ days without gaps, up to
# and including today — and it is the same high-resolution model the bias offset is
# measured against, so the numbers stay mutually consistent.
RECENT_DAYS: Final = 120

DROUGHT_SPI_THRESHOLD: Final = -1.0
DROUGHT_DRY_DAYS_THRESHOLD: Final = 14

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.baseline"

ATTRIBUTION: Final = "Wetter/Klima: Open-Meteo (ERA5) · Grundwasser: BGR GRUVO"

GRUVO_URL: Final = "https://gruvo.bgr.de/website/mapapp"

# Groundwater classes, straight from the BGR GRUVO legend endpoint (verified against
# .../MapServer/legend). Percentiles are against the 1991-2020 reference period.
# The integration does not invent this scale — it reports the official one.
GW_CLASS_VERY_LOW: Final = "sehr_niedrig"
GW_CLASS_LOW: Final = "niedrig"
GW_CLASS_NORMAL: Final = "normal"
GW_CLASS_HIGH: Final = "hoch"
GW_CLASS_VERY_HIGH: Final = "sehr_hoch"

GW_STATE_CLASSES: Final[dict[int, str]] = {
    1: GW_CLASS_VERY_LOW,
    2: GW_CLASS_LOW,
    3: GW_CLASS_NORMAL,
    4: GW_CLASS_HIGH,
    5: GW_CLASS_VERY_HIGH,
}

GW_STATE_OPTIONS: Final[list[str]] = list(GW_STATE_CLASSES.values())

# "kritisch" in the user's words maps to the official lowest class.
GW_CRITICAL_CLASS: Final = GW_CLASS_VERY_LOW

# change_a_4w_c — absolute change in metres, bucketed by BGR. Same legend source.
GW_TREND_CLASSES: Final[dict[int, str]] = {
    1: "stark_fallend",
    2: "fallend",
    3: "gleichbleibend",
    4: "steigend",
    5: "stark_steigend",
}

GW_TREND_OPTIONS: Final[list[str]] = list(GW_TREND_CLASSES.values())

# Metre ranges behind each trend bucket, so the attribute can say what it means.
GW_TREND_RANGES: Final[dict[int, str]] = {
    1: "<= -0,3 m",
    2: "> -0,3 bis -0,1 m",
    3: "> -0,1 bis 0,1 m",
    4: "> 0,1 bis 0,3 m",
    5: "> 0,3 m",
}
