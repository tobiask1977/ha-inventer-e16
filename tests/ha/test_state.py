# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""State derived from the zone status: fan on/off and whether the last command still applies."""
from types import SimpleNamespace

import pytest

from custom_components.inventer_e16.client import FOREVER
from custom_components.inventer_e16.fan import E16Fan
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
