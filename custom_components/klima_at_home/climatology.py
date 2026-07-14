"""Climate normals and temperature anomaly.

Pure functions over plain lists — no Home Assistant imports — so the maths can be
unit-tested without standing up HA.
"""

from __future__ import annotations

from datetime import date
from statistics import fmean

from .const import NORMALS_SMOOTHING_WINDOW

DAYS_PER_YEAR = 366


def day_key(day: date) -> int:
    """Map a date to a 1..366 slot that is stable across leap and non-leap years.

    From March onwards a non-leap year is one day behind a leap year, so the raw
    ordinal would compare 1 March against 29 February. Shifting non-leap dates keeps
    every calendar date in the same slot every year.
    """
    doy = day.timetuple().tm_yday
    is_leap = day.year % 4 == 0 and (day.year % 100 != 0 or day.year % 400 == 0)
    if not is_leap and day.month > 2:
        doy += 1
    return doy


def _circular_window(centre: int, half_width: int) -> list[int]:
    return [((centre - 1 + offset) % DAYS_PER_YEAR) + 1 for offset in range(-half_width, half_width + 1)]


def daily_normals(
    dates: list[date],
    values: list[float | None],
    window: int = NORMALS_SMOOTHING_WINDOW,
) -> dict[int, float]:
    """Build a smoothed day-of-year normal from a multi-decade daily series.

    Each day is averaged together with its +/- `window` neighbours. Without the
    smoothing the normal jumps around by a degree between adjacent calendar days —
    30 samples per day is simply not enough — and the anomaly inherits that jitter.
    """
    buckets: dict[int, list[float]] = {}
    for day, value in zip(dates, values):
        if value is None:
            continue
        buckets.setdefault(day_key(day), []).append(value)

    normals: dict[int, float] = {}
    for slot in range(1, DAYS_PER_YEAR + 1):
        samples: list[float] = []
        for neighbour in _circular_window(slot, window):
            samples.extend(buckets.get(neighbour, ()))
        if samples:
            normals[slot] = fmean(samples)
    return normals


def bias_offset(
    reference_dates: list[date],
    reference_values: list[float | None],
    model_dates: list[date],
    model_values: list[float | None],
) -> float:
    """Systematic offset of the high-resolution model against ERA5, in Kelvin.

    The normals come from ERA5 (~28 km cells), today's temperature from the
    high-resolution forecast model. The two disagree systematically — mostly because
    the ERA5 cell's mean elevation is not the site's elevation, which in hilly terrain
    is worth 1-2 K. Subtracting them raw yields an anomaly that is permanently wrong
    while looking entirely plausible. This offset removes that.
    """
    reference = {d: v for d, v in zip(reference_dates, reference_values) if v is not None}
    paired = [
        (model_value, reference[day])
        for day, model_value in zip(model_dates, model_values)
        if model_value is not None and day in reference
    ]
    if not paired:
        return 0.0
    return fmean(model - ref for model, ref in paired)


def temperature_anomaly(
    today_mean: float,
    normals: dict[int, float],
    offset: float,
    today: date,
) -> float | None:
    """Today's mean temperature minus the 1961-1990 normal for this calendar day."""
    normal = normals.get(day_key(today))
    if normal is None:
        return None
    return (today_mean - offset) - normal
