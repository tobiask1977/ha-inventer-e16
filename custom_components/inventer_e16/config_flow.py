# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Config flow: host, device identity and PSK from the BLE onboarding tool."""
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import E16Client
from .const import CONF_DEVICE_ID, CONF_FIRMWARE_CATALOG, CONF_PSK, DOMAIN


class E16ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input[CONF_PSK] = user_input[CONF_PSK].strip().replace(" ", "").lower()
            try:
                client = E16Client(user_input[CONF_HOST], user_input[CONF_PSK])
                zone = await self.hass.async_add_executor_job(client.get_zone)
            except ValueError:
                errors["base"] = "invalid_key"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_DEVICE_ID].strip())
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                title = f"inVENTer {zone['name']}" if zone["name"] else "inVENTer e16"
                return self.async_create_entry(title=title, data=user_input)
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_PSK): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return E16OptionsFlow()


class E16OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_FIRMWARE_CATALOG, True)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_FIRMWARE_CATALOG, default=current): bool}),
        )
