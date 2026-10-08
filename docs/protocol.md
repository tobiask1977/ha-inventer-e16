# Zirconia protocol of the inVENTer Easy Connect e16

What this integration knows about the local protocol of the Easy Connect e16 controller, and how
sure we are. "Verified" means checked against a real controller (firmware: Wi-Fi module 1.3.11,
controller 5.30.10, fans 5.30.9, sensors 5.30.8). Everything else is derived from analysing how
the official app talks to the device and is marked as such.

## How this was obtained

Observing the controller's replies on the local network and on Bluetooth LE, plus analysing the
official Android app for the sole purpose of interoperability with Home Assistant. No code,
images or other assets of the manufacturer are part of this repository; this document describes
data formats in our own words.

## Transport

| | |
|---|---|
| Wi-Fi | TCP **47820**, TLS 1.2 with pre-shared key, cipher `PSK-AES128-CBC-SHA` (0x008C) |
| PSK identity | `zirconia` (fixed) |
| PSK | 8 bytes, **individual per device**; readable over BLE in pairing mode (see below) |
| Port 8883 | MQTT over the same TLS-PSK. Accepts subscriptions but publishes nothing for the e16 (verified); the app uses MQTT only for other product families |
| BLE | Same packets, split into 20-byte frames (see end of document) |

One request, one reply; the controller answers on the same connection. A new TLS connection per
poll works fine. Keep only one connection open at a time.

## Packet

| Offset | Size | Content |
|---:|---:|---|
| 0 | 1 | CRC-8 over bytes 1..length-1 |
| 1 | 1 | Packet length including header (max. 128) |
| 2 | 1 | Number of backtracking entries (0 for direct TCP) |
| 3 | 1 | Packet type |
| 4 | 1 | Operation bits: 1 Update, 2 DataRequest, 4 AcknowledgementRequest, 32 Acknowledge, 64 Response, 128 Encrypted |
| 5 | 1 | Final destination: 0 controller ("master"), 159 Wi-Fi module (ESP32) |
| 6 | 4 | Unix timestamp; the app sends big endian, the controller replies little endian; apparently not evaluated |
| 10 | n | Payload |

**CRC-8** (verified): start 0; for every byte `crc ^= byte`, then 8 times `crc = (crc << 1) & 0xFF;
if crc & 0x80: crc ^= 0x07`. This differs from the textbook CRC-8 (which tests the bit *before*
shifting): `"123456789"` gives `0xAF`, not `0xF4`.

Requests use operation `DataRequest`; replies come back with bit 64 set. Writes use `Update`;
the app does not wait for a reply and simply reads the state again (verified: the next request
on the same connection returns the new state).

## DataObjectArray wrapper

Several payloads are wrapped:

| Offset | Size | Content |
|---:|---:|---|
| 0 | 2 | Magic `0x0ABA`, little endian (`BA 0A`) |
| 2 | 1 | Type: 0 Raw, 7 RawWithId (others exist) |
| 3 | 1 | Length of what follows (Raw: record length; RawWithId: 4 + value length) |
| 4 | … | Raw: the record. RawWithId: field id `UInt32LE`, then the value |

## Packet types used by the integration

| Type | Name | Dest. | Request payload | Reply / purpose | Status |
|---:|---|---:|---|---|---|
| 13 | WifiStatus | 159 | – | IP `u32`, RSSI `i8` @4, client count @5, flags @6 (bit0 connected, bit1 IP, bit2 listening) | verified |
| 54 | FirmwareUpdateStatus | 159 | – | list of 10-byte image records (below) | verified |
| 56 | UserOverride | 0 | wrapper(Raw) + 8-byte record | time-limited command (below) | verified |
| 136 | GlobalDataField | 0 | wrapper(RawWithId, id) | system settings (below) | verified (read, filter reset) |
| 141 | DeviceViewHeader | 0 | – | row count `u8`, version `u16` | verified |
| 142 | DeviceViewRow | 0 | row index `u8` | one radio device (below) | verified |
| 144 | ZoneRowField | 0 | wrapper(RawWithId, zone_id × 65536 + field) | zone settings (below) | verified (read) |
| 146 | ZoneViewRow | 0 | zone index `u8` (0 = first zone) | zone status (below) | verified |

Other types exist (time programs 48, firmware transfer 52–55, reboot 10, Wi-Fi config 12, …) and
are deliberately not used.

### 146 ZoneViewRow (V5)

| Offset | Type | Content |
|---:|---|---|
| 0 | u8 | Zone id (1-based) |
| 1 | 16 bytes UTF-8 | Zone name |
| 17 | u8 | Fan speed 0–4 |
| 18 | u8 | Playback: 0 play, 1 pause, 2 boost, 3 shut off, 4 shut down, 5 override |
| 19 | u32 | Remaining timer in seconds |
| 23 | u8 | Flags: bit0 timer active, bit1 CO₂ sensor, bit2 external sensor, bit3 fan unit, bit4 global command, bit5 has devices |
| 24 | u8 | Ventilation mode: **0 off, 1 ventilation, 2 heat recovery** |
| 25 | u8 | Ventilation profile (table below) |
| 26 | 5 × f32 | Comfort room temperature, comfort outdoor temperature, RH threshold, CO₂ threshold, VOC threshold |
| 46 | f32 | Outdoor temperature |
| 50 | f32 | Outdoor humidity |
| 54 | f32 | Indoor temperature |
| 58 | f32 | Indoor humidity |
| 62 | f32 | CO₂ |
| 66 | f32 | VOC |
| 70 | u32 | System status: 2 time not set, 4 device lost, 8 firmware update failed, 16 battery critical, 32 alarm, 64 filter timeout, 128 service timeout, 256 notifications |
| 74 | 8 bytes | Last UserOverride record received |

Missing sensors report `-inf` or NaN.

### Ventilation profiles

| Value | Profile | Note |
|---:|---|---|
| 0 | Default | |
| 1–5 | Bedroom, children's room, bathroom, living room, kitchen | |
| 6 | Holiday | |
| 7–15 | Custom profile 1–9 | user-defined in the app |
| 251 | Winter | |
| 252 | Summer | automatic, needs outdoor sensor |
| 253 | Cellar heat recovery | automatic, switches between ventilation and heat recovery by itself (observed) |
| 254 | Cellar with ventilation | automatic |
| 255 | Not set | |

### 56 UserOverride

Record (8 bytes, inside a Raw wrapper → payload `BA 0A 00 08` + record):

| Offset | Type | Content |
|---:|---|---|
| 0 | u8 | Command |
| 1 | u8 | Fan speed |
| 2 | u8 | Fan mode – **different table than the zone status!** |
| 3 | u8 | Zone id, 255 = all |
| 4 | u32 | Duration in seconds, `0xFFFFFFFF` = unlimited |

| Command | Value | As used by the app |
|---|---:|---|
| Global boost | 1 | speed 4, mode 2, zone 255, 900 s |
| Global pause | 2 | power button "off": duration `0xFFFFFFFF` |
| Zone speed/mode | 5 | speed 1–4, mode 1/2, one zone, 900–28 800 s |
| Cancel | 7 | power button "on": back to the profile |
| (zone boost 3, zone pause 4, zone profile 6, fans off 8/9) | | defined, not used by the app |

| Fan mode in the command | Value |
|---|---:|
| Heat recovery | **1** |
| Ventilation | **2** |
| Pause, flap closed | 3 |
| Pause, flap open | 4 |

Verified: zone 1, speed 2, mode 2, 900 s → status speed 2, playback 5, timer counting down,
mode reported as 1 (= ventilation in the status table). Cancel restored the profile.

Note: Cancel also makes an automatic profile re-evaluate immediately, so the state after
"cancel" can differ from the state before the command.

### 136 GlobalDataField

| Id | Content | Encoding |
|---:|---|---|
| 0 | Filter interval | u8 months, 255 = disabled (app offers 1–6) |
| 1 | Service interval | u8 months, 255 = disabled (app offers 3/6/9/12) |
| 16384 | Filter time left | f32 months |
| 16385 | Service time left | f32 months |
| 32768 | Reset filter timer | write u32 `0x46768482` |
| 32769 | Reset service timer | write u32 `0x83698286` |
| 32–35 | Fan power of speed level 1–4 | u8 %, read: 25 / 35 / 50 / 100 (installer setting) |
| 36 | Reversal interval of the push-pull fans | u16 seconds, read: 70 |
| 37 / 38 | Default profile mode / speed | u8, read: 1 / 1 |

Verified: reading all, and resetting the filter timer (5.98 → 6.0 months, nothing else changed).
The remaining time is updated rarely (unchanged over 20 minutes).

### 144 ZoneRowField

Field id = zone id × 65536 + field. Fields: 0 name (16 bytes), 1 profile (u8), 2 comfort room
temperature, 3 comfort outdoor temperature, 4 RH threshold, 5 CO₂ threshold, 6 VOC threshold
(each f32). Verified by reading: zone 1 field 0 returns the zone name, field 1 the profile. Verified by writing: field 1 (profile 253 → 0 → 253) and field 2 (comfort room temperature 20.0 → 20.5 → 20.0 °C); the zone status reflects the new value immediately, other fields stay unchanged.

### 142 DeviceViewRow (V5)

| Offset | Type | Content |
|---:|---|---|
| 0 | u8 | Address |
| 1 | u8 | Device type: 1 controller, 2/3 fan unit, 4 indoor T/RH sensor, 5 outdoor T/RH sensor, 6 CO₂ sensor, 8 alarm interface, 12 battery sensor, 21 Wi-Fi module, … |
| 2 | u8 | Hardware type (1 controller, 2 fan, 3 sensor) |
| 3 | u8 | Zone id |
| 4 | u32 | Status bits: 1 offline, 2 online, 4 config pending, 8/16/32 firmware update in progress/ready/failed, 64 battery low, 128 battery critical, 1024 device lost, 2048 alarm, 8192 service due soon, 16384 filter due soon, 32768 service expired, 65536 filter expired, 131072 time not set |
| 8 | i8 | Direct radio level in dBm (126 seen = no reading) |
| 9 | u32 | Firmware version |
| 13 | 16 bytes | Name |
| 29 | f32 | Temperature |
| 33 | f32 | Humidity |
| 37 | u32 | Total runtime, seconds (inferred from a controller replaced half a day earlier: 43 200) |
| 41 | type-dependent | fan units: polarity u8; T/RH and battery sensors: battery level f32 (percent inferred, values 62–64 seen); alarm interface: alarm u8 |
| 54 | u8 / u8 / i8 | Repeater flag, repeater address, repeated signal |

**Version numbers** are shown as 8 digits split 2.3.3: `5030010` → 5.30.10.

### 54 FirmwareUpdateStatus (images)

Records of 10 bytes: index `u8`, valid `u8` (1 valid), version `u32`, CRC `u32`. Index 255 is the
running image.

## Firmware catalog

The app asks a Firebase function which firmware is current:

```
POST https://europe-west3-volution-group-apps.cloudfunctions.net/getBrandHardwareTypes
{"data": {"brand": "inventer"}}
```

The reply lists `hardwareType` (6 Wi-Fi module, 1 controller, 2 fans, 3 sensors), `version` and
checksums. It needs no authentication. The checksum of the running ESP32 image matched the
catalog entry. Installing firmware (packets 52–55, encrypted images) is left to the official app.

## Bluetooth LE onboarding

| Service / characteristic | UUID |
|---|---|
| Authentication service | `e6834e4b-7b3a-48e6-91e4-f1d005f564d3` |
| Device id | `673de933-963b-4298-bfc1-b0ccdada690a` |
| TLS identity (discovery id, not the PSK identity) | `98faf8a5-1ee6-4b0c-911e-dc37bff5206f` |
| TLS key (the PSK) | `638ff62c-3823-4e0f-8179-1695c46ee8ad` |
| PIN (`u32` LE) | `4cad343a-209a-40b7-b911-4d9b3df569b2` |
| PIN confirmation | `d1ae6b70-ee12-4f6d-b166-d2063dcaffe1` |
| Protocol service | `e6ec2fd8-e888-4eb2-9680-e78ed6ea89e1` |
| Fragment characteristic | `e6ec2fd8-e888-4eb2-9681-e78ed6ea89e1` |

In pairing mode (LED blinking blue) identity and key are readable. **Read them before writing
the PIN** – after the PIN is confirmed the controller returns zeros (verified).

BLE frames are 20 bytes: `(sequence << 4) | count`, CRC-8 over the 17 padded payload bytes,
acknowledge byte, 17 payload bytes. Sequence numbers start at **1**. Replies are read from the
fragment characteristic; every received fragment is acknowledged with a frame `00 00 <seq>` plus
zeros. The integration itself does not use BLE.
