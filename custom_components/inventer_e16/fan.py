# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Speed 1-4 and mode as time-limited command, off as unlimited pause - like the app."""
import math

import voluptuous as vol

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_platform

from . import client
from .entity import E16Entity
from .select import HIDDEN_PROFILES, PROFILES

HEAT_RECOVERY, VENTILATION = "heat_recovery", "ventilation"
PRESET_TO_FAN = {HEAT_RECOVERY: client.FAN_HEAT_RECOVERY, VENTILATION: client.FAN_VENTILATION}
# Zone status reports 1 = ventilation, 2 = heat recovery (other table than the command)
READ_MODE_TO_PRESET = {1: VENTILATION, 2: HEAT_RECOVERY}
SPEEDS = 4
# Service set_mode: time-limited command with explicit mode, speed and duration - for automations.
# The pause modes are what the app's mode dialog sends (always with speed 0); unlike turn_off they end.
SET_MODE_MODES = {HEAT_RECOVERY: client.FAN_HEAT_RECOVERY, VENTILATION: client.FAN_VENTILATION,
                  "pause": client.FAN_OFF, "pause_open": client.FAN_STOP}
# Service get_time_program: profiles 1-15 have a time program; entries use the set_mode keys
PROGRAM_PROFILES = {key: value for value, key in {**PROFILES, **HIDDEN_PROFILES}.items()
                    if value in client.PROGRAM_PROFILES}
PROGRAM_MODES = {value: key for key, value in SET_MODE_MODES.items()}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def program_response(profile, entries):
    """Service response: the used entries of a time program, in the controller's order."""
    return {
        "profile": {**PROFILES, **HIDDEN_PROFILES}[profile],
        "entries": [
            {"entry": index, "time": f"{item['seconds'] // 3600:02}:{item['seconds'] % 3600 // 60:02}",
             "days": [day for bit, day in enumerate(DAYS) if item["days"] >> bit & 1],
             "mode": PROGRAM_MODES.get(item["mode"], item["mode"]), "speed": item["speed"]}
            for index, item in enumerate(entries) if item
        ],
    }


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([E16Fan(entry.runtime_data.zone, entry, "fan")])
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


class E16Fan(E16Entity, FanEntity):
    _attr_name = None
    _attr_preset_modes = [HEAT_RECOVERY, VENTILATION]
    _attr_speed_count = SPEEDS
    _attr_supported_features = (FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
                                | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF)

    @property
    def is_on(self):
        # Not from playback: after a command it often lags behind for a poll or longer, while
        # fan speed already fits (pause and global pause report speed 0) - issue #1
        data = self.coordinator.data
        return data["mode"] != 0 and data["speed"] > 0

    @property
    def percentage(self):
        return self.coordinator.data["speed"] * 100 // SPEEDS if self.is_on else 0

    @property
    def preset_mode(self):
        return READ_MODE_TO_PRESET.get(self.coordinator.data["mode"])

    async def _speed_mode(self, speed=None, preset=None):
        data = self.coordinator.data
        speed = speed or max(data["speed"], 1)
        mode = PRESET_TO_FAN.get(preset) or client.READ_MODE_TO_FAN.get(
            data["mode"], client.FAN_HEAT_RECOVERY)
        await self.coordinator.async_override(
            client.CMD_ZONE_SPEED_MODE, speed, mode, data["zone_id"],
            self.coordinator.override_minutes * 60)

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
            await self.coordinator.async_override(client.CMD_CANCEL)

    async def async_turn_off(self, **kwargs):
        # App power button "off": global pause without end
        await self.coordinator.async_override(client.CMD_GLOBAL_PAUSE, duration=client.FOREVER)

    async def async_get_time_program(self, profile=None):
        """Read only. Default: the zone's current profile."""
        value = PROGRAM_PROFILES[profile] if profile else self.coordinator.data["profile"]
        if value not in client.PROGRAM_PROFILES:
            raise ServiceValidationError(
                f"Profile {value} has no time program (only profiles 1-15 have one)")
        try:
            entries = await self.hass.async_add_executor_job(
                self.coordinator.client.get_time_program, value)
        except (client.E16AuthError, OSError, ValueError) as error:
            raise HomeAssistantError(f"Reading the time program failed: {error}") from error
        return program_response(value, entries)

    async def async_set_mode(self, mode, speed=1, minutes=None):
        fan_mode = SET_MODE_MODES[mode]
        if fan_mode in (client.FAN_OFF, client.FAN_STOP):
            speed = 0
        await self.coordinator.async_override(
            client.CMD_ZONE_SPEED_MODE, speed, fan_mode, self.coordinator.data["zone_id"],
            (minutes or self.coordinator.override_minutes) * 60)

