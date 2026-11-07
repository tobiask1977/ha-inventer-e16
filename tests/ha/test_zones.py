# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""The whole integration against the simulated controller (tests/simulator.py): which zones become
devices, and which command each entity sends with one zone and with several (issue #22)."""
import importlib.util
from pathlib import Path
import struct
import time
from types import SimpleNamespace

import pytest

from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.inventer_e16 import client
from custom_components.inventer_e16.const import DOMAIN

spec = importlib.util.spec_from_file_location("simulator", Path(__file__).parents[1] / "simulator.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

DEVICE_ID = "ABCDE-FGHIJ"
DATA = {"host": "192.0.2.1", "device_id": DEVICE_ID, "psk": "0102030405060708"}
FOREVER = client.FOREVER


async def _setup(hass, monkeypatch, controller):
    monkeypatch.setattr(client.E16Client, "_connect", lambda self: controller.connect())
    # Only the client's clock: its sleeps move the simulated time
    monkeypatch.setattr(client, "time", SimpleNamespace(time=time.time, sleep=controller.advance))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=DATA, title="inVENTer Zone 1",
                            minor_version=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass, domain, unique_id):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{DEVICE_ID}_{unique_id}")
    assert entity_id, unique_id
    return entity_id


def _last_command(controller):
    payload = next(p for t, op, p in reversed(controller.requests)
                   if t == sim.USER_OVERRIDE and op == sim.UPDATE)
    return struct.unpack("<BBBBI", payload[4:12])


async def _call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)


async def test_single_zone_keeps_its_entities_and_global_commands(hass, monkeypatch):
    controller = sim.FakeController()
    entry = await _setup(hass, monkeypatch, controller)
    assert entry.runtime_data.zone.zone_ids == (1,)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert not any("_zone" in identifier for device in devices for _, identifier in device.identifiers)
    fan = _entity(hass, "fan", "fan")
    _entity(hass, "sensor", "outside_temperature")
    # The app's commands for all zones, as before multi-zone support
    await _call(hass, "fan", "turn_off", fan)
    assert _last_command(controller) == (client.CMD_GLOBAL_PAUSE, 0, client.FAN_OFF, 255, FOREVER)
    assert hass.states.get(fan).state == "off"
    await _call(hass, "fan", "turn_on", fan)
    assert _last_command(controller) == (client.CMD_CANCEL, 0, client.FAN_OFF, 255, 0)
    await _call(hass, "button", "press", _entity(hass, "button", "boost"))
    assert _last_command(controller) == (client.CMD_GLOBAL_BOOST, 4, client.FAN_VENTILATION, 255, 900)
    await _call(hass, "button", "press", _entity(hass, "button", "pause_1h"))
    assert _last_command(controller) == (client.CMD_GLOBAL_PAUSE, 0, client.FAN_OFF, 255, 3600)
    await _call(hass, "fan", "set_percentage", fan, percentage=75)
    assert _last_command(controller) == (client.CMD_ZONE_SPEED_MODE, 3, client.FAN_HEAT_RECOVERY, 1, 3600)


async def test_several_zones_become_devices_with_their_own_commands(hass, monkeypatch):
    controller = sim.FakeController(zones=3)
    entry = await _setup(hass, monkeypatch, controller)
    data = entry.runtime_data
    assert data.zone.zone_ids == (1, 2, 3)
    registry = dr.async_get(hass)
    zone2 = registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_zone2"), entry.entry_id)
    assert zone2.name == "inVENTer Zone 2" and zone2.via_device_id == data.main_device_id
    assert registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_zone4"), entry.entry_id) is None
    # Each fan hangs below its zone
    fan3 = registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_3"), entry.entry_id)
    assert fan3.via_device_id == zone2.id
    # Zone 1 keeps its unique ids; outdoor and indoor values are not repeated without a sensor
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DEVICE_ID}_zone2_outside_temperature") is None
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DEVICE_ID}_zone2_inside_temperature") is None
    _entity(hass, "sensor", "zone2_speed")

    fan2 = _entity(hass, "fan", "zone2_fan")
    await _call(hass, "fan", "turn_off", fan2)
    assert _last_command(controller) == (client.CMD_ZONE_SPEED_MODE, 0, client.FAN_OFF, 2, FOREVER)
    assert hass.states.get(fan2).state == "off"
    assert hass.states.get(_entity(hass, "fan", "fan")).state == "on"
    await _call(hass, "button", "press", _entity(hass, "button", "zone3_boost"))
    assert _last_command(controller) == (client.CMD_ZONE_SPEED_MODE, 4, client.FAN_HEAT_RECOVERY, 3, 900)
    await _call(hass, "button", "press", _entity(hass, "button", "pause_1h"))
    assert _last_command(controller) == (client.CMD_ZONE_SPEED_MODE, 0, client.FAN_OFF, 1, 3600)
    await _call(hass, "button", "press", _entity(hass, "button", "zone3_resume"))
    assert _last_command(controller) == (client.CMD_CANCEL, 0, client.FAN_OFF, 3, 0)
    await _call(hass, "fan", "turn_on", fan2)
    assert _last_command(controller) == (client.CMD_CANCEL, 0, client.FAN_OFF, 2, 0)
    assert hass.states.get(fan2).state == "on"

    # Duration and profile per zone
    await _call(hass, "number", "set_value", _entity(hass, "number", "zone2_override_minutes"), value=30)
    await _call(hass, "fan", "set_preset_mode", fan2, preset_mode="ventilation")
    assert _last_command(controller) == (client.CMD_ZONE_SPEED_MODE, 1, client.FAN_VENTILATION, 2, 1800)
    await _call(hass, "select", "select_option", _entity(hass, "select", "zone3_profile"), option="bedroom")
    assert controller.zones[3].profile == 1 and controller.zones[1].profile == 0


def _last_override(hass, unique_id):
    return hass.states.get(_entity(hass, "sensor", unique_id)).attributes["active"]


async def test_zone_cancel_ends_the_pause_without_end(hass, monkeypatch):
    # A cancel for one zone keeps that zone's record (#22): the pause must not stay "active"
    controller = sim.FakeController(zones=2)
    await _setup(hass, monkeypatch, controller)
    fan2 = _entity(hass, "fan", "zone2_fan")
    await _call(hass, "fan", "turn_off", fan2)
    assert _last_override(hass, "zone2_last_override") is True
    await _call(hass, "fan", "turn_on", fan2)
    assert hass.states.get(_entity(hass, "sensor", "zone2_last_override")).state == "zone_speed_mode"
    assert _last_override(hass, "zone2_last_override") is False


async def test_resume_during_a_pause_for_all_zones_ends_it_everywhere(hass, monkeypatch):
    controller = sim.FakeController(zones=3)
    entry = await _setup(hass, monkeypatch, controller)
    controller.command(bytes.fromhex("020003ffffffffff"))  # global pause from the app
    await entry.runtime_data.zone.async_refresh()
    await _call(hass, "button", "press", _entity(hass, "button", "zone2_resume"))
    assert _last_command(controller) == (client.CMD_CANCEL, 0, client.FAN_OFF, 255, 0)
    assert all(controller.zones[n].speed == 1 for n in (1, 2, 3))
    # Without a global command the cancel stays in the zone
    await _call(hass, "fan", "turn_off", _entity(hass, "fan", "zone3_fan"))
    await _call(hass, "button", "press", _entity(hass, "button", "zone3_resume"))
    assert _last_command(controller) == (client.CMD_CANCEL, 0, client.FAN_OFF, 3, 0)


async def test_moved_device_reloads_and_stale_zone_can_be_deleted(hass, monkeypatch):
    from custom_components.inventer_e16 import async_remove_config_entry_device
    controller = sim.FakeController(zones=3)
    entry = await _setup(hass, monkeypatch, controller)
    registry = dr.async_get(hass)
    zone2 = registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_zone2"), entry.entry_id)
    zone3 = registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_zone3"), entry.entry_id)
    # The only fan of zone 3 (address 4) moves to zone 2
    controller.devices[4] = sim.device_row(4, 2, 2, "Fan 4", 5030009, zone=2)
    await entry.runtime_data.info.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.zone.zone_ids == (1, 2)
    fan4 = registry.async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}_4"), entry.entry_id)
    assert fan4.via_device_id == zone2.id
    assert await async_remove_config_entry_device(hass, entry, zone3) is True
    assert await async_remove_config_entry_device(hass, entry, zone2) is False
    assert await async_remove_config_entry_device(hass, entry, fan4) is False


async def test_new_zone_reloads_the_entry(hass, monkeypatch):
    controller = sim.FakeController(zones=2)
    entry = await _setup(hass, monkeypatch, controller)
    assert entry.runtime_data.zone.zone_ids == (1, 2)
    controller.zones[3].used = True
    controller.devices.append(sim.device_row(9, 2, 2, "Fan 9", 5030009, zone=3))
    await entry.runtime_data.info.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.zone.zone_ids == (1, 2, 3)
    _entity(hass, "fan", "zone3_fan")


@pytest.mark.parametrize("zones", [1, 3])
async def test_diagnostics_contain_every_zone(hass, monkeypatch, zones):
    from custom_components.inventer_e16.diagnostics import async_get_config_entry_diagnostics
    entry = await _setup(hass, monkeypatch, sim.FakeController(zones=zones))
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert list(result["zones"]) == list(range(1, zones + 1))
    assert result["entry"]["psk"] == "**REDACTED**"
