# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Local Zirconia client for the inVENTer Easy Connect e16 (TLS-PSK, TCP 47820).

Pure Python, no Home Assistant imports, so it can be tested on its own.
Requires Python >= 3.13 for ssl.SSLContext.set_psk_client_callback.
See docs/protocol.md for the packet layouts.
"""
from contextlib import contextmanager
import math
import socket
import ssl
import struct
import threading
import time

PORT = 47820
PSK_IDENTITY = "zirconia"
CIPHER = "PSK-AES128-CBC-SHA"

# Operation bits
UPDATE, DATA_REQUEST, RESPONSE = 1, 2, 64
# Final destinations
MASTER, ESP32 = 0, 159
# Packet types
T_WIFI_STATUS = 13
T_FIRMWARE_STATUS = 54
T_USER_OVERRIDE = 56
T_GLOBAL_FIELD = 136
T_DEVICE_HEADER = 141
T_DEVICE_ROW = 142
T_ZONE_FIELD = 144
T_ZONE_VIEW = 146

# DataObjectArray wrapper used by several payloads
DOA_MAGIC = 0x0ABA
DOA_RAW, DOA_RAW_WITH_ID = 0, 7

# UserOverride command types and the fan modes of THAT packet.
# Note: the zone status reports the mode with a DIFFERENT table (see READ_MODE_TO_FAN).
CMD_GLOBAL_BOOST, CMD_GLOBAL_PAUSE, CMD_ZONE_SPEED_MODE, CMD_CANCEL = 1, 2, 5, 7
FAN_HEAT_RECOVERY, FAN_VENTILATION, FAN_OFF, FAN_STOP = 1, 2, 3, 4
ZONE_GLOBAL = 255
FOREVER = 0xFFFFFFFF
# Zone status mode (0 off, 1 ventilation, 2 heat recovery) -> UserOverride fan mode
READ_MODE_TO_FAN = {1: FAN_VENTILATION, 2: FAN_HEAT_RECOVERY}

# GlobalDataField ids: intervals in months (255 = disabled), remaining time as float months,
# resets only with the magic value the app sends
F_FILTER_INTERVAL, F_SERVICE_INTERVAL = 0, 1
F_FILTER_LEFT, F_SERVICE_LEFT = 16384, 16385
F_FILTER_RESET, F_SERVICE_RESET = 32768, 32769
# Installer settings, read only here: fan power per speed level (u8 %) and reversal interval (u16 s)
F_FAN_SPEED_1, F_FAN_AUTO_DIRECTION = 32, 36
RESET_MAGIC = {F_FILTER_RESET: 0x46768482, F_SERVICE_RESET: 0x83698286}

# ZoneRowField ids: zone_id * 65536 + field; fields 2-6 are float32 LE
ZF_NAME, ZF_PROFILE = 0, 1
ZF_COMFORT_ROOM, ZF_COMFORT_OUTSIDE, ZF_RH_THRESHOLD, ZF_CO2_THRESHOLD, ZF_VOC_THRESHOLD = 2, 3, 4, 5, 6

# DeviceViewRow.deviceStatus bits
DEV_OFFLINE, DEV_ONLINE, DEV_LOST = 1, 2, 1024
DEV_BATTERY_LOW, DEV_BATTERY_CRITICAL, DEV_ALARM = 64, 128, 2048
DEV_SERVICE_DUE, DEV_FILTER_DUE, DEV_SERVICE_OVER, DEV_FILTER_OVER = 8192, 16384, 32768, 65536
# ZoneViewRowV5.systemStatusFlag bits
SYS_BATTERY_CRITICAL, SYS_ALARM, SYS_FILTER_TIMEOUT, SYS_SERVICE_TIMEOUT = 16, 32, 64, 128
# Device types whose row carries a battery level at offset 41 (T/RH sensors, battery SSU)
BATTERY_DEVICE_TYPES = {4, 5, 12}
# A controller has a handful of radio devices; cap what a (faulty) reply can make us query
MAX_DEVICES = 32
# Hardware types as used by the vendor firmware catalog; device rows use 1-3,
# the ESP32 Wi-Fi module comes from packet 54
HW_MZCU, HW_FCU, HW_SENSORS, HW_ESP32 = 1, 2, 3, 6


def crc8(data: bytes) -> int:
    """CRC-8 as the app computes it: shift first, then test bit 7 (not standard CRC-8)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc << 1) & 255
            if crc & 128:
                crc ^= 7
    return crc


def packet(ptype, payload=b"", operation=DATA_REQUEST, destination=MASTER):
    body = bytes([10 + len(payload), 0, ptype, operation, destination])
    body += struct.pack(">I", int(time.time())) + payload
    return bytes([crc8(body)]) + body


def override_payload(command, speed=0, mode=FAN_OFF, zone=ZONE_GLOBAL, duration=0):
    """DataObjectArray(Raw) around the 8 byte UserOverride record."""
    record = struct.pack("<BBBBI", command, speed, mode, zone, duration)
    return struct.pack("<HBB", DOA_MAGIC, DOA_RAW, len(record)) + record


def field_payload(field_id, raw=b""):
    """DataObjectArray(RawWithId) for GlobalDataField/ZoneRowField; empty raw = read."""
    return struct.pack("<HBBI", DOA_MAGIC, DOA_RAW_WITH_ID, 4 + len(raw), field_id) + raw


def receive_exact(connection, count):
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise ConnectionError("e16 closed the connection")
        data.extend(chunk)
    return bytes(data)


def read_packet(connection):
    header = receive_exact(connection, 2)
    length = header[1]
    if not 10 <= length <= 128:
        raise ValueError("Invalid Zirconia packet length")
    answer = header + receive_exact(connection, length - 2)
    if crc8(answer[1:]) != answer[0]:
        raise ValueError("Zirconia CRC mismatch")
    return answer


def version_text(number):
    """App format: 8 digits split 2.3.3, e.g. 5030010 -> 5.30.10."""
    digits = f"{number:08d}"
    return f"{int(digits[:2])}.{int(digits[2:5])}.{int(digits[5:])}"


def _finite(value):
    return round(value, 2) if math.isfinite(value) else None


def parse_override(data):
    command, speed, mode, zone, duration = struct.unpack("<BBBBI", data[:8])
    return {"command": command, "speed": speed, "mode": mode, "zone": zone, "duration": duration}


def parse_zone(data):
    """ZoneViewRowV5."""
    if len(data) < 74:
        raise ValueError("Zone status too short")
    values = {
        "zone_id": data[0],
        "name": data[1:17].split(b"\0")[0].decode("utf-8", "replace"),
        "speed": data[17],
        "playback": data[18],
        "timer": struct.unpack_from("<I", data, 19)[0],
        "flags": data[23],
        "mode": data[24],
        "profile": data[25],
        "status": struct.unpack_from("<I", data, 70)[0],
        "last_override": parse_override(data[74:82]) if len(data) >= 82 else None,
    }
    # Missing sensors report -inf/NaN and become None; offsets 26-45: the zone's comfort settings
    for name, offset in (("comfort_room_temperature", 26), ("comfort_outdoor_temperature", 30),
                         ("humidity_threshold", 34), ("co2_threshold", 38), ("voc_threshold", 42),
                         ("outside_temperature", 46), ("outside_humidity", 50),
                         ("inside_temperature", 54), ("inside_humidity", 58),
                         ("co2", 62), ("voc", 66)):
        values[name] = _finite(struct.unpack_from("<f", data, offset)[0])
    return values


def parse_firmware_images(data):
    """FirmwareImageInfo, 10 bytes each: index, valid, version, crc. Index 255 = running image."""
    images = {}
    for offset in range(0, len(data) - len(data) % 10, 10):
        index, valid, version, crc = struct.unpack_from("<BBII", data, offset)
        if valid == 1:
            images[index] = {"version": version, "crc": crc}
    return images


def parse_device(data):
    """DeviceViewRowV5: controller, fans and sensors on the radio bus."""
    if len(data) < 45:
        raise ValueError("Device row too short")
    address, device_type, hardware, zone, status, signal, firmware = struct.unpack_from(
        "<BBBBIbI", data)
    temperature, humidity, runtime, battery = struct.unpack_from("<ffIf", data, 29)
    return {
        "address": address, "type": device_type, "hardware": hardware, "zone": zone,
        "status": status, "signal": signal, "firmware": firmware,
        "name": data[13:29].split(b"\0")[0].decode("utf-8", "replace").strip(),
        "temperature": _finite(temperature), "humidity": _finite(humidity), "runtime": runtime,
        "battery": _finite(battery) if device_type in BATTERY_DEVICE_TYPES else None,
    }


@contextmanager
def _malformed_as_value_error():
    """Truncated or garbled replies must surface as ValueError, never as struct/index errors."""
    try:
        yield
    except (struct.error, IndexError) as error:
        raise ValueError(f"Malformed Zirconia reply: {error}") from error


class E16Client:
    def __init__(self, host, psk, port=PORT):
        self.host, self.port = host, port
        self.key = bytes.fromhex(psk)
        if len(self.key) != 8 or not any(self.key):
            raise ValueError("The e16 PSK must be 8 non-zero bytes (16 hex characters)")
        # Never poll and command at the same time: the controller is a small ESP32
        self._lock = threading.Lock()

    @contextmanager
    def _connect(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(CIPHER)
        context.set_psk_client_callback(lambda hint: (PSK_IDENTITY, self.key))
        with self._lock, socket.create_connection((self.host, self.port), timeout=10) as transport:
            with context.wrap_socket(transport, server_hostname=None) as connection:
                yield connection

    @staticmethod
    def _request(connection, ptype, payload=b"", destination=MASTER):
        connection.sendall(packet(ptype, payload, destination=destination))
        # Skip a possible reply to a previous command
        for _ in range(4):
            answer = read_packet(connection)
            if answer[3] == ptype:
                break
        else:
            raise ValueError("Unexpected Zirconia packet type")
        if answer[4] & 128:
            raise ValueError("Encrypted Zirconia reply")
        if answer[2]:
            raise ValueError("Backtracking replies are not supported")
        return answer[10:answer[1]]

    @classmethod
    def _field(cls, connection, ptype, field_id):
        answer = cls._request(connection, ptype, field_payload(field_id))
        if len(answer) < 9:
            raise ValueError(f"Short reply for field {field_id}")
        magic, kind, length, answer_id = struct.unpack_from("<HBBI", answer)
        if magic != DOA_MAGIC or kind != DOA_RAW_WITH_ID or answer_id != field_id or length < 4:
            raise ValueError(f"Unexpected reply for field {field_id}")
        return answer[8:4 + length]

    def _update(self, ptype, payload):
        """Send like the app does: no reply expected, state is read again afterwards."""
        with self._connect() as connection, _malformed_as_value_error():
            connection.sendall(packet(ptype, payload, operation=UPDATE))
            time.sleep(0.5)
            return parse_zone(self._request(connection, T_ZONE_VIEW, b"\x00"))

    def get_zone(self, index=0):
        with self._connect() as connection, _malformed_as_value_error():
            return parse_zone(self._request(connection, T_ZONE_VIEW, bytes([index])))

    def get_info(self):
        """Maintenance, firmware, Wi-Fi and radio devices - rarely changes."""
        with self._connect() as connection, _malformed_as_value_error():
            def months(field_id):
                return struct.unpack("<f", self._field(connection, T_GLOBAL_FIELD, field_id)[:4])[0]

            info = {
                "filter_interval": self._field(connection, T_GLOBAL_FIELD, F_FILTER_INTERVAL)[0],
                "service_interval": self._field(connection, T_GLOBAL_FIELD, F_SERVICE_INTERVAL)[0],
                "filter_months_left": months(F_FILTER_LEFT),
                "service_months_left": months(F_SERVICE_LEFT),
            }
            try:
                info["fan_speed_levels"] = [self._field(connection, T_GLOBAL_FIELD, F_FAN_SPEED_1 + n)[0]
                                            for n in range(4)]
                info["fan_reversal_interval"] = struct.unpack(
                    "<H", self._field(connection, T_GLOBAL_FIELD, F_FAN_AUTO_DIRECTION)[:2])[0]
            except ValueError:
                info["fan_speed_levels"], info["fan_reversal_interval"] = None, None
            wifi = self._request(connection, T_WIFI_STATUS, b"", ESP32)
            info["wifi_rssi"] = struct.unpack_from("<b", wifi, 4)[0]
            images = self._request(connection, T_FIRMWARE_STATUS, b"", ESP32)
            info["esp32_firmware"] = parse_firmware_images(images).get(255)
            count = min(self._request(connection, T_DEVICE_HEADER)[0], MAX_DEVICES)
            info["devices"] = [parse_device(self._request(connection, T_DEVICE_ROW, bytes([index])))
                               for index in range(count)]
        return info

    def user_override(self, command, speed=0, mode=FAN_OFF, zone=ZONE_GLOBAL, duration=0):
        return self._update(T_USER_OVERRIDE, override_payload(command, speed, mode, zone, duration))

    def set_global_field(self, field_id, raw):
        return self._update(T_GLOBAL_FIELD, field_payload(field_id, raw))

    def set_zone_field(self, zone_id, field, raw):
        return self._update(T_ZONE_FIELD, field_payload(zone_id * 65536 + field, raw))
