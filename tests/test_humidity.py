# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Dew point, absolute humidity and the 'ventilation dries' rule."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "humidity", Path(__file__).resolve().parents[1] / "custom_components/inventer_e16/humidity.py")
humidity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(humidity)


def zone(t_in, rh_in, t_out, rh_out):
    return {"inside_temperature": t_in, "inside_humidity": rh_in,
            "outside_temperature": t_out, "outside_humidity": rh_out}


def test_reference_values():
    # Tables: 20 °C / 50 % -> dew point 9.3 °C, about 8.6 g/m³; 0 °C / 80 % -> 3.9 g/m³
    assert humidity.dew_point(20, 50) == 9.3
    assert abs(humidity.absolute_humidity(20, 50) - 8.65) < 0.05
    assert abs(humidity.absolute_humidity(0, 80) - 3.88) < 0.05


def test_missing_or_invalid_values():
    assert humidity.dew_point(None, 50) is None
    assert humidity.dew_point(20, 0) is None
    assert humidity.absolute_humidity(20, None) is None
    assert humidity.ventilation_dries(zone(None, 60, 5, 80)) is None


def test_humid_autumn_day_does_not_dry():
    # Measured 08.10.2026: 21.4 °C / 62.3 % inside, 14.0 °C / 95.3 % outside - only 0.5 K apart
    assert humidity.ventilation_dries(zone(21.4, 62.3, 14.0, 95.3)) is False


def test_cold_dry_day_dries():
    assert humidity.ventilation_dries(zone(20, 60, 2, 80)) is True


def test_hysteresis():
    # About 4.5 K apart: not enough to switch on, enough to stay on
    z = zone(20, 60, 10.0, 84)
    diff = humidity.dew_point(20, 60) - humidity.dew_point(10.0, 84)
    assert 4.0 <= diff < 5.0
    assert humidity.ventilation_dries(z, was_on=False) is False
    assert humidity.ventilation_dries(z, was_on=True) is True


def test_no_drying_when_room_is_cold():
    assert humidity.ventilation_dries(zone(9, 90, -5, 80)) is False
