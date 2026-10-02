"""Tests for the drought metrics."""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.klima_at_home.drought import (  # noqa: E402
    consecutive_dry_days,
    deficit_percent,
    historical_window_sums,
    percentile_of,
    spi,
    window_sum,
)


def test_dry_streak_counts_back_from_today():
    # 5 mm, then eight dry days.
    precipitation = [5.0] + [0.0] * 8
    assert consecutive_dry_days(precipitation) == 8


def test_drizzle_below_one_millimetre_does_not_break_the_streak():
    # The ETCCDI threshold is < 1 mm, not "exactly zero". A 0.4 mm trace is still a dry
    # day; using "== 0" here would report 2 days instead of 6 and permanently understate
    # every dry spell.
    precipitation = [5.0, 0.0, 0.0, 0.4, 0.0, 0.9, 0.0]
    assert consecutive_dry_days(precipitation) == 6


def test_two_millimetres_does_break_the_streak():
    precipitation = [0.0, 0.0, 2.0, 0.0, 0.0]
    assert consecutive_dry_days(precipitation) == 2


def test_a_wet_final_day_means_no_streak():
    assert consecutive_dry_days([0.0, 0.0, 3.0]) == 0


def test_window_sum_needs_a_full_window():
    assert window_sum([1.0] * 10, 30) is None
    assert window_sum([1.0] * 30, 30) == 30.0
    assert window_sum([None] + [1.0] * 29, 30) is None


def test_deficit_percent_against_the_seasonal_mean():
    # Half of a 50 mm normal is 50 %.
    assert deficit_percent(25.0, [40.0, 50.0, 60.0]) == 50.0


def test_percentile_of():
    assert percentile_of(5.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == 100.0
    assert percentile_of(3.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == 60.0
    assert percentile_of(0.0, [1.0, 2.0]) == 0.0
    assert percentile_of(1.0, []) is None


def test_historical_window_sums_is_anchored_to_the_season():
    # 1 mm every single day for three years. A 30-day window ending on any given date is
    # therefore always 30 mm, once per year.
    dates: list[date] = []
    precipitation: list[float] = []
    day = date(2000, 1, 1)
    while day <= date(2002, 12, 31):
        dates.append(day)
        precipitation.append(1.0)
        day += timedelta(days=1)

    sums = historical_window_sums(dates, precipitation, 30, date(2026, 6, 15))

    # 2000 and 2001 and 2002 all have a full 30 days before 15 June.
    assert len(sums) == 3
    assert all(abs(value - 30.0) < 1e-9 for value in sums)


def test_spi_is_near_zero_for_an_ordinary_amount():
    random.seed(7)
    # A plausible spread of 30-day totals around ~50 mm.
    historical = [random.gammavariate(4.0, 12.5) for _ in range(60)]
    median = sorted(historical)[len(historical) // 2]

    value = spi(median, historical)
    assert value is not None
    assert abs(value) < 0.35  # the middle of the distribution is, by definition, normal


def test_spi_goes_sharply_negative_in_a_dry_spell_and_positive_when_wet():
    random.seed(11)
    historical = [random.gammavariate(4.0, 12.5) for _ in range(60)]

    dry = spi(min(historical) / 4.0, historical)
    wet = spi(max(historical) * 2.0, historical)

    assert dry is not None and wet is not None
    assert dry < -1.5, f"a near-rainless month must read as drought, got {dry}"
    assert wet > 1.0, f"a very wet month must read positive, got {wet}"
    assert dry < wet


def test_spi_ordering_is_monotonic():
    random.seed(3)
    historical = [random.gammavariate(4.0, 12.5) for _ in range(80)]
    values = [spi(amount, historical) for amount in (5.0, 20.0, 50.0, 90.0, 150.0)]
    assert all(value is not None for value in values)
    assert values == sorted(values), "more rain must never mean a lower SPI"


def test_spi_refuses_to_guess_from_too_little_history():
    # Fitting a gamma to five numbers would produce a confident-looking figure built on
    # nothing. Better to report nothing.
    assert spi(20.0, [10.0, 20.0, 30.0]) is None


def test_spi_handles_a_climate_with_bone_dry_months():
    # Half the historical months are zero. A plain gamma cannot represent the point mass
    # at zero; the mixed distribution must still return a finite, ordered answer.
    rng = random.Random(5)
    historical = [0.0] * 30 + [rng.gammavariate(3.0, 10.0) for _ in range(30)]
    dry = spi(0.0, historical)
    wet = spi(80.0, historical)
    assert dry is not None and wet is not None
    assert dry < wet


def test_spi_declines_to_fit_a_distribution_with_no_spread():
    # Every year identical. There is no distribution here to speak of, and a gamma fit
    # would divide by zero — better to say nothing than to emit a confident number.
    assert spi(50.0, [50.0] * 40) is None
