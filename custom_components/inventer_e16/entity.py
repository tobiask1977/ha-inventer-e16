# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Device mapping: the controller is the main device, fans and sensors hang below it."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import version_text
from .const import CONF_DEVICE_ID, DOMAIN

MODELS = {1: "Easy Connect e16", 2: "Fan unit (FCU)", 3: "Fan unit (FCU)",
          4: "Indoor sensor", 5: "Outdoor sensor"}


class E16Entity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, device=None):
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = key
        main = entry.data[CONF_DEVICE_ID]
        if device is None or device["type"] == 1:
            self._attr_unique_id = f"{main}_{key}"
            self._attr_device_info = {"identifiers": {(DOMAIN, main)}}
        else:
            self.address = device["address"]
            self._attr_unique_id = f"{main}_{device['address']}_{key}"
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{main}_{device['address']}")},
                "name": f"inVENTer {device['name'] or device['address']}",
                "manufacturer": "inVENTer",
                "model": MODELS.get(device["type"], f"Type {device['type']}"),
                "sw_version": version_text(device["firmware"]),
                "via_device_id": entry.runtime_data.main_device_id,
            }

    def device_row(self):
        return next((d for d in self.coordinator.data["devices"] if d["address"] == self.address), None)
