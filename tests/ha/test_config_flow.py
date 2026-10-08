# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Config flow: user, DHCP discovery, re-authentication and reconfigure."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
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
