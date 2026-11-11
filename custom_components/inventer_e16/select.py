# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
# Copyright (c) 2026 Markus Hennig
"""Ventilation profile of the zone, filter and service interval, and fan zone assignment."""
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

try:
    from homeassistant.helpers import device_registry as dr, entity_registry as er
except ImportError:
    dr = None
    er = None

from . import client
from .const import CONF_DEVICE_ID, DOMAIN
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


def interval_option(months):
    return "off" if months == 255 else str(months)


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    entities = [
        *(E16Profile(data.zone, entry, "profile", zone_id=zone_id)
          for zone_id in data.zone.zone_ids),
        *(E16Interval(data.info, entry, *item) for item in INTERVALS),
    ]
    if data.info.data and "devices" in data.info.data:
        for device in data.info.data["devices"]:
            if device["type"] in client.FAN_DEVICE_TYPES or device["type"] == 27:
                entities.append(E16DeviceZone(data.info, entry, device))
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


class E16DeviceZone(E16Entity, SelectEntity):
    """Zone assignment for a fan on the radio bus."""
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, device):
        super().__init__(coordinator, entry, "zone", device=device)
        self._entry = entry

    def _find_fan_entity_id(self) -> str | None:
        """Find a fan entity ID belonging to this integration entry."""
        if not self.hass or not er:
            return None
        registry = er.async_get(self.hass)
        entries = er.async_entries_for_config_entry(registry, self._entry.entry_id)
        for e in entries:
            if e.domain == "fan":
                return e.entity_id
        return None

    def _get_available_zones(self) -> list[int]:
        """Max 4 zones: show only zones with name or registered in Home Assistant."""
        data = getattr(self._entry, "runtime_data", None)
        if not data or not getattr(data, "zone", None):
            return [1]
        available = set()
        zone_data = data.zone.data or {}
        main = self._entry.data.get(CONF_DEVICE_ID) if self._entry else None
        registry = dr.async_get(self.hass) if (self.hass and dr) else None

        for zid in data.zone.zone_ids:
            if not (1 <= zid <= client.MAX_ZONES):
                continue
            has_name = bool(zone_data.get(zid, {}).get("name") and str(zone_data[zid]["name"]).strip())
            is_registered = False
            if registry and main:
                is_registered = bool(
                    registry.async_get_device(identifiers={(DOMAIN, f"{main}_zone{zid}")})
                    or registry.async_get_device(identifiers={(DOMAIN, f"{main}_z{zid}")})
                    or (zid == 1 and registry.async_get_device(identifiers={(DOMAIN, main)}))
                )
            if has_name or is_registered or zid == 1:
                available.add(zid)

        current = self.device_row()
        if current and current.get("zone") and 1 <= current["zone"] <= client.MAX_ZONES:
            available.add(current["zone"])

        return sorted(available)

    def _zone_options_map(self) -> dict[int, str]:
        """Map available zone IDs (1-4) to user-facing option labels including zone names."""
        data = getattr(self._entry, "runtime_data", None)
        zone_data = (data.zone.data or {}) if (data and getattr(data, "zone", None)) else {}
        available = self._get_available_zones()
        mapping = {}
        for zid in available:
            name = zone_data.get(zid, {}).get("name")
            if name and str(name).strip() and str(name).strip().lower() != f"zone {zid}".lower():
                mapping[zid] = f"Zone {zid} - {str(name).strip()}"
            else:
                mapping[zid] = f"Zone {zid}"
        return mapping

    @property
    def options(self) -> list[str]:
        return list(self._zone_options_map().values())

    @property
    def current_option(self) -> str | None:
        device = self.device_row()
        if device and device.get("zone") is not None:
            zid = device["zone"]
            mapping = self._zone_options_map()
            if zid in mapping:
                return mapping[zid]
            data = getattr(self._entry, "runtime_data", None)
            zone_data = (data.zone.data or {}) if (data and getattr(data, "zone", None)) else {}
            name = zone_data.get(zid, {}).get("name")
            if name and str(name).strip() and str(name).strip().lower() != f"zone {zid}".lower():
                return f"Zone {zid} - {str(name).strip()}"
            return f"Zone {zid}"
        return None

    @property
    def extra_state_attributes(self) -> dict:
        device = self.device_row()
        zone_id = device.get("zone") if device else None
        data = getattr(self._entry, "runtime_data", None)
        zone_name = None
        if data and getattr(data, "zone", None) and data.zone.data and zone_id in data.zone.data:
            zone_name = data.zone.data[zone_id].get("name")
        return {
            "address": self.address,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "available_zones": self._zone_options_map(),
        }

    async def async_get_devices(self, refresh: bool = False) -> dict | None:
        """Call get_devices service to fetch devices and zones."""
        fan_entity_id = self._find_fan_entity_id()
        if fan_entity_id and self.hass and self.hass.services.has_service(DOMAIN, "get_devices"):
            return await self.hass.services.async_call(
                DOMAIN,
                "get_devices",
                {"refresh": refresh},
                target={"entity_id": fan_entity_id},
                blocking=True,
                return_response=True,
            )
        return None

    async def async_select_option(self, option: str) -> None:
        mapping = self._zone_options_map()
        target_zone = next((zid for zid, label in mapping.items() if label == option), None)
        if target_zone is None:
            for zid in mapping:
                if str(zid) == option.strip() or option.strip().startswith(f"Zone {zid}"):
                    target_zone = zid
                    break
        if target_zone is None:
            try:
                target_zone = int(option.split()[1].rstrip("-:"))
            except (IndexError, ValueError) as err:
                raise ValueError(f"Unknown zone option: {option}") from err

        fan_entity_id = self._find_fan_entity_id()
        if fan_entity_id and self.hass and self.hass.services.has_service(DOMAIN, "set_device_zone"):
            await self.hass.services.async_call(
                DOMAIN,
                "set_device_zone",
                {"address": self.address, "zone": target_zone},
                target={"entity_id": fan_entity_id},
                blocking=True,
            )
        else:
            await self.coordinator.async_set_device_zone(self.address, target_zone)

