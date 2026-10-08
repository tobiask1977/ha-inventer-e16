"""Zone status every 30 s, maintenance/firmware every 10 min, vendor catalog once a day."""
from dataclasses import dataclass
from datetime import timedelta
import logging

import aiohttp

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import E16Client
from .const import CATALOG_BRAND, CATALOG_URL, CONF_FIRMWARE_CATALOG, CONF_PSK

LOGGER = logging.getLogger(__package__)
CATALOG_INTERVAL = timedelta(hours=24)


@dataclass
class E16Data:
    zone: "E16ZoneCoordinator"
    info: "E16InfoCoordinator"
    main_device_id: str | None = None


class E16ZoneCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass, LOGGER, name=f"{entry.title} zone", config_entry=entry,
            update_interval=timedelta(seconds=30), always_update=False,
        )
        self.client = client
        # Duration for speed/mode commands; the app offers 15 min to 8 h
        self.override_minutes = 60

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self.client.get_zone)
        except (OSError, ValueError) as error:
            raise UpdateFailed(f"Reading the e16 zone failed: {error}") from error

    async def _async_command(self, method, *args):
        LOGGER.debug("e16 command %s%s", method.__name__, args)
        try:
            zone = await self.hass.async_add_executor_job(method, *args)
        except (OSError, ValueError) as error:
            raise HomeAssistantError(f"e16 command failed: {error}") from error
        self.async_set_updated_data(zone)

    async def async_override(self, command, speed=0, mode=3, zone=255, duration=0):
        await self._async_command(self.client.user_override, command, speed, mode, zone, duration)

    async def async_set_zone_field(self, field, raw):
        await self._async_command(self.client.set_zone_field, self.data["zone_id"], field, raw)


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
        except (OSError, ValueError) as error:
            raise UpdateFailed(f"Reading e16 maintenance data failed: {error}") from error
        if not self.config_entry.options.get(CONF_FIRMWARE_CATALOG, True):
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
            self.catalog = {item["hardwareType"]: item["version"] for item in result}
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError) as error:
            LOGGER.warning("Vendor firmware catalog not reachable: %s", error)

    async def async_set_global_field(self, field_id, raw):
        try:
            await self.hass.async_add_executor_job(self.client.set_global_field, field_id, raw)
        except (OSError, ValueError) as error:
            raise HomeAssistantError(f"e16 setting failed: {error}") from error
        await self.async_request_refresh()


def create(hass, entry):
    client = E16Client(entry.data[CONF_HOST], entry.data[CONF_PSK])
    return E16Data(E16ZoneCoordinator(hass, entry, client), E16InfoCoordinator(hass, entry, client))
