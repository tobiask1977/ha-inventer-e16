"""Speed 1-4 and mode as time-limited command, off as unlimited pause - like the app."""
import math

from homeassistant.components.fan import FanEntity, FanEntityFeature

from . import client
from .entity import E16Entity

HEAT_RECOVERY, VENTILATION = "heat_recovery", "ventilation"
PRESET_TO_FAN = {HEAT_RECOVERY: client.FAN_HEAT_RECOVERY, VENTILATION: client.FAN_VENTILATION}
# Zone status reports 1 = ventilation, 2 = heat recovery (other table than the command)
READ_MODE_TO_PRESET = {1: VENTILATION, 2: HEAT_RECOVERY}
# Playback in the zone status: 1 pause, 3 shut off, 4 shut down
STOPPED = {1, 3, 4}
SPEEDS = 4


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([E16Fan(entry.runtime_data.zone, entry, "fan")])


class E16Fan(E16Entity, FanEntity):
    _attr_name = None
    _attr_preset_modes = [HEAT_RECOVERY, VENTILATION]
    _attr_speed_count = SPEEDS
    _attr_supported_features = (FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
                                | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF)

    @property
    def is_on(self):
        data = self.coordinator.data
        return data["playback"] not in STOPPED and data["mode"] != 0 and data["speed"] > 0

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
