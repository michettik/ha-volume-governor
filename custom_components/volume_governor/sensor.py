"""Sensor platform for Volume Governor - status display."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from datetime import timedelta

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
        self._attr_name = f"Governor: {device_name} Status"
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
        attrs = {
            "governed_entity": self._governed_entity_id,
            "engaged": device.engaged,
            "persistent": device.persistent,
            "cap_percent": int(device.cap * 100),
            "schedule_days": self._coordinator.schedule_days,
            "schedule_start": self._coordinator.schedule_start.strftime("%H:%M"),
            "schedule_end": self._coordinator.schedule_end.strftime("%H:%M"),
            "schedule_active_now": self._coordinator.is_schedule_active(),
            "cap_floor_percent": int(self._coordinator.cap_floor * 100),
        }
        if device.lift_at:
            attrs["lift_at"] = device.lift_at.isoformat()
        return attrs

    async def async_added_to_hass(self) -> None:
        """Register for coordinator updates and periodic refresh."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                "volume_governor_updated", self._on_governor_event
            )
        )
        # Periodic refresh for schedule-based transitions
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
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
