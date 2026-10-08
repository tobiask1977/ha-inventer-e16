# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Config flow: host, device identity and PSK from the BLE onboarding tool.

Reauth starts by itself when the controller rejects the PSK (e.g. after a factory reset);
reconfigure changes host or PSK later - both keep entities, history and dashboards.
DHCP discovery: the controller's host name is "Easy Connect e16-<device id>" (seen on a real unit),
so host and device id come for free and only the PSK must be entered. For a configured controller a
new IP address is taken over automatically.
"""
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .client import E16AuthError, E16Client
from .const import CONF_DEVICE_ID, CONF_FIRMWARE_CATALOG, CONF_PSK, DOMAIN

PSK_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _clean_psk(value):
    return (value or "").strip().replace(" ", "").lower()


class E16ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._discovered = {}

    async def _async_check(self, host, psk):
        """Read the zone once; returns (zone, error key)."""
        try:
            zone = await self.hass.async_add_executor_job(E16Client(host, psk).get_zone)
        except (E16AuthError, ValueError):
            return None, "invalid_key"
        except OSError:
            return None, "cannot_connect"
        return zone, None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input[CONF_PSK] = _clean_psk(user_input[CONF_PSK])
            zone, error = await self._async_check(user_input[CONF_HOST], user_input[CONF_PSK])
            if error:
                errors["base"] = error
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
                vol.Required(CONF_PSK): PSK_SELECTOR,
            }),
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        # HA hands over the host name in lower case; device ids are upper case
        _, _, device_id = (discovery_info.hostname or "").partition("-")
        if not device_id:
            return self.async_abort(reason="not_supported")
        device_id = device_id.upper()
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self._discovered = {CONF_HOST: discovery_info.ip, CONF_DEVICE_ID: device_id}
        self.context["title_placeholders"] = {"name": device_id}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            psk = _clean_psk(user_input[CONF_PSK])
            zone, error = await self._async_check(self._discovered[CONF_HOST], psk)
            if error:
                errors["base"] = error
            else:
                title = f"inVENTer {zone['name']}" if zone["name"] else "inVENTer e16"
                return self.async_create_entry(title=title, data={**self._discovered, CONF_PSK: psk})
        return self.async_show_form(
            step_id="dhcp_confirm", errors=errors,
            description_placeholders={"host": self._discovered[CONF_HOST],
                                      "device_id": self._discovered[CONF_DEVICE_ID]},
            data_schema=vol.Schema({vol.Required(CONF_PSK): PSK_SELECTOR}),
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            psk = _clean_psk(user_input[CONF_PSK])
            _, error = await self._async_check(entry.data[CONF_HOST], psk)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PSK: psk})
        return self.async_show_form(
            step_id="reauth_confirm", errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
            data_schema=vol.Schema({vol.Required(CONF_PSK): PSK_SELECTOR}),
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            # Empty PSK field keeps the stored key
            psk = _clean_psk(user_input.get(CONF_PSK)) or entry.data[CONF_PSK]
            _, error = await self._async_check(host, psk)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host, CONF_PSK: psk})
        return self.async_show_form(
            step_id="reconfigure", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Optional(CONF_PSK): PSK_SELECTOR,
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
