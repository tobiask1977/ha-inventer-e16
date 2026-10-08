"""Constants for the inVENTer Easy Connect e16 integration."""

DOMAIN = "inventer_e16"

CONF_DEVICE_ID = "device_id"
CONF_PSK = "psk"
CONF_FIRMWARE_CATALOG = "firmware_catalog"

# Firebase function the official app uses to decide whether a firmware update is available.
# It answers without authentication; can be switched off in the integration options.
CATALOG_URL = "https://europe-west3-volution-group-apps.cloudfunctions.net/getBrandHardwareTypes"
CATALOG_BRAND = "inventer"
