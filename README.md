# inVENTer Easy Connect e16 for Home Assistant

Local control of inVENTer decentralised ventilation through the **Easy Connect e16** controller:
over your Wi-Fi, without the manufacturer's cloud.

> **Unofficial.** Not affiliated with, endorsed or supported by inVENTer GmbH. Use at your own
> risk, see [Disclaimer](#disclaimer).

## Features

- **Control:** a fan entity with speed 1–4 and the modes *heat recovery* and *ventilation*.
  Off pauses the ventilation until you switch it on again; on returns to the profile. Buttons
  *Boost 15 min*, *Pause 1 h* and *Resume profile*.
- **Profiles:** select the ventilation profile and set its comfort values (indoor and outdoor
  comfort temperature, humidity threshold, CO₂/VOC threshold if such a sensor is installed).
- **Sensors:** speed, mode, playback, timer, indoor and outdoor temperature and humidity, CO₂/VOC,
  system status and last command. Calculated: dew points, absolute humidity, and *Ventilation
  dries*, which tells whether outdoor air would actually remove moisture (useful for cellars).
- **Zones:** on controllers with several zones, every zone becomes its own device with its own
  fan, sensors, profile and buttons (see [Several zones](#several-zones)).
- **Radio devices:** every fan and sensor becomes its own device with radio signal, runtime,
  temperature, humidity, battery and problem flags.
- **Maintenance:** filter change and service with due date, days left, interval and *confirm*
  buttons.
- **Firmware:** update entities for the Wi-Fi module, controller, fans and sensors. Installing
  updates stays with the official app.
- **Time programs:** read and edit the schedules of the ventilation profiles (see
  [Actions](#actions)).
- **Diagnostics:** fan power per speed level, reversal interval, and a diagnostics download with
  PSK, host and device ID redacted.

## Requirements

- Easy Connect e16 with Wi-Fi module, connected to your network with the official app.
- Home Assistant 2026.9 or newer.
- Once, to read the device key: a phone with a Bluetooth app, or a computer with Bluetooth LE and
  Python.

## Installation

### 1. Install the integration

[![Open in Marketplace](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tobiask1977&repository=ha-inventer-e16&category=integration)

Home Assistant 2026.11 or newer: *Settings → Marketplace*, search for **inVENTer Easy Connect
e16** and install it. On older versions, download it from HACS and restart Home Assistant.

Manual installation: copy `custom_components/inventer_e16` to `/config/custom_components/` and
restart.

### 2. Read the device ID and PSK (once)

The controller encrypts the local connection with a key (PSK) that is different for every
device. The official app never shows it, but the controller hands it out over Bluetooth while it
is in pairing mode. **[docs/onboarding.md](docs/onboarding.md)** shows both ways step by step:
with a free Bluetooth app on your phone, or with the Python tool in this repository:

```bash
pip install -r tools/requirements.txt
# hold the mode button on the controller until the LED blinks blue, then:
python tools/e16_onboard.py read
```

Reading changes nothing on the controller, and the official app keeps working. Keep the PSK
private: anyone on your network who has it can control the ventilation.

### 3. Add the controller

Home Assistant usually discovers the controller by itself and fills in host and device ID, so you
only enter the PSK. Otherwise go to *Settings → Devices & services → Add integration →
inVENTer Easy Connect e16* and enter host, device ID and PSK.

Reserve the controller's IP address in your router. If it changes anyway, Home Assistant usually
picks up the new one by itself. For a new address or key (for example after a factory reset), use
**Reconfigure** on the integration. If the controller rejects the stored key, Home Assistant asks
for the new one.

**Options:** how often the status is polled (15–3600 s, default 30 s; it is read again right after
every command) and the firmware check (see [Privacy](#privacy)).

## Usage

Speed and mode changes are **temporary**, as in the app. The *Command duration* entity
(15 min–8 h) sets how long they last; after that the controller returns to its profile. For
permanent changes, select another profile or edit its time program.

### Several zones

Every zone with fans or sensors assigned becomes its own device below the controller; zone 1
stays on the controller device, so a single-zone installation looks as before. Each zone has its
own fan, buttons, profile, command duration and sensors, and its commands go to that zone only.
Outdoor values show on zone 1, indoor values on zones with an indoor sensor.

- With a single zone, switching the fan off or on and the buttons send the app's commands for
  all zones, as before.
- While a pause or boost for all zones is running (for example started in the app), switching a
  zone on or *Resume profile* ends it in all zones.
- Time programs belong to a profile, not to a zone: editing one changes every zone that uses
  that profile.
- When a radio device is added, removed or moved to another zone, the integration reloads by
  itself. Zones and devices the controller no longer reports can be deleted on their device page.

### Actions

| Action | What it does |
|---|---|
| `inventer_e16.set_mode` | Temporary mode, speed and duration in one call |
| `inventer_e16.get_time_program` | Returns the time program of a profile (default: the current one) |
| `inventer_e16.set_time_program_entry` | Writes one entry (0–31) of a profile's time program and reads it back |
| `inventer_e16.delete_time_program_entry` | Deletes one entry |

A pause that ends by itself after 30 minutes:

```yaml
action: inventer_e16.set_mode
target:
  entity_id: fan.my_inventer
data:
  mode: pause          # heat_recovery | ventilation | pause | pause_open
  minutes: 30
```

Read a time program. Each entry has `time`, `days`, `mode` and `speed`:

```yaml
action: inventer_e16.get_time_program
target:
  entity_id: fan.my_inventer
data:
  profile: bedroom     # bedroom … holiday, custom_1 … custom_9
response_variable: program
```

Change one entry. It applies whenever that profile is active:

```yaml
action: inventer_e16.set_time_program_entry
target:
  entity_id: fan.my_inventer
data:
  profile: custom_1
  entry: 0
  time: "06:30"
  days: [monday, tuesday, wednesday, thursday, friday]
  mode: heat_recovery
  speed: 2
```

There is no undo: read the program first and keep a copy. The automatic and cellar profiles have
no time program.

## Privacy

Everything runs locally over TCP port 47820. The only exception is the optional firmware check.
When you switch it on in the options, the integration asks the manufacturer's firmware catalog
once a day which versions are current. It sends only the brand name, but the manufacturer's cloud
sees your public IP address and Home Assistant version. Without the check, the firmware entities
show the installed version only.

The check is off for installations set up with 0.3.14 or later. Older installations keep it on
until you switch it off.

## Limitations

- Support for several zones is new. It is based on tests from a four-zone installation, but has
  not run on one yet; feedback in [#22](https://github.com/tobiask1977/ha-inventer-e16/issues/22)
  is welcome. Devices cannot be moved to another zone.
- Custom profiles cannot be created or renamed (their time programs can be edited).
- Firmware cannot be installed from Home Assistant.
- Developed on one installation with two iV14 Zero fans and an indoor and outdoor sensor. Other
  fans on the e16 should work, but this hasn't been confirmed.

Something doesn't work, or your setup is different? Open an issue and attach the diagnostics
download, see [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

[docs/protocol.md](docs/protocol.md) describes the packet formats and what has been verified on a
real controller.

## Development

```bash
pip install pytest
pytest tests --ignore=tests/ha          # protocol tests, any OS
pip install pytest-homeassistant-custom-component
pytest tests/ha                         # Home Assistant tests, Linux/macOS
```

The protocol client (`custom_components/inventer_e16/client.py`) has no Home Assistant
dependency and can be used on its own.

## License

[MIT](LICENSE), Copyright (c) 2026 Tobias Krautkremer.

"inVENTer" and "Easy Connect" are trademarks of their owner and are used here only to say which
devices this software works with. This repository contains no code, images, logos or other
material from the manufacturer or its app. The icon in `custom_components/inventer_e16/brand/` is
an original design for this project.

## Disclaimer

This is an independent, unofficial project, provided **as is, without warranty of any kind**. It
was developed by analysing the device's communication for interoperability, and you use it **at
your own risk**:

- Commands change how your ventilation runs. Wrong settings over a longer time can affect indoor
  air quality and humidity (risk of condensation and mould). Check the result.
- Using unofficial software may affect warranty or support claims against the manufacturer.
- The manufacturer can change the firmware or its cloud services at any time, which may break this
  integration without notice.

To the extent permitted by law, the authors are not liable for damage to devices, buildings,
health or data, or for any other loss arising from the use of this software. This does not limit
liability for intent or gross negligence, or for injury to life, body or health.
