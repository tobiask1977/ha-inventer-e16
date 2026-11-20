# Firmware and external sensor research

Research record dated **15 November 2026**, based on Android app **7.0.1**, its Hermes bundle,
the integration and four firmware downloads. The initial analysis was offline; later checks
used owner-authorized TCP and BLE reads, as described below. No device writes were performed.
Packet layouts are
in [protocol.md](protocol.md); this record preserves artifact identities, source locations,
conclusions and unresolved questions. All descriptions are written for this project; app code,
firmware binaries, personal device data and temporary download URLs are not included.

## Evidence and limits

The owner reports a spare, Bluetooth-only e16 with board marking **PCB 479446 – Iss.A**.
This is an owner-reported board marking, not a processor identification. No matching public
board documentation was found in the targeted search. Chip markings, test-point assignments
and the relationship to the WLAN hardware remain unestablished.

| Finding | Evidence | Limit |
|---|---|---|
| Separate firmware for WLAN, controller, fans and sensors | Manufacturer catalog and downloaded container headers | Does not establish the physical processor interconnect |
| WLAN firmware targets the ESP32 family | Catalog name `Esp32IvConnect`, app type 6 | Exact chip, module, flash size and revision unknown |
| 256-byte file prefix, 64-byte transfer header, CRC coverage | Files, app serializer and Hermes constructor | No firmware upload tested |
| Temperature getter uses packet 84, DataRequest, Object/Float | Real `IvConnectDevice` path | No measurement-write handler established |
| Virtual input configuration is an Econiq feature in this app | Concrete class and BMS screen gate | Not an e16 feature merely because its names exist in shared enums |
| Shared PropertySync container and virtual property IDs exist | Shared serializers and enums | e16 acceptance, encoding and control use unknown |
| Original sensor emulation needs more than a read-reply format | Destination/backtracking layout; missing peripheral implementation | RF framing, pairing and acceptance rules unresolved |

The Hermes bundle uses bytecode version 98. The available decompiler warns that this version
is not formally fully supported and omits some constructors. Product identities and critical
header constants were checked against the bundle's function headers/literal buffers as well;
firmware lengths and CRCs were checked against the files. App-derived means a client behavior
was reconstructed, not that a controller accepted a newly constructed request. File-checked
means consistency of a downloaded container, not execution on hardware.

## Inspected firmware files

Catalog and files were retrieved on the research date. Sizes are bytes; the payload excludes
the 256-byte file prefix. All four encrypted-payload and header CRCs matched their container
and catalog fields. The plaintext was not recovered, so its CRC remains unchecked.

| Component | Hardware type | Version | File size | Encrypted payload | Declared plaintext | Payload CRC |
|---|---:|---|---:|---:|---:|---|
| WLAN | 6 | 1.3.11 | 859408 | 859152 | 859152 | `6c3f48c8` |
| Controller | 1 | 5.30.11 | 229120 | 228864 | 228860 | `2fa606cb` |
| Fans | 2 | 5.30.10 | 213248 | 212992 | 212984 | `46db29db` |
| Sensors | 3 | 5.30.8 | 153968 | 153712 | 153712 | `c47a91b0` |

SHA-256 identifies the downloaded containers without redistributing them:

| Component | SHA-256 |
|---|---|
| WLAN | `1e981a738c2282d041152c6392c95aff1db7d9ecc345ce61cae3f86ecf96e8a5` |
| Controller | `516a2362f873ab942838c9a9c7b1aae9f3f18ac552f0c87e10b404b8d66a30b6` |
| Fans | `d2f00893ff42b068de6ae84d980e9efc152559a7896aa69fb39bf36ce1782f69` |
| Sensors | `0a3fa0edd60f5c698217fe1402df9c24022d3f483224cf862ad9e8cdbf893e31` |

Encrypted lengths equal plaintext lengths rounded up to 16 bytes in these files. That is
consistent with block alignment, but does not establish the padding contents or AES key size.
CRCs identify corruption; a matching CRC is not a cryptographic authenticity check.

## ESP32 binary followup

The ESP32 container was scanned at every `0xE9` byte for a complete Espressif image: 24-byte
header, segment count, segment headers/lengths, image-relative footer alignment, segment XOR
checksum and optional SHA-256. Address filters did not assume Xtensa, to avoid excluding
RISC-V variants. The scanner was checked with synthetic valid, damaged and embedded images.

Of 3357 `0xE9` candidates, 3167 had invalid segment counts, 147 had segment lengths not
divisible by four, and 43 had lengths extending beyond the file. None produced a complete
segment chain. Therefore none yielded a defensible chip ID, flash size or SDK version.
No plaintext app descriptor magic (`0xABCD5432`), plausible partition table, ELF/archive
signature or searched ESP-IDF/ESP32/FreeRTOS/Zirconia string was found in the payload.
The other three firmware containers also yielded no complete ESP image or conventional
STM32 vector table. These are negative findings about readable structures, not evidence
against either processor family. See the
[official Espressif image format](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/firmware-image-format.html).

Payload entropy (7.99903–7.99977 bits/byte) and absence of repeated aligned 16-byte blocks
are supporting statistics, not encryption proofs. With CBC, different IVs/chaining prevent
using different ciphertext blocks as evidence for different encryption keys. The app's
AES-CBC transfer mode and the container fields provide the stronger context.

A bounded search of 32 firmware/WLAN/TLS-related app modules found no fixed 16/24/32-byte
array or key-length hex string. Broader syntactic matches were module lists and labels;
16 byte interpretations derived from those literals were tried locally against the ESP32
ciphertext, with no valid image header. No candidate values were retained or published.
This neither supplies a key nor excludes obscured/native key representations. It is not
a reason to treat arbitrary data as executable code. Program-level reverse engineering
still requires plaintext or another independently analyzable firmware artifact.

A further bounded offline check tried 281 simple candidate interpretations: repeated bytes,
counting sequences, a public AES test key, brand/protocol words with repetition or padding,
MD5/SHA-256 derivations and byte order variants. The container IV was used with AES-CBC.
None produced even a plausible ESP header in the first 4096 decrypted bytes. No candidate
reached full-image/declared-plaintext-CRC validation. This rules out only the tried patterns
under that format assumption; it does not prove a random, unique or otherwise strong key.
No device was contacted and no key material was published.

## Read only controller observations

The owner authorized all reads while retaining the prohibition on writes. TCP requests were
guarded to permit only `DataRequest` (2), and BLE used standard readable device-information
characteristics with no pairing request, PIN write, GATT write or notification subscription.
Addresses, device identifiers, personal keys and arbitrary strings were kept out of the record.

| Read | Observation |
|---|---|
| Firmware images, target 159 | Running index 255, WLAN 1.3.11, CRC `6c3f48c8` |
| Firmware images, target 0 | Indices 0/255: controller 5.30.11, CRC `2fa606cb`; index 2: fans 5.30.10, CRC `46db29db` |
| Global field 65535 | Controller version 5.30.11 |
| Global field 65534 | Ten-byte reply, no searched ESP32/STM32/ESP-IDF/Xtensa marker |
| BLE hardware revision `0x2A27` | `02.00` |
| BLE model number `0x2A24` | Numeric product code `50`; not an Espressif chip ID |
| BLE software revision `0x2A28` | `1.03.11` |
| BLE firmware revision `0x2A26` | `5.30.11` |

The firmware-image CRCs connect the downloaded artifacts to the running/staged image
metadata. They do not decrypt an image or prove a raw flash readback path. The BLE hardware
string is a product-reported revision, not an ESP32 silicon identification.

Exploratory `DataRequest` messages for enum types 29/30/31 (device information/input/output
services), an empty PropertySync list (type 49), and external temperature (84) produced no
matching reply within three seconds at either target 0 or 159. Except for the temperature
getter, these were not reconstructed app request/response exchanges. Silence can mean an
unsupported or malformed query or another timing/transport constraint; it does not establish
absence of a firmware handler. No `Update` variant was tried.

## ESP32 to controller hypothesis

The hypothesis that the ESP32 can supply measurements to the regulator remains plausible.
Existing local commands already reach master address 0 through the WLAN bridge. In the app,
`writePacketToDevice` passes the packet to the connection, whose TCP implementation serializes
it directly to the socket. No app-side packet-type allowlist or sensor source credential is
inserted in that path. This says nothing about filtering or source metadata inside the bridge.

The shared property catalog provides another lead: `ZirconiaSensorTemp1` through `Temp32`
have IDs 507–538. A separate enum names `Temperature = 10`, but no concrete app exchange
establishes the association, numeric representation, e16 support or writability. The ESP32
CloudSync configuration (type 15, target 159) contains configuration fields, not a discovered
temperature input. The app's `fshSensorOverride` references belong to MEV behavior.

Three architectures remain consistent with the evidence:

1. An existing master measurement handler is reachable through ordinary forwarded packets.
   A new HA protocol client could then suffice without changing ESP32 firmware.
2. A measurement handler exists only for an internal source/port the ESP32 could use.
   An ESP32 extension might provide the missing source role or internal framing.
3. The master requires paired peripheral input or lacks such a handler. An ESP32 endpoint
   alone would then be insufficient without additional sensor emulation or master changes.

The missing evidence is the bridge/master dispatch code or an internal bus trace: physical
interconnect, frame format, source/port attribution, filtering and the path from a received
sensor value to the actual control input. Absence of an app setter does not decide between
these architectures. Neither the BIN scan nor read-only revision queries reveal that code.

## External measurement inputs

The concrete product factory connects Easy Connect e16 to `IvConnectDeviceManager`, which
creates `IvConnectDevice`, derived from `ZirconiaDevice`. It selects a TCP or BLE connection
and reads V5 zone views. The demo `DummyIvConnectDevice` is a separate path; its constant
temperature is not a controller input function.

The real temperature methods read values. The known field setters change configuration:
comfort temperatures, thresholds, device assignment, polarity and similar settings. No setter
for an external temperature measurement was found. This bounds what can be derived from the
app; it does not prove the absence of every unused handler in the closed firmware.

The BMS screen explicitly requires `EconiqDevice`. Its virtual-input configuration includes a
name, zone and type. The app did not reveal a value-writing topic or serializer in that path.
The shared PropertyID names for virtual values are therefore an investigation lead, not an
implemented e16 API. MQTT configuration indices 1–10 and PropertyID names numbered 0–9 must
not be treated as a proven mapping between interfaces.

For a future direct-input implementation, the unresolved behavior includes units/encoding,
indoor versus outdoor assignment, sensor-presence flags, freshness/expiry, priority over real
sensors and use by the actual control algorithm. An acknowledgement or a changed status value
alone would not demonstrate control use. A simulator cannot establish a proprietary firmware
handler by implementing the behavior we hope it has.

## Sensor transport

The app's temperature-read reply has a float container; it does not reveal the original
sensor's on-air report. Return-path source metadata does not demonstrate a way to impersonate
a paired sensor over TCP. Shared enum names for pairing (1–4), forwarding (23/24), address
changes (32–34), promiscuous mode (35) and pairing-table storage (47) were found, but no
complete peripheral pairing exchange was reconstructed from them.

RF modulation, data rate, synchronization, air framing, source identity, pairing, possible
keys/counters, acknowledgement and offline semantics remain unknown. The firmware's
AES-CBC mode and local TLS-PSK do not establish the radio cipher or radio key. RS485 removes
RF modulation questions but not protocol, addressing or acceptance questions; its presence
does not imply a Modbus register map.

The app also has a CO₂ calibration command (type 116); a calibration reference is not a
continuous measurement override. Sampling intervals and reporting thresholds likewise do
not supply replacement measurements.

## Development paths

| Approach | What is available | What remains |
|---|---|---|
| Control in HA using external sensors | Existing temporary mode/speed commands | Define control rules, validity limits, manual ownership and fallback |
| Direct virtual sensor input | Shared PropertySync and names | Establish a real e16 handler and its semantics |
| Emulate an original sensor | Read formats and some transport metadata | Reconstruct peripheral transport and pairing |
| Extend manufacturer firmware | Original encrypted images and transfer description | Obtain analyzable code, hardware details and an accepted installation/recovery path |

A new input on the ESP32 would still need a way to deliver its value to the regulator's
measurement path. Separate images do not prove whether an existing internal command can do
that. Neither the exact internal interconnect nor such a command has been reconstructed.
Knowing how to transfer an original encrypted image does not establish the ability to modify
it. Image decryption, boot-time signature validation and flash read protection are separate
questions; their state on the e16 remains unknown.

The available HA alternative sends decisions, not sensor values:

```text
Original sensor -> e16 measurements -> e16 control -> fans
HA sensor -> proposed HA control -> temporary mode/speed command -> e16
```

`inventer_e16.set_mode` already supports explicit 15–480 minute commands. A proposed HA
controller could renew a 15-minute command only while its inputs are valid; if renewals stop,
the timed command expires and the existing profile resumes. The fallback profile must suit
the installed sensors. Normal `fan.turn_off` uses an indefinite pause, so it is not equivalent
to a timed fallback strategy. Manual changes, global pause/boost and multiple zones also need
an ownership policy. This research did not install an automation.

Temperature alone may serve a cooling rule; moisture control needs matching indoor/outdoor
temperature and humidity. For example, the integration's Magnus function gives dew points
of 12.0 °C for indoor air at 20 °C/60% RH, 1.5 °C for outdoor air at 15 °C/40% RH, and 13.4 °C
at 15 °C/90% RH. Equal outdoor temperatures can therefore imply opposite moisture outcomes.
The integration's own drying-indicator thresholds are not established manufacturer thresholds.

## Source index

Artifact identities for the locally retained Android app 7.0.1:

| Artifact | SHA-256 |
|---|---|
| `base.apk` | `c7e476584a77eefb5b2cd9c359acaa2786a2a26d472e0f3dafe5d2204adc2375` |
| `assets/index.android.bundle` | `1f600c57588ea027589160ae56a6231551ee265cbce1273a73ba07dc0e640aca` |
| Local decompiler output `inventer-7.0.1-decompiled.js` | `2ab858abf83a49f4c41326ee2e877b52c93f578fce4643e59871778a6b70ab87` |

The line references below identify that exact decompiler output, which is not distributed in
this repository. Module/function identifiers and method names help locate equivalent code
in a separately obtained copy. They are analysis references, not e16 protocol numbers.

| Subject | App source locations |
|---|---|
| Product factory | Module 3481, lines 1393317–1393329 and 1393581–1393595 |
| e16 manager creates real device | Module 3314, lines 1268555–1268595 and 1268679–1268692; constructor #22393 |
| Real e16 class and transport | Module 3126, lines 1161383–1161537; constructor #21490; base module 2811/#19140 |
| Temperature getters | Lines 1162223–1162403 and 1163977–1164150 |
| V5 zone view | Lines 1165064–1165078 |
| Zone and device field enums | Lines 1005499–1005544 |
| Global settings enum and serializer | Lines 1155634–1155763 and 1155911–1156057 |
| Real Econiq virtual configuration | Module 2769/#18351, lines 866392–866529 |
| Econiq screen gate | Module 3712, lines 1524221–1524267 |
| Virtual configuration schema | Lines 1026543–1026580; configuration export lines 1152218–1152321 |
| Shared virtual property IDs and types | Lines 1020601–1020720 and 1023126–1023133 |
| PropertySync serializer and specific setter | Lines 1002596–1002663 and 1012894–1013120 |
| Sensor response wrapper and float object | Lines 999075–999133, 999751–999897 and 1000065–1000106; constructors #18907/#18913 |
| Backtracking parser | Lines 998338–998387 and 998605–998643 |
| Pairing and sensor packet names | Lines 997163–997180, 997254–997352 and 997490–997629 |
| Firmware endpoint and parameters | Lines 807247–807260 and 710578–710645 |
| Firmware file read and buffer retrieval | Lines 806454–806545 and 712388–712412 |
| Hardware IDs and preferred banks | Lines 804186–804344 |
| Firmware CRC function | Lines 1008180–1008306 |
| Transfer status and state enum | Lines 1006304–1006505 and 1010541–1011062 |
| Transfer header fields | Lines 1019819–1019960; constructor #19260 and literal buffer: 48 persistent + 16 variable bytes |
| Upload and resume | Lines 1010727–1010855 and 1011149–1011901 |
| Data chunk encoding | Lines 1012029–1012224 and 1019716–1019739 |
| Apply and destination selection | Lines 1012277–1012380 and 1857518–1857656 |
| App packet forwarding and TCP serialization | Lines 1009490–1009499 and 996502–996548 |
| Sensor temperature property names | Lines 1022193–1022320; Temperature type constant/assignment 1020205 and 1023072–1023074 |
| ESP32 CloudSync configuration | Lines 1009870–1009884, 1009995–1010035 and 998678–998782 |
| BLE revision getters | Lines 1015887–1015894, 1016037–1016044 and 1167417–1167425 |

Relevant repository implementation: `client.py` (packets and field IDs), `fan.py` (`set_mode`),
`coordinator.py` (pause/resume and zone behavior), `number.py` (comfort values and duration),
`humidity.py` (dew point and the integration's drying thresholds).

Manufacturer and chip-vendor background, distinct from device verification:

- [inVENTer WLAN hardware information](https://inventer.de/dokumente/technische%20infos/2025-09-16%20Kundeninformation%20inVENTer%20Mobile%20App.pdf): ESP32-based WLAN-capable e16 generation.
- [inVENTer wiring instructions](https://www.inventer.de/dl/15159/17199202685454/5040-0032_BD_Easy-Connect-e16_DE.pdf): RF868 and RS485 alternatives.
- [inVENTer planning handbook](https://www.inventer.de/dl/14736/1623662241603/inVENTer-Planungshandbuch.pdf): indoor/outdoor temperature and humidity in dew-point-based cellar ventilation; not the complete control algorithm.
- [Espressif Secure Boot](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/security/secure-boot-v2.html) and [flash encryption](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/security/flash-encryption.html): distinct mechanisms; these references do not establish their activation on the e16.
