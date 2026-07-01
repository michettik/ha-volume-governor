"""Switch platform for Volume Governor - tap to engage/disengage."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES, CONF_DEVICE_ENTITY_ID, CONF_DEVICE_NAME, device_info_for
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
        entity_id = dev_conf[CONF_DEVICE_ENTITY_ID]
        name = dev_conf[CONF_DEVICE_NAME]
        # Main engage/disengage switch
        entities.append(
            VolumeGovernorEngageSwitch(coordinator, entity_id, name, entry.entry_id)
        )
        # Persistent mode toggle
        entities.append(
            VolumeGovernorPersistentSwitch(coordinator, entity_id, name, entry.entry_id)
        )

    async_add_entities(entities)


class VolumeGovernorEngageSwitch(SwitchEntity):
    """Switch to engage/disengage volume governance on a device.
    
    This is the main control — tap to enforce the volume cap immediately,
    tap again to release it. Works regardless of schedule.
    """

    _attr_has_entity_name = True

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

        slug = entity_id.replace(".", "_")
        self._attr_unique_id = f"volume_governor_{slug}_engage"
        self._attr_name = "Enforce"
        self.entity_id = f"switch.volume_governor_{slug}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entity_id)},
            name=f"Governor: {device_name}",
            manufacturer="Volume Governor",
            model="Governed Audio Device",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """Return true if governor is engaged."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        return device.engaged if device else False

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
        attrs = {
            "governed_entity": self._governed_entity_id,
            "cap_percent": int(device.cap * 100),
            "persistent": device.persistent,
            "schedule_active": self._coordinator.is_schedule_active(),
        }
        if device.lift_at:
            attrs["lift_at"] = device.lift_at.isoformat()
        return attrs

    async def async_turn_on(self, **kwargs) -> None:
        """Engage the governor — enforce volume cap immediately."""
        self._coordinator.engage(self._governed_entity_id)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disengage the governor — remove volume cap."""
        self._coordinator.disengage(self._governed_entity_id)
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


class VolumeGovernorPersistentSwitch(SwitchEntity):
    """Switch to toggle persistent mode for a governed device.
    
    When persistent is ON, the enforcement never auto-lifts.
    When OFF, enforcement lifts at the configured schedule_end time.
    """

    _attr_has_entity_name = True

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

        slug = entity_id.replace(".", "_")
        self._attr_unique_id = f"volume_governor_{slug}_persistent"
        self._attr_name = "Persistent"
        self.entity_id = f"switch.volume_governor_{slug}_persistent"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entity_id)},
            name=f"Governor: {device_name}",
            manufacturer="Volume Governor",
            model="Governed Audio Device",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """Return true if persistent mode is on."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        return device.persistent if device else False

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:lock" if self.is_on else "mdi:lock-open-variant"

    async def async_turn_on(self, **kwargs) -> None:
        """Enable persistent mode."""
        self._coordinator.set_persistent(self._governed_entity_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable persistent mode."""
        self._coordinator.set_persistent(self._governed_entity_id, False)
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
