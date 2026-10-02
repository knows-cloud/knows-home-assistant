"""Data coordinators.

Two of them, on deliberately different clocks: weather moves constantly (30 min), while
GRUVO only advances its data once a month, so polling it hard would hammer the BGR for
nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import gruvo, open_meteo
from .api.gruvo import Station
from .climatology import bias_offset, daily_normals, day_key, temperature_anomaly
from .const import (
    BASELINE_END,
    BASELINE_START,
    BIAS_YEARS,
    DOMAIN,
    DRY_DAY_THRESHOLD_MM,
    GROUNDWATER_UPDATE_INTERVAL,
    RECENT_DAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
    WEATHER_UPDATE_INTERVAL,
)
from .drought import (
    consecutive_dry_days,
    deficit_percent,
    historical_window_sums,
    percentile_of,
    spi,
    window_sum,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Baseline:
    """The 1961-1990 climatology for one location.

    Computed once and persisted. It cannot change — the reference period is closed — so
    re-fetching 30 years of ERA5 on every Home Assistant restart would be pure waste and
    would block startup for minutes.
    """

    normals: dict[int, float]
    temperature_offset: float
    precipitation_scale: float
    dates: list[date]
    precipitation: list[float | None]

    def as_dict(self) -> dict:
        return {
            "normals": {str(key): value for key, value in self.normals.items()},
            "temperature_offset": self.temperature_offset,
            "precipitation_scale": self.precipitation_scale,
            "dates": [day.isoformat() for day in self.dates],
            "precipitation": self.precipitation,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Baseline:
        return cls(
            normals={int(key): value for key, value in raw["normals"].items()},
            temperature_offset=raw["temperature_offset"],
            precipitation_scale=raw["precipitation_scale"],
            dates=[date.fromisoformat(value) for value in raw["dates"]],
            precipitation=raw["precipitation"],
        )


@dataclass(slots=True)
class WeatherData:
    """What the weather, climate and drought entities render."""

    snapshot: open_meteo.WeatherSnapshot
    today_mean: float | None
    anomaly: float | None
    normal_today: float | None
    dry_days: int
    precipitation_30d: float | None
    precipitation_30d_percent: float | None
    precipitation_90d_percent: float | None
    spi_30d: float | None
    spi_90d: float | None
    dry_spell_percentile: float | None


class WeatherCoordinator(DataUpdateCoordinator[WeatherData]):
    """Open-Meteo: current conditions, forecast, climate anomaly, drought."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, latitude: float, longitude: float
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_weather",
            update_interval=WEATHER_UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.latitude = latitude
        self.longitude = longitude
        self._session = async_get_clientsession(hass)
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._baseline: Baseline | None = None

    async def _async_baseline(self) -> Baseline:
        if self._baseline is not None:
            return self._baseline

        stored = await self._store.async_load()
        if stored:
            try:
                self._baseline = Baseline.from_dict(stored)
                return self._baseline
            except (KeyError, ValueError):
                _LOGGER.warning("Baseline-Cache unlesbar, wird neu berechnet")

        _LOGGER.info(
            "Lade einmalig die Klima-Baseline 1961-1990 fuer %.4f/%.4f — das dauert einen Moment",
            self.latitude,
            self.longitude,
        )
        self._baseline = await self._async_build_baseline()
        await self._store.async_save(self._baseline.as_dict())
        return self._baseline

    async def _async_build_baseline(self) -> Baseline:
        era5 = await open_meteo.async_fetch_archive(
            self._session, self.latitude, self.longitude, BASELINE_START, BASELINE_END
        )
        if not era5.dates:
            raise UpdateFailed("ERA5 lieferte keine Baseline-Daten")

        normals = daily_normals(era5.dates, era5.temperature_mean)

        # Measure the high-resolution model against ERA5 over a recent overlap, so the
        # anomaly compares like with like. Without this the difference between a ~28 km
        # ERA5 cell and the real site — mostly elevation — is silently booked as climate
        # signal.
        today = datetime.now().date()
        overlap_end = today - timedelta(days=7)  # ERA5 lags reality by ~5 days.
        overlap_start = overlap_end - timedelta(days=365 * BIAS_YEARS)

        temperature_offset = 0.0
        precipitation_scale = 1.0
        try:
            reference = await open_meteo.async_fetch_archive(
                self._session,
                self.latitude,
                self.longitude,
                overlap_start.isoformat(),
                overlap_end.isoformat(),
            )
            model = await open_meteo.async_fetch_historical_forecast(
                self._session,
                self.latitude,
                self.longitude,
                overlap_start.isoformat(),
                overlap_end.isoformat(),
            )
            temperature_offset = bias_offset(
                reference.dates,
                reference.temperature_mean,
                model.dates,
                model.temperature_mean,
            )
            precipitation_scale = _precipitation_scale(reference, model)
        except open_meteo.OpenMeteoError as err:
            # An uncorrected anomaly is still far better than no anomaly; be loud, not fatal.
            _LOGGER.warning(
                "Bias-Korrektur konnte nicht bestimmt werden (%s) — die Temperaturabweichung "
                "kann dadurch systematisch um bis zu ~1-2 K daneben liegen",
                err,
            )

        return Baseline(
            normals=normals,
            temperature_offset=temperature_offset,
            precipitation_scale=precipitation_scale,
            dates=era5.dates,
            precipitation=era5.precipitation,
        )

    async def _async_update_data(self) -> WeatherData:
        try:
            snapshot = await open_meteo.async_fetch_weather(
                self._session, self.latitude, self.longitude
            )
            recent_series = await open_meteo.async_fetch_recent(
                self._session, self.latitude, self.longitude, RECENT_DAYS
            )
            baseline = await self._async_baseline()
        except open_meteo.OpenMeteoError as err:
            raise UpdateFailed(str(err)) from err

        today = datetime.now().date()

        today_mean = _value_on(recent_series, today)
        anomaly = None
        normal_today = baseline.normals.get(day_key(today))
        if today_mean is not None:
            anomaly = temperature_anomaly(
                today_mean, baseline.normals, baseline.temperature_offset, today
            )

        # Recent precipitation comes from the high-resolution model, the climatology from
        # ERA5. Same mismatch as with temperature, but precipitation biases are
        # multiplicative rather than additive, so it is scaled rather than shifted.
        recent = [
            value * baseline.precipitation_scale if value is not None else None
            for value in recent_series.precipitation
        ]

        dry_days = consecutive_dry_days(recent_series.precipitation)
        sum_30d = window_sum(recent, 30)
        sum_90d = window_sum(recent, 90)

        history_30d = historical_window_sums(baseline.dates, baseline.precipitation, 30, today)
        history_90d = historical_window_sums(baseline.dates, baseline.precipitation, 90, today)

        dry_spell_percentile = None
        historical_streaks = _historical_dry_spells(baseline.dates, baseline.precipitation, today)
        if historical_streaks:
            dry_spell_percentile = percentile_of(float(dry_days), historical_streaks)

        return WeatherData(
            snapshot=snapshot,
            today_mean=today_mean,
            anomaly=anomaly,
            normal_today=normal_today,
            dry_days=dry_days,
            precipitation_30d=sum_30d,
            precipitation_30d_percent=(
                deficit_percent(sum_30d, history_30d) if sum_30d is not None else None
            ),
            precipitation_90d_percent=(
                deficit_percent(sum_90d, history_90d) if sum_90d is not None else None
            ),
            spi_30d=spi(sum_30d, history_30d) if sum_30d is not None else None,
            spi_90d=spi(sum_90d, history_90d) if sum_90d is not None else None,
            dry_spell_percentile=dry_spell_percentile,
        )


class GroundwaterCoordinator(DataUpdateCoordinator[list[Station]]):
    """BGR GRUVO: the nearest wells and their official classification."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        latitude: float,
        longitude: float,
        count: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_groundwater",
            update_interval=GROUNDWATER_UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.latitude = latitude
        self.longitude = longitude
        self.count = count
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> list[Station]:
        try:
            return await gruvo.async_find_nearest(
                self._session, self.latitude, self.longitude, self.count
            )
        except gruvo.GruvoError as err:
            raise UpdateFailed(str(err)) from err


def _value_on(series: open_meteo.DailySeries, day: date) -> float | None:
    """The daily mean temperature on a given day, if the series carries it."""
    for index, entry in enumerate(series.dates):
        if entry == day and index < len(series.temperature_mean):
            return series.temperature_mean[index]
    return None


def _precipitation_scale(
    reference: open_meteo.DailySeries, model: open_meteo.DailySeries
) -> float:
    """How much wetter the high-resolution model is than ERA5 at this spot."""
    reference_total = sum(value for value in reference.precipitation if value)
    model_total = sum(value for value in model.precipitation if value)
    if model_total <= 0 or reference_total <= 0:
        return 1.0
    scale = reference_total / model_total
    # A correction outside this range means something else is wrong; don't let a bad fit
    # quietly rescale every drought number.
    return scale if 0.5 <= scale <= 2.0 else 1.0


def _historical_dry_spells(
    dates: list[date], precipitation: list[float | None], ending_on: date
) -> list[float]:
    """Dry-spell length on this calendar day, one value per historical year.

    Fourteen dry days in August is unremarkable; in November it is not. Comparing against
    the same day of the year is what makes "how unusual is this" mean anything.
    """
    series = [(day, value) for day, value in zip(dates, precipitation) if value is not None]
    target = day_key(ending_on)

    spells: list[float] = []
    for index, (day, _) in enumerate(series):
        if day_key(day) != target:
            continue
        streak = 0
        for back in range(index, -1, -1):
            if series[back][1] >= DRY_DAY_THRESHOLD_MM:
                break
            streak += 1
        spells.append(float(streak))
    return spells
