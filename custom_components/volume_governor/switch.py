"""Switch platform for Volume Governor - ad-hoc on/off toggle."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
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
    """Set up Volume Governor switch entities."""
    coordinator: VolumeGovernorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for dev_conf in entry.data.get(CONF_DEVICES, []):
        entities.append(
            VolumeGovernorSwitch(
                coordinator,
                dev_conf[CONF_DEVICE_ENTITY_ID],
                dev_conf[CONF_DEVICE_NAME],
                entry.entry_id,
            )
        )

    async_add_entities(entities)


class VolumeGovernorSwitch(SwitchEntity):
    """Switch to activate/deactivate ad-hoc volume cap."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:volume-off"

    def __init__(
        self,
        coordinator: VolumeGovernorCoordinator,
        entity_id: str,
        device_name: str,
        entry_id: str,
    ) -> None:
        """Initialize."""
        self._coordinator = coordinator
        self._governed_entity_id = entity_id
        self._device_name = device_name

        # Unique ID based on the governed entity
        slug = entity_id.replace(".", "_")
        self._attr_unique_id = f"volume_governor_{slug}_adhoc"
        self._attr_name = f"Volume Governor {device_name}"
        self.entity_id = f"switch.volume_governor_{slug}"

    @property
    def is_on(self) -> bool:
        """Return true if ad-hoc cap is active."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        return device.adhoc_active if device else False

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:volume-off" if self.is_on else "mdi:volume-high"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        if not device:
            return {}
        return {
            "governed_entity": self._governed_entity_id,
            "adhoc_cap": int(device.adhoc_cap * 100),
            "lift_time": device.adhoc_lift_time.strftime("%H:%M"),
            "effective_cap": (
                int(device.effective_cap * 100)
                if device.effective_cap is not None
                else None
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Activate ad-hoc cap."""
        self._coordinator.set_adhoc(self._governed_entity_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Deactivate ad-hoc cap."""
        self._coordinator.set_adhoc(self._governed_entity_id, False)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
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
        """React to governor events (e.g., auto-lift)."""
        if event.data.get("entity_id") == self._governed_entity_id:
            self.async_write_ha_state()
