"""Shared entity plumbing: the two device shapes."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.gruvo import Station
from .const import ATTRIBUTION, DOMAIN, GRUVO_URL
from .coordinator import GroundwaterCoordinator, WeatherCoordinator


class WeatherDeviceEntity(CoordinatorEntity[WeatherCoordinator]):
    """Entity on the "Wetter <place>" device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: WeatherCoordinator, entry_id: str, place: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_weather")},
            name=f"Wetter {place}",
            manufacturer="Open-Meteo",
            model="ERA5 / Vorhersagemodell",
            entry_type=None,
            configuration_url="https://open-meteo.com/",
        )


class GroundwaterDeviceEntity(CoordinatorEntity[GroundwaterCoordinator]):
    """Entity on a "Grundwasser <well>" device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: GroundwaterCoordinator, entry_id: str, station: Station
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._well_id = station.well_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_gw_{station.well_id}")},
            name=f"Grundwasser {station.name.title()}",
            manufacturer="BGR",
            model="GRUVO Messstelle",
            configuration_url=GRUVO_URL,
        )

    @property
    def station(self) -> Station | None:
        """This entity's well in the latest poll — wells can drop out of the answer."""
        for station in self.coordinator.data or []:
            if station.well_id == self._well_id:
                return station
        return None

    @property
    def available(self) -> bool:
        return super().available and self.station is not None
