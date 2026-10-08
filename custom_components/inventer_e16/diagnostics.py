# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Diagnostics download - PSK, host and device identity are redacted."""
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .const import CONF_DEVICE_ID, CONF_PSK

TO_REDACT = {CONF_PSK, CONF_HOST, CONF_DEVICE_ID}


async def async_get_config_entry_diagnostics(hass, entry):
    data = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "zone": data.zone.data,
        "info": data.info.data,
    }
