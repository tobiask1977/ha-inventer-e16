# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Zone values, maintenance dates, Wi-Fi and radio values, runtimes."""
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory,
                                 UnitOfRatio, UnitOfTemperature, UnitOfTime)
from homeassistant.util import dt as dt_util

from .client import FOREVER
from .entity import E16Entity

PLAYBACK = {0: "play", 1: "pause", 2: "boost", 3: "off", 4: "shutdown", 5: "override"}
# Zone status mode table (not the one of the UserOverride command)
MODES = {0: "off", 1: "ventilation", 2: "heat_recovery"}
COMMANDS = {0: "none", 1: "global_boost", 2: "global_pause", 3: "zone_boost", 4: "zone_pause",
            5: "zone_speed_mode", 6: "zone_profile", 7: "cancel", 8: "fan_off", 9: "fan_off_cancel"}
ZONE_SENSORS = (
    ("speed", None, None),
    ("playback", SensorDeviceClass.ENUM, None),
    ("mode", SensorDeviceClass.ENUM, None),
    ("timer", SensorDeviceClass.DURATION, UnitOfTime.SECONDS),
    ("inside_temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    ("inside_humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    ("outside_temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    ("outside_humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    ("status", None, None),
    ("last_override", SensorDeviceClass.ENUM, None),
)
# Only created when the controller reports a value (needs a CO2/VOC sensor in the zone)
OPTIONAL_ZONE_SENSORS = (
    ("co2", SensorDeviceClass.CO2, UnitOfRatio.PARTS_PER_MILLION),
    ("voc", None, None),
)
# Indoor/outdoor sensors on the radio bus (device types 4 and 5)
SENSOR_DEVICE_TYPES = {4, 5}
OPTIONS = {"playback": PLAYBACK, "mode": MODES, "last_override": COMMANDS}
# The controller reports remaining time in months (float); use the mean month length for days
DAYS_PER_MONTH = 30.4375


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    entities = [E16ZoneSensor(data.zone, entry, *description) for description in ZONE_SENSORS]
    entities += [E16ZoneSensor(data.zone, entry, *description) for description in OPTIONAL_ZONE_SENSORS
                 if data.zone.data[description[0]] is not None]
    for prefix in ("filter", "service"):
        entities += [E16DueSensor(data.info, entry, prefix, as_date=True),
                     E16DueSensor(data.info, entry, prefix, as_date=False)]
    entities.append(E16WifiSensor(data.info, entry, "wifi_rssi"))
    for device in data.info.data["devices"]:
        if device["type"] == 1:
            continue
        entities.append(E16RadioSensor(data.info, entry, "signal", device))
        if device["runtime"]:
            entities.append(E16RuntimeSensor(data.info, entry, "runtime", device))
        if device["battery"] is not None:
            entities.append(E16Battery(data.info, entry, "battery", device))
        if device["type"] in SENSOR_DEVICE_TYPES:
            entities += [E16DeviceMeasurement(data.info, entry, "temperature", device),
                         E16DeviceMeasurement(data.info, entry, "humidity", device)]
    async_add_entities(entities)


class E16ZoneSensor(E16Entity, SensorEntity):
    def __init__(self, coordinator, entry, key, device_class, unit):
        super().__init__(coordinator, entry, key)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if device_class in (SensorDeviceClass.TEMPERATURE, SensorDeviceClass.HUMIDITY,
                            SensorDeviceClass.CO2) or key == "voc":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key in OPTIONS:
            self._attr_options = list(OPTIONS[key].values())
        if key in ("status", "last_override"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        value = self.coordinator.data[self.key]
        if self.key == "last_override":
            return COMMANDS.get(value["command"]) if value else None
        if self.key in OPTIONS:
            return OPTIONS[self.key].get(value)
        return value

    @property
    def extra_state_attributes(self):
        value = self.coordinator.data.get("last_override")
        if self.key != "last_override" or not value:
            return None
        return {"speed": value["speed"], "fan_mode": value["mode"], "zone": value["zone"],
                "duration_s": None if value["duration"] == FOREVER else value["duration"]}


class E16DueSensor(E16Entity, SensorEntity):
    """Filter change / service: due date or remaining days. Interval 255 = disabled."""

    def __init__(self, coordinator, entry, prefix, as_date):
        super().__init__(coordinator, entry, f"{prefix}_{'due' if as_date else 'days_left'}")
        self.prefix, self.as_date = prefix, as_date
        if as_date:
            self._attr_device_class = SensorDeviceClass.DATE
        else:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.DAYS
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self):
        data = self.coordinator.data
        if data[f"{self.prefix}_interval"] == 255:
            return None
        days = data[f"{self.prefix}_months_left"] * DAYS_PER_MONTH
        if self.as_date:
            return (dt_util.now() + timedelta(days=days)).date()
        return round(days, 1)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        interval = data[f"{self.prefix}_interval"]
        return {"interval_months": None if interval == 255 else interval,
                "months_left": round(data[f"{self.prefix}_months_left"], 3)}


class E16WifiSensor(E16Entity, SensorEntity):
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self.coordinator.data["wifi_rssi"]


class E16RadioSensor(E16Entity, SensorEntity):
    """Direct radio level to the controller; non-negative values (seen: 126) mean no reading."""
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        row = self.device_row()
        return row["signal"] if row and row["signal"] < 0 else None


class E16RuntimeSensor(E16Entity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        row = self.device_row()
        # Reported in seconds (a controller replaced half a day earlier reported 43200)
        return round(row["runtime"] / 3600, 1) if row else None


class E16DeviceMeasurement(E16Entity, SensorEntity):
    """Temperature/humidity of one radio sensor (device list, refreshed every 10 min)."""
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, key, device):
        super().__init__(coordinator, entry, key, device)
        if key == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self):
        row = self.device_row()
        return row[self.key] if row else None


class E16Battery(E16Entity, SensorEntity):
    """Battery level of a radio sensor. Unit inferred as percent (rows reported 62 and 64)."""
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        row = self.device_row()
        return row["battery"] if row else None
