"""Drought metrics: consecutive dry days, precipitation deficit, SPI.

Pure functions over plain lists — no Home Assistant imports.

The statistics are deliberately implemented against the standard library. SPI needs a
gamma fit and an inverse normal CDF, which would normally mean scipy; pulling scipy
into a Home Assistant integration drags a large wheel that fails to build on 32-bit ARM
installs, so both are implemented here instead.
"""

from __future__ import annotations

import math
from datetime import date
from statistics import fmean, pstdev

from .climatology import day_key
from .const import DRY_DAY_THRESHOLD_MM


def consecutive_dry_days(
    precipitation: list[float | None],
    threshold: float = DRY_DAY_THRESHOLD_MM,
) -> int:
    """Length of the dry spell ending at the most recent day.

    A dry day is < 1 mm, per the ETCCDI definition of consecutive dry days — not
    "exactly zero", which any trace of drizzle or dew would reset.
    """
    streak = 0
    for value in reversed(precipitation):
        if value is None or value >= threshold:
            break
        streak += 1
    return streak


def window_sum(precipitation: list[float | None], days: int) -> float | None:
    """Total precipitation over the last `days` days."""
    window = precipitation[-days:]
    if len(window) < days or any(value is None for value in window):
        return None
    return sum(value for value in window if value is not None)


def historical_window_sums(
    dates: list[date],
    precipitation: list[float | None],
    days: int,
    ending_on: date,
) -> list[float]:
    """One `days`-long precipitation total per historical year, ending on the same
    calendar day as today.

    Comparing an August dry spell against the whole-year distribution would call it
    normal when it is not, so the comparison is anchored to the season.
    """
    series = [(day, value) for day, value in zip(dates, precipitation) if value is not None]
    values = [value for _, value in series]

    target_slot = day_key(ending_on)
    sums: list[float] = []
    for index, (day, _) in enumerate(series):
        if day_key(day) != target_slot or index + 1 < days:
            continue
        sums.append(sum(values[index + 1 - days : index + 1]))
    return sums


def deficit_percent(recent: float, historical: list[float]) -> float | None:
    """Recent precipitation as a percentage of the historical mean for this season."""
    if not historical:
        return None
    normal = fmean(historical)
    if normal <= 0:
        return None
    return recent / normal * 100.0


def percentile_of(value: float, population: list[float]) -> float | None:
    """Share of the population at or below `value`, in percent."""
    if not population:
        return None
    at_or_below = sum(1 for sample in population if sample <= value)
    return at_or_below / len(population) * 100.0


def _lower_gamma_regularised(shape: float, x: float) -> float:
    """Regularised lower incomplete gamma P(a, x), via series / continued fraction."""
    if x <= 0.0:
        return 0.0
    if x < shape + 1.0:
        # Series expansion converges quickly on this side.
        term = 1.0 / shape
        total = term
        for n in range(1, 200):
            term *= x / (shape + n)
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return total * math.exp(-x + shape * math.log(x) - math.lgamma(shape))

    # Continued fraction (Lentz) for the upper tail, then complement.
    tiny = 1e-300
    b = x + 1.0 - shape
    c = 1.0 / tiny
    d = 1.0 / b if b != 0.0 else 1.0 / tiny
    h = d
    for i in range(1, 200):
        an = -i * (i - shape)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    upper = math.exp(-x + shape * math.log(x) - math.lgamma(shape)) * h
    return 1.0 - upper


def _inverse_standard_normal(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf

    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)

    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


def spi(recent: float, historical: list[float]) -> float | None:
    """Standardized Precipitation Index — the WMO's standard drought index.

    Fits a gamma distribution to the historical totals for this season (Thom's
    maximum-likelihood estimator), reads off where the recent total falls, and maps
    that probability onto a standard normal. Negative means drier than usual;
    roughly, -1 is moderate drought, -2 extreme.

    Zero-precipitation periods are handled as a mixed distribution: the gamma is fitted
    to the wet totals only, and the probability of zero is folded back in afterwards.
    A gamma cannot represent a point mass at zero, and in dry climates that matters.
    """
    if len(historical) < 10:
        # Too few years to fit a distribution that means anything.
        return None

    wet = [value for value in historical if value > 0.0]
    if len(wet) < 5:
        return None

    zero_probability = (len(historical) - len(wet)) / len(historical)

    mean = fmean(wet)
    if mean <= 0.0:
        return None

    # A near-degenerate sample has no distribution to fit. The guard has to be a real
    # epsilon, not "> 0": with identical inputs, floating-point rounding leaves a gap of
    # ~1e-16 rather than exactly zero, the shape parameter explodes, and SPI happily
    # reports something like -4.7 ("extreme drought") for a value equal to every single
    # historical observation. Silence is the only honest answer here.
    if pstdev(wet) / mean < 1e-6:
        return None

    log_mean_gap = math.log(mean) - fmean(math.log(value) for value in wet)
    if log_mean_gap < 1e-9:
        return None

    shape = (1.0 + math.sqrt(1.0 + 4.0 * log_mean_gap / 3.0)) / (4.0 * log_mean_gap)
    scale = mean / shape
    if shape <= 0.0 or scale <= 0.0:
        return None

    if recent <= 0.0:
        # Everything at or below zero sits inside the zero point mass; convention puts
        # it at the midpoint of that mass.
        cumulative = zero_probability / 2.0
    else:
        gamma_cdf = _lower_gamma_regularised(shape, recent / scale)
        cumulative = zero_probability + (1.0 - zero_probability) * gamma_cdf

    # Keep the result off the infinities when the recent total sits outside the fitted
    # range entirely.
    cumulative = min(max(cumulative, 1e-6), 1.0 - 1e-6)
    return _inverse_standard_normal(cumulative)
