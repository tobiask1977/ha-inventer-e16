# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Firmware per component against the vendor catalog. Installing stays with the official app."""
from homeassistant.components.update import UpdateEntity
from homeassistant.const import EntityCategory

from . import client
from .entity import E16Entity

PARTS = ((client.HW_ESP32, "firmware_esp32"), (client.HW_MZCU, "firmware_mzcu"),
         (client.HW_FCU, "firmware_fcu"), (client.HW_SENSORS, "firmware_sensors"))


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(E16Firmware(entry.runtime_data.info, entry, *part) for part in PARTS)


class E16Firmware(E16Entity, UpdateEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, hardware, key):
        super().__init__(coordinator, entry, key)
        self.hardware = hardware

    def _installed(self):
        data = self.coordinator.data
        if self.hardware == client.HW_ESP32:
            image = data["esp32_firmware"]
            return image["version"] if image else None
        # Several fans/sensors: the oldest version counts
        versions = [d["firmware"] for d in data["devices"] if d["hardware"] == self.hardware]
        return min(versions) if versions else None

    @property
    def installed_version(self):
        version = self._installed()
        return client.version_text(version) if version else None

    @property
    def latest_version(self):
        catalog = self.coordinator.data.get("catalog")
        if not catalog or self.hardware not in catalog:
            # Catalog disabled or unreachable: report no update rather than a wrong one
            return self.installed_version
        return client.version_text(max(catalog[self.hardware], self._installed() or 0))
