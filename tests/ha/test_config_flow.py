# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Config flow: user, DHCP discovery, re-authentication and reconfigure."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.discovery_flow import DiscoveryKey
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.inventer_e16.client import E16AuthError
from custom_components.inventer_e16.const import DOMAIN

PSK = "0102030405060708"
DATA = {"host": "192.0.2.1", "device_id": "ABCDE-FGHIJ", "psk": PSK}
# Host name as Home Assistant hands it over: lower case
DHCP = DhcpServiceInfo(ip="192.0.2.10", hostname="easy connect e16-abcde-fghij", macaddress="6825dd000001")
CLIENT = "custom_components.inventer_e16.config_flow.E16Client"
SETUP = "custom_components.inventer_e16.async_setup_entry"
UNLOAD = "custom_components.inventer_e16.async_unload_entry"


def _client(mock, error=None):
    if error:
        mock.return_value.get_zone.side_effect = error
    else:
        mock.return_value.get_zone.return_value = {"name": "Zone 1"}
    return mock


async def test_user_flow(hass):
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, "psk": "01 02 03 04 05 06 07 08"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "inVENTer Zone 1"
    assert result["data"] == DATA


@pytest.mark.parametrize("typed", ["(0x) 01-02-03-04-05-06-07-08", "0x0102030405060708",
                                   "01:02:03:04:05:06:07:08", " 0102030405060708\n"])
async def test_user_flow_accepts_psk_as_ble_apps_show_it(hass, typed):
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, "psk": typed})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["psk"] == PSK


@pytest.mark.parametrize("typed", ["ABCDE-FGHIJ", " ABCDE-FGHIJ ", "4142 4344 452D 4647 4849 4A",
                                   "(0x) 41-42-43-44-45-2D-46-47-48-49-4A", "4142434445 2D4647484 94A00"])
async def test_user_flow_accepts_device_id_as_text_or_hex(hass, typed):
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, "device_id": typed})
    assert result["data"]["device_id"] == "ABCDE-FGHIJ"
    assert result["result"].unique_id == "ABCDE-FGHIJ"


async def test_dhcp_discovers_new_controller(hass):
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "dhcp_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"psk": PSK})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "192.0.2.10", "device_id": "ABCDE-FGHIJ", "psk": PSK}
    assert result["result"].unique_id == "ABCDE-FGHIJ"


async def test_dhcp_noname_host_name(hass):
    """Some controllers announce themselves as noName-<device id> (issue #3)."""
    other = DhcpServiceInfo(ip="192.0.2.12", hostname="noname-abcde-fghij", macaddress="5c013b000001")
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=other)
        assert result["step_id"] == "dhcp_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"psk": PSK})
    assert result["result"].unique_id == "ABCDE-FGHIJ"


async def test_dhcp_wrong_psk_shows_error(hass):
    with patch(CLIENT) as client:
        _client(client, E16AuthError())
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"psk": PSK})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "invalid_key"}


async def test_dhcp_known_controller_takes_new_ip(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA)
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data["host"] == "192.0.2.10"


async def test_dhcp_ignores_unexpected_host_name(hass):
    other = DhcpServiceInfo(ip="192.0.2.11", hostname="easyconnect", macaddress="6825dd000002")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=other)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "not_supported"


async def test_reauth_saves_new_psk(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA)
    entry.add_to_hass(hass)
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"psk": "a1b2c3d4e5f60718"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data["psk"] == "a1b2c3d4e5f60718"


async def test_reconfigure_keeps_psk_when_empty(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA)
    entry.add_to_hass(hass)
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "192.0.2.20"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data == {**DATA, "host": "192.0.2.20"}


async def test_recorded_discovery_key_does_not_reload(hass):
    """Home Assistant stores the DHCP discovery key on the entry - that alone must not reload it."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA, title="inVENTer Zone 1")
    entry.add_to_hass(hass)
    data = MagicMock()
    data.zone.async_config_entry_first_refresh = AsyncMock()
    data.info.async_config_entry_first_refresh = AsyncMock()
    with patch("custom_components.inventer_e16.coordinator.create", return_value=data) as create, \
            patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert entry.update_listeners == []
        key = DiscoveryKey(domain="dhcp", key="6825dd000001", version=1)
        same_ip = DhcpServiceInfo(ip=DATA["host"], hostname=DHCP.hostname, macaddress=DHCP.macaddress)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP, "discovery_key": key}, data=same_ip)
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.discovery_keys == {"dhcp": (key,)}
    assert create.call_count == 1


async def test_options_change_reloads_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA)
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True) as setup, patch(UNLOAD, return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"firmware_catalog": False})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"firmware_catalog": False, "scan_interval": 30}
    assert setup.call_count == 2


async def test_options_reject_too_short_polling_interval(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 5, "firmware_catalog": True})


async def test_new_entry_has_firmware_catalog_off(hass):
    with patch(CLIENT) as client, patch(SETUP, return_value=True):
        _client(client)
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    entry = result["result"]
    assert entry.minor_version == 2 and "firmware_catalog" not in entry.options
    result = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults["firmware_catalog"] is False


async def _migrate(hass, options):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="ABCDE-FGHIJ", data=DATA, options=options,
                            version=1, minor_version=1)
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


async def test_migration_keeps_firmware_catalog_on_for_old_entries(hass):
    entry = await _migrate(hass, {})
    assert entry.minor_version == 2 and entry.options == {"firmware_catalog": True}


async def test_migration_keeps_an_explicit_choice(hass):
    entry = await _migrate(hass, {"firmware_catalog": False, "scan_interval": 60})
    assert entry.options == {"firmware_catalog": False, "scan_interval": 60}
