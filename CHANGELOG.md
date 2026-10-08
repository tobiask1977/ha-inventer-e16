# Changelog

## 0.3.0 – 2026-10-08

First version in its own repository.

- Ventilation profile select (zone profile, written via ZoneRowField)
- Temperature, humidity and battery per radio sensor; CO₂/VOC when a sensor is present
- *Battery low* and *alarm* binary sensors
- Entity names and states translated (English, German) – state values are now keys
  (`heat_recovery` instead of `Wärmerückgewinnung`)
- Option to disable the vendor firmware catalog
- Diagnostics download with PSK, host and device ID redacted
- Onboarding tool `tools/e16_onboard.py`

## 0.2.0

- Control: fan entity, boost, resume, command duration
- Maintenance: filter/service dates, intervals, confirm buttons
- Firmware update entities against the vendor catalog

## 0.1.0

- Read-only zone status over TLS-PSK
