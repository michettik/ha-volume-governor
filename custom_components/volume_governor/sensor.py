"""Sensor platform for Volume Governor - status display."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
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
    """Set up Volume Governor sensor entities."""
    coordinator: VolumeGovernorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for dev_conf in entry.data.get(CONF_DEVICES, []):
        entities.append(
            VolumeGovernorSensor(
                coordinator,
                dev_conf[CONF_DEVICE_ENTITY_ID],
                dev_conf[CONF_DEVICE_NAME],
                entry.entry_id,
            )
        )

    async_add_entities(entities)


class VolumeGovernorSensor(SensorEntity):
    """Sensor showing the current governor status for a device."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-lock"

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
        self._attr_unique_id = f"volume_governor_{slug}_status"
        self._attr_name = f"Volume Governor {device_name} Status"
        self.entity_id = f"sensor.volume_governor_{slug}_status"

    @property
    def native_value(self) -> str:
        """Return the current status."""
        return self._coordinator.get_status(self._governed_entity_id)

    @property
    def extra_state_attributes(self) -> dict:
        """Return detailed status attributes."""
        device = self._coordinator.devices.get(self._governed_entity_id)
        if not device:
            return {}
        return {
            "governed_entity": self._governed_entity_id,
            "adhoc_active": device.adhoc_active,
            "adhoc_cap_percent": int(device.adhoc_cap * 100),
            "adhoc_lift_time": device.adhoc_lift_time.strftime("%H:%M"),
            "schedule_enabled": device.schedule_enabled,
            "schedule_start": device.schedule_start.strftime("%H:%M"),
            "schedule_end": device.schedule_end.strftime("%H:%M"),
            "schedule_cap_percent": int(device.schedule_cap * 100),
            "effective_cap_percent": (
                int(device.effective_cap * 100)
                if device.effective_cap is not None
                else None
            ),
            "cap_floor_percent": int(device.cap_floor * 100),
        }

    async def async_added_to_hass(self) -> None:
        """Register for coordinator updates and state changes."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                "volume_governor_updated", self._on_governor_event
            )
        )
        # Also update periodically when schedule state might change
        self.async_on_remove(
            self.hass.helpers.event.async_track_time_interval(
                self._async_periodic_update,
                timedelta(minutes=1),
            )
        )

    @callback
    def _on_governor_event(self, event) -> None:
        """React to governor events."""
        if event.data.get("entity_id") == self._governed_entity_id:
            self.async_write_ha_state()

    @callback
    def _async_periodic_update(self, _now) -> None:
        """Periodic refresh for schedule-based state transitions."""
        self.async_write_ha_state()
