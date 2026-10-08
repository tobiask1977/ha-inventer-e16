# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Dew point and absolute humidity (Magnus formula over water) - no Home Assistant imports.

Ventilating removes moisture only if the outdoor air holds less water per cubic metre than the
indoor air, i.e. if the outdoor dew point is lower. Relative humidity alone says nothing: cold
air at 95 % can hold less water than warm air at 60 %.
"""
import math

MAGNUS_A, MAGNUS_B = 17.62, 243.12   # over water, -45 to 60 °C


def dew_point(temperature, humidity):
    """Dew point in °C, or None if a value is missing or out of range."""
    if temperature is None or humidity is None or not 0 < humidity <= 100:
        return None
    gamma = math.log(humidity / 100) + MAGNUS_A * temperature / (MAGNUS_B + temperature)
    return round(MAGNUS_B * gamma / (MAGNUS_A - gamma), 1)


def absolute_humidity(temperature, humidity):
    """Water content in g/m³, or None if a value is missing or out of range."""
    if temperature is None or humidity is None or not 0 <= humidity <= 100:
        return None
    vapour_pressure = humidity / 100 * 6.112 * math.exp(MAGNUS_A * temperature / (MAGNUS_B + temperature))
    return round(216.7 * vapour_pressure / (273.15 + temperature), 2)


# Common rule for dew point ventilation: switch on from 5 K dew point difference, off below 4 K,
# and not when the room would cool down too much or the outdoor air is very cold.
DRY_ON_K, DRY_OFF_K = 5.0, 4.0
MIN_INSIDE_C, MIN_OUTSIDE_C = 10.0, -10.0


def ventilation_dries(zone, was_on=False):
    """True if bringing in outdoor air dries the room noticeably (with hysteresis)."""
    inside = dew_point(zone.get("inside_temperature"), zone.get("inside_humidity"))
    outside = dew_point(zone.get("outside_temperature"), zone.get("outside_humidity"))
    if inside is None or outside is None:
        return None
    if zone["inside_temperature"] < MIN_INSIDE_C or zone["outside_temperature"] < MIN_OUTSIDE_C:
        return False
    return inside - outside >= (DRY_OFF_K if was_on else DRY_ON_K)
