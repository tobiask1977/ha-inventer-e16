# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Device mapping: the controller is the main device and carries zone 1. Further zones are devices
below it, and each fan and sensor hangs below its zone."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import version_text
from .const import CONF_DEVICE_ID, DOMAIN

MODELS = {1: "Easy Connect e16", 2: "Fan unit (FCU)", 3: "Fan unit (FCU)",
          4: "Indoor sensor", 5: "Outdoor sensor", 27: "Fan unit (iV-Twin+)"}
INDOOR_SENSOR = 4
# One outdoor sensor serves all zones: its values show on zone 1 only
OUTDOOR_KEYS = {"outside_temperature", "outside_humidity", "dew_point_outside",
                "absolute_humidity_outside"}
# Need an indoor sensor in the zone
INDOOR_KEYS = {"inside_temperature", "inside_humidity", "dew_point_inside",
               "absolute_humidity_inside", "dew_point_difference", "ventilation_dries"}


def zone_has(data, zone_id, key):
    """Whether a zone gets the entity `key`. Zone 1 keeps all of its entities as before."""
    if zone_id == 1:
        return True
    if key in OUTDOOR_KEYS:
        return False
    if key in INDOOR_KEYS:
        return data.zone.data[zone_id]["inside_temperature"] is not None or any(
            device["type"] == INDOOR_SENSOR and device["zone"] == zone_id
            for device in data.info.data["devices"])
    return True


class E16Entity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, device=None, zone_id=1):
        super().__init__(coordinator)
        self.key = key
        self.zone_id = zone_id
        self._attr_translation_key = key
        main = entry.data[CONF_DEVICE_ID]
        if device is not None and device["type"] != 1:
            data = entry.runtime_data
            self.address = device["address"]
            self._attr_unique_id = f"{main}_{device['address']}_{key}"
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{main}_{device['address']}")},
                "name": f"inVENTer {device['name'] or device['address']}",
                "manufacturer": "inVENTer",
                "model": MODELS.get(device["type"], f"Type {device['type']}"),
                "sw_version": version_text(device["firmware"]),
                "via_device_id": data.zone_device_ids.get(device["zone"], data.main_device_id),
            }
        elif zone_id == 1:
            # Unique ids of zone 1 stay as they were before multi-zone support
            self._attr_unique_id = f"{main}_{key}"
            self._attr_device_info = {"identifiers": {(DOMAIN, main)}}
        else:
            self._attr_unique_id = f"{main}_zone{zone_id}_{key}"
            self._attr_device_info = {"identifiers": {(DOMAIN, f"{main}_zone{zone_id}")}}

    @property
    def zone(self):
        """Status of the entity's zone (entities of the zone coordinator)."""
        return self.coordinator.data[self.zone_id]

    def device_row(self):
        return next((d for d in self.coordinator.data["devices"] if d["address"] == self.address), None)
