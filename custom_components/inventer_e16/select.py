# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
# Copyright (c) 2026 Markus Hennig
"""Ventilation profile of the zone, filter and service interval, polarity and zone of the
fan units."""
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from . import client
from .entity import E16Entity

# VentilationProfile values. Custom profiles appear when they have a time program or are active,
# winter only when active.
PROFILES = {0: "default", 1: "bedroom", 2: "childrens_room", 3: "bathroom", 4: "living_room",
            5: "kitchen", 6: "holiday", 252: "summer", 253: "cellar_heat_recovery",
            254: "cellar_ventilation"}
HIDDEN_PROFILES = {**{7 + n: f"custom_{n + 1}" for n in range(9)}, 251: "winter"}
ALL_PROFILES = {**PROFILES, **HIDDEN_PROFILES}
INTERVALS = (
    ("filter_interval", client.F_FILTER_INTERVAL, (1, 2, 3, 4, 5, 6)),
    ("service_interval", client.F_SERVICE_INTERVAL, (3, 6, 9, 12)),
)
POLARITIES = {client.POLARITY_SUPPLY: "supply", client.POLARITY_EXTRACT: "extract"}


def interval_option(months):
    return "off" if months == 255 else str(months)


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    entities = [
        *(E16Profile(data.zone, entry, "profile", zone_id=zone_id)
          for zone_id in data.zone.zone_ids),
        *(E16Interval(data.info, entry, *item) for item in INTERVALS),
        *(E16Polarity(data.info, entry, "polarity", device)
          for device in data.info.data["devices"]
          if device["type"] in client.FAN_DEVICE_TYPES),
    ]
    # Moving fans between zones only makes sense with several zones in use (a device or a name)
    if data.zone.multi_zone:
        entities += [E16DeviceZone(data.info, entry, "zone", device, data.zone)
                     for device in data.info.data["devices"]
                     if device["type"] in client.FAN_DEVICE_TYPES | {27}]
    async_add_entities(entities)


class E16Profile(E16Entity, RestoreEntity, SelectEntity):
    """Permanent profile of the zone (ZoneRowField 1), like the profile choice in the app."""

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Until the time programs are read, offer the custom profiles offered before the restart
        if (last := await self.async_get_last_state()) is not None:
            offered = set(last.attributes.get("options") or ())
            self.coordinator.custom_profiles |= {
                value for value in client.CUSTOM_PROFILES if HIDDEN_PROFILES[value] in offered}

    @property
    def options(self):
        values = set(PROFILES) | self.coordinator.custom_profiles
        if self.zone["profile"] in HIDDEN_PROFILES:
            values.add(self.zone["profile"])
        return [ALL_PROFILES[value] for value in sorted(values)]

    @property
    def current_option(self):
        return ALL_PROFILES.get(self.zone["profile"])

    async def async_select_option(self, option):
        value = next(k for k, v in ALL_PROFILES.items() if v == option)
        await self.coordinator.async_set_zone_field(self.zone_id, client.ZF_PROFILE, bytes([value]))


class E16Interval(E16Entity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key, field_id, months):
        super().__init__(coordinator, entry, key)
        self.field_id = field_id
        self.values = {interval_option(m): m for m in (255, *months)}

    @property
    def options(self):
        current = interval_option(self.coordinator.data[self.key])
        # Show a value set elsewhere even if the app would not offer it
        return list(self.values) + ([current] if current not in self.values else [])

    @property
    def current_option(self):
        return interval_option(self.coordinator.data[self.key])

    async def async_select_option(self, option):
        months = self.values.get(option, 255 if option == "off" else int(option))
        await self.coordinator.async_set_global_field(self.field_id, bytes([months]))


class E16Polarity(E16Entity, SelectEntity):
    """Direction a fan unit starts in (#33). Only this fan is written; some controllers switch the
    other fan of the pair along (#38), and the select shows what the controller reports."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(POLARITIES.values())

    @property
    def current_option(self):
        row = self.device_row()
        return POLARITIES.get(row["polarity"]) if row else None

    async def async_select_option(self, option):
        polarity = next(k for k, v in POLARITIES.items() if v == option)
        await self.coordinator.async_set_polarity(self.address, polarity)


class E16DeviceZone(E16Entity, SelectEntity):
    """Zone of a fan unit (#37): choosing another zone moves the fan there. Offers the zones in use,
    which includes named zones without devices."""
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key, device, zones):
        super().__init__(coordinator, entry, key, device)
        self.zones = zones

    def _label(self, zone_id):
        zone = (self.zones.data or {}).get(zone_id)
        name = zone["name"].strip() if zone else ""
        return f"Zone {zone_id} - {name}" if name and name.lower() != f"zone {zone_id}" else f"Zone {zone_id}"

    def _zone_ids(self):
        row = self.device_row()
        current = {row["zone"]} if row and 1 <= row["zone"] <= client.MAX_ZONES else set()
        return sorted(set(self.zones.zone_ids) | current)

    @property
    def options(self):
        return [self._label(zone_id) for zone_id in self._zone_ids()]

    @property
    def current_option(self):
        row = self.device_row()
        return self._label(row["zone"]) if row and 1 <= row["zone"] <= client.MAX_ZONES else None

    @property
    def extra_state_attributes(self):
        row = self.device_row()
        return {"address": self.address, "zone_id": row["zone"] if row else None}

    async def async_select_option(self, option):
        zone_id = next(zone_id for zone_id in self._zone_ids() if self._label(zone_id) == option)
        await self.coordinator.async_set_device_zone(self.address, zone_id)
