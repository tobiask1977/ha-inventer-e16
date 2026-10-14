# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Constants for the inVENTer Easy Connect e16 integration."""

DOMAIN = "inventer_e16"

CONF_DEVICE_ID = "device_id"
CONF_PSK = "psk"
CONF_FIRMWARE_CATALOG = "firmware_catalog"
CONF_SCAN_INTERVAL = "scan_interval"
# Zone polling in seconds; each poll is a new TLS session on the controller
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL = 15, 3600

# Firebase function the official app uses to decide whether a firmware update is available.
# It answers without authentication; can be switched off in the integration options.
CATALOG_URL = "https://europe-west3-volution-group-apps.cloudfunctions.net/getBrandHardwareTypes"
CATALOG_BRAND = "inventer"
