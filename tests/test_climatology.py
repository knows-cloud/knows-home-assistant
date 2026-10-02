"""Tests for the climate normals and the bias correction."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.klima_at_home.climatology import (  # noqa: E402
    bias_offset,
    daily_normals,
    day_key,
    temperature_anomaly,
)


def _series(start_year: int, end_year: int, value_for):
    dates: list[date] = []
    values: list[float] = []
    day = date(start_year, 1, 1)
    while day <= date(end_year, 12, 31):
        dates.append(day)
        values.append(value_for(day))
        day += timedelta(days=1)
    return dates, values


def test_day_key_aligns_the_same_calendar_date_across_leap_years():
    # 1 March must land in the same slot whether or not February had 29 days. Without the
    # shift, a non-leap 1 March would be compared against a leap year's 29 February.
    assert day_key(date(2024, 3, 1)) == day_key(date(2023, 3, 1))
    assert day_key(date(2024, 12, 31)) == day_key(date(2023, 12, 31))
    # January is before the divergence, so it is untouched.
    assert day_key(date(2023, 1, 15)) == day_key(date(2024, 1, 15)) == 15


def test_normal_of_a_constant_series_is_that_constant():
    dates, values = _series(1961, 1990, lambda _day: 10.0)
    normals = daily_normals(dates, values)
    assert len(normals) >= 365
    for value in normals.values():
        assert abs(value - 10.0) < 1e-9


def test_anomaly_recovers_a_known_offset():
    # A baseline that is flat at 10 degrees; today is 13.2 => the anomaly must be +3.2.
    dates, values = _series(1961, 1990, lambda _day: 10.0)
    normals = daily_normals(dates, values)

    anomaly = temperature_anomaly(13.2, normals, offset=0.0, today=date(2026, 7, 14))
    assert anomaly is not None
    assert abs(anomaly - 3.2) < 1e-6


def test_smoothing_damps_a_single_day_spike():
    # Flat at 10 degrees, except one calendar day that is always 5 K hotter. That kind of
    # single-day bump is a sampling artefact of having only 30 samples per day — exactly
    # what the smoothing window exists to absorb.
    def value_for(day: date) -> float:
        return 10.0 + (5.0 if (day.month, day.day) == (7, 14) else 0.0)

    dates, values = _series(1961, 1990, value_for)
    normals = daily_normals(dates, values)

    spike = normals[day_key(date(2026, 7, 14))]
    neighbour = normals[day_key(date(2026, 7, 13))]
    far_away = normals[day_key(date(2026, 4, 1))]

    # Unsmoothed this day's normal would be a full 15.0. Spread across a 15-day window
    # the 5 K becomes ~0.33 K.
    assert 10.0 < spike < 10.6, spike
    # And there is no cliff between the spike day and its neighbour — both sit inside the
    # same window, so the normal stays continuous.
    assert abs(spike - neighbour) < 0.05
    # Outside the window nothing moved at all.
    assert abs(far_away - 10.0) < 1e-9


def test_smoothing_preserves_the_seasonal_signal():
    # A real annual cycle peaking in mid-July. Smoothing must not flatten summer away.
    import math

    def value_for(day: date) -> float:
        return 10.0 - 10.0 * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365.0)

    dates, values = _series(1961, 1990, value_for)
    normals = daily_normals(dates, values)

    july = normals[day_key(date(2026, 7, 14))]
    january = normals[day_key(date(2026, 1, 14))]
    assert july > january + 15.0, (july, january)


def test_bias_offset_measures_a_constant_model_warm_bias():
    dates, era5 = _series(2020, 2024, lambda _day: 9.0)
    _, model = _series(2020, 2024, lambda _day: 10.5)

    offset = bias_offset(dates, era5, dates, model)
    assert abs(offset - 1.5) < 1e-9


def test_bias_offset_is_actually_removed_from_the_anomaly():
    # The whole point: the high-res model reads 1.5 K warm against ERA5 at this site.
    # A raw subtraction would report +1.5 of anomaly on a perfectly normal day.
    dates, era5 = _series(1961, 1990, lambda _day: 10.0)
    normals = daily_normals(dates, era5)

    today_mean_from_model = 11.5  # = the 10.0 normal seen through a +1.5 K biased model

    uncorrected = temperature_anomaly(today_mean_from_model, normals, 0.0, date(2026, 7, 14))
    corrected = temperature_anomaly(today_mean_from_model, normals, 1.5, date(2026, 7, 14))

    assert abs(uncorrected - 1.5) < 1e-6  # the bug we are guarding against
    assert abs(corrected - 0.0) < 1e-6  # a normal day reports as normal


def test_bias_offset_without_overlap_is_neutral():
    assert bias_offset([], [], [], []) == 0.0
