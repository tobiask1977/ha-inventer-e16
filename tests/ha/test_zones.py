# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""The whole integration against the simulated controller (tests/simulator.py): which zones become
devices, and which command each entity sends with one zone and with several (issue #22)."""
import importlib.util
from pathlib import Path
from datetime import timedelta
import struct
import time
from types import SimpleNamespace

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (MockConfigEntry, async_fire_time_changed,
                                                          mock_restore_cache)

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


def _device(hass, entry, identifier):
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, f"{DEVICE_ID}{identifier}"),
                                                            entry.entry_id)


def _device_of(hass, domain, unique_id):
    return er.async_get(hass).async_get(_entity(hass, domain, unique_id)).device_id


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
    main = _device(hass, entry, "")
    assert main.name == "inVENTer Zone 1"
    assert _device(hass, entry, "_1").via_device_id == main.id
    fan = _entity(hass, "fan", "fan")
    assert _device_of(hass, "fan", "fan") == main.id
    assert _device_of(hass, "sensor", "outside_temperature") == main.id
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
    # The controller goes by its model name, every zone is a device below it (zone 1 too)
    assert _device(hass, entry, "").name == "inVENTer Easy Connect e16"
    zone1, zone2 = _device(hass, entry, "_zone1"), _device(hass, entry, "_zone2")
    assert zone1.name == "inVENTer Zone 1" and zone1.via_device_id == data.main_device_id
    assert zone2.name == "inVENTer Zone 2" and zone2.via_device_id == data.main_device_id
    assert _device(hass, entry, "_zone4") is None
    # Each fan hangs below its zone
    assert _device(hass, entry, "_1").via_device_id == zone1.id
    assert _device(hass, entry, "_3").via_device_id == zone2.id
    # Zone entities sit on their zone, controller-wide ones and the outdoor values on the controller
    assert _device_of(hass, "fan", "fan") == zone1.id
    assert _device_of(hass, "button", "boost") == zone1.id
    assert _device_of(hass, "fan", "zone2_fan") == zone2.id
    for domain, unique_id in (("sensor", "outside_temperature"), ("sensor", "dew_point_outside"),
                              ("sensor", "filter_due"), ("binary_sensor", "alarm"),
                              ("select", "filter_interval")):
        assert _device_of(hass, domain, unique_id) == data.main_device_id, unique_id
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


@pytest.mark.parametrize("zones", [1, 3])
async def test_diagnostics_contain_every_zone(hass, monkeypatch, zones):
    from custom_components.inventer_e16.diagnostics import async_get_config_entry_diagnostics
    entry = await _setup(hass, monkeypatch, sim.FakeController(zones=zones))
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert list(result["zones"]) == list(range(1, zones + 1))
    assert result["entry"]["psk"] == "**REDACTED**"


def _options(hass, unique_id):
    return hass.states.get(_entity(hass, "select", unique_id)).attributes["options"]


async def test_custom_profiles_with_a_time_program_can_be_selected(hass, monkeypatch, freezer):
    controller = sim.FakeController(zones=2)
    # Custom profile 3 (profile 9, table 8) has a time program, the others are empty
    controller.programs[(8, 5)] = client.program_record(8 * 3600, 127, client.FAN_VENTILATION, 2)
    entry = await _setup(hass, monkeypatch, controller)
    await hass.async_block_till_done(wait_background_tasks=True)
    for unique_id in ("profile", "zone2_profile"):
        assert "custom_3" in _options(hass, unique_id) and "custom_1" not in _options(hass, unique_id)
    # One connection per profile: polls and commands only wait for one profile, not for all nine
    connections = controller.connections
    await entry.runtime_data.zone.async_check_custom_profiles(client.CUSTOM_PROFILES)
    assert controller.connections - connections == 9
    await _call(hass, "select", "select_option", _entity(hass, "select", "zone2_profile"), option="custom_3")
    assert controller.zones[2].profile == 9
    # A program written or deleted through the services shows or hides the profile
    fan = _entity(hass, "fan", "fan")
    await _call(hass, DOMAIN, "set_time_program_entry", fan, profile="custom_1", entry=0, time="07:30",
                days=["monday"], mode="ventilation", speed=2)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_1" in _options(hass, "profile")
    await _call(hass, DOMAIN, "delete_time_program_entry", fan, profile="custom_1", entry=0)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_1" not in _options(hass, "profile")
    # A program from the app shows up with the daily check, not with the checks in between
    controller.programs[(14, 31)] = client.program_record(0, 1, client.FAN_HEAT_RECOVERY, 1)
    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_9" not in _options(hass, "profile")
    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_9" in _options(hass, "profile")


async def test_profile_options_follow_the_profile_numbers(hass, monkeypatch):
    controller = sim.FakeController()
    controller.zones[1].profile = 7  # custom 1 is active but has no program
    controller.programs[(7, 0)] = client.program_record(0, 127, client.FAN_HEAT_RECOVERY, 1)
    await _setup(hass, monkeypatch, controller)
    await hass.async_block_till_done(wait_background_tasks=True)
    options = _options(hass, "profile")
    assert options[options.index("holiday"):options.index("summer") + 1] == [
        "holiday", "custom_1", "custom_2", "summer"]
    assert hass.states.get(_entity(hass, "select", "profile")).state == "custom_1"


async def test_custom_profiles_survive_a_restart_and_a_failed_read(hass, monkeypatch, freezer, caplog):
    # Offered before the restart: custom 4. On the controller only custom 3 has a program.
    mock_restore_cache(hass, [State("select.inventer_zone_1_ventilation_profile", "default",
                                    {"options": ["default", "custom_4", "summer"]})])
    controller = sim.FakeController()
    controller.programs[(8, 0)] = client.program_record(0, 127, client.FAN_HEAT_RECOVERY, 1)
    read = client.E16Client.profiles_with_program
    calls = []

    def first_read_fails(self, profiles):
        calls.append(profiles)
        if len(calls) == 1:
            raise TimeoutError("no reply")
        return read(self, profiles)

    monkeypatch.setattr(client.E16Client, "profiles_with_program", first_read_fails)
    await _setup(hass, monkeypatch, controller)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_4" in _options(hass, "profile") and "custom_3" not in _options(hass, "profile")
    assert "retrying in 10 minutes" in caplog.text
    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "custom_3" in _options(hass, "profile") and "custom_4" not in _options(hass, "profile")


async def test_polarity_of_a_pair_can_be_changed(hass, monkeypatch):
    controller = sim.FakeController(zones=3)  # zone 1: fans 1 and 2
    controller.devices[2] = sim.device_row(2, 2, 2, "Fan 2", 5030009, polarity=0, signal=-54)
    # 0.4.0 showed the polarity as a sensor
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", DOMAIN, f"{DEVICE_ID}_1_polarity")
    entry = await _setup(hass, monkeypatch, controller)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{DEVICE_ID}_1_polarity") is None
    fan1, fan2 = _entity(hass, "select", "1_polarity"), _entity(hass, "select", "2_polarity")
    assert registry.async_get(fan1).entity_category == "config"
    assert (hass.states.get(fan1).state, hass.states.get(fan2).state) == ("extract", "supply")
    assert hass.states.get(fan1).attributes["options"] == ["supply", "extract"]
    # The controller switches the other fan of the pair along; both show it at once
    await _call(hass, "select", "select_option", fan2, option="extract")
    assert (hass.states.get(fan1).state, hass.states.get(fan2).state) == ("supply", "extract")
    writes = [p for t, op, p in controller.requests if t == sim.DEVICE_FIELD]
    assert writes == [sim.raw_with_id(2 * 65536 + 32, b"\x01")]
    # Neither the controller nor the sensors have a polarity; no reload for it
    assert registry.async_get_entity_id("select", DOMAIN, f"{DEVICE_ID}_0_polarity") is None
    assert entry.state is ConfigEntryState.LOADED


async def test_polarity_write_that_is_not_stored(hass, monkeypatch):
    controller = sim.FakeController()
    await _setup(hass, monkeypatch, controller)
    monkeypatch.setattr(controller, "_write_device_field", lambda *args: False)
    with pytest.raises(HomeAssistantError, match="not stored"):
        await _call(hass, "select", "select_option", _entity(hass, "select", "2_polarity"),
                    option="supply")
    assert hass.states.get(_entity(hass, "select", "2_polarity")).state == "extract"


async def test_wired_devices_have_no_radio_signal(hass, monkeypatch):
    controller = sim.FakeController()  # fan 1 is wired, the others use radio
    registry = er.async_get(hass)
    # 0.4.0 created a signal sensor that always showed unknown
    registry.async_get_or_create("sensor", DOMAIN, f"{DEVICE_ID}_1_signal")
    await _setup(hass, monkeypatch, controller)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{DEVICE_ID}_1_signal") is None
    assert hass.states.get(_entity(hass, "sensor", "2_signal")).state == "-54"
    # The wired fan keeps its other entities
    _entity(hass, "select", "1_polarity")


async def test_fan_units_have_zone_select_entity(hass, monkeypatch):
    controller = sim.FakeController(zones=2)
    controller.zones[1].name = "Wohnzimmer"
    controller.zones[2].name = "Schlafzimmer"
    controller.devices[2] = sim.device_row(2, 2, 2, "Fan 2", 5030009, zone=1)
    entry = await _setup(hass, monkeypatch, controller)
    fan2_zone_select = _entity(hass, "select", "2_zone")
    state = hass.states.get(fan2_zone_select)
    assert state is not None
    assert state.state == "Zone 1 - Wohnzimmer"
    assert "Zone 1 - Wohnzimmer" in state.attributes["options"]
    assert "Zone 2 - Schlafzimmer" in state.attributes["options"]

    # Select another zone using select_option
    await _call(hass, "select", "select_option", fan2_zone_select, option="Zone 2 - Schlafzimmer")
    assert hass.states.get(fan2_zone_select).state == "Zone 2 - Schlafzimmer"
    assert controller.devices[2][3] == 2

    # Controller (address 0) does not get a zone select entity
    assert er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{DEVICE_ID}_0_zone") is None

    # Switch back using the set_device_zone service
    fan_entity = _entity(hass, "fan", "fan")
    await _call(hass, DOMAIN, "set_device_zone", fan_entity, address=2, zone=1)
    assert hass.states.get(fan2_zone_select).state == "Zone 1 - Wohnzimmer"
    assert controller.devices[2][3] == 1
