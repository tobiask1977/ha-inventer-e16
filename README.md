# inVENTer Easy Connect e16 for Home Assistant

Local control of inVENTer decentralised ventilation systems with the **Easy Connect e16**
controller – over your Wi-Fi, without the manufacturer's cloud.

> **Unofficial.** This project is not affiliated with, endorsed or supported by inVENTer GmbH.
> "inVENTer" and "Easy Connect" are trademarks of their respective owner and are used here only
> to describe compatibility. Use at your own risk.

## Features

| Area | Entities |
|---|---|
| **Control** | Fan with speed 1–4 and modes *heat recovery* / *ventilation*; off = unlimited pause, on = resume the profile; buttons *Boost 15 min* and *Resume profile*; *command duration* 15 min–8 h |
| **Profile** | Select the ventilation profile (default, bedroom, …, summer, cellar heat recovery, cellar with ventilation) |
| Zone | Speed, playback, mode, timer, indoor/outdoor temperature and humidity, CO₂/VOC (if a sensor is present), system status, last command |
| **Maintenance** | Filter change and service: due date, days left, "due" flags from the controller, interval selection, *confirm* buttons |
| **Firmware** | Update entities for Wi-Fi module, controller, fans and sensors, compared against the manufacturer's firmware catalog (can be disabled). Installing stays with the official app |
| Radio devices | Each fan and sensor as its own device: radio signal, runtime, temperature, humidity, battery; *battery low*, *radio device missing* and *alarm* flags |
| Diagnostics | Downloadable diagnostics with PSK, host and device ID redacted |

Speed and mode are **time-limited commands** exactly like in the app: when the command duration
ends, the controller returns to its profile. Permanent changes are made through the profile.

## Requirements

- Easy Connect e16 with Wi-Fi module, connected to your network (set up with the official app)
- Home Assistant 2026.9 or newer (Python ≥ 3.13 for TLS-PSK)
- Once: a computer with Bluetooth LE and Python to read the device key

## Installation

### 1. Read device ID and PSK (once)

The controller encrypts the local connection with a key that is individual per device. The app
never shows it, but the controller hands it out over Bluetooth while in pairing mode.
Step-by-step guide with troubleshooting: **[docs/onboarding.md](docs/onboarding.md)**
(also in German).

```bash
pip install -r tools/requirements.txt
# hold the mode button on the controller until the LED blinks blue, then:
python tools/e16_onboard.py scan
python tools/e16_onboard.py read            # or: read AA:BB:CC:DD:EE:FF
```

The tool prints the **device ID** and the **PSK**. It only reads – it does not change the
pairing with your app. Keep the PSK private: anyone on your network with it can control the
ventilation.

### 2. Install the integration

**HACS:** add this repository as a custom repository (category *Integration*), install
*inVENTer Easy Connect e16*, restart Home Assistant.

**Manual:** copy `custom_components/inventer_e16` to `/config/custom_components/` and restart.

### 3. Add it

*Settings → Devices & services → Add integration → inVENTer Easy Connect e16*, then enter host,
device ID and PSK. Reserve the controller's IP address in your DHCP server.

## Privacy

Everything runs locally on TCP 47820. The only exception is the optional firmware check: once a
day the integration asks the manufacturer's firmware catalog (a Firebase function) which versions
are current – sending only the brand name `inventer`. Switch it off in the integration options.

## Limitations

- Only the first zone of a controller is supported (multi-zone systems: please open an issue).
- Time programs and custom profiles cannot be edited.
- Firmware cannot be installed from Home Assistant.
- Tested with one installation (two fan units, indoor and outdoor sensor).

## How it works

See [docs/protocol.md](docs/protocol.md) for the packet formats and what has been verified on a
real device.

## Development

```bash
pip install pytest
pytest tests
```

The protocol client (`custom_components/inventer_e16/client.py`) has no Home Assistant
dependency and can be used on its own.

## License

Copyright (c) 2026 Tobias Krautkremer. Released under the [MIT License](LICENSE): you may use,
copy, modify and distribute this software, including commercially, as long as the copyright
notice and the license text are kept. Source files carry the identifier
`SPDX-License-Identifier: MIT`.

"inVENTer" and "Easy Connect" are trademarks of their respective owner. They are used only to
describe which devices this software works with; no endorsement is implied. This repository
contains no code, images, logos or other material of the manufacturer or its app.

## Disclaimer

This is an independent, unofficial project, provided **"as is", without warranty of any kind**
(see the [license](LICENSE)). It was developed by observing and analysing the device's
communication for interoperability and has been tested on a single installation only.

You use it **at your own risk**. In particular:

- Commands change how your ventilation runs. Wrong settings over a longer time can affect indoor
  air quality and humidity (risk of condensation and mould). Check the result.
- Using unofficial software may affect warranty or support claims against the manufacturer.
- The manufacturer can change firmware or cloud services at any time, which may break this
  integration without notice.

To the extent permitted by law, the authors are not liable for any damage to devices, buildings,
health or data, or for any other loss arising from the use of this software.

### Haftungsausschluss (Deutsch)

Dies ist ein unabhängiges, inoffizielles Projekt, das ohne jede Gewährleistung bereitgestellt
wird („wie besehen“, siehe [Lizenz](LICENSE)). Es entstand durch Beobachtung und Analyse der
Gerätekommunikation zum Zweck der Interoperabilität und wurde nur an einer einzigen Anlage
getestet. Die Nutzung erfolgt **auf eigene Gefahr**. Befehle verändern den Betrieb der Lüftung;
falsche Einstellungen über längere Zeit können Raumluft und Feuchte beeinträchtigen
(Kondensat- und Schimmelgefahr). Die Verwendung inoffizieller Software kann Gewährleistungs- oder
Supportansprüche gegenüber dem Hersteller berühren. Soweit gesetzlich zulässig, haften die
Autoren nicht für Schäden an Geräten, Gebäuden, Gesundheit oder Daten oder sonstige Schäden, die
aus der Nutzung entstehen; die gesetzliche Haftung für Vorsatz und grobe Fahrlässigkeit sowie für
Schäden aus der Verletzung von Leben, Körper oder Gesundheit bleibt unberührt.
