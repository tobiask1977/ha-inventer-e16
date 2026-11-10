# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
# Copyright (c) 2026 Markus Hennig
"""Speed 1-4 and mode as time-limited command, off as unlimited pause - like the app."""
import math

import voluptuous as vol

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform

from . import client
from .entity import E16Entity, MODELS
from .select import HIDDEN_PROFILES, PROFILES

HEAT_RECOVERY, VENTILATION = "heat_recovery", "ventilation"
PRESET_TO_FAN = {HEAT_RECOVERY: client.FAN_HEAT_RECOVERY, VENTILATION: client.FAN_VENTILATION}
# Zone status reports 1 = ventilation, 2 = heat recovery (other table than the command)
READ_MODE_TO_PRESET = {1: VENTILATION, 2: HEAT_RECOVERY}
SPEEDS = 4
HARDWARE_TYPES = {1: "controller", 2: "fan", 3: "sensor", 6: "wifi"}
# Service set_mode: time-limited command with explicit mode, speed and duration - for automations.
# The pause modes are what the app's mode dialog sends (always with speed 0); unlike turn_off they end.
SET_MODE_MODES = {HEAT_RECOVERY: client.FAN_HEAT_RECOVERY, VENTILATION: client.FAN_VENTILATION,
                  "pause": client.FAN_OFF, "pause_open": client.FAN_STOP}
# Service get_time_program: profiles 1-15 have a time program; entries use the set_mode keys
PROGRAM_PROFILES = {key: value for value, key in {**PROFILES, **HIDDEN_PROFILES}.items()
                    if value in client.PROGRAM_PROFILES}
PROGRAM_MODES = {value: key for key, value in SET_MODE_MODES.items()}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def program_record(start, days, mode, speed):
    """Service fields -> 8-byte record; pause modes always run with speed 0, like set_mode."""
    fan_mode = SET_MODE_MODES[mode]
    if fan_mode in (client.FAN_OFF, client.FAN_STOP):
        speed = 0
    bits = sum(1 << DAYS.index(day) for day in set(days))
    return client.program_record(start.hour * 3600 + start.minute * 60, bits, fan_mode, speed)


def program_entry(index, item):
    return {"entry": index, "time": f"{item['seconds'] // 3600:02}:{item['seconds'] % 3600 // 60:02}",
            "days": [day for bit, day in enumerate(DAYS) if item["days"] >> bit & 1],
            "mode": PROGRAM_MODES.get(item["mode"], item["mode"]), "speed": item["speed"]}


def program_response(profile, entries):
    """Service response: the used entries of a time program, in the controller's order."""
    return {
        "profile": {**PROFILES, **HIDDEN_PROFILES}[profile],
        "entries": [program_entry(index, item) for index, item in enumerate(entries) if item],
    }


async def async_setup_entry(hass, entry, async_add_entities):
    zones = entry.runtime_data.zone
    async_add_entities([E16Fan(zones, entry, "fan", zone_id=zone_id) for zone_id in zones.zone_ids])
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_mode",
        {
            vol.Required("mode"): vol.In(list(SET_MODE_MODES)),
            vol.Optional("speed", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=SPEEDS)),
            # Same range as the app: 15 min to 8 h
            vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(min=15, max=480)),
        },
        "async_set_mode",
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        "get_time_program",
        {vol.Optional("profile"): vol.In(list(PROGRAM_PROFILES))},
        "async_get_time_program",
        supports_response=SupportsResponse.ONLY,
    )
    entry_fields = {
        vol.Required("profile"): vol.In(list(PROGRAM_PROFILES)),
        vol.Required("entry"): vol.All(vol.Coerce(int), vol.Range(min=0, max=client.PROGRAM_ENTRIES - 1)),
    }
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_time_program_entry",
        {
            **entry_fields,
            vol.Required("time"): cv.time,
            vol.Required("days"): vol.All(cv.ensure_list, [vol.In(DAYS)], vol.Length(min=1)),
            vol.Required("mode"): vol.In(list(SET_MODE_MODES)),
            vol.Optional("speed", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=SPEEDS)),
        },
        "async_set_time_program_entry",
        supports_response=SupportsResponse.OPTIONAL,
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        "delete_time_program_entry", entry_fields, "async_delete_time_program_entry")
    entity_platform.async_get_current_platform().async_register_entity_service(
        "get_devices",
        {vol.Optional("refresh", default=False): cv.boolean},
        "async_get_devices",
        supports_response=SupportsResponse.ONLY,
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_device_zone",
        {
            vol.Required("address"): vol.All(vol.Coerce(int), vol.Range(min=0, max=client.MAX_DEVICES - 1)),
            vol.Required("zone"): vol.All(vol.Coerce(int), vol.Range(min=1, max=client.MAX_ZONES)),
        },
        "async_set_device_zone",
        supports_response=SupportsResponse.OPTIONAL,
    )


class E16Fan(E16Entity, FanEntity):
    _attr_name = None
    _attr_preset_modes = [HEAT_RECOVERY, VENTILATION]
    _attr_speed_count = SPEEDS
    _attr_supported_features = (FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
                                | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF)

    def __init__(self, coordinator, entry, key, zone_id=None):
        super().__init__(coordinator, entry, key, zone_id=zone_id)
        self._entry = entry
    @property
    def is_on(self):
        # Not from playback: after a command it often lags behind for a poll or longer, while
        # fan speed already fits (pause and global pause report speed 0) - issue #1
        data = self.zone
        return data["mode"] != 0 and data["speed"] > 0

    @property
    def percentage(self):
        return self.zone["speed"] * 100 // SPEEDS if self.is_on else 0

    @property
    def preset_mode(self):
        return READ_MODE_TO_PRESET.get(self.zone["mode"])

    async def _speed_mode(self, speed=None, preset=None):
        data = self.zone
        speed = speed or max(data["speed"], 1)
        mode = PRESET_TO_FAN.get(preset) or client.READ_MODE_TO_FAN.get(
            data["mode"], client.FAN_HEAT_RECOVERY)
        await self.coordinator.async_override(
            client.CMD_ZONE_SPEED_MODE, speed, mode, self.zone_id,
            self.coordinator.minutes(self.zone_id) * 60)

    async def async_set_percentage(self, percentage):
        if percentage == 0:
            await self.async_turn_off()
        else:
            await self._speed_mode(speed=math.ceil(percentage * SPEEDS / 100))

    async def async_set_preset_mode(self, preset_mode):
        await self._speed_mode(preset=preset_mode)

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if percentage or preset_mode:
            speed = math.ceil(percentage * SPEEDS / 100) if percentage else None
            await self._speed_mode(speed=speed, preset=preset_mode)
        else:
            # App power button "on": cancel, the controller returns to its profile
            await self.coordinator.async_resume(self.zone_id)

    async def async_turn_off(self, **kwargs):
        # App power button "off": pause without end
        await self.coordinator.async_pause(self.zone_id, client.FOREVER)

    async def async_get_time_program(self, profile=None):
        """Read only. Default: the zone's current profile."""
        value = PROGRAM_PROFILES[profile] if profile else self.zone["profile"]
        if value not in client.PROGRAM_PROFILES:
            raise ServiceValidationError(
                f"Profile {value} has no time program (only profiles 1-15 have one)")
        try:
            entries = await self.hass.async_add_executor_job(
                self.coordinator.client.get_time_program, value)
        except (client.E16AuthError, OSError, ValueError) as error:
            raise HomeAssistantError(f"Reading the time program failed: {error}") from error
        return program_response(value, entries)

    async def _write_program_entry(self, profile, entry, record):
        """Write one entry; the client reads it back and raises if it was not stored."""
        try:
            stored = await self.hass.async_add_executor_job(
                self.coordinator.client.set_time_program_entry, PROGRAM_PROFILES[profile], entry, record)
        except (client.E16AuthError, OSError, ValueError) as error:
            raise HomeAssistantError(f"Writing the time program failed: {error}") from error
        # The entry may change what the current profile does right now
        await self.coordinator.async_request_refresh()
        if (value := PROGRAM_PROFILES[profile]) in client.CUSTOM_PROFILES:
            # Whether the profile select offers it
            self.coordinator.config_entry.async_create_background_task(
                self.hass, self.coordinator.async_check_custom_profiles((value,)),
                "inventer_e16 custom profile")
        return stored

    async def async_set_time_program_entry(self, profile, entry, time, days, mode, speed=1):
        stored = await self._write_program_entry(profile, entry, program_record(time, days, mode, speed))
        return program_entry(entry, stored)

    async def async_delete_time_program_entry(self, profile, entry):
        await self._write_program_entry(profile, entry, None)

    async def async_set_mode(self, mode, speed=1, minutes=None):
        fan_mode = SET_MODE_MODES[mode]
        if fan_mode in (client.FAN_OFF, client.FAN_STOP):
            speed = 0
        await self.coordinator.async_override(
            client.CMD_ZONE_SPEED_MODE, speed, fan_mode, self.zone_id,
            (minutes or self.coordinator.minutes(self.zone_id)) * 60)

    async def async_get_devices(self, refresh=False):
        data = self._entry.runtime_data
        if refresh or data.info.data is None:
            await data.info.async_request_refresh()
        info_data = data.info.data or {}
        zone_data = data.zone.data or {}
        zone_names = {zone_id: zone_data.get(zone_id, {}).get("name")
                      for zone_id in data.zone.zone_ids}
        devices = []
        for d in info_data.get("devices", []):
            devices.append({
                "address": d["address"],
                "name": d.get("name") or None,
                "type": d["type"],
                "type_name": MODELS.get(d["type"]),
                "hardware": d["hardware"],
                "hardware_type": HARDWARE_TYPES.get(d["hardware"]),
                "hardware_name": HARDWARE_TYPES.get(d["hardware"]),
                "zone": d["zone"],
                "zone_name": zone_names.get(d["zone"]),
                "status": d["status"],
                "online": bool(d["status"] & client.DEV_ONLINE),
                "signal": d["signal"] if d.get("signal") is not None and d["signal"] < 0 else None,
                "firmware": client.version_text(d["firmware"]) if d.get("firmware") else None,
                "temperature": d.get("temperature"),
                "humidity": d.get("humidity"),
                "runtime": d.get("runtime"),
                "battery": d.get("battery"),
            })
        zones = [
            {
                "zone_id": zone_id,
                "name": zone_data.get(zone_id, {}).get("name") or None,
                "speed": zone_data.get(zone_id, {}).get("speed", 0),
                "mode": zone_data.get(zone_id, {}).get("mode", 0),
            }
            for zone_id in data.zone.zone_ids
        ]
        return {"devices": devices, "zones": zones}

    async def async_set_device_zone(self, address: int, zone: int):
        data = self._entry.runtime_data
        await data.info.async_set_device_zone(address, zone)
        return {"success": True, "address": address, "zone": zone}


