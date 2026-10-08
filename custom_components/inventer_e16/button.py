# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Quick commands as on the app home screen, and resetting the maintenance timers."""
import struct

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from . import client
from .entity import E16Entity

# Boost like the app's quick boost for this controller family: 15 min
COMMANDS = (
    ("boost", (client.CMD_GLOBAL_BOOST, 4, client.FAN_VENTILATION, client.ZONE_GLOBAL, 900)),
    ("resume", (client.CMD_CANCEL, 0, client.FAN_OFF, client.ZONE_GLOBAL, 0)),
    # Quick pause of the app's home screen: ends after one hour
    ("pause_1h", (client.CMD_GLOBAL_PAUSE, 0, client.FAN_OFF, client.ZONE_GLOBAL, 3600)),
)
RESETS = (("filter_reset", client.F_FILTER_RESET), ("service_reset", client.F_SERVICE_RESET))


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    async_add_entities([*(E16Command(data.zone, entry, *item) for item in COMMANDS),
                        *(E16Reset(data.info, entry, *item) for item in RESETS)])


class E16Command(E16Entity, ButtonEntity):
    def __init__(self, coordinator, entry, key, command):
        super().__init__(coordinator, entry, key)
        self.command = command

    async def async_press(self):
        await self.coordinator.async_override(*self.command)


class E16Reset(E16Entity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key, field_id):
        super().__init__(coordinator, entry, key)
        self.field_id = field_id

    async def async_press(self):
        await self.coordinator.async_set_global_field(
            self.field_id, struct.pack("<I", client.RESET_MAGIC[self.field_id]))
