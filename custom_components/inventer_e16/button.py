# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Quick commands as on the app home screen, and resetting the maintenance timers."""
import struct

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from . import client
from .entity import E16Entity

# Boost like the app's quick boost for this controller family: 15 min. Quick pause of the app's
# home screen: ends after one hour. Which command goes out depends on the number of zones.
COMMANDS = {
    "boost": lambda zones, zone_id: zones.async_boost(zone_id, 900),
    "resume": lambda zones, zone_id: zones.async_resume(zone_id),
    "pause_1h": lambda zones, zone_id: zones.async_pause(zone_id, 3600),
}
RESETS = (("filter_reset", client.F_FILTER_RESET), ("service_reset", client.F_SERVICE_RESET))


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    async_add_entities([
        *(E16Command(data.zone, entry, key, zone_id=zone_id)
          for zone_id in data.zone.zone_ids for key in COMMANDS),
        *(E16Reset(data.info, entry, *item) for item in RESETS),
    ])


class E16Command(E16Entity, ButtonEntity):
    async def async_press(self):
        await COMMANDS[self.key](self.coordinator, self.zone_id)


class E16Reset(E16Entity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key, field_id):
        super().__init__(coordinator, entry, key)
        self.field_id = field_id

    async def async_press(self):
        await self.coordinator.async_set_global_field(
            self.field_id, struct.pack("<I", client.RESET_MAGIC[self.field_id]))
