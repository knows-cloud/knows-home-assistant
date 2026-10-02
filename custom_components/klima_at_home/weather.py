"""The weather entity: current conditions plus a 7-day forecast."""

from __future__ import annotations

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KlimaAtHomeConfigEntry
from .entity import WeatherDeviceEntity

# WMO 4677 weather codes -> Home Assistant conditions.
# HA has no "drizzle" or "freezing rain" of its own, so drizzle folds into rainy and
# freezing rain into the sleet-ish snowy-rainy, which is what a user would expect to see.
WMO_CONDITIONS: dict[int, str] = {
    0: "sunny",
    1: "sunny",
    2: "partlycloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rainy",
    53: "rainy",
    55: "rainy",
    56: "snowy-rainy",
    57: "snowy-rainy",
    61: "rainy",
    63: "rainy",
    65: "pouring",
    66: "snowy-rainy",
    67: "snowy-rainy",
    71: "snowy",
    73: "snowy",
    75: "snowy",
    77: "snowy",
    80: "rainy",
    81: "rainy",
    82: "pouring",
    85: "snowy",
    86: "snowy",
    95: "lightning",
    96: "lightning-rainy",
    99: "lightning-rainy",
}


def to_condition(code: int | None, is_night: bool = False) -> str | None:
    """Translate a WMO code, keeping the clear-night distinction HA expects."""
    if code is None:
        return None
    condition = WMO_CONDITIONS.get(code)
    if condition == "sunny" and is_night:
        return "clear-night"
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlimaAtHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [KlimaAtHomeWeather(runtime.weather, entry.entry_id, runtime.name)]
    )


class KlimaAtHomeWeather(WeatherDeviceEntity, WeatherEntity):
    """Open-Meteo weather for the configured place."""

    _attr_name = None  # The device name is the entity name.
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = "mm"

    def __init__(self, coordinator, entry_id: str, place: str) -> None:
        super().__init__(coordinator, entry_id, place)
        self._attr_unique_id = f"{entry_id}_weather"

    @property
    def condition(self) -> str | None:
        sun = self.hass.states.get("sun.sun")
        is_night = sun is not None and sun.state == "below_horizon"
        return to_condition(self.coordinator.data.snapshot.condition_code, is_night)

    @property
    def native_temperature(self) -> float | None:
        return self.coordinator.data.snapshot.temperature

    @property
    def native_apparent_temperature(self) -> float | None:
        return self.coordinator.data.snapshot.apparent_temperature

    @property
    def humidity(self) -> float | None:
        return self.coordinator.data.snapshot.humidity

    @property
    def native_pressure(self) -> float | None:
        return self.coordinator.data.snapshot.pressure

    @property
    def native_wind_speed(self) -> float | None:
        return self.coordinator.data.snapshot.wind_speed

    @property
    def wind_bearing(self) -> float | None:
        return self.coordinator.data.snapshot.wind_bearing

    async def async_forecast_daily(self) -> list[Forecast]:
        return [
            Forecast(
                datetime=day.day.isoformat(),
                condition=to_condition(day.condition_code),
                native_temperature=day.temperature_max,
                native_templow=day.temperature_min,
                native_precipitation=day.precipitation,
                precipitation_probability=day.precipitation_probability,
                native_wind_speed=day.wind_speed,
            )
            for day in self.coordinator.data.snapshot.forecast
        ]
