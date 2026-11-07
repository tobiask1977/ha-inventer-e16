# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Zones in use every 30 s (option), maintenance/firmware/radio devices every 10 min, vendor catalog
once a day."""
from dataclasses import dataclass, field
from datetime import timedelta
import logging

import aiohttp

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (CMD_CANCEL, CMD_GLOBAL_BOOST, CMD_GLOBAL_PAUSE, CMD_ZONE_SPEED_MODE,
                     FAN_HEAT_RECOVERY, FAN_OFF, FAN_VENTILATION, READ_MODE_TO_FAN,
                     ZONE_FLAG_GLOBAL_COMMAND, ZONE_GLOBAL, E16AuthError, E16Client)
from .const import (CATALOG_BRAND, CATALOG_URL, CONF_FIRMWARE_CATALOG, CONF_PSK, CONF_SCAN_INTERVAL,
                    DEFAULT_FIRMWARE_CATALOG, DEFAULT_SCAN_INTERVAL)

LOGGER = logging.getLogger(__package__)
CATALOG_INTERVAL = timedelta(hours=24)
# Duration of speed/mode commands until the user sets one; the app offers 15 min to 8 h
DEFAULT_OVERRIDE_MINUTES = 60


@dataclass
class E16Data:
    zone: "E16ZoneCoordinator"
    info: "E16InfoCoordinator"
    main_device_id: str | None = None
    # Device registry id per zone; zone 1 is the main device
    zone_device_ids: dict = field(default_factory=dict)


class E16ZoneCoordinator(DataUpdateCoordinator):
    """Status of the zones in use, as {zone_id: zone}."""

    def __init__(self, hass, entry, client):
        super().__init__(
            hass, LOGGER, name=f"{entry.title} zone", config_entry=entry,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            always_update=False,
        )
        self.client = client
        # Set before the first refresh from the radio devices (client.zones_in_use)
        self.zone_ids = (1,)
        # Duration of speed/mode commands per zone, in minutes
        self.override_minutes = {}

    @property
    def multi_zone(self):
        return len(self.zone_ids) > 1

    def minutes(self, zone_id):
        return self.override_minutes.get(zone_id, DEFAULT_OVERRIDE_MINUTES)

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self.client.get_zones, self.zone_ids)
        except E16AuthError as error:
            raise ConfigEntryAuthFailed("The controller rejected the PSK") from error
        except (OSError, ValueError) as error:
            raise UpdateFailed(f"Reading the e16 zones failed: {error}") from error

    async def _async_command(self, method, *args):
        LOGGER.debug("e16 command %s%s", method.__name__, args)
        try:
            zones = await self.hass.async_add_executor_job(method, *args)
        except (E16AuthError, OSError, ValueError) as error:
            raise HomeAssistantError(f"e16 command failed: {error}") from error
        self.async_set_updated_data(zones)

    async def async_override(self, command, speed=0, mode=FAN_OFF, zone=ZONE_GLOBAL, duration=0):
        await self._async_command(
            self.client.user_override, command, speed, mode, zone, duration, self.zone_ids)

    # Power button and quick commands. With one zone they are the app's commands for all zones.
    # With several zones they go to one zone only: a command for all zones ends or overrides the
    # other zones as well (verified on a controller with four zones, issue #22).
    async def async_pause(self, zone_id, duration):
        if self.multi_zone:
            await self.async_override(CMD_ZONE_SPEED_MODE, 0, FAN_OFF, zone_id, duration)
        else:
            await self.async_override(CMD_GLOBAL_PAUSE, 0, FAN_OFF, ZONE_GLOBAL, duration)

    async def async_resume(self, zone_id):
        # A pause or boost for all zones (e.g. from the app) ends for all zones, like in the app
        zone = ZONE_GLOBAL
        if self.multi_zone and not self.data[zone_id]["flags"] & ZONE_FLAG_GLOBAL_COMMAND:
            zone = zone_id
        await self.async_override(CMD_CANCEL, 0, FAN_OFF, zone)

    async def async_boost(self, zone_id, duration):
        if self.multi_zone:
            # Speed 4 in the zone's current mode: the global boost doesn't change the mode either
            mode = READ_MODE_TO_FAN.get(self.data[zone_id]["mode"], FAN_HEAT_RECOVERY)
            await self.async_override(CMD_ZONE_SPEED_MODE, 4, mode, zone_id, duration)
        else:
            await self.async_override(CMD_GLOBAL_BOOST, 4, FAN_VENTILATION, ZONE_GLOBAL, duration)

    async def async_set_zone_field(self, zone_id, field_id, raw):
        await self._async_command(self.client.set_zone_field, zone_id, field_id, raw, self.zone_ids)


class E16InfoCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass, LOGGER, name=f"{entry.title} maintenance", config_entry=entry,
            update_interval=timedelta(minutes=10),
        )
        self.client = client
        self.catalog = None
        self._catalog_at = None

    async def _async_update_data(self):
        try:
            info = await self.hass.async_add_executor_job(self.client.get_info)
        except E16AuthError as error:
            raise ConfigEntryAuthFailed("The controller rejected the PSK") from error
        except (OSError, ValueError) as error:
            raise UpdateFailed(f"Reading e16 maintenance data failed: {error}") from error
        if not self.config_entry.options.get(CONF_FIRMWARE_CATALOG, DEFAULT_FIRMWARE_CATALOG):
            self.catalog = None
        elif self._catalog_at is None or dt_util.utcnow() - self._catalog_at > CATALOG_INTERVAL:
            await self._async_fetch_catalog()
            self._catalog_at = dt_util.utcnow()
        info["catalog"] = self.catalog
        return info

    async def _async_fetch_catalog(self):
        # An outage of the vendor cloud must never hide the local values
        try:
            async with async_get_clientsession(self.hass).post(
                CATALOG_URL, json={"data": {"brand": CATALOG_BRAND}},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                result = (await response.json())["result"]["hardwareTypes"]
            # Accept only plausible integers; anything else must not reach the update entities
            self.catalog = {
                item["hardwareType"]: item["version"] for item in result
                if all(type(item.get(key)) is int for key in ("hardwareType", "version"))
                and 0 <= item["version"] < 100_000_000
            }
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError) as error:
            LOGGER.warning("Vendor firmware catalog not reachable: %s", error)

    async def async_set_global_field(self, field_id, raw):
        try:
            # The zone status read afterwards is not needed here
            await self.hass.async_add_executor_job(self.client.set_global_field, field_id, raw)
        except (E16AuthError, OSError, ValueError) as error:
            raise HomeAssistantError(f"e16 setting failed: {error}") from error
        await self.async_request_refresh()


def create(hass, entry):
    client = E16Client(entry.data[CONF_HOST], entry.data[CONF_PSK])
    return E16Data(E16ZoneCoordinator(hass, entry, client), E16InfoCoordinator(hass, entry, client))
