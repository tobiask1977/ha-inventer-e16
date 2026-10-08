"""inVENTer Easy Connect e16 - local control over Wi-Fi (TLS-PSK)."""
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr

from . import coordinator
from .const import CONF_DEVICE_ID, DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.FAN, Platform.BUTTON,
             Platform.NUMBER, Platform.SELECT, Platform.UPDATE]


async def async_setup_entry(hass, entry):
    data = coordinator.create(hass, entry)
    await data.zone.async_config_entry_first_refresh()
    await data.info.async_config_entry_first_refresh()
    # Create the main device first: fans and sensors reference it via via_device_id
    data.main_device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_DEVICE_ID])},
        name=entry.title, manufacturer="inVENTer", model="Easy Connect e16",
    ).id
    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
