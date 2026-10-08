# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Status flag, filter/service due and missing radio devices from the status bits."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from . import client
from .entity import E16Entity
from .humidity import DRY_OFF_K, DRY_ON_K, MIN_INSIDE_C, dew_point, ventilation_dries

DUE_BITS = {
    "filter": (client.SYS_FILTER_TIMEOUT, client.DEV_FILTER_DUE | client.DEV_FILTER_OVER),
    "service": (client.SYS_SERVICE_TIMEOUT, client.DEV_SERVICE_DUE | client.DEV_SERVICE_OVER),
}


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    async_add_entities([
        E16Problem(data.zone, entry, "problem"),
        E16Due(data.info, entry, "filter", data.zone),
        E16Due(data.info, entry, "service", data.zone),
        E16RadioLost(data.info, entry, "radio_lost"),
        E16BatteryLow(data.info, entry, "battery_low", data.zone),
        E16Alarm(data.info, entry, "alarm", data.zone),
        E16VentilationDries(data.zone, entry, "ventilation_dries"),
    ])


class E16Problem(E16Entity, BinarySensorEntity):
    """System status not zero - no interpretation of single bits."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self):
        return self.coordinator.data["status"] != 0


class E16Due(E16Entity, BinarySensorEntity):
    """On as soon as the controller or a radio device reports 'due soon' or 'expired'."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, kind, zone):
        super().__init__(coordinator, entry, f"{kind}_due_flag")
        self.kind, self.zone = kind, zone

    def _devices(self):
        _, device_bits = DUE_BITS[self.kind]
        return [d["name"] or "controller" for d in self.coordinator.data["devices"]
                if d["status"] & device_bits]

    @property
    def is_on(self):
        system_bit, _ = DUE_BITS[self.kind]
        zone_status = self.zone.data["status"] if self.zone.data else 0
        return bool(zone_status & system_bit or self._devices())

    @property
    def extra_state_attributes(self):
        return {"devices": self._devices()}


class E16RadioLost(E16Entity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _missing(self):
        return [d["name"] or "controller" for d in self.coordinator.data["devices"]
                if d["status"] & (client.DEV_OFFLINE | client.DEV_LOST)
                or not d["status"] & client.DEV_ONLINE]

    @property
    def is_on(self):
        return bool(self._missing())

    @property
    def extra_state_attributes(self):
        return {"devices": self._missing()}


class E16BatteryLow(E16Entity, BinarySensorEntity):
    """Battery low/critical as flagged by the controller - the same signal the app uses."""
    _attr_device_class = BinarySensorDeviceClass.BATTERY

    def __init__(self, coordinator, entry, key, zone):
        super().__init__(coordinator, entry, key)
        self.zone = zone

    def _devices(self):
        bits = client.DEV_BATTERY_LOW | client.DEV_BATTERY_CRITICAL
        return [d["name"] or "controller" for d in self.coordinator.data["devices"] if d["status"] & bits]

    @property
    def is_on(self):
        zone_status = self.zone.data["status"] if self.zone.data else 0
        return bool(zone_status & client.SYS_BATTERY_CRITICAL or self._devices())

    @property
    def extra_state_attributes(self):
        return {"devices": self._devices()}


class E16Alarm(E16Entity, BinarySensorEntity):
    """Alarm input triggered (alarm interface module, e.g. a fire alarm contact)."""
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator, entry, key, zone):
        super().__init__(coordinator, entry, key)
        self.zone = zone

    @property
    def is_on(self):
        zone_status = self.zone.data["status"] if self.zone.data else 0
        return bool(zone_status & client.SYS_ALARM
                    or any(d["status"] & client.DEV_ALARM for d in self.coordinator.data["devices"]))


class E16VentilationDries(E16Entity, BinarySensorEntity):
    """On while bringing in outdoor air would dry the room noticeably (dew point rule, hysteresis)."""
    _attr_icon = "mdi:water-off"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._on = False

    @property
    def is_on(self):
        result = ventilation_dries(self.coordinator.data, self._on)
        if result is not None:
            self._on = result
        return result

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        inside = dew_point(data["inside_temperature"], data["inside_humidity"])
        outside = dew_point(data["outside_temperature"], data["outside_humidity"])
        return {
            "dew_point_difference_k": None if inside is None or outside is None else round(inside - outside, 1),
            "switch_on_from_k": DRY_ON_K, "switch_off_below_k": DRY_OFF_K,
            "min_inside_temperature_c": MIN_INSIDE_C,
        }
