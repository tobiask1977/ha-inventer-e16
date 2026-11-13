# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""inVENTer Easy Connect e16 - local control over Wi-Fi (TLS-PSK)."""
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from . import client, coordinator
from .client import zones_in_use
from .const import CONF_DEVICE_ID, CONF_FIRMWARE_CATALOG, DOMAIN
from .entity import INDOOR_SENSOR, zone_device_key

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


def layout(devices, zone_ids):
    """What needs other devices or entities, and so a reload: a new or removed radio device, a zone
    coming into use or going out of use, an indoor sensor moved to another zone (the zone's indoor
    values). Fans and other devices moving between zones in use are moved in the registry."""
    return zone_ids, frozenset(
        (device["address"], device["zone"] if device["type"] == INDOOR_SENSOR else None)
        for device in devices if device["type"] != 1)


async def async_setup_entry(hass, entry):
    data = coordinator.create(hass, entry)
    # Zones with a radio device or a name are in use: read the devices, then all zones once
    await data.info.async_config_entry_first_refresh()
    data.zone.zone_ids = tuple(range(1, client.MAX_ZONES + 1))
    await data.zone.async_config_entry_first_refresh()
    data.zone.zone_ids = zones_in_use(data.info.data["devices"], data.zone.data)
    data.zone.async_set_updated_data({zone_id: data.zone.data[zone_id]
                                      for zone_id in data.zone.zone_ids})
    main = entry.data[CONF_DEVICE_ID]
    registry = dr.async_get(hass)
    # Create the devices first: entities, fans and sensors reference them via via_device_id
    multi_zone = data.zone.multi_zone
    # The entry is named after zone 1. With several zones, zone 1 is a device of its own, so the
    # controller goes by its model name.
    data.main_device_id = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, main)},
        name="inVENTer Easy Connect e16" if multi_zone else entry.title,
        manufacturer="inVENTer", model="Easy Connect e16",
    ).id
    # One zone: the controller carries it, so single-zone installations keep their devices
    data.zone_device_ids = {1: data.main_device_id}
    if multi_zone:
        known = {key for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
                 for _, key in device.identifiers}
        for zone_id in data.zone.zone_ids:
            key, name = zone_device_key(main, zone_id, True), data.zone.data[zone_id]["name"]
            device = registry.async_get_or_create(
                config_entry_id=entry.entry_id, identifiers={(DOMAIN, key)},
                name=f"inVENTer {name or f'Zone {zone_id}'}", manufacturer="inVENTer",
                model="Ventilation zone", via_device_id=data.main_device_id,
            )
            if zone_id == 1 and key not in known:
                # Zone 1 sat on the controller until now: keep its entities in the same area
                registry.async_update_device(
                    device.id, area_id=registry.async_get(data.main_device_id).area_id)
            data.zone_device_ids[zone_id] = device.id
    entry.runtime_data = data
    at_setup = layout(data.info.data["devices"], data.zone.zone_ids)

    @callback
    def follow_layout():
        if not data.info.data or not data.zone.data:
            return
        devices = data.info.data["devices"]
        if layout(devices, zones_in_use(devices, data.zone.data)) != at_setup:
            coordinator.LOGGER.info("Radio devices or zones changed, reloading %s", entry.title)
            hass.config_entries.async_schedule_reload(entry.entry_id)
            return
        # A device moved between zones in use (action, zone select or app): below its new zone
        by_key = {key: device
                  for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
                  for _, key in device.identifiers}
        for device in devices:
            registered = by_key.get(f"{main}_{device['address']}")
            via = data.zone_device_ids.get(device["zone"], data.main_device_id)
            if device["type"] != 1 and registered and registered.via_device_id != via:
                registry.async_update_device(registered.id, via_device_id=via)

    entry.async_on_unload(data.info.async_add_listener(follow_layout))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def check_custom_profiles(_now=None):
        entry.async_create_background_task(
            hass, data.zone.async_check_custom_profiles(), "inventer_e16 custom profiles")

    check_custom_profiles()
    entry.async_on_unload(async_track_time_interval(
        hass, check_custom_profiles, coordinator.CUSTOM_PROFILE_RETRY))
    # No update listener: it would reload on every entry change, even when Home Assistant only
    # records a DHCP discovery key. Options reload via OptionsFlowWithReload, flows via their abort.
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device):
    """Zones and radio devices the controller no longer reports can be deleted in the UI."""
    main, data = entry.data[CONF_DEVICE_ID], entry.runtime_data
    zones = (zone_device_key(main, zone_id, data.zone.multi_zone) for zone_id in data.zone.zone_ids)
    current = {main, *zones,
               *(f"{main}_{d['address']}" for d in data.info.data["devices"] if d["type"] != 1)}
    return not any(domain == DOMAIN and key in current for domain, key in device.identifiers)
