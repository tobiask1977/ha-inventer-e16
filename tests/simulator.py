# SPDX-License-Identifier: MIT
"""A simulated e16 controller for client tests - no Home Assistant needed.

`FakeController` answers the Zirconia packets described in docs/protocol.md byte by byte and keeps
its state across connections: a test can send a command with one client call and read the result
with the next. It is written from the protocol description and the captures in
tests/test_acknowledgements.py, not from client.py, so a mistake in the client is not repeated
here. Packets the client sends are checked strictly; anything unexpected fails the test.

Time is simulated. The clock only moves in `advance()`, which tests also install as `time.sleep`;
a reply that is late or missing moves it while the client waits.

Behaviour seen on real controllers:
- `playback_lag`: after cancel and global pause, playback (offset 18) shows the previous value
  for a while; speed (17) and the record (74) fit at once (#1, captures in #4)
- a time-limited command runs out with the clock; the record at 74 stays (#2)
- after a UserOverride the controller sends its zone status (`ack_delay`, None = not at all)

Faults to test error handling with:
- `apply_commands=False`: a command is stored (74) but not applied
- `store_programs=False`: time program writes are ignored
- `silent`, `missing_fields`, `drop_replies()`, `send_before_reply()`, `mutate_next_reply()`,
  `close_after()`, `refuse_connections`: missing, incomplete, extra, altered and cut-off replies

Not modelled: time program evaluation (the zone runs `schedule` while no command is active),
automatic profiles, sensors that come and go. Writes to the installer fields (32-36) and to the
default profile (37/38) are accepted here; whether a real controller accepts them is not verified.
"""
import contextlib
import math
import struct

# Packet types, operation bits and destinations
WIFI_STATUS, TIME_PROGRAM, FIRMWARE_STATUS, USER_OVERRIDE = 13, 48, 54, 56
GLOBAL_FIELD, DEVICE_HEADER, DEVICE_ROW, ZONE_FIELD, ZONE_VIEW = 136, 141, 142, 144, 146
UPDATE, DATA_REQUEST = 1, 2
CONTROLLER, WIFI_MODULE = 0, 159
DESTINATION = {WIFI_STATUS: WIFI_MODULE, FIRMWARE_STATUS: WIFI_MODULE}
WRITABLE_TYPES = {USER_OVERRIDE, GLOBAL_FIELD, ZONE_FIELD, TIME_PROGRAM}
DOA_MAGIC, DOA_RAW, DOA_RAW_WITH_ID = 0x0ABA, 0, 7

# Zone status: playback (18), mode (24, status table) and flags (23)
PLAY, PAUSE, BOOST, SHUT_OFF, SHUT_DOWN, OVERRIDE = range(6)
STATUS_OFF, STATUS_VENTILATION, STATUS_HEAT_RECOVERY = 0, 1, 2
TIMER_ACTIVE, FAN_UNIT, GLOBAL_COMMAND, HAS_DEVICES = 1, 8, 16, 32

# UserOverride record: commands and the fan modes of the command table
GLOBAL_BOOST, GLOBAL_PAUSE, ZONE_SPEED_MODE, CANCEL = 1, 2, 5, 7
HEAT_RECOVERY, VENTILATION, PAUSE_CLOSED, PAUSE_OPEN = 1, 2, 3, 4
COMMAND_TO_STATUS = {HEAT_RECOVERY: STATUS_HEAT_RECOVERY, VENTILATION: STATUS_VENTILATION,
                     PAUSE_CLOSED: STATUS_OFF, PAUSE_OPEN: STATUS_OFF}
ALL_ZONES, FOREVER = 255, 0xFFFFFFFF
CANCEL_RECORD = bytes.fromhex("070003ff00000000")

# GlobalDataField ids
FILTER_INTERVAL, SERVICE_INTERVAL, FILTER_LEFT, SERVICE_LEFT = 0, 1, 16384, 16385
FAN_LEVEL_1, REVERSAL_INTERVAL, DEFAULT_MODE, DEFAULT_SPEED = 32, 36, 37, 38
# reset id -> (magic value, field reset, interval it is reset to)
RESETS = {32768: (0x46768482, FILTER_LEFT, FILTER_INTERVAL),
          32769: (0x83698286, SERVICE_LEFT, SERVICE_INTERVAL)}
READ_ONLY_FIELDS = {FILTER_LEFT, SERVICE_LEFT}

PROGRAM_TABLES, PROGRAM_ENTRIES, WHOLE_STORE = 15, 32, 0xFFFF
SOCKET_TIMEOUT = 10.0  # what the client passes to socket.create_connection
CHUNK = 3  # bytes per recv(), so the client has to reassemble packets
MISSING = b"\xff\xff\xff\xff"  # device rows: no reading


def crc8(data):
    """CRC-8 of the protocol: shift first, then test bit 7 (polynomial 7)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc << 1) & 255
            if crc & 128:
                crc ^= 7
    return crc


def reply_packet(ptype, payload):
    """A reply laid out like the captures: byte 4 is 0 and the timestamp is zeroed (anonymised).
    Byte 5 is 0x90-0x92 in the captures and its meaning is unknown; the client ignores it, the
    simulator repeats the type."""
    body = bytes([10 + len(payload), 0, ptype, 0, ptype]) + bytes(4) + payload
    return bytes([crc8(body)]) + body


def with_payload(packet, payload):
    """The same packet with another payload, length and CRC recalculated."""
    body = bytes([10 + len(payload)]) + packet[2:10] + payload
    return bytes([crc8(body)]) + body


def raw_with_id(field_id, value=b""):
    return struct.pack("<HBBI", DOA_MAGIC, DOA_RAW_WITH_ID, 4 + len(value), field_id) + value


def _f32(value):
    return MISSING if value is None else struct.pack("<f", value)


def device_row(address, device_type, hardware, name, firmware, zone=1, status=2, signal=126,
               temperature=None, humidity=None, runtime=0, battery=None, polarity=1):
    """DeviceViewRow as the two recorded rows in tests/test_client.py are laid out: a fan unit
    carries its polarity at 41, T/RH and battery sensors their battery level."""
    row = struct.pack("<BBBBIbI", address, device_type, hardware, zone, status, signal, firmware)
    row += name.encode().ljust(16, b"\0") + _f32(temperature) + _f32(humidity)
    row += struct.pack("<I", runtime)
    if device_type in (4, 5, 12):
        row += _f32(battery) + b"\xff" * 9
    else:
        row += bytes([polarity]) + b"\xff" * 14
    return row + bytes.fromhex("00007fff")


class _Connection:
    """One TLS connection: what the client sends is handled at once, replies are queued with the
    simulated time at which they arrive."""

    def __init__(self, controller, limit):
        self.controller = controller
        self.inbox = bytearray()
        self.outbox = []  # [arrival, sequence, bytearray]
        self.limit = limit  # bytes left before the controller closes the connection
        self.open = True

    def sendall(self, data):
        assert self.open, "client wrote to a closed connection"
        self.inbox.extend(data)
        while len(self.inbox) >= 2 and len(self.inbox) >= self.inbox[1]:
            length = self.inbox[1]
            packet = bytes(self.inbox[:length])
            del self.inbox[:length]
            self.controller._receive(self, packet)

    def queue(self, packet, delay=0.0):
        self.controller._sequence += 1
        arrival = self.controller.now + delay
        self.outbox.append([arrival, self.controller._sequence, bytearray(packet)])
        self.outbox.sort(key=lambda item: item[:2])

    def recv(self, count):
        controller = self.controller
        if self.limit is not None and self.limit <= 0:
            return b""
        while not self.outbox or self.outbox[0][0] > controller.now:
            wait = self.outbox[0][0] - controller.now if self.outbox else math.inf
            if wait > SOCKET_TIMEOUT:
                controller.advance(SOCKET_TIMEOUT)
                raise TimeoutError("timed out")
            controller.advance(wait)
        data = self.outbox[0][2]
        size = min(count, CHUNK, len(data))
        if self.limit is not None:
            size = min(size, self.limit)
            self.limit -= size
        chunk = bytes(data[:size])
        del data[:size]
        if not data:
            self.outbox.pop(0)
        return chunk


class FakeController:
    """One controller with zone 1, four fans and no sensors, as in the captures.

    Install `connect` as the client's `_connect` and `advance` as `time.sleep`; the attributes
    (speed, profile, fields, programs, devices, ...) can be set directly to prepare a test.
    """

    def __init__(self, playback_lag=0.0, ack_delay=0.0, apply_commands=True, store_programs=True):
        self.playback_lag = playback_lag
        self.ack_delay = ack_delay
        self.apply_commands = apply_commands
        self.store_programs = store_programs
        self.now = 0.0
        self.refuse_connections = False
        self.silent = set()  # packet types that are never answered
        self.missing_fields = set()  # GlobalDataField ids answered without a value
        self.connections = 0
        self.requests = []  # (type, operation, payload) of every packet received
        self.replies = []  # every reply packet sent, after mutation
        self.ignored_writes = []  # (type, field id or entry, value) the controller did not take

        # Zone 1 as in the captures: default profile, four fans, no sensors
        self.zone_id, self.zone_name = 1, "Zone 1"
        self.schedule = (1, STATUS_HEAT_RECOVERY)  # speed and mode while no command is active
        self.speed, self.mode = self.schedule
        self.profile = 0
        self.comfort = [20.0, 16.0, 70.0, 1500.0, 3.0]
        self.sensors = [-math.inf] * 6  # outdoor T/RH, indoor T/RH, CO2, VOC
        self.system_status = 0
        self.record = CANCEL_RECORD
        self.global_command = False
        self.ends = None  # simulated time at which the running command ends
        self._playback, self._lag = PLAY, None

        self.fields = {FILTER_INTERVAL: b"\x06", SERVICE_INTERVAL: b"\x06",
                       FILTER_LEFT: struct.pack("<f", 6.0), SERVICE_LEFT: struct.pack("<f", 6.0),
                       FAN_LEVEL_1: b"\x19", FAN_LEVEL_1 + 1: b"\x23", FAN_LEVEL_1 + 2: b"\x32",
                       FAN_LEVEL_1 + 3: b"\x64", REVERSAL_INTERVAL: struct.pack("<H", 70),
                       DEFAULT_MODE: b"\x01", DEFAULT_SPEED: b"\x01"}
        self.programs = {}  # (table, entry) -> 8-byte record; missing = empty
        self.devices = [device_row(0, 1, 1, "Controller", 5030010, polarity=0)] + [
            device_row(n, 2, 2, f"Fan {n}", 5030009) for n in range(1, 5)]
        self.wifi_rssi = -60
        self.firmware_images = [(255, 1, 1003011, 0x12345678)]  # index, valid, version, crc

        self._sequence = 0
        self._drop = 0
        self._before_reply = []
        self._mutate = None
        self._limit = None

    # -- clock and faults ------------------------------------------------------------------------
    def advance(self, seconds):
        self.now += seconds
        if self.ends is not None and self.now >= self.ends:
            # A time-limited command ran out: back to the schedule, the record stays (#2)
            self.ends = None
            self.speed, self.mode = self.schedule
            self.global_command = False
            self._playback, self._lag = PLAY, None

    def drop_replies(self, count=1):
        """The next `count` requests get no reply."""
        self._drop += count

    def send_before_reply(self, *packets):
        """Packets that arrive before the next reply, e.g. a late answer to an earlier request."""
        self._before_reply.extend(packets)

    def mutate_next_reply(self, function, skip=0):
        """The next reply after `skip` others is passed through `function` (bytes -> bytes)."""
        self._mutate = [skip, function]

    def close_after(self, size):
        """The next connection is closed by the controller after `size` bytes."""
        self._limit = size

    @contextlib.contextmanager
    def connect(self):
        """Use in place of E16Client._connect."""
        self.connections += 1
        if self.refuse_connections:
            raise ConnectionRefusedError("e16 refused the connection")
        connection = _Connection(self, self._limit)
        self._limit = None
        try:
            yield connection
        finally:
            connection.open = False

    # -- state -----------------------------------------------------------------------------------
    @property
    def playback(self):
        if self._lag and self.now < self._lag[0]:
            return self._lag[1]
        return self._playback

    def _set_playback(self, value, while_lagging=None):
        shown = self.playback if while_lagging is None else while_lagging
        self._playback = value
        lagging = self.playback_lag and shown != value
        self._lag = (self.now + self.playback_lag, shown) if lagging else None

    @property
    def timer(self):
        return 0 if self.ends is None else max(0, math.ceil(self.ends - self.now - 1e-6))

    def zone_row(self):
        """ZoneViewRow V5 of zone 1 - 85 bytes like the captured replies."""
        flags = FAN_UNIT | HAS_DEVICES | (TIMER_ACTIVE if self.timer else 0)
        flags |= GLOBAL_COMMAND if self.global_command else 0
        row = bytes([self.zone_id]) + self.zone_name.encode().ljust(16, b"\0")
        row += struct.pack("<BBIBBB", self.speed, self.playback, self.timer, flags, self.mode,
                           self.profile)
        row += struct.pack("<5f", *self.comfort) + struct.pack("<6f", *self.sensors)
        return row + struct.pack("<I", self.system_status) + self.record + bytes(3)

    def command(self, record):
        """Apply an 8-byte UserOverride record, as if it came from the client or the app."""
        command, speed, mode, zone, duration = struct.unpack("<BBBBI", record)
        self.record = bytes(record)
        if not self.apply_commands:
            return
        timed = duration not in (0, FOREVER)
        if command == CANCEL:
            self.ends, self.global_command = None, False
            self.speed, self.mode = self.schedule
            self._set_playback(PLAY)
        elif command == GLOBAL_PAUSE:
            self.ends, self.global_command = (self.now + duration if timed else None), True
            self.speed, self.mode = 0, STATUS_OFF
            self._set_playback(SHUT_DOWN, while_lagging=PAUSE)
        elif command == GLOBAL_BOOST:  # from protocol.md, not captured
            self.ends, self.global_command = (self.now + duration if timed else None), True
            self.speed, self.mode = speed, COMMAND_TO_STATUS.get(mode, STATUS_OFF)
            self._set_playback(BOOST)
        elif command == ZONE_SPEED_MODE and zone in (self.zone_id, ALL_ZONES):
            self.ends, self.global_command = (self.now + duration if timed else None), False
            self.speed, self.mode = speed, COMMAND_TO_STATUS.get(mode, STATUS_OFF)
            self._playback, self._lag = OVERRIDE, None  # an override shows at once (captures)
        # Other commands (zone boost/pause/profile, fans off) are defined but not modelled

    # -- packets ---------------------------------------------------------------------------------
    def _receive(self, connection, packet):
        assert crc8(packet[1:]) == packet[0], "client sent a packet with a wrong CRC"
        length, backtracking, ptype, operation, destination = packet[1:6]
        assert backtracking == 0, "client sent backtracking entries"
        assert operation in (UPDATE, DATA_REQUEST), f"unexpected operation {operation}"
        assert destination == DESTINATION.get(ptype, CONTROLLER), f"type {ptype} to {destination}"
        payload = packet[10:length]
        self.requests.append((ptype, operation, payload))
        if operation == UPDATE:
            assert ptype in WRITABLE_TYPES, f"client sent an update of type {ptype}"
            self._update(connection, ptype, payload)
            return
        reply = self._answer(ptype, payload)
        if reply is None or ptype in self.silent:
            return
        if self._drop:
            self._drop -= 1
            return
        for extra in self._before_reply:
            connection.queue(extra)
        self._before_reply = []
        packet = reply_packet(ptype, reply)
        if self._mutate and self._mutate[0]:
            self._mutate[0] -= 1
        elif self._mutate:
            packet, self._mutate = self._mutate[1](packet), None
        self.replies.append(packet)
        connection.queue(packet)

    def _answer(self, ptype, payload):
        if ptype == ZONE_VIEW:
            assert len(payload) == 1, "zone status request is one index byte"
            return self.zone_row() if payload[0] == 0 else None
        if ptype in (GLOBAL_FIELD, ZONE_FIELD):
            field_id = self._unwrap(payload, read=True)[0]
            value = self._read_field(ptype, field_id)
            return raw_with_id(field_id, value)
        if ptype == TIME_PROGRAM:
            table, entry, _ = self._program(payload, size=5)
            body = struct.pack("<HH", table, entry) + self.programs.get((table, entry), bytes(8))
            return body + bytes([crc8(body)])
        if ptype == WIFI_STATUS:
            return struct.pack("<IbBB", 0, self.wifi_rssi, 1, 7)
        if ptype == FIRMWARE_STATUS:
            return b"".join(struct.pack("<BBII", *image) for image in self.firmware_images)
        if ptype == DEVICE_HEADER:
            return struct.pack("<BH", len(self.devices), 5)
        if ptype == DEVICE_ROW:
            assert len(payload) == 1, "device row request is one index byte"
            return self.devices[payload[0]] if payload[0] < len(self.devices) else None
        raise AssertionError(f"client requested unknown packet type {ptype}")

    def _update(self, connection, ptype, payload):
        if ptype == USER_OVERRIDE:
            magic, kind, size = struct.unpack_from("<HBB", payload)
            assert (magic, kind, size, len(payload)) == (DOA_MAGIC, DOA_RAW, 8, 12), "bad UserOverride"
            self.command(payload[4:12])
            if self.ack_delay is not None:
                connection.queue(reply_packet(ZONE_VIEW, self.zone_row()), self.ack_delay)
        elif ptype == TIME_PROGRAM:
            table, entry, record = self._program(payload, size=13)
            if self.store_programs:
                self.programs[(table, entry)] = record
            else:
                self.ignored_writes.append((ptype, (table, entry), record))
        else:
            field_id, value = self._unwrap(payload, read=False)
            if not self._write_field(ptype, field_id, value):
                self.ignored_writes.append((ptype, field_id, value))

    @staticmethod
    def _unwrap(payload, read):
        magic, kind, size, field_id = struct.unpack_from("<HBBI", payload)
        assert (magic, kind) == (DOA_MAGIC, DOA_RAW_WITH_ID), "bad field wrapper"
        assert size == len(payload) - 4 and (size == 4) == read, "bad field length"
        return field_id, payload[8:]

    @staticmethod
    def _program(payload, size):
        assert len(payload) == size, f"time program payload of {len(payload)} bytes"
        assert crc8(payload[:-1]) == payload[-1], "time program payload with a wrong CRC"
        table, entry = struct.unpack_from("<HH", payload)
        # Table and entry 65535 address the whole store; an update with them resets every program
        assert WHOLE_STORE not in (table, entry), "time program store addressed as a whole"
        assert table < PROGRAM_TABLES and entry < PROGRAM_ENTRIES, "no such time program entry"
        return table, entry, payload[4:-1]

    def _read_field(self, ptype, field_id):
        if ptype == GLOBAL_FIELD:
            return b"" if field_id in self.missing_fields else self.fields.get(field_id, b"")
        zone, field = divmod(field_id, 65536)
        if zone != self.zone_id:
            return b""
        if field == 0:
            return self.zone_name.encode().ljust(16, b"\0")
        if field == 1:
            return bytes([self.profile])
        return struct.pack("<f", self.comfort[field - 2]) if 2 <= field <= 6 else b""

    def _write_field(self, ptype, field_id, value):
        if ptype == GLOBAL_FIELD:
            if field_id in RESETS:
                magic, left, interval = RESETS[field_id]
                if value != struct.pack("<I", magic):
                    return False
                self.fields[left] = struct.pack("<f", float(self.fields[interval][0]))
                return True
            current = self.fields.get(field_id)
            if field_id in READ_ONLY_FIELDS or current is None or len(value) != len(current):
                return False
            self.fields[field_id] = value
            return True
        zone, field = divmod(field_id, 65536)
        if zone != self.zone_id:
            return False
        if field == 1 and len(value) == 1:
            self.profile = value[0]
        elif 2 <= field <= 6 and len(value) == 4:
            self.comfort[field - 2] = struct.unpack("<f", value)[0]
        else:
            return False
        return True
