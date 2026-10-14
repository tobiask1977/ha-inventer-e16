# SPDX-License-Identifier: MIT
"""Captured command/acknowledgement pairs from a second e16 - no Home Assistant needed.

Source: a controller with four fans (Wi-Fi module 1.3.11, controller 5.30.10, fans 5.30.9),
captured in August 2026. Each pair is the UserOverride packet that was sent and the ZoneViewRow
the controller answered with. Names and timestamps are replaced and the CRC recalculated;
nothing else is changed.

They back the notes in docs/protocol.md (issues #1 and #4): the acknowledgement already carries
the sent record (offset 74) and a fitting fan speed (17), while playback (18) can still differ
from the new state. The checks describe what this recording shows, not general protocol rules.
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "client", Path(__file__).resolve().parents[1] / "custom_components/inventer_e16/client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

CANCEL = bytes.fromhex("070003ff00000000")
GLOBAL_PAUSE = bytes.fromhex("020003ffffffffff")
# Speed of the time program while these captures were taken; cancel returned to it
SCHEDULE_SPEED = 1

# (label, UserOverride packet sent, ZoneViewRow the controller acknowledged it with,
#  playback in that reply), in the order of the captures
PAIRS = [
    ("00-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("01-speed1-heat-recovery-60min", "20160038010000000000ba0a000805010101100e0000",
     "f75f0092009200000000015a6f6e652031000000000000000000000105100e00002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005010101100e0000000000", 5),
    ("02-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("03-speed2-heat-recovery-60min", "4a160038010000000000ba0a000805020101100e0000",
     "5a5f0092009200000000015a6f6e652031000000000000000000000205100e00002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005020101100e0000000000", 5),
    ("04-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("05-speed3-heat-recovery-60min", "91160038010000000000ba0a000805030101100e0000",
     "3c5f0092009200000000015a6f6e652031000000000000000000000305100e00002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005030101100e0000000000", 5),
    ("06-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("07-speed4-heat-recovery-60min", "99160038010000000000ba0a000805040101100e0000",
     "005f0092009200000000015a6f6e652031000000000000000000000405100e00002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005040101100e0000000000", 5),
    ("08-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("09-speed1-heat-recovery-15min", "50160038010000000000ba0a00080501010184030000",
     "665f0092009200000000015a6f6e652031000000000000000000000105840300002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff000000000501010184030000000000", 5),
    ("10-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("11-speed1-heat-recovery-480min", "b9160038010000000000ba0a00080501010180700000",
     "f75f0092009200000000015a6f6e652031000000000000000000000105807000002902000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff000000000501010180700000000000", 5),
    ("12-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("13-speed1-ventilation-60min", "c5160038010000000000ba0a000805010201100e0000",
     "cb5f0092009200000000015a6f6e652031000000000000000000000105100e00002901000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005010201100e0000000000", 5),
    ("14-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("15-speed0-stop-60min", "d3160038010000000000ba0a000805000401100e0000",
     "ff5f0092009200000000015a6f6e652031000000000000000000000005100e00002900000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005000401100e0000000000", 5),
    ("16-cancel", "6c160038010000000000ba0a0008070003ff00000000",
     "3a5f0092009200000000015a6f6e652031000000000000000000000105000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 5),
    ("17-speed0-off-60min", "bd160038010000000000ba0a000805000301100e0000",
     "445f0092009200000000015a6f6e652031000000000000000000000005100e00002900000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff0000000005000301100e0000000000", 5),
    ("18-global-pause", "e9160038010000000000ba0a0008020003ffffffffff",
     "cd5f0092009100000000015a6f6e652031000000000000000000000001000000003800000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000020003ffffffffff000000", 1),
    ("19-cancel-after-global-pause", "6c160038010000000000ba0a0008070003ff00000000",
     "625f0092009100000000015a6f6e652031000000000000000000000104000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 4),
]

# Later polls of the zone without a new command, about ten seconds after the
# acknowledgement: (label, index in PAIRS, ZoneViewRow, playback)
LATER = [
    ("after-12-cancel", 12,
     "835f0092009200000000015a6f6e652031000000000000000000000100000000002802000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000070003ff00000000000000", 0),
    ("after-18-global-pause", 18,
     "745f0092009100000000015a6f6e652031000000000000000000000004000000003800000000a0410000804100008c42"
     "0080bb4400004040000080ff000080ff000080ff000080ff000080ff000080ff00000000020003ffffffffff000000", 4),
]


def _packet(hex_string, packet_type):
    packet = bytes.fromhex(hex_string)
    assert packet[1] == len(packet) and packet[3] == packet_type
    assert client.crc8(packet[1:]) == packet[0]
    return packet


def _sent(hex_string):
    packet = _packet(hex_string, client.T_USER_OVERRIDE)
    assert packet[10:14] == bytes.fromhex("ba0a0008")
    return packet[14:22]


def _zone(hex_string):
    packet = _packet(hex_string, client.T_ZONE_VIEW)
    return client.parse_zone(packet[10:packet[1]])


CASES = [pytest.param(sent, reply, playback, id=label) for label, sent, reply, playback in PAIRS]


@pytest.mark.parametrize(("sent", "reply", "playback"), CASES)
def test_acknowledgement_carries_the_sent_record(sent, reply, playback):
    assert _zone(reply)["last_override"] == client.parse_override(_sent(sent))


@pytest.mark.parametrize(("sent", "reply", "playback"), CASES)
def test_recorded_acknowledgement_has_expected_fan_speed(sent, reply, playback):
    # Requested speed for an override, 0 for global pause, and after cancel the speed of the time
    # program running at the time - a time program can also stop the fans, so this is the value
    # seen in this recording, not a rule
    record, zone = _sent(sent), _zone(reply)
    if record == GLOBAL_PAUSE:
        assert zone["speed"] == 0
    elif record == CANCEL:
        assert zone["speed"] == SCHEDULE_SPEED
    else:
        assert zone["speed"] == client.parse_override(record)["speed"]


@pytest.mark.parametrize(("sent", "reply", "playback"), CASES)
def test_zone_status_reports_the_mode_with_the_other_table(sent, reply, playback):
    record, zone = client.parse_override(_sent(sent)), _zone(reply)
    if record["command"] != client.CMD_ZONE_SPEED_MODE:
        return
    if record["mode"] in (client.FAN_OFF, client.FAN_STOP):
        assert zone["mode"] == 0
    else:
        assert client.READ_MODE_TO_FAN[zone["mode"]] == record["mode"]


@pytest.mark.parametrize(("sent", "reply", "playback"), CASES)
def test_playback_in_the_acknowledgement(sent, reply, playback):
    assert _zone(reply)["playback"] == playback


def test_playback_differs_from_the_new_state_in_eleven_acknowledgements():
    # Playback that fits the new state: 0 after cancel, 4 after global pause, 5 while an override
    # runs. Eleven acknowledgements still show something else. A later poll was captured for only
    # two of them (LATER); for the other nine this recording does not show when playback changed.
    expected = {CANCEL: 0, GLOBAL_PAUSE: 4}
    differing = [playback for _, sent, _, playback in PAIRS
                 if playback != expected.get(_sent(sent), 5)]
    assert (len(PAIRS), len(differing)) == (20, 11)


@pytest.mark.parametrize(("index", "reply", "playback"),
                         [pytest.param(*later[1:], id=later[0]) for later in LATER])
def test_playback_catches_up_without_a_new_command(index, reply, playback):
    acknowledged, later = _zone(PAIRS[index][2]), _zone(reply)
    assert later["last_override"] == acknowledged["last_override"]
    assert later["speed"] == acknowledged["speed"]
    assert acknowledged["playback"] != later["playback"] == playback
