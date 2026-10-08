# Changelog

## 0.3.5 – 2026-10-08

- Service `inventer_e16.set_mode` (fan entity): time-limited command with mode (heat recovery,
  ventilation, pause with flap closed or open), speed and duration (15 min–8 h). Unlike
  `fan.turn_off` a pause ends by itself, so an automation that stops renewing it hands control
  back to the controller's profile.

## 0.3.4 – 2026-10-08

- Dew point and absolute humidity indoor/outdoor, dew point difference
- *Ventilation dries* binary sensor: on from 5 K dew point difference, off below 4 K, never when
  the room is below 10 °C – shows whether bringing in outdoor air removes moisture
  (relative humidity alone does not tell: cold air at 95 % can hold less water than warm air at 60 %)
- Fan speed is recorded in the long-term statistics

## 0.3.3 – 2026-10-08

- Own brand icon in `custom_components/inventer_e16/brand/` (shown in Home Assistant 2026.3+);
  a neutral fan symbol, deliberately not the manufacturer's logo
- HACS validation runs without exceptions

## 0.3.2 – 2026-10-08

Security review before publishing:

- Truncated or garbled controller replies end as a handled error instead of an unhandled
  struct/index error; short field replies are rejected; at most 32 radio devices are queried
- Only integer versions are accepted from the vendor firmware catalog
- `tools/e16_onboard.py --output` creates the key file readable for the owner only
- CI actions pinned to commit SHAs
- Threat model in SECURITY.md; AGENTS.md/CLAUDE.md with contributor rules

## 0.3.1 – 2026-10-08

- CO₂ unit: `UnitOfRatio.PARTS_PER_MILLION` instead of the deprecated constant (removed in HA 2027.8)
- Onboarding guide `docs/onboarding.md` (English/German)
- License notice, trademark note and disclaimer in the README; SPDX identifiers in all sources

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
