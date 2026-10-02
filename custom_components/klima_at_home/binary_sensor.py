"""Binary sensors: the two "is this bad right now" triggers for automations."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KlimaAtHomeConfigEntry
from .api.gruvo import Station
from .const import (
    DROUGHT_DRY_DAYS_THRESHOLD,
    DROUGHT_SPI_THRESHOLD,
    GW_CRITICAL_CLASS,
    GW_STATE_CLASSES,
)
from .coordinator import GroundwaterCoordinator, WeatherCoordinator
from .entity import GroundwaterDeviceEntity, WeatherDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlimaAtHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data

    entities: list[BinarySensorEntity] = [
        DroughtBinarySensor(runtime.weather, entry.entry_id, runtime.name)
    ]

    if runtime.groundwater is not None:
        entities.extend(
            GroundwaterCriticalBinarySensor(runtime.groundwater, entry.entry_id, station)
            for station in runtime.groundwater.data
        )

    async_add_entities(entities)


class DroughtBinarySensor(WeatherDeviceEntity, BinarySensorEntity):
    """On when the place is meaningfully in drought.

    Two independent ways to qualify, because they catch different things: a long rainless
    streak (what people notice) and a genuinely deficient 30-day total (what plants and
    groundwater notice). A short, sharp dry spell after a wet month is not a drought, and
    a wet month with drizzle every fourth day but well below normal is.
    """

    _attr_translation_key = "drought"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:sprout-outline"

    def __init__(self, coordinator: WeatherCoordinator, entry_id: str, place: str) -> None:
        super().__init__(coordinator, entry_id, place)
        self._attr_unique_id = f"{entry_id}_drought"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        long_dry_spell = data.dry_days >= DROUGHT_DRY_DAYS_THRESHOLD
        deficient = data.spi_30d is not None and data.spi_30d <= DROUGHT_SPI_THRESHOLD
        return long_dry_spell or deficient

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "tage_ohne_regen": data.dry_days,
            "spi_30d": None if data.spi_30d is None else round(data.spi_30d, 2),
            "ausgeloest_durch": _drought_reason(data.dry_days, data.spi_30d),
        }


def _drought_reason(dry_days: int, spi_30d: float | None) -> str | None:
    reasons = []
    if dry_days >= DROUGHT_DRY_DAYS_THRESHOLD:
        reasons.append(f"{dry_days} Tage ohne Regen")
    if spi_30d is not None and spi_30d <= DROUGHT_SPI_THRESHOLD:
        reasons.append(f"SPI-30 = {spi_30d:.2f}")
    return " und ".join(reasons) if reasons else None


class GroundwaterCriticalBinarySensor(GroundwaterDeviceEntity, BinarySensorEntity):
    """On when BGR classes this well's level as "sehr niedrig".

    This is the user-facing "kritisch" flag. It is kept separate from the five-class
    sensor on purpose: the official scale has no "critical" step, and bending it to add
    one would misreport what BGR actually says. BGR is also explicit that "sehr niedrig"
    is a statistical statement, not a declaration of water shortage.
    """

    _attr_translation_key = "groundwater_critical"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:water-alert"

    def __init__(
        self, coordinator: GroundwaterCoordinator, entry_id: str, station: Station
    ) -> None:
        super().__init__(coordinator, entry_id, station)
        self._attr_unique_id = f"{entry_id}_gw_{station.well_id}_critical"

    @property
    def is_on(self) -> bool | None:
        station = self.station
        if station is None:
            return None
        state = GW_STATE_CLASSES.get(station.state_now)
        if state is None:
            return None
        return state == GW_CRITICAL_CLASS
