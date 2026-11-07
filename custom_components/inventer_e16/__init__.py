# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""inVENTer Easy Connect e16 - local control over Wi-Fi (TLS-PSK)."""
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr

from . import coordinator
from .client import zones_in_use
from .const import CONF_DEVICE_ID, CONF_FIRMWARE_CATALOG, DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.FAN, Platform.BUTTON,
             Platform.NUMBER, Platform.SELECT, Platform.UPDATE]


async def async_migrate_entry(hass, entry):
    """1.1 -> 1.2: the firmware catalog became opt-in. Entries that never stored the option had it
    on, so store that explicitly - an update must not silently switch it off."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        options = {CONF_FIRMWARE_CATALOG: True, **entry.options}
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


def device_zones(devices):
    """Radio devices and their zones. A change needs other devices or entities: a new or removed
    device, a zone coming into use or going out of use, a device moved to another zone."""
    return {(device["address"], device["zone"]) for device in devices if device["type"] != 1}


async def async_setup_entry(hass, entry):
    data = coordinator.create(hass, entry)
    # The radio devices tell which zones are in use, so read them before the zones
    await data.info.async_config_entry_first_refresh()
    data.zone.zone_ids = zones_in_use(data.info.data["devices"])
    await data.zone.async_config_entry_first_refresh()
    # Create the devices first: entities, fans and sensors reference them via via_device_id
    main = entry.data[CONF_DEVICE_ID]
    registry = dr.async_get(hass)
    data.main_device_id = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, main)},
        name=entry.title, manufacturer="inVENTer", model="Easy Connect e16",
    ).id
    # Zone 1 stays on the main device, so single-zone installations keep their entities
    data.zone_device_ids = {1: data.main_device_id}
    for zone_id in data.zone.zone_ids[1:]:
        name = data.zone.data[zone_id]["name"] or f"Zone {zone_id}"
        data.zone_device_ids[zone_id] = registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{main}_zone{zone_id}")},
            name=f"inVENTer {name}", manufacturer="inVENTer", model="Ventilation zone",
            via_device_id=data.main_device_id,
        ).id
    entry.runtime_data = data
    layout = device_zones(data.info.data["devices"])

    @callback
    def reload_on_new_layout():
        if data.info.data and device_zones(data.info.data["devices"]) != layout:
            coordinator.LOGGER.info("Radio devices or zones changed, reloading %s", entry.title)
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(data.info.async_add_listener(reload_on_new_layout))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # No update listener: it would reload on every entry change, even when Home Assistant only
    # records a DHCP discovery key. Options reload via OptionsFlowWithReload, flows via their abort.
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device):
    """Zones and radio devices the controller no longer reports can be deleted in the UI."""
    main, data = entry.data[CONF_DEVICE_ID], entry.runtime_data
    current = {main, *(f"{main}_zone{zone_id}" for zone_id in data.zone.zone_ids),
               *(f"{main}_{d['address']}" for d in data.info.data["devices"] if d["type"] != 1)}
    return not any(domain == DOMAIN and key in current for domain, key in device.identifiers)
