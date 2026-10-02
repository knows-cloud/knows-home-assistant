"""Sensors: weather, climate anomaly, drought, groundwater classification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KlimaAtHomeConfigEntry
from .api.gruvo import Station
from .const import (
    GRUVO_URL,
    GW_STATE_CLASSES,
    GW_STATE_OPTIONS,
    GW_TREND_CLASSES,
    GW_TREND_OPTIONS,
    GW_TREND_RANGES,
)
from .coordinator import GroundwaterCoordinator, WeatherCoordinator, WeatherData
from .entity import GroundwaterDeviceEntity, WeatherDeviceEntity


@dataclass(frozen=True, kw_only=True)
class KlimaSensorDescription(SensorEntityDescription):
    """A weather-device sensor and how to read its value."""

    value_fn: Callable[[WeatherData], float | int | None]
    attributes_fn: Callable[[WeatherData], dict[str, Any]] | None = None


WEATHER_SENSORS: tuple[KlimaSensorDescription, ...] = (
    KlimaSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.snapshot.temperature,
    ),
    KlimaSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.snapshot.humidity,
    ),
    KlimaSensorDescription(
        key="temperature_anomaly",
        translation_key="temperature_anomaly",
        # Deliberately not device_class TEMPERATURE: this is a temperature *difference*,
        # and HA would happily convert it to Fahrenheit by adding 32.
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-alert",
        suggested_display_precision=1,
        value_fn=lambda data: data.anomaly,
        attributes_fn=lambda data: {
            "normal_1961_1990": _round(data.normal_today, 1),
            "tagesmittel_heute": _round(data.today_mean, 1),
            "referenzperiode": "1961-1990 (WMO)",
        },
    ),
    KlimaSensorDescription(
        key="dry_days",
        translation_key="dry_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda data: data.dry_days,
        attributes_fn=lambda data: {
            # "A dry day is < 1 mm" is the ETCCDI convention, not an arbitrary choice —
            # say so, because the number is otherwise unfalsifiable.
            "definition": "Trockentag = weniger als 1 mm Niederschlag (ETCCDI)",
            "trockener_als_in_prozent_der_jahre": _round(data.dry_spell_percentile, 0),
        },
    ),
    KlimaSensorDescription(
        key="precipitation_30d_percent",
        translation_key="precipitation_30d_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        suggested_display_precision=0,
        value_fn=lambda data: data.precipitation_30d_percent,
        attributes_fn=lambda data: {
            "niederschlag_30_tage_mm": _round(data.precipitation_30d, 1),
            "vergleichszeitraum": "1961-1990, gleiche Jahreszeit",
        },
    ),
    KlimaSensorDescription(
        key="precipitation_90d_percent",
        translation_key="precipitation_90d_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        suggested_display_precision=0,
        value_fn=lambda data: data.precipitation_90d_percent,
    ),
    KlimaSensorDescription(
        key="spi_30d",
        translation_key="spi_30d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        suggested_display_precision=2,
        value_fn=lambda data: data.spi_30d,
        attributes_fn=lambda data: {
            "einordnung": _spi_label(data.spi_30d),
            "methode": "Standardized Precipitation Index (WMO)",
        },
    ),
    KlimaSensorDescription(
        key="spi_90d",
        translation_key="spi_90d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        suggested_display_precision=2,
        value_fn=lambda data: data.spi_90d,
        attributes_fn=lambda data: {"einordnung": _spi_label(data.spi_90d)},
    ),
)


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _spi_label(value: float | None) -> str | None:
    """The conventional SPI wording, so the bare number means something."""
    if value is None:
        return None
    if value <= -2.0:
        return "extreme Duerre"
    if value <= -1.5:
        return "schwere Duerre"
    if value <= -1.0:
        return "maessige Duerre"
    if value < 1.0:
        return "normal"
    if value < 1.5:
        return "feucht"
    return "sehr feucht"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlimaAtHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data

    entities: list[SensorEntity] = [
        KlimaWeatherSensor(runtime.weather, entry.entry_id, runtime.name, description)
        for description in WEATHER_SENSORS
    ]

    if runtime.groundwater is not None:
        for station in runtime.groundwater.data:
            entities.append(
                GroundwaterStateSensor(runtime.groundwater, entry.entry_id, station)
            )
            entities.append(
                GroundwaterForecastSensor(runtime.groundwater, entry.entry_id, station)
            )
            entities.append(
                GroundwaterTrendSensor(runtime.groundwater, entry.entry_id, station)
            )

    async_add_entities(entities)


class KlimaWeatherSensor(WeatherDeviceEntity, SensorEntity):
    """A sensor on the weather device."""

    entity_description: KlimaSensorDescription

    def __init__(
        self,
        coordinator: WeatherCoordinator,
        entry_id: str,
        place: str,
        description: KlimaSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, place)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class GroundwaterStateSensor(GroundwaterDeviceEntity, SensorEntity):
    """The official BGR classification of the current groundwater level."""

    _attr_translation_key = "groundwater_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GW_STATE_OPTIONS
    _attr_icon = "mdi:water-well"

    def __init__(
        self, coordinator: GroundwaterCoordinator, entry_id: str, station: Station
    ) -> None:
        super().__init__(coordinator, entry_id, station)
        self._attr_unique_id = f"{entry_id}_gw_{station.well_id}_state"

    @property
    def native_value(self) -> str | None:
        station = self.station
        if station is None:
            return None
        # An unknown code must not be guessed into a class — 121 of GRUVO's wells carry
        # no current state at all, and a wrong "normal" would be worse than no reading.
        return GW_STATE_CLASSES.get(station.state_now)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        station = self.station
        if station is None:
            return None
        return {
            "messstelle": station.name,
            "messstellen_id": station.well_id,
            "entfernung_km": round(station.distance_km, 1),
            "datenstand": station.measured_on.isoformat() if station.measured_on else None,
            "typ": "Referenzmessstelle" if station.is_reference else "Clustermessstelle",
            "trend_4_wochen": GW_TREND_CLASSES.get(station.trend_4w),
            "trend_4_wochen_bereich": GW_TREND_RANGES.get(station.trend_4w),
            "prognose_12_wochen": GW_STATE_CLASSES.get(station.state_12w),
            "bgr_guete_code": station.quality_code,
            "referenzzeitraum": "1991-2020 (Perzentile, BGR)",
            "quelle": GRUVO_URL,
        }


class GroundwaterForecastSensor(GroundwaterDeviceEntity, SensorEntity):
    """BGR's 4-week outlook for the same well."""

    _attr_translation_key = "groundwater_forecast_4w"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GW_STATE_OPTIONS
    _attr_icon = "mdi:water-outline"

    def __init__(
        self, coordinator: GroundwaterCoordinator, entry_id: str, station: Station
    ) -> None:
        super().__init__(coordinator, entry_id, station)
        self._attr_unique_id = f"{entry_id}_gw_{station.well_id}_forecast_4w"

    @property
    def native_value(self) -> str | None:
        station = self.station
        if station is None:
            return None
        return GW_STATE_CLASSES.get(station.state_4w)


class GroundwaterTrendSensor(GroundwaterDeviceEntity, SensorEntity):
    """Direction of travel over the next four weeks."""

    _attr_translation_key = "groundwater_trend"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GW_TREND_OPTIONS
    _attr_icon = "mdi:trending-down"

    def __init__(
        self, coordinator: GroundwaterCoordinator, entry_id: str, station: Station
    ) -> None:
        super().__init__(coordinator, entry_id, station)
        self._attr_unique_id = f"{entry_id}_gw_{station.well_id}_trend"

    @property
    def native_value(self) -> str | None:
        station = self.station
        if station is None:
            return None
        return GW_TREND_CLASSES.get(station.trend_4w)
