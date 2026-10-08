# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Read device identity and PSK of an inVENTer Easy Connect e16 over Bluetooth LE.

The Home Assistant integration talks to the controller over Wi-Fi with TLS-PSK. The key is
individual per device and the official app never shows it, but the controller exposes it over
BLE while it is in pairing mode.

Usage (needs `pip install bleak`, a Bluetooth adapter and the controller within range):

    1. Put the controller into pairing mode: hold the mode button until the LED blinks blue.
    2. python e16_onboard.py scan              # list controllers in range
    3. python e16_onboard.py read [ADDRESS]    # print device ID and PSK

Important: identity and key must be read BEFORE the PIN is confirmed - afterwards the
controller returns zeros. `read` therefore never writes anything unless --confirm-pin is given.
The PSK grants control over your ventilation: do not post it in issues or logs.
"""
import argparse
import asyncio
import json
import os
import struct
import sys

from bleak import BleakClient, BleakScanner

SERVICE_AUTH = "e6834e4b-7b3a-48e6-91e4-f1d005f564d3"
SERVICE_PROTOCOL = "e6ec2fd8-e888-4eb2-9680-e78ed6ea89e1"
CHAR_DEVICE_ID = "673de933-963b-4298-bfc1-b0ccdada690a"
CHAR_TLS_IDENTITY = "98faf8a5-1ee6-4b0c-911e-dc37bff5206f"
CHAR_TLS_KEY = "638ff62c-3823-4e0f-8179-1695c46ee8ad"
CHAR_PIN = "4cad343a-209a-40b7-b911-4d9b3df569b2"
CHAR_PIN_CONFIRMED = "d1ae6b70-ee12-4f6d-b166-d2063dcaffe1"


async def scan(timeout):
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    controllers = []
    for address, (device, adv) in found.items():
        uuids = {u.lower() for u in adv.service_uuids}
        if uuids & {SERVICE_AUTH, SERVICE_PROTOCOL}:
            controllers.append((adv.rssi, address, adv.local_name or device.name or ""))
    return sorted(controllers, reverse=True)


async def read(address, confirm_pin):
    kwargs = {}
    if sys.platform == "win32":
        # Windows caches incomplete GATT tables; force a fresh discovery
        kwargs["winrt"] = {"use_cached_services": False}
    async with BleakClient(address, timeout=30, **kwargs) as client:
        device_id = bytes(await client.read_gatt_char(CHAR_DEVICE_ID))
        identity = bytes(await client.read_gatt_char(CHAR_TLS_IDENTITY))
        key = bytes(await client.read_gatt_char(CHAR_TLS_KEY))
        if not any(key):
            sys.exit("The controller returned an empty key. Restart pairing mode (LED blinking "
                     "blue) and run `read` again without confirming the PIN first.")
        result = {
            "device_id": device_id.split(b"\0")[0].decode("ascii", "replace"),
            "psk": key.hex(),
            "tls_identity_hex": identity.hex(),
        }
        if confirm_pin:
            pin = bytes(await client.read_gatt_char(CHAR_PIN))
            if len(pin) < 4 or not any(pin):
                sys.exit("No PIN offered - is the controller in pairing mode?")
            await client.write_gatt_char(CHAR_PIN, pin[:4], response=True)
            confirmed = bytes(await client.read_gatt_char(CHAR_PIN_CONFIRMED))
            result["pin_confirmed"] = confirmed == b"\x01"
            result["pin"] = struct.unpack("<I", pin[:4])[0]
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    scan_parser = sub.add_parser("scan", help="list controllers in range")
    scan_parser.add_argument("--timeout", type=float, default=15)
    read_parser = sub.add_parser("read", help="read device ID and PSK")
    read_parser.add_argument("address", nargs="?", help="BLE address; scans if omitted")
    read_parser.add_argument("--confirm-pin", action="store_true",
                             help="also confirm the PIN, as the app does at the end of pairing")
    read_parser.add_argument("--output", help="write the result as JSON to this file "
                                              "instead of printing the PSK")
    args = parser.parse_args()

    if args.command == "scan":
        controllers = asyncio.run(scan(args.timeout))
        for rssi, address, name in controllers:
            print(f"{address}  {rssi:4} dBm  {name}")
        if not controllers:
            print("No controller found. Is it in pairing mode (LED blinking blue)?")
        return

    address = args.address
    if not address:
        controllers = asyncio.run(scan(15))
        if len(controllers) != 1:
            sys.exit(f"{len(controllers)} controllers found - pass the address explicitly.")
        address = controllers[0][1]
    result = asyncio.run(read(address, args.confirm_pin))
    if args.output:
        # Readable for the owner only (no effect on Windows ACLs)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2)
        print(f"Device ID {result['device_id']}; key written to {args.output}")
    else:
        print(f"Device ID: {result['device_id']}")
        print(f"PSK:       {result['psk']}")
        print("Enter both in Home Assistant. Keep the PSK private.")


if __name__ == "__main__":
    main()
