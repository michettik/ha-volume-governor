"""Number platform for Volume Governor - adjustable cap levels."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES, CONF_DEVICE_ENTITY_ID, CONF_DEVICE_NAME
from .coordinator import VolumeGovernorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Volume Governor number entities."""
    coordinator: VolumeGovernorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for dev_conf in entry.data.get(CONF_DEVICES, []):
        entity_id = dev_conf[CONF_DEVICE_ENTITY_ID]
        name = dev_conf[CONF_DEVICE_NAME]
        # Ad-hoc cap slider
        entities.append(
            VolumeGovernorCapNumber(
                coordinator, entity_id, name, entry.entry_id, "adhoc"
            )
        )
        # Schedule cap slider
        entities.append(
            VolumeGovernorCapNumber(
                coordinator, entity_id, name, entry.entry_id, "schedule"
            )
        )

    async_add_entities(entities)


class VolumeGovernorCapNumber(NumberEntity):
    """Number entity to adjust volume cap level."""

    _attr_has_entity_name = True
    _attr_native_min_value = 5
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:volume-minus"

    def __init__(
        self,
        coordinator: VolumeGovernorCoordinator,
        entity_id: str,
        device_name: str,
        entry_id: str,
        cap_type: str,
    ) -> None:
        """Initialize."""
        self._coordinator = coordinator
        self._governed_entity_id = entity_id
        self._device_name = device_name
        self._cap_type = cap_type

        slug = entity_id.replace(".", "_")
        self._attr_unique_id = f"volume_governor_{slug}_{cap_type}_cap"
        self._attr_name = f"Volume Governor {device_name} ({cap_type} cap)"
        self.entity_id = f"number.volume_governor_{slug}_{cap_type}_cap"

    @property
    def native_value(self) -> float | None:
        """Return current cap value as percentage."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        if not device:
            return None
        if self._cap_type == "adhoc":
            return int(device.adhoc_cap * 100)
        return int(device.schedule_cap * 100)

    async def async_set_native_value(self, value: float) -> None:
        """Update the cap value."""
        cap = value / 100.0
        if self._cap_type == "adhoc":
            self._coordinator.set_adhoc_cap(self._governed_entity_id, cap)
        else:
            self._coordinator.set_schedule_cap(self._governed_entity_id, cap)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register for coordinator updates."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                "volume_governor_updated", self._on_governor_event
            )
        )

    @callback
    def _on_governor_event(self, event) -> None:
        """React to governor events."""
        if event.data.get("entity_id") == self._governed_entity_id:
            self.async_write_ha_state()
