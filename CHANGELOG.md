# Changelog

## 0.5.0b1 – 2026-11-13 (pre-release)

Pre-release for moving fans between zones; based on #37 by @Kadz93.

- **Move fans between zones** (#37): with several zones, every fan unit has a *Zone* select, and
  the action `inventer_e16.set_device_zone` moves a fan unit or indoor sensor to another zone and
  reads it back. The controller and the outdoor sensor can't be moved.
- **Named zones stay**: a zone with a name is in use even without devices, so fans can be moved
  to it, as in the app. A controller with one zone in use and another named zone becomes a
  controller with several zones.
- A fan moved between zones in use (here or in the app) moves below its new zone without a
  reload. The integration still reloads by itself when a radio device is added or removed, a zone
  comes into use or goes out of use, or an indoor sensor moves.
- New action `inventer_e16.get_devices`: the radio devices with address, type, zone, signal,
  firmware and values, and the zones in use, e.g. for dashboard cards.
- Documentation: the polarity doesn't switch the other fan of a pair on every installation. On one
  controller the partner switched along, on another every fan switches on its own (#38). The
  integration only ever writes the fan you change.

## 0.4.1 – 2026-11-12

- **Polarity can be changed** (#33): the polarity of a fan unit is now a select in its
  configuration instead of the diagnostic sensor from 0.4.0, which is removed (same states,
  `supply` and `extract`). The controller keeps the two fans of a pair opposite, so changing one
  switches the other along; both show the new value at once. Tested with one pair of fans.
- **Fans on a cable** no longer get a *Radio signal* sensor, which always showed *unknown* for
  them: the controller reports a fixed marker instead of a radio level. The old sensor is removed.

## 0.4.0 – 2026-11-08

Stable release of the multi-zone support from 0.4.0b1 and 0.4.0b2, confirmed on two installations
with several zones in #22.

- **Several zones** (#22): every zone in use becomes a device of its own with fan, sensors,
  profile, comfort settings, command duration and buttons, and its commands go to that zone only.
  Switching a zone's fan off pauses that zone without an end. The controller device is then named
  *inVENTer Easy Connect e16* and keeps filter and service, firmware, Wi-Fi, alarms and the
  outdoor values. Zone 1's entities move from the controller to the new zone 1 device, keep their
  entity IDs, and the zone 1 device takes over the controller's area. Single-zone installations
  keep their devices, entities and commands.
- **Custom profiles** can be selected once they have a time program, not only while they are
  active. The integration reads this once a day, one profile at a time, and after a change
  through the time program actions; after an error it tries again 10 minutes later. Until then
  the profiles offered before a restart stay.
- **Polarity** of each fan unit (#33): whether it starts with supply or extract air, as a
  diagnostic sensor. Changing it stays with the app for now.
- The integration reloads by itself when radio devices are added, removed or moved to another
  zone; zones and devices the controller no longer reports can be deleted in the UI.
- Diagnostics contain every zone in use (`zones` instead of `zone`) and the custom profiles with
  a time program. Device type 27 is shown as iV-Twin+ fan unit.
- Documentation in English only; installation via the Marketplace of Home Assistant 2026.11.

## 0.4.0b2 – 2026-11-07 (pre-release)

Second pre-release for controllers with several zones, after the first test report in #22.

- With several zones, zone 1 becomes a device of its own like the other zones. Before, it sat on
  the controller device, which carried zone 1's name and twice as many entities as the other
  zones. The controller is now named *inVENTer Easy Connect e16* and keeps filter and service,
  firmware, Wi-Fi, alarms and the outdoor values. Zone 1's entities keep their entity IDs, and
  the zone 1 device takes over the controller's area. Single-zone installations don't change.

## 0.4.0b1 – 2026-11-07 (pre-release)

Pre-release for testing on controllers with several zones; see #22.

- **Several zones** (#22): every zone with radio devices assigned becomes its own device with fan,
  sensors, profile, comfort settings, command duration and buttons. Commands go to that zone only;
  before, switching the fan off or on and the buttons *Boost 15 min*, *Pause 1 h* and *Resume
  profile* acted on all zones. Zone 1 stays on the controller device and keeps its entities, and
  single-zone installations send the same commands as before. Each fan and sensor hangs below its
  zone.
- The integration reloads by itself when a radio device is added, removed or moved to another
  zone (before, new devices needed a restart). Zones and devices the controller no longer reports
  can be deleted in the UI.
- Diagnostics contain the status of every zone in use (`zones` instead of `zone`).
- Device type 27 is shown as iV-Twin+ fan unit.
- Documentation: README and onboarding guide rewritten in English only and shortened.
  Installation via the Marketplace of Home Assistant 2026.11 (HACS on older versions).

## 0.3.15 – 2026-10-21

- **Onboarding with the phone** (#18): device ID and PSK can be read with a free BLE app such as
  nRF Connect, no Python needed. Step-by-step guide with screenshots in `docs/onboarding.md`.
- Setup accepts the PSK and the device ID the way BLE apps show them: hex with spaces, dashes,
  colons or `0x`; the device ID also as hex bytes.
- `tools/e16_onboard.py scan` also finds the controller by its name. On macOS it is reported
  without its services, so the scan found nothing before (#3).
- README: install directly from the HACS default list.

## 0.3.14 – 2026-10-14

- **Firmware check opt-in** (#6): new installations no longer ask the manufacturer's cloud; switch
  it on in the options. Existing installations keep it on (config entry migration 1.1 → 1.2), an
  explicit choice is kept.

## 0.3.13 – 2026-10-14

- **Services `set_time_program_entry` and `delete_time_program_entry`**: change one entry of a
  profile's time program, read back from the controller after every write (#9).

## 0.3.12 – 2026-10-14

- Client: read the time program of a ventilation profile and write or delete single entries,
  each write read back (#9). Writing is not available in Home Assistant yet. Packet 48 documented in
  `docs/protocol.md`.
- **Service `get_time_program`** (response only): the time program of a ventilation profile with
  time, weekdays, mode and speed per entry (#9).

## 0.3.11 – 2026-10-14

- **Fan on/off** follows fan speed and mode instead of playback: playback often lags behind a
  command, so the fan could show *off* although it was already running again (#1).
- **Last command** sensor: new attribute `active`. A time-limited command that has run out keeps
  its record, only the timer drops to 0 – `active` is then `false` (#2).
- **DHCP discovery** also for controllers that announce themselves as `noName-<device id>` (#3).
- **Option: polling interval** of the zone status, 15–3600 s, default 30 s (#8).
- CI: Home Assistant tests run on Python 3.14, i.e. against the supported Home Assistant version.

## 0.3.10 – 2026-10-08

- No more reload when Home Assistant only records a DHCP discovery key on the entry: the
  integration no longer uses a config entry update listener. Options still reload the entry
  (`OptionsFlowWithReload`), re-authentication and reconfigure reload as before.
- Removes the Home Assistant 2026.10 warning *"has an update listener and should use it for
  scheduling a reload"* – that combination stops working in Home Assistant 2026.12.
- README: through a router integration (e.g. UniFi device trackers) Home Assistant passes a new IP
  address on only when the tracker is added, i.e. at the next start – DHCP traffic in the same
  network is picked up right away.

## 0.3.9 – 2026-10-08

- **DHCP discovery**: the controller reports itself as `Easy Connect e16-<device id>`, so Home
  Assistant offers it as "discovered" with host and device ID filled in – only the PSK is needed.
  Works also when HA sees the controller only through a router integration (e.g. UniFi device
  trackers), not just with DHCP traffic in the same network.
- A configured controller that gets a new IP address is updated automatically.
- Config flow tests against a real Home Assistant core (`tests/ha`, CI on Linux).

## 0.3.8 – 2026-10-08

- Wrong PSK is recognised (the controller ends the TLS handshake with *bad record mac*) and starts
  Home Assistant's **re-authentication**: enter the new key, entities and history stay. Timeouts
  stay "unavailable" and never trigger it.
- **Reconfigure**: change host or PSK later without removing the integration (empty PSK keeps the
  stored key).

## 0.3.7 – 2026-10-08

- *Pause 1 h* button like the app's quick pause (ends by itself)
- Fan power per speed level (e.g. 25/35/50/100 %) and the reversal interval of the push-pull
  fans as diagnostic sensors – installer settings, deliberately read only

## 0.3.6 – 2026-10-08

- Comfort settings of the zone as number entities: comfort temperature indoor and outdoor,
  humidity threshold; CO₂ and VOC threshold only when such a sensor is present. They feed the
  controller's automatic profiles. The app offers no end-user form for them on the e16, so the
  allowed ranges are a conservative choice of this integration.

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
