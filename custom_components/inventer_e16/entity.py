# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Device mapping: the controller is the main device. With one zone it also carries the zone, as
before multi-zone support. With several, every zone is a device below it, and each fan and sensor
hangs below its zone."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import version_text
from .const import CONF_DEVICE_ID, DOMAIN

MODELS = {1: "Easy Connect e16", 2: "Fan unit (FCU)", 3: "Fan unit (FCU)",
          4: "Indoor sensor", 5: "Outdoor sensor", 27: "Fan unit (iV-Twin+)"}
INDOOR_SENSOR = 4
# One outdoor sensor serves all zones: its values come from zone 1 and belong to the controller
OUTDOOR_KEYS = {"outside_temperature", "outside_humidity", "dew_point_outside",
                "absolute_humidity_outside"}
# Need an indoor sensor in the zone
INDOOR_KEYS = {"inside_temperature", "inside_humidity", "dew_point_inside",
               "absolute_humidity_inside", "dew_point_difference", "ventilation_dries"}


def zone_device_key(main, zone_id, multi_zone):
    """Device identifier of a zone: the controller itself with one zone, a device of its own with
    several. Unique ids don't change with it."""
    return f"{main}_zone{zone_id}" if multi_zone else main


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

    def __init__(self, coordinator, entry, key, device=None, zone_id=None):
        """An entity of a radio device (`device`), of a zone (`zone_id`) or of the controller."""
        super().__init__(coordinator)
        self.key = key
        self.zone_id = zone_id or 1
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
        else:
            # Unique ids of zone 1 stay as they were before multi-zone support
            self._attr_unique_id = f"{main}_{key}" if self.zone_id == 1 else f"{main}_zone{zone_id}_{key}"
            identifier = main
            if zone_id is not None and key not in OUTDOOR_KEYS:
                identifier = zone_device_key(main, zone_id, entry.runtime_data.zone.multi_zone)
            self._attr_device_info = {"identifiers": {(DOMAIN, identifier)}}

    @property
    def zone(self):
        """Status of the entity's zone (entities of the zone coordinator)."""
        return self.coordinator.data[self.zone_id]

    def device_row(self):
        return next((d for d in self.coordinator.data["devices"] if d["address"] == self.address), None)
