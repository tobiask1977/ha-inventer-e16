# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Ventilation profile of the zone, filter and service interval."""
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from . import client
from .entity import E16Entity

# VentilationProfile values; custom profiles and winter only appear when active
PROFILES = {0: "default", 1: "bedroom", 2: "childrens_room", 3: "bathroom", 4: "living_room",
            5: "kitchen", 6: "holiday", 252: "summer", 253: "cellar_heat_recovery",
            254: "cellar_ventilation"}
HIDDEN_PROFILES = {**{7 + n: f"custom_{n + 1}" for n in range(9)}, 251: "winter"}
INTERVALS = (
    ("filter_interval", client.F_FILTER_INTERVAL, (1, 2, 3, 4, 5, 6)),
    ("service_interval", client.F_SERVICE_INTERVAL, (3, 6, 9, 12)),
)


def interval_option(months):
    return "off" if months == 255 else str(months)


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    async_add_entities([E16Profile(data.zone, entry, "profile"),
                        *(E16Interval(data.info, entry, *item) for item in INTERVALS)])


class E16Profile(E16Entity, SelectEntity):
    """Permanent profile of the zone (ZoneRowField 1), like the profile choice in the app."""

    def _current(self):
        value = self.coordinator.data["profile"]
        return PROFILES.get(value) or HIDDEN_PROFILES.get(value)

    @property
    def options(self):
        current = self._current()
        options = list(PROFILES.values())
        return options + [current] if current and current not in options else options

    @property
    def current_option(self):
        return self._current()

    async def async_select_option(self, option):
        value = next(k for k, v in {**PROFILES, **HIDDEN_PROFILES}.items() if v == option)
        await self.coordinator.async_set_zone_field(client.ZF_PROFILE, bytes([value]))


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
