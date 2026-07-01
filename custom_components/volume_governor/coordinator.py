"""Volume Governor coordinator - the enforcement engine."""
from __future__ import annotations

import logging
from datetime import time, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_PLAYING, STATE_IDLE, STATE_PAUSED
from homeassistant.core import HomeAssistant, Event, callback, CALLBACK_TYPE
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    DOMAIN as MP_DOMAIN,
    SERVICE_VOLUME_SET,
)

from .const import (
    CONF_DEVICES,
    CONF_DEVICE_ENTITY_ID,
    CONF_ADHOC_CAP,
    CONF_ADHOC_LIFT_TIME,
    CONF_SCHEDULE_ENABLED,
    CONF_SCHEDULE_START,
    CONF_SCHEDULE_END,
    CONF_SCHEDULE_CAP,
    CONF_CAP_FLOOR,
    DEFAULT_ADHOC_CAP,
    DEFAULT_ADHOC_LIFT_TIME,
    DEFAULT_SCHEDULE_CAP,
    DEFAULT_SCHEDULE_START,
    DEFAULT_SCHEDULE_END,
    DEFAULT_CAP_FLOOR,
)

_LOGGER = logging.getLogger(__name__)

ACTIVE_STATES = {STATE_ON, STATE_PLAYING, STATE_IDLE, STATE_PAUSED}


class GovernedDevice:
    """State and config for a single governed device."""

    def __init__(self, entity_id: str, config: dict[str, Any]) -> None:
        """Initialize."""
        self.entity_id = entity_id
        self.adhoc_active: bool = False
        self.adhoc_cap: float = config.get(CONF_ADHOC_CAP, DEFAULT_ADHOC_CAP)
        self.adhoc_lift_time: time = _parse_time(
            config.get(CONF_ADHOC_LIFT_TIME, DEFAULT_ADHOC_LIFT_TIME)
        )
        self.schedule_enabled: bool = config.get(CONF_SCHEDULE_ENABLED, False)
        self.schedule_start: time = _parse_time(
            config.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START)
        )
        self.schedule_end: time = _parse_time(
            config.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END)
        )
        self.schedule_cap: float = config.get(CONF_SCHEDULE_CAP, DEFAULT_SCHEDULE_CAP)
        self.cap_floor: float = config.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR)

    @property
    def effective_cap(self) -> float | None:
        """Return the lowest active cap, or None if no cap is active."""
        caps: list[float] = []
        if self.adhoc_active:
            caps.append(self.adhoc_cap)
        if self.schedule_enabled and _in_time_range(
            datetime.now().time(), self.schedule_start, self.schedule_end
        ):
            caps.append(self.schedule_cap)
        if not caps:
            return None
        return max(min(caps), self.cap_floor)


class VolumeGovernorCoordinator:
    """Coordinates enforcement across all governed devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.devices: dict[str, GovernedDevice] = {}
        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_lift_listeners: list[CALLBACK_TYPE] = []
        self._enforcing: set[str] = set()  # prevent re-entrancy

    async def async_setup(self) -> None:
        """Set up the coordinator: register listeners."""
        devices_config = self.entry.data.get(CONF_DEVICES, [])
        for dev_conf in devices_config:
            entity_id = dev_conf[CONF_DEVICE_ENTITY_ID]
            self.devices[entity_id] = GovernedDevice(entity_id, dev_conf)

        # Listen for state changes on all governed entities
        entity_ids = list(self.devices.keys())
        if entity_ids:
            self._unsub_state = async_track_state_change_event(
                self.hass, entity_ids, self._async_on_state_change
            )

        # Set up ad-hoc lift timers for each device
        for device in self.devices.values():
            unsub = async_track_time_change(
                self.hass,
                self._make_lift_callback(device.entity_id),
                hour=device.adhoc_lift_time.hour,
                minute=device.adhoc_lift_time.minute,
                second=0,
            )
            self._unsub_lift_listeners.append(unsub)

    async def async_teardown(self) -> None:
        """Tear down listeners."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        for unsub in self._unsub_lift_listeners:
            unsub()
        self._unsub_lift_listeners.clear()

    @callback
    def _make_lift_callback(self, entity_id: str):
        """Create a time-based callback to lift ad-hoc cap for a specific device."""

        @callback
        def _lift_adhoc(_now: datetime) -> None:
            device = self.devices.get(entity_id)
            if device and device.adhoc_active:
                device.adhoc_active = False
                _LOGGER.info(
                    "Volume Governor: ad-hoc cap lifted for %s at scheduled time",
                    entity_id,
                )
                # Fire event so entities update
                self.hass.bus.async_fire(
                    "volume_governor_updated", {"entity_id": entity_id}
                )

        return _lift_adhoc

    @callback
    def _async_on_state_change(self, event: Event) -> None:
        """React to volume changes on governed devices."""
        entity_id = event.data.get("entity_id")
        if not entity_id or entity_id in self._enforcing:
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state not in ACTIVE_STATES:
            return

        device = self.devices.get(entity_id)
        if not device:
            return

        cap = device.effective_cap
        if cap is None:
            return

        current_volume = new_state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
        if current_volume is None:
            return

        if current_volume > cap:
            _LOGGER.info(
                "Volume Governor: %s at %.3f exceeds cap %.3f, enforcing",
                entity_id,
                current_volume,
                cap,
            )
            self._enforcing.add(entity_id)
            self.hass.async_create_task(self._async_enforce(entity_id, cap))

    async def _async_enforce(self, entity_id: str, cap: float) -> None:
        """Set volume back to cap."""
        try:
            await self.hass.services.async_call(
                MP_DOMAIN,
                SERVICE_VOLUME_SET,
                {
                    "entity_id": entity_id,
                    ATTR_MEDIA_VOLUME_LEVEL: cap,
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception("Volume Governor: failed to enforce cap on %s", entity_id)
        finally:
            self._enforcing.discard(entity_id)

    def set_adhoc(self, entity_id: str, active: bool) -> None:
        """Activate or deactivate ad-hoc mode for a device."""
        device = self.devices.get(entity_id)
        if device:
            device.adhoc_active = active
            _LOGGER.info(
                "Volume Governor: ad-hoc %s for %s",
                "activated" if active else "deactivated",
                entity_id,
            )
            # Immediately enforce if turning on
            if active:
                state = self.hass.states.get(entity_id)
                if state and state.state in ACTIVE_STATES:
                    current = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
                    cap = device.effective_cap
                    if current is not None and cap is not None and current > cap:
                        self.hass.async_create_task(
                            self._async_enforce(entity_id, cap)
                        )

    def set_adhoc_cap(self, entity_id: str, cap: float) -> None:
        """Update the ad-hoc cap value for a device."""
        device = self.devices.get(entity_id)
        if device:
            device.adhoc_cap = max(cap, device.cap_floor)

    def set_schedule_cap(self, entity_id: str, cap: float) -> None:
        """Update the schedule cap value for a device."""
        device = self.devices.get(entity_id)
        if device:
            device.schedule_cap = max(cap, device.cap_floor)

    def get_status(self, entity_id: str) -> str:
        """Get human-readable status for a device."""
        device = self.devices.get(entity_id)
        if not device:
            return "unknown"

        cap = device.effective_cap
        if cap is None:
            return "inactive"

        parts = []
        if device.adhoc_active:
            parts.append("ad-hoc")
        if device.schedule_enabled and _in_time_range(
            datetime.now().time(), device.schedule_start, device.schedule_end
        ):
            parts.append("scheduled")

        return f"active ({' + '.join(parts)}, cap: {int(cap * 100)}%)"


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def _in_time_range(now: time, start: time, end: time) -> bool:
    """Check if a time is within a range (handles overnight spans)."""
    if start <= end:
        return start <= now <= end
    # Overnight (e.g., 22:00 -> 07:00)
    return now >= start or now <= end
