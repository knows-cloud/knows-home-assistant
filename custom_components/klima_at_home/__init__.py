"""Klima @ Home — local climate, drought and groundwater for one place."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_STATION_COUNT, DEFAULT_STATION_COUNT, DOMAIN
from .coordinator import GroundwaterCoordinator, WeatherCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.WEATHER]


@dataclass(slots=True)
class KlimaAtHomeRuntime:
    """Everything the platforms need, hung off the config entry."""

    name: str
    weather: WeatherCoordinator
    groundwater: GroundwaterCoordinator | None


type KlimaAtHomeConfigEntry = ConfigEntry[KlimaAtHomeRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: KlimaAtHomeConfigEntry) -> bool:
    """Set up one location."""
    name = entry.data[CONF_NAME]
    latitude = entry.data[CONF_LATITUDE]
    longitude = entry.data[CONF_LONGITUDE]
    station_count = int(entry.options.get(CONF_STATION_COUNT, DEFAULT_STATION_COUNT))

    weather = WeatherCoordinator(hass, entry, latitude, longitude)
    await weather.async_config_entry_first_refresh()

    # Groundwater is Germany-only, so a location can legitimately have none. That is a
    # different thing from GRUVO being briefly unreachable: the first raises
    # ConfigEntryNotReady and gets retried, the second must not, or a location abroad
    # would retry forever. Only an empty *successful* answer means "no coverage here".
    groundwater: GroundwaterCoordinator | None = GroundwaterCoordinator(
        hass, entry, latitude, longitude, station_count
    )
    await groundwater.async_config_entry_first_refresh()
    if not groundwater.data:
        _LOGGER.info(
            "Keine Grundwassermessstellen in der Naehe von %s — die Integration laeuft "
            "ohne Grundwasser-Geraete weiter",
            name,
        )
        groundwater = None

    entry.runtime_data = KlimaAtHomeRuntime(
        name=name, weather=weather, groundwater=groundwater
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KlimaAtHomeConfigEntry) -> bool:
    """Tear the location down again."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: KlimaAtHomeConfigEntry) -> None:
    """Rebuild when the options change — the well count changes the entity set."""
    await hass.config_entries.async_reload(entry.entry_id)
