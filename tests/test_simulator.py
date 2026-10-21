# SPDX-License-Identifier: MIT
"""Client tests against the simulated controller in tests/simulator.py - no Home Assistant needed.

The first tests check the simulator against recorded replies (tests/test_acknowledgements.py and
tests/test_client.py). The others run the real client against it: round trips that need state,
behaviour seen on real controllers (#1, #2), and replies that are missing, late, cut off or
malformed, which must end in ValueError or OSError (AGENTS.md, rule 6).
"""
import importlib.util
from pathlib import Path
import random
import struct

import pytest

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = _load("client", HERE.parent / "custom_components/inventer_e16/client.py")
sim = _load("simulator", HERE / "simulator.py")
recorded = _load("recorded_acknowledgements", HERE / "test_acknowledgements.py")
recorded_rows = _load("recorded_rows", HERE / "test_client.py")


def wired(monkeypatch, controller):
    """A real E16Client talking to `controller`; its sleeps move the simulated clock."""
    e16 = client.E16Client("192.0.2.1", "0102030405060708")
    monkeypatch.setattr(e16, "_connect", controller.connect)
    monkeypatch.setattr(client.time, "sleep", controller.advance)
    return e16


def _payload(packet):
    return packet[10:packet[1]]


# -- the simulator against recorded data -----------------------------------------------------------

def test_answers_the_recorded_commands_like_the_recorded_controller():
    """All 20 acknowledgements and both later polls, payload byte for byte. The recording has no
    timing, so the commands are 60 s apart and playback lags 10 s."""
    controller = sim.FakeController(playback_lag=10)
    controller.command(bytes.fromhex("05010101100e0000"))  # an override ran before the recording
    later = {index: reply for _, index, reply, _ in recorded.LATER}
    for index, (label, sent, reply, _) in enumerate(recorded.PAIRS):
        controller.advance(60)
        with controller.connect() as connection:
            connection.sendall(bytes.fromhex(sent))
            acknowledgement = client.read_packet(connection)
        assert _payload(acknowledgement) == _payload(bytes.fromhex(reply)), label
        if index in later:
            controller.advance(60)
            with controller.connect() as connection:
                connection.sendall(client.packet(client.T_ZONE_VIEW, b"\x00"))
                poll = client.read_packet(connection)
            assert _payload(poll) == _payload(bytes.fromhex(later[index])), f"after {label}"


def test_device_rows_are_laid_out_like_the_recorded_ones():
    assert sim.device_row(1, 2, 2, "Fan 1", 5030009, runtime=78003026) == recorded_rows.FAN_ROW
    temperature, humidity = struct.unpack_from("<ff", recorded_rows.SENSOR_ROW, 29)
    battery = struct.unpack_from("<f", recorded_rows.SENSOR_ROW, 41)[0]
    assert sim.device_row(3, 4, 3, "Indoor", 5030008, signal=-53, temperature=temperature,
                          humidity=humidity, battery=battery) == recorded_rows.SENSOR_ROW


def test_simulator_refuses_to_address_the_whole_time_program_store():
    body = struct.pack("<HH", 0xFFFF, 0xFFFF) + bytes(8)
    update = client.packet(client.T_TIME_PROGRAM, body + bytes([sim.crc8(body)]),
                           operation=client.UPDATE)
    with sim.FakeController().connect() as connection, pytest.raises(AssertionError):
        connection.sendall(update)


# -- round trips -----------------------------------------------------------------------------------

def test_command_and_cancel(monkeypatch):
    controller = sim.FakeController()
    e16 = wired(monkeypatch, controller)
    zone = e16.user_override(client.CMD_ZONE_SPEED_MODE, 3, client.FAN_VENTILATION, 1, 1800)
    assert (zone["speed"], zone["mode"], zone["playback"], zone["timer"]) == (3, 1, 5, 1800)
    assert zone["last_override"] == {"command": 5, "speed": 3, "mode": 2, "zone": 1, "duration": 1800}
    zone = e16.user_override(client.CMD_CANCEL)
    assert (zone["speed"], zone["mode"], zone["playback"], zone["timer"]) == (1, 2, 0, 0)
    assert zone["last_override"]["command"] == client.CMD_CANCEL


def test_time_limited_command_runs_out_and_keeps_its_record(monkeypatch):
    # Issue #2: when the timer reaches 0 the record at offset 74 is not rewritten
    controller = sim.FakeController()
    e16 = wired(monkeypatch, controller)
    e16.user_override(client.CMD_ZONE_SPEED_MODE, 4, client.FAN_HEAT_RECOVERY, 1, 900)
    controller.advance(899)
    assert e16.get_zone()["speed"] == 4
    controller.advance(1)
    zone = e16.get_zone()
    assert (zone["speed"], zone["timer"], zone["playback"]) == (1, 0, 0)
    assert zone["last_override"] == {"command": 5, "speed": 4, "mode": 1, "zone": 1, "duration": 900}


def test_playback_lags_while_speed_and_record_fit_at_once(monkeypatch):
    # Issue #1: once about four minutes
    controller = sim.FakeController(playback_lag=240)
    e16 = wired(monkeypatch, controller)
    e16.user_override(client.CMD_ZONE_SPEED_MODE, 2, client.FAN_HEAT_RECOVERY, 1, 3600)
    zone = e16.user_override(client.CMD_CANCEL)
    assert (zone["speed"], zone["playback"], zone["last_override"]["command"]) == (1, 5, 7)
    controller.advance(240)
    assert e16.get_zone()["playback"] == 0


def test_global_pause_and_cancel(monkeypatch):
    controller = sim.FakeController(playback_lag=10)
    e16 = wired(monkeypatch, controller)
    zone = e16.user_override(client.CMD_GLOBAL_PAUSE, duration=client.FOREVER)
    assert (zone["speed"], zone["mode"], zone["playback"], zone["flags"] & 16) == (0, 0, 1, 16)
    controller.advance(10)
    assert e16.get_zone()["playback"] == 4
    zone = e16.user_override(client.CMD_CANCEL)
    assert (zone["speed"], zone["playback"], zone["flags"] & 16) == (1, 4, 0)


def test_command_stored_but_not_applied_is_reported_as_it_is(monkeypatch):
    # The record says speed 4, the fans still run the schedule: speed tells what really runs
    controller = sim.FakeController(apply_commands=False)
    zone = wired(monkeypatch, controller).user_override(
        client.CMD_ZONE_SPEED_MODE, 4, client.FAN_VENTILATION, 1, 900)
    assert zone["last_override"]["speed"] == 4
    assert (zone["speed"], zone["mode"], zone["playback"]) == (1, 2, 0)


def test_zone_settings_show_in_the_next_zone_status(monkeypatch):
    controller = sim.FakeController()
    e16 = wired(monkeypatch, controller)
    zone = e16.set_zone_field(1, client.ZF_COMFORT_ROOM, struct.pack("<f", 20.5))
    assert zone["comfort_room_temperature"] == 20.5
    assert e16.set_zone_field(1, client.ZF_PROFILE, bytes([7]))["profile"] == 7
    e16.set_zone_field(2, client.ZF_PROFILE, bytes([3]))  # there is no zone 2
    assert e16.get_zone()["profile"] == 7
    assert controller.ignored_writes == [(client.T_ZONE_FIELD, 2 * 65536 + 1, b"\x03")]


def test_maintenance_values_and_filter_reset(monkeypatch):
    controller = sim.FakeController()
    controller.fields[sim.FILTER_LEFT] = struct.pack("<f", -1.75)
    e16 = wired(monkeypatch, controller)
    info = e16.get_info()
    assert (info["filter_interval"], info["service_interval"]) == (6, 6)
    assert info["filter_months_left"] == -1.75
    assert (info["fan_speed_levels"], info["fan_reversal_interval"]) == ([25, 35, 50, 100], 70)
    assert info["wifi_rssi"] == -60 and info["esp32_firmware"]["version"] == 1003011
    assert [device["name"] for device in info["devices"]] == [
        "Controller", "Fan 1", "Fan 2", "Fan 3", "Fan 4"]
    e16.set_global_field(client.F_FILTER_RESET, (0x12345678).to_bytes(4, "little"))
    assert e16.get_info()["filter_months_left"] == -1.75  # wrong magic value: nothing happens
    magic = client.RESET_MAGIC[client.F_FILTER_RESET]
    e16.set_global_field(client.F_FILTER_RESET, magic.to_bytes(4, "little"))
    assert e16.get_info()["filter_months_left"] == 6.0


def test_time_program_entries(monkeypatch):
    controller = sim.FakeController()
    e16 = wired(monkeypatch, controller)
    record = client.program_record(22 * 3600, 64, client.FAN_HEAT_RECOVERY, 2)  # Sunday 22:00
    stored = e16.set_time_program_entry(7, 2, record)
    assert stored == {"seconds": 79200, "days": 64, "mode": 1, "speed": 2, "type": 1}
    connections = controller.connections
    program = e16.get_time_program(7)
    assert controller.connections == connections + 1  # 32 requests on one connection
    assert program == [None, None, stored] + [None] * 29
    assert e16.get_time_program(8) == [None] * 32
    assert e16.set_time_program_entry(7, 2) is None
    assert e16.get_time_program(7) == [None] * 32


def test_time_program_write_that_is_not_stored(monkeypatch):
    controller = sim.FakeController(store_programs=False)
    with pytest.raises(ValueError):
        wired(monkeypatch, controller).set_time_program_entry(
            7, 1, client.program_record(0, 127, client.FAN_HEAT_RECOVERY, 1))
    assert len(controller.ignored_writes) == 1


# -- missing, late, extra and cut-off replies ------------------------------------------------------

def test_late_zone_status_after_a_command(monkeypatch):
    # The zone status the controller sends after a command arrives after the client's own poll
    controller = sim.FakeController(ack_delay=2.0)
    zone = wired(monkeypatch, controller).user_override(
        client.CMD_ZONE_SPEED_MODE, 2, client.FAN_HEAT_RECOVERY, 1, 900)
    assert (zone["speed"], zone["timer"]) == (2, 900)


def test_replies_to_earlier_requests_are_skipped(monkeypatch):
    controller = sim.FakeController()
    e16 = wired(monkeypatch, controller)
    stray = sim.reply_packet(client.T_USER_OVERRIDE, b"")
    controller.send_before_reply(stray, stray, stray)
    assert e16.get_zone()["zone_id"] == 1
    controller.send_before_reply(stray, stray, stray, stray)
    with pytest.raises(ValueError):
        e16.get_zone()


@pytest.mark.parametrize("call", [
    pytest.param(lambda e16: e16.get_zone(), id="get_zone"),
    pytest.param(lambda e16: e16.get_info(), id="get_info"),
    pytest.param(lambda e16: e16.get_time_program(7), id="get_time_program"),
    pytest.param(lambda e16: e16.set_time_program_entry(
        7, 0, client.program_record(0, 1, client.FAN_HEAT_RECOVERY, 1)), id="set_time_program_entry"),
    pytest.param(lambda e16: e16.user_override(client.CMD_CANCEL), id="user_override"),
])
def test_missing_reply_ends_in_a_timeout(monkeypatch, call):
    controller = sim.FakeController(ack_delay=None)
    controller.drop_replies()
    with pytest.raises(TimeoutError):
        call(wired(monkeypatch, controller))


def test_connection_closed_in_the_middle_of_a_reply(monkeypatch):
    controller = sim.FakeController()
    controller.close_after(20)
    with pytest.raises(ConnectionError):
        wired(monkeypatch, controller).get_zone()


def test_refused_connection(monkeypatch):
    controller = sim.FakeController()
    controller.refuse_connections = True
    with pytest.raises(OSError):
        wired(monkeypatch, controller).get_zone()


def test_unexpected_reply_to_an_installer_field_leaves_the_levels_empty(monkeypatch):
    controller = sim.FakeController()
    # The fifth reply of get_info answers field 32 (fan power of level 1) - here with another id
    controller.mutate_next_reply(lambda packet: sim.with_payload(packet, sim.raw_with_id(99, b"\x19")),
                                 skip=4)
    info = wired(monkeypatch, controller).get_info()
    assert info["fan_speed_levels"] is None and info["fan_reversal_interval"] is None
    assert info["filter_interval"] == 6 and len(info["devices"]) == 5


def test_installer_fields_answered_without_a_value(monkeypatch):
    controller = sim.FakeController()
    controller.missing_fields = {32, 33, 34, 35, 36}
    info = wired(monkeypatch, controller).get_info()
    assert info["fan_speed_levels"] is None and info["fan_reversal_interval"] is None
    assert info["filter_interval"] == 6 and len(info["devices"]) == 5


READS = {
    "get_zone": lambda e16: e16.get_zone(),
    "get_info": lambda e16: e16.get_info(),
    "get_time_program": lambda e16: e16.get_time_program(7),
}


@pytest.mark.parametrize("name", READS)
def test_malformed_replies_end_in_value_or_os_error(monkeypatch, name):
    """Every reply of the call, cut to every shorter length and replaced by random bytes, with a
    valid CRC: the client may fail, but only with ValueError or OSError."""
    reference = sim.FakeController()
    READS[name](wired(monkeypatch, reference))
    assert {operation for _, operation, _ in reference.requests} == {client.DATA_REQUEST}
    for index, reply in enumerate(reference.replies):
        payload, rng = _payload(reply), random.Random(index)
        variants = [payload[:size] for size in range(len(payload))]
        variants += [rng.randbytes(rng.randrange(119)) for _ in range(10)]
        for variant in variants:
            controller = sim.FakeController()
            controller.mutate_next_reply(
                lambda packet, variant=variant: sim.with_payload(packet, variant), skip=index)
            try:
                READS[name](wired(monkeypatch, controller))
            except (ValueError, OSError):
                pass
