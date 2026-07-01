"""Volume Governor coordinator - the enforcement engine.

Core design:
- Devices are discovered via config flow (media_player entities with VOLUME_SET)
- Dashboard shows all governed devices; tap the switch to ENGAGE the governor
- Governance schedule applies on configured days only (default Mon-Fri)
- When engaged (ad-hoc or scheduled), volume is capped at the configured level
- Ad-hoc engagement auto-lifts at the schedule_end time the NEXT day
- Persistent mode keeps enforcement running until manually toggled off
- Real-time enforcement via state change listeners (no polling needed)
- Per-device caps stored in .storage/volume_governor (survives restarts)
"""
from __future__ import annotations

import logging
from datetime import time, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_PLAYING, STATE_IDLE, STATE_PAUSED
from homeassistant.core import HomeAssistant, Event, callback, CALLBACK_TYPE
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    DOMAIN as MP_DOMAIN,
    SERVICE_VOLUME_SET,
)

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ENTITY_ID,
    CONF_SCHEDULE_DAYS,
    CONF_SCHEDULE_START,
    CONF_SCHEDULE_END,
    CONF_DEFAULT_CAP,
    CONF_CAP_FLOOR,
    DEFAULT_SCHEDULE_DAYS,
    DEFAULT_SCHEDULE_START,
    DEFAULT_SCHEDULE_END,
    DEFAULT_CAP,
    DEFAULT_CAP_FLOOR,
)

_LOGGER = logging.getLogger(__name__)

ACTIVE_STATES = {STATE_ON, STATE_PLAYING, STATE_IDLE, STATE_PAUSED}
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.device_caps"


class GovernedDevice:
    """State and config for a single governed device."""

    def __init__(self, entity_id: str, name: str) -> None:
        """Initialize."""
        self.entity_id = entity_id
        self.name = name
        # Runtime state
        self.engaged: bool = False
        self.persistent: bool = False
        self.cap: float = DEFAULT_CAP
        # Computed: when the current engagement should auto-lift
        self.lift_at: datetime | None = None


class VolumeGovernorCoordinator:
    """Coordinates enforcement across all governed devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.devices: dict[str, GovernedDevice] = {}

        # Global schedule config
        data = entry.data
        self.schedule_days: list[int] = data.get(CONF_SCHEDULE_DAYS, DEFAULT_SCHEDULE_DAYS)
        self.schedule_start: time = _parse_time(data.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START))
        self.schedule_end: time = _parse_time(data.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END))
        self.default_cap: float = data.get(CONF_DEFAULT_CAP, DEFAULT_CAP)
        self.cap_floor: float = data.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR)

        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_lift_check: CALLBACK_TYPE | None = None
        self._enforcing: set[str] = set()
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_setup(self) -> None:
        """Set up the coordinator: register listeners."""
        # Load persisted per-device caps from .storage
        stored = await self._store.async_load() or {}

        devices_config = self.entry.data.get(CONF_DEVICES, [])
        for dev_conf in devices_config:
            entity_id = dev_conf[CONF_DEVICE_ENTITY_ID]
            name = dev_conf.get("name", entity_id)
            device = GovernedDevice(entity_id, name)
            # Load per-device cap from storage, fall back to global default
            device.cap = stored.get(entity_id, {}).get("cap", self.default_cap)
            self.devices[entity_id] = device

        # Listen for state changes on all governed entities
        entity_ids = list(self.devices.keys())
        if entity_ids:
            self._unsub_state = async_track_state_change_event(
                self.hass, entity_ids, self._async_on_state_change
            )

        # Check every minute at :00 for auto-lift
        self._unsub_lift_check = async_track_time_change(
            self.hass, self._async_check_lifts, second=0
        )

    async def async_teardown(self) -> None:
        """Tear down listeners."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_lift_check:
            self._unsub_lift_check()
            self._unsub_lift_check = None

    async def _async_save_caps(self) -> None:
        """Persist per-device caps to .storage file."""
        data = {}
        for entity_id, device in self.devices.items():
            data[entity_id] = {"cap": device.cap}
        await self._store.async_save(data)

    @callback
    def _async_check_lifts(self, _now: datetime) -> None:
        """Check if any engaged devices should be auto-lifted."""
        now = datetime.now()
        for device in self.devices.values():
            if device.engaged and not device.persistent and device.lift_at:
                if now >= device.lift_at:
                    device.engaged = False
                    device.lift_at = None
                    # Reset per-device cap override back to global default
                    if device.cap != self.default_cap:
                        device.cap = self.default_cap
                        self.hass.async_create_task(self._async_save_caps())
                    _LOGGER.info(
                        "Volume Governor: auto-lifted %s (schedule end reached)",
                        device.entity_id,
                    )
                    self.hass.bus.async_fire(
                        "volume_governor_updated", {"entity_id": device.entity_id}
                    )

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

        # Only enforce if device is engaged
        if not device.engaged:
            return

        current_volume = new_state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
        if current_volume is None:
            return

        cap = max(device.cap, self.cap_floor)
        if current_volume > cap:
            _LOGGER.info(
                "Volume Governor: %s at %.3f exceeds cap %.3f, enforcing",
                entity_id,
                current_volume,
                cap,
            )
            self._enforcing.add(entity_id)
            self.hass.async_create_task(self._async_enforce(entity_id))

    async def _async_enforce(self, entity_id: str) -> None:
        """Set volume back to cap. Always reads LIVE cap from device."""
        try:
            device = self.devices.get(entity_id)
            if not device or not device.engaged:
                return
            cap = max(device.cap, self.cap_floor)
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

    def engage(self, entity_id: str) -> None:
        """Engage the governor for a device (tap to activate)."""
        device = self.devices.get(entity_id)
        if not device:
            return

        device.engaged = True

        # Clear any stale enforcing block from a prior disengage
        self._enforcing.discard(entity_id)

        # Compute auto-lift time: next occurrence of schedule_end
        if not device.persistent:
            device.lift_at = self._compute_lift_time()

        _LOGGER.info(
            "Volume Governor: engaged %s (cap=%d%%, lift_at=%s, persistent=%s)",
            entity_id,
            int(device.cap * 100),
            device.lift_at,
            device.persistent,
        )

        # Immediately enforce if currently over cap
        state = self.hass.states.get(entity_id)
        if state and state.state in ACTIVE_STATES:
            current = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
            cap = max(device.cap, self.cap_floor)
            if current is not None and current > cap:
                self.hass.async_create_task(self._async_enforce(entity_id))

    def disengage(self, entity_id: str) -> None:
        """Disengage the governor for a device."""
        device = self.devices.get(entity_id)
        if not device:
            return

        device.engaged = False
        device.lift_at = None
        # Reset per-device cap override back to global default for next cycle
        if device.cap != self.default_cap:
            device.cap = self.default_cap
            self.hass.async_create_task(self._async_save_caps())
            _LOGGER.info(
                "Volume Governor: reset %s cap to global default %d%%",
                entity_id, int(self.default_cap * 100),
            )
        # Block state-change listener for 1 second to let in-flight events pass
        self._enforcing.add(entity_id)
        self.hass.async_create_task(self._async_clear_enforcing(entity_id))
        _LOGGER.info("Volume Governor: disengaged %s", entity_id)

    async def _async_clear_enforcing(self, entity_id: str) -> None:
        """Clear enforcing flag after a short delay to let in-flight events pass."""
        import asyncio
        await asyncio.sleep(1)
        self._enforcing.discard(entity_id)

    def set_persistent(self, entity_id: str, persistent: bool) -> None:
        """Set or clear persistent mode."""
        device = self.devices.get(entity_id)
        if not device:
            return

        device.persistent = persistent
        if persistent:
            device.lift_at = None
        elif device.engaged:
            device.lift_at = self._compute_lift_time()

        _LOGGER.info(
            "Volume Governor: %s persistent=%s", entity_id, persistent
        )

    def set_cap(self, entity_id: str, cap: float) -> None:
        """Update the cap value for a device and persist."""
        device = self.devices.get(entity_id)
        if device:
            device.cap = max(cap, self.cap_floor)
            # Persist to .storage (no config entry mutation, no reload)
            self.hass.async_create_task(self._async_save_caps())
            # If engaged and current volume exceeds new cap, enforce NOW
            if device.engaged:
                state = self.hass.states.get(entity_id)
                if state and state.state in ACTIVE_STATES:
                    current = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
                    if current is not None and current > device.cap:
                        self._enforcing.discard(entity_id)
                        self.hass.async_create_task(self._async_enforce(entity_id))

    def get_status(self, entity_id: str) -> str:
        """Get human-readable status for a device."""
        device = self.devices.get(entity_id)
        if not device:
            return "unknown"

        if not device.engaged:
            return "idle"

        parts = [f"cap: {int(device.cap * 100)}%"]
        if device.persistent:
            parts.append("persistent")
        elif device.lift_at:
            parts.append(f"lifts: {device.lift_at.strftime('%a %H:%M')}")

        return f"enforcing ({', '.join(parts)})"

    def is_schedule_active(self) -> bool:
        """Check if current time is within the governance schedule."""
        now = datetime.now()
        if now.weekday() not in self.schedule_days:
            return False
        return _in_time_range(now.time(), self.schedule_start, self.schedule_end)

    def _compute_lift_time(self) -> datetime:
        """Compute the next occurrence of schedule_end time."""
        now = datetime.now()
        target = now.replace(
            hour=self.schedule_end.hour,
            minute=self.schedule_end.minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        return target


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
