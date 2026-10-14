# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""State derived from the zone status: fan on/off and whether the last command still applies."""
from datetime import time
import struct
from types import SimpleNamespace

import pytest

from custom_components.inventer_e16.client import FOREVER
from custom_components.inventer_e16.fan import PROGRAM_PROFILES, E16Fan, program_record, program_response
from custom_components.inventer_e16.sensor import override_active


def _fan_on(**zone):
    return E16Fan.is_on.fget(SimpleNamespace(coordinator=SimpleNamespace(data=zone)))


@pytest.mark.parametrize(("speed", "mode", "playback", "on"), [
    (3, 2, 5, True),
    (1, 1, 0, True),
    # Playback still at pause/shut down while the fans already run again (issue #1)
    (1, 2, 1, True),
    (1, 2, 4, True),
    # Global pause or a zone pause: speed 0, whatever playback says
    (0, 2, 5, False),
    (0, 2, 0, False),
    (2, 0, 0, False),
])
def test_fan_on_follows_speed_not_playback(speed, mode, playback, on):
    assert _fan_on(speed=speed, mode=mode, playback=playback) is on


def _record(command, duration):
    return {"command": command, "speed": 2, "mode": 1, "zone": 1, "duration": duration}


@pytest.mark.parametrize(("record", "timer", "active"), [
    (_record(5, 900), 600, True),
    # Expired: the record stays, only the timer is 0 (issue #2)
    (_record(5, 900), 0, False),
    (_record(2, FOREVER), 0, True),
    (_record(7, 0), 0, False),
    (_record(9, 0), 0, False),
])
def test_override_active(record, timer, active):
    assert override_active(record, timer) is active


def test_time_program_profiles_are_the_ones_with_a_table():
    assert PROGRAM_PROFILES["bedroom"] == 1 and PROGRAM_PROFILES["custom_9"] == 15
    assert len(PROGRAM_PROFILES) == 15 and "cellar_heat_recovery" not in PROGRAM_PROFILES


def test_time_program_response():
    entries = [None] * 32
    entries[0] = {"seconds": 0, "days": 0b0011111, "mode": 1, "speed": 1, "type": 1}
    entries[5] = {"seconds": 21 * 3600 + 30 * 60, "days": 0b1100000, "mode": 4, "speed": 0, "type": 1}
    assert program_response(1, entries) == {"profile": "bedroom", "entries": [
        {"entry": 0, "time": "00:00", "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
         "mode": "heat_recovery", "speed": 1},
        {"entry": 5, "time": "21:30", "days": ["saturday", "sunday"], "mode": "pause_open", "speed": 0},
    ]}


def test_time_program_record_from_service_fields():
    record = program_record(time(6, 30, 59), ["friday", "monday", "monday"], "ventilation", 3)
    assert record == struct.pack("<IBBBB", 6 * 3600 + 30 * 60, 0b0010001, 2, 3, 1)
    # Pause runs with speed 0, whatever was given
    assert program_record(time(22), ["sunday"], "pause", 4)[4:8] == bytes([64, 3, 0, 1])
