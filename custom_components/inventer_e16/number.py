# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Duration for speed and mode commands, and the zone's comfort settings."""
import struct

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfRatio, UnitOfTemperature, UnitOfTime

from . import client
from .entity import E16Entity

# Comfort settings of the zone (ZoneRowField 2-6). The app has no end-user form for these on the e16
# (they come from the installer configuration), so the ranges are our own conservative choice.
# (key, field, min, max, step, unit, device class, only with sensor)
ZONE_SETTINGS = (
    ("comfort_room_temperature", client.ZF_COMFORT_ROOM, 15, 28, 0.5,
     UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE, None),
    ("comfort_outdoor_temperature", client.ZF_COMFORT_OUTSIDE, 5, 25, 0.5,
     UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE, None),
    ("humidity_threshold", client.ZF_RH_THRESHOLD, 40, 90, 1, PERCENTAGE, NumberDeviceClass.HUMIDITY, None),
    ("co2_threshold", client.ZF_CO2_THRESHOLD, 400, 2000, 50,
     UnitOfRatio.PARTS_PER_MILLION, NumberDeviceClass.CO2, "co2"),
    ("voc_threshold", client.ZF_VOC_THRESHOLD, 0, 10, 0.5, None, None, "voc"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    zone = entry.runtime_data.zone
    async_add_entities([
        E16Duration(zone, entry, "override_minutes"),
        *(E16ZoneSetting(zone, entry, *setting) for setting in ZONE_SETTINGS
          if setting[7] is None or zone.data.get(setting[7]) is not None),
    ])


class E16Duration(E16Entity, RestoreNumber):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 15
    _attr_native_max_value = 480
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value:
            self.coordinator.override_minutes = int(last.native_value)

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return self.coordinator.override_minutes

    async def async_set_native_value(self, value):
        self.coordinator.override_minutes = int(value)
        self.async_write_ha_state()


class E16ZoneSetting(E16Entity, NumberEntity):
    """A comfort setting of the zone; used by the controller's automatic profiles."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, key, field, minimum, maximum, step, unit, device_class, _):
        super().__init__(coordinator, entry, key)
        self.field = field
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_zone_field(self.field, struct.pack("<f", float(value)))

