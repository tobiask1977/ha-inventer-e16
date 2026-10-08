"""Duration for speed and mode commands (app: 15 min to 8 h in 15 min steps)."""
from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime

from .entity import E16Entity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([E16Duration(entry.runtime_data.zone, entry, "override_minutes")])


class E16Duration(E16Entity, RestoreNumber):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 15
    _attr_native_max_value = 480
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value:
            self.coordinator.override_minutes = int(last.native_value)

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return self.coordinator.override_minutes

    async def async_set_native_value(self, value):
        self.coordinator.override_minutes = int(value)
        self.async_write_ha_state()
