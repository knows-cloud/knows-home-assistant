"""End-to-end run inside a real Home Assistant, against the real APIs.

This is the test that actually proves the thing works: it stands up Home Assistant, sets
up a config entry exactly as the UI would, lets the integration talk to Open-Meteo and
BGR for real, and then inspects the entities a user would see.

Entities are resolved through the entity registry by unique_id, never by entity_id. Home
Assistant derives entity_ids from the *translated* entity name, so they come out German
on a German instance and English on an English one — asserting on them would make this
test pass or fail depending on the user's language.

Needs the network. Skip with:  pytest -m "not live"
"""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klima_at_home.const import (
    CONF_STATION_COUNT,
    DOMAIN,
    GW_STATE_OPTIONS,
    GW_TREND_OPTIONS,
)

pytestmark = pytest.mark.live

KASSEL = (51.3127, 9.4797)
VIENNA = (48.2082, 16.3738)  # Outside Germany: no groundwater coverage.


async def _setup(hass: HomeAssistant, name: str, lat: float, lon: float, count: int = 3):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={CONF_NAME: name, CONF_LATITUDE: lat, CONF_LONGITUDE: lon},
        options={CONF_STATION_COUNT: count},
        unique_id=f"{lat:.2f},{lon:.2f}",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, platform: str, unique_id: str) -> State:
    """Resolve one entity by unique_id — language-proof, unlike entity_id."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, f"keine Entitaet mit unique_id {unique_id}"
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} hat keinen Zustand"
    return state


def _states_ending(hass: HomeAssistant, entry_id: str, suffix: str) -> list[State]:
    registry = er.async_get(hass)
    return [
        hass.states.get(entry.entity_id)
        for entry in registry.entities.values()
        if entry.config_entry_id == entry_id and entry.unique_id.endswith(suffix)
    ]


@pytest.mark.asyncio
async def test_german_location_gets_weather_climate_drought_and_groundwater(
    hass: HomeAssistant, live_network
):
    entry = await _setup(hass, "Kassel", *KASSEL)
    eid = entry.entry_id

    # --- weather -------------------------------------------------------------
    weather = _state(hass, "weather", f"{eid}_weather")
    assert weather.state not in ("unknown", "unavailable")
    assert isinstance(weather.attributes.get("temperature"), (int, float))
    assert isinstance(weather.attributes.get("humidity"), (int, float))

    forecast = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": weather.entity_id, "type": "daily"},
        blocking=True,
        return_response=True,
    )
    days = forecast[weather.entity_id]["forecast"]
    assert len(days) == 7, f"7-Tage-Vorhersage erwartet, bekommen: {len(days)}"
    assert all(day["condition"] is not None for day in days)

    # --- climate anomaly -----------------------------------------------------
    anomaly = _state(hass, "sensor", f"{eid}_temperature_anomaly")
    value = float(anomaly.state)
    # Outside this band it is not an anomaly, it is a bug — most likely the ERA5 /
    # high-res bias offset failing to apply.
    assert -20.0 < value < 20.0, f"unplausible Abweichung {value}"
    assert anomaly.attributes["referenzperiode"] == "1961-1990 (WMO)"
    assert isinstance(anomaly.attributes["normal_1961_1990"], (int, float))
    assert isinstance(anomaly.attributes["tagesmittel_heute"], (int, float))

    # The published number must actually be today's mean minus the normal (give or take
    # the bias offset), or the sensor is not what its label says it is.
    raw_gap = (
        anomaly.attributes["tagesmittel_heute"] - anomaly.attributes["normal_1961_1990"]
    )
    assert abs(value - raw_gap) < 3.0, (value, raw_gap)

    # --- drought -------------------------------------------------------------
    assert int(_state(hass, "sensor", f"{eid}_dry_days").state) >= 0

    # These are the ones that used to come back empty: the forecast endpoint's past_days
    # silently returns null beyond ~67 days, which emptied the 90-day window. An
    # "unknown" here means that regression is back.
    for key in (
        "spi_30d",
        "spi_90d",
        "precipitation_30d_percent",
        "precipitation_90d_percent",
    ):
        sensor = _state(hass, "sensor", f"{eid}_{key}")
        assert sensor.state not in ("unknown", "unavailable"), f"{key} hat keine Daten"

    assert -5.0 < float(_state(hass, "sensor", f"{eid}_spi_30d").state) < 5.0
    assert -5.0 < float(_state(hass, "sensor", f"{eid}_spi_90d").state) < 5.0
    assert float(_state(hass, "sensor", f"{eid}_precipitation_30d_percent").state) >= 0.0

    assert _state(hass, "binary_sensor", f"{eid}_drought").state in ("on", "off")

    # --- groundwater ---------------------------------------------------------
    classes = _states_ending(hass, eid, "_state")
    assert len(classes) == 3, f"3 Messstellen erwartet, bekommen: {len(classes)}"

    for state in classes:
        assert state.state in GW_STATE_OPTIONS, state.state
        assert state.attributes["messstellen_id"]
        assert state.attributes["referenzzeitraum"] == "1991-2020 (Perzentile, BGR)"

    distances = [state.attributes["entfernung_km"] for state in classes]
    assert distances == sorted(distances), f"nicht nach Entfernung sortiert: {distances}"
    assert max(distances) < 200.0, distances

    forecasts = _states_ending(hass, eid, "_forecast_4w")
    assert len(forecasts) == 3
    assert all(state.state in GW_STATE_OPTIONS for state in forecasts)

    trends = _states_ending(hass, eid, "_trend")
    assert len(trends) == 3
    assert all(state.state in GW_TREND_OPTIONS for state in trends)

    # "kritisch" must fire exactly when BGR says "sehr niedrig" — never on its own.
    critical = _states_ending(hass, eid, "_critical")
    assert len(critical) == 3
    assert all(state.state in ("on", "off") for state in critical)

    very_low = sum(1 for state in classes if state.state == "sehr_niedrig")
    flagged = sum(1 for state in critical if state.state == "on")
    assert flagged == very_low, (
        f"{very_low} Messstellen sind 'sehr niedrig', aber {flagged} als kritisch markiert"
    )


@pytest.mark.asyncio
async def test_location_without_groundwater_still_gets_weather(
    hass: HomeAssistant, live_network
):
    """Vienna has no GRUVO coverage. Weather must still work, and nothing may error."""
    entry = await _setup(hass, "Wien", *VIENNA)
    eid = entry.entry_id

    assert _state(hass, "weather", f"{eid}_weather").state not in (
        "unknown",
        "unavailable",
    )
    assert -20.0 < float(_state(hass, "sensor", f"{eid}_temperature_anomaly").state) < 20.0

    assert _states_ending(hass, eid, "_state") == []
    assert _states_ending(hass, eid, "_critical") == []
