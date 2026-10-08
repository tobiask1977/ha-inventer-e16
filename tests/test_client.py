# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Protocol tests for client.py - no Home Assistant needed.

The byte strings are real e16 replies with names and timestamps replaced; they contain no keys.
"""
import importlib.util
from pathlib import Path
import struct

import pytest

spec = importlib.util.spec_from_file_location(
    "client", Path(__file__).resolve().parents[1] / "custom_components/inventer_e16/client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

ZONE_REPLY = bytes.fromhex(
    "d75f009200906a000000015a6f6e652031000000000000000000000300000000002c01fd0000a041000080410000"
    "8c420080bb4400004040d84e79412a03c2424cb8ac413aa37942000080ff000080ff00000000070003ff00000000"
    "000000")
FAN_ROW = bytes.fromhex(
    "01020201020000007e79c04c0046616e20310000000000000000000000ffffffffffffffff523ba60401ffffffff"
    "ffffffffffffffffffff00007fff")
SENSOR_ROW = bytes.fromhex(
    "0304030102000000cb78c04c00496e646f6f720000000000000000000044b7ab410947794200000000b309804"
    "2ffffffffffffffffff00007fff")


def test_crc_shifts_before_testing_bit7():
    assert client.crc8(b"\x01") == 0x0E
    assert client.crc8(b"\x80") == 0
    assert client.crc8(b"123456789") == 0xAF


def test_zone_reply():
    assert client.crc8(ZONE_REPLY[1:]) == ZONE_REPLY[0]
    zone = client.parse_zone(ZONE_REPLY[10:ZONE_REPLY[1]])
    assert (zone["zone_id"], zone["name"], zone["speed"], zone["playback"]) == (1, "Zone 1", 3, 0)
    assert (zone["mode"], zone["profile"]) == (1, 253)
    assert zone["inside_temperature"] == 21.59
    assert zone["outside_humidity"] == 97.01
    assert zone["co2"] is None and zone["voc"] is None
    # Comfort settings of the zone (offsets 26-45)
    assert (zone["comfort_room_temperature"], zone["comfort_outdoor_temperature"], zone["humidity_threshold"],
            zone["co2_threshold"], zone["voc_threshold"]) == (20.0, 16.0, 70.0, 1500.0, 3.0)
    assert zone["last_override"] == {"command": 7, "speed": 0, "mode": 3, "zone": 255, "duration": 0}


def test_missing_sensor_is_none():
    payload = bytearray(ZONE_REPLY[10:ZONE_REPLY[1]])
    struct.pack_into("<f", payload, 54, float("-inf"))
    assert client.parse_zone(payload)["inside_temperature"] is None


def test_device_rows():
    fan = client.parse_device(FAN_ROW)
    assert (fan["name"], fan["type"], fan["hardware"], fan["status"]) == ("Fan 1", 2, 2, client.DEV_ONLINE)
    assert client.version_text(fan["firmware"]) == "5.30.9"
    assert fan["runtime"] == 78003026 and fan["battery"] is None
    sensor = client.parse_device(SENSOR_ROW)
    assert (sensor["name"], sensor["signal"]) == ("Indoor", -53)
    assert (sensor["temperature"], sensor["humidity"], sensor["battery"]) == (21.46, 62.32, 64.02)


def test_firmware_images_and_versions():
    images = client.parse_firmware_images(bytes.fromhex("ff01034e0f00c8483f6c00000000000000000000"))
    assert images == {255: {"version": 1003011, "crc": 0x6C3F48C8}}
    assert client.version_text(1003011) == "1.3.11"
    assert client.version_text(5030010) == "5.30.10"


def test_override_payload_matches_app_serializer():
    payload = client.override_payload(client.CMD_ZONE_SPEED_MODE, 2, client.FAN_HEAT_RECOVERY, 1, 3600)
    assert payload.hex() == "ba0a0008" "05020101" "100e0000"
    frame = client.packet(client.T_USER_OVERRIDE, payload, operation=client.UPDATE)
    assert (frame[1], frame[3], frame[4], frame[5]) == (22, 56, 1, 0)
    assert client.crc8(frame[1:]) == frame[0]


def test_field_payloads():
    assert client.field_payload(client.F_FILTER_LEFT).hex() == "ba0a070400400000"
    reset = client.field_payload(
        client.F_FILTER_RESET, client.RESET_MAGIC[client.F_FILTER_RESET].to_bytes(4, "little"))
    assert reset.hex() == "ba0a0708" "00800000" "82847646"
    # Zone field: zone id 1, field 1 (profile) -> id 65537
    assert client.field_payload(1 * 65536 + client.ZF_PROFILE, b"\xfd").hex() == "ba0a070501000100fd"
    # Comfort room temperature 20.5 degC as float32 LE -> id 65538
    assert client.field_payload(1 * 65536 + client.ZF_COMFORT_ROOM, struct.pack("<f", 20.5)).hex() == (
        "ba0a0708" "02000100" "0000a441")


def test_packet_timestamp_is_big_endian(monkeypatch):
    monkeypatch.setattr(client.time, "time", lambda: 0x01020304)
    frame = client.packet(13, destination=client.ESP32)
    assert frame[1:] == bytes.fromhex("0a000d029f01020304")


class FakeConnection:
    def __init__(self, stream):
        self.stream = bytearray(stream)

    def sendall(self, data):
        pass

    def recv(self, count):
        chunk = bytes(self.stream[:min(count, 3)])  # deliver in small pieces
        del self.stream[:len(chunk)]
        return chunk


def test_request_skips_reply_to_previous_command():
    stray = client.packet(client.T_USER_OVERRIDE, b"", operation=client.RESPONSE)
    payload = client.E16Client._request(FakeConnection(stray + ZONE_REPLY[:ZONE_REPLY[1]]),
                                        client.T_ZONE_VIEW, b"\x00")
    assert client.parse_zone(payload)["name"] == "Zone 1"


def test_closed_connection_raises():
    with pytest.raises(ConnectionError):
        client.receive_exact(FakeConnection(b"ab"), 4)


def test_malformed_reply_becomes_value_error():
    with pytest.raises(ValueError):
        with client._malformed_as_value_error():
            struct.unpack_from("<b", b"\x00", 4)


def test_short_field_reply_is_rejected():
    reply = client.packet(client.T_GLOBAL_FIELD, b"\xba\x0a\x07", operation=client.RESPONSE)
    with pytest.raises(ValueError):
        client.E16Client._field(FakeConnection(reply), client.T_GLOBAL_FIELD, client.F_FILTER_LEFT)


def test_psk_validation():
    with pytest.raises(ValueError):
        client.E16Client("192.0.2.1", "0000000000000000")
    with pytest.raises(ValueError):
        client.E16Client("192.0.2.1", "abcd")
