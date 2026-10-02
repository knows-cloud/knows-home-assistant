"""Config flow — pick a place on the map, that's it."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_LOCATION,
    CONF_STATION_COUNT,
    DEFAULT_STATION_COUNT,
    DOMAIN,
    MAX_STATION_COUNT,
)


class KlimaAtHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one location."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            location = user_input[CONF_LOCATION]
            latitude = location[CONF_LATITUDE]
            longitude = location[CONF_LONGITUDE]

            # One entry per place. Rounding to ~1 km keeps a nudge on the map from
            # creating a duplicate location.
            await self.async_set_unique_id(f"{latitude:.2f},{longitude:.2f}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                },
                options={CONF_STATION_COUNT: user_input[CONF_STATION_COUNT]},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self.hass.config.location_name): str,
                vol.Required(
                    CONF_LOCATION,
                    default={
                        CONF_LATITUDE: self.hass.config.latitude,
                        CONF_LONGITUDE: self.hass.config.longitude,
                    },
                ): selector.LocationSelector(),
                vol.Required(
                    CONF_STATION_COUNT, default=DEFAULT_STATION_COUNT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=MAX_STATION_COUNT, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> KlimaAtHomeOptionsFlow:
        return KlimaAtHomeOptionsFlow()


class KlimaAtHomeOptionsFlow(OptionsFlow):
    """Change how many wells are tracked."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_STATION_COUNT, DEFAULT_STATION_COUNT)
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_COUNT, default=current): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=MAX_STATION_COUNT, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
