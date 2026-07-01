"""Config flow for Volume Governor integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    MediaPlayerEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ENTITY_ID,
    CONF_DEVICE_NAME,
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


def _discover_audio_devices(hass: HomeAssistant) -> dict[str, str]:
    """Find all media_player entities that support volume_set."""
    devices: dict[str, str] = {}
    states = hass.states.async_all("media_player")

    for state in states:
        # Check if entity supports VOLUME_SET feature
        features = state.attributes.get("supported_features", 0)
        if features & MediaPlayerEntityFeature.VOLUME_SET:
            friendly_name = state.attributes.get("friendly_name", state.entity_id)
            devices[state.entity_id] = friendly_name

    return devices


class VolumeGovernorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volume Governor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovered_devices: dict[str, str] = {}
        self._selected_devices: list[str] = []
        self._device_configs: list[dict[str, Any]] = []
        self._current_device_index: int = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Discover and select devices."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        self._discovered_devices = _discover_audio_devices(self.hass)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            # multi_select returns {entity_id: bool} dict — extract selected ones
            selected = user_input.get("devices", {})
            if isinstance(selected, dict):
                self._selected_devices = [k for k, v in selected.items() if v]
            else:
                self._selected_devices = selected
            if not self._selected_devices:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._devices_schema(),
                    errors={"base": "no_devices_selected"},
                )
            self._current_device_index = 0
            return await self.async_step_device_config()

        return self.async_show_form(
            step_id="user",
            data_schema=self._devices_schema(),
        )

    async def async_step_device_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2+: Configure each selected device."""
        if user_input is not None:
            entity_id = self._selected_devices[self._current_device_index]
            device_config = {
                CONF_DEVICE_ENTITY_ID: entity_id,
                CONF_DEVICE_NAME: self._discovered_devices.get(entity_id, entity_id),
                CONF_ADHOC_CAP: user_input.get(CONF_ADHOC_CAP, DEFAULT_ADHOC_CAP),
                CONF_ADHOC_LIFT_TIME: user_input.get(
                    CONF_ADHOC_LIFT_TIME, DEFAULT_ADHOC_LIFT_TIME
                ),
                CONF_SCHEDULE_ENABLED: user_input.get(CONF_SCHEDULE_ENABLED, False),
                CONF_SCHEDULE_START: user_input.get(
                    CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START
                ),
                CONF_SCHEDULE_END: user_input.get(
                    CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END
                ),
                CONF_SCHEDULE_CAP: user_input.get(
                    CONF_SCHEDULE_CAP, DEFAULT_SCHEDULE_CAP
                ),
                CONF_CAP_FLOOR: user_input.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR),
            }
            self._device_configs.append(device_config)
            self._current_device_index += 1

            if self._current_device_index >= len(self._selected_devices):
                # All devices configured — create the entry
                return self.async_create_entry(
                    title="Volume Governor",
                    data={CONF_DEVICES: self._device_configs},
                )

        # Show config form for current device
        entity_id = self._selected_devices[self._current_device_index]
        device_name = self._discovered_devices.get(entity_id, entity_id)

        return self.async_show_form(
            step_id="device_config",
            data_schema=self._device_config_schema(),
            description_placeholders={
                "device_name": device_name,
                "device_number": str(self._current_device_index + 1),
                "device_total": str(len(self._selected_devices)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VolumeGovernorOptionsFlow:
        """Get the options flow."""
        return VolumeGovernorOptionsFlow(config_entry)

    def _devices_schema(self) -> vol.Schema:
        """Build the device selection schema."""
        return vol.Schema(
            {
                vol.Required("devices"): cv.multi_select(self._discovered_devices),
            }
        )

    def _device_config_schema(self) -> vol.Schema:
        """Build per-device configuration schema."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_ADHOC_CAP, default=int(DEFAULT_ADHOC_CAP * 100)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                vol.Required(
                    CONF_ADHOC_LIFT_TIME, default=DEFAULT_ADHOC_LIFT_TIME
                ): str,
                vol.Required(CONF_SCHEDULE_ENABLED, default=False): bool,
                vol.Required(
                    CONF_SCHEDULE_START, default=DEFAULT_SCHEDULE_START
                ): str,
                vol.Required(
                    CONF_SCHEDULE_END, default=DEFAULT_SCHEDULE_END
                ): str,
                vol.Required(
                    CONF_SCHEDULE_CAP, default=int(DEFAULT_SCHEDULE_CAP * 100)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                vol.Required(
                    CONF_CAP_FLOOR, default=int(DEFAULT_CAP_FLOOR * 100)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            }
        )


class VolumeGovernorOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Volume Governor (reconfigure devices)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry
        self._discovered_devices: dict[str, str] = {}
        self._selected_devices: list[str] = []
        self._device_configs: list[dict[str, Any]] = []
        self._current_device_index: int = 0

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - same flow as initial setup."""
        self._discovered_devices = _discover_audio_devices(self.hass)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Pre-select currently configured devices
        current_devices = [
            d[CONF_DEVICE_ENTITY_ID]
            for d in self.config_entry.data.get(CONF_DEVICES, [])
        ]

        if user_input is not None:
            selected = user_input.get("devices", {})
            if isinstance(selected, dict):
                self._selected_devices = [k for k, v in selected.items() if v]
            else:
                self._selected_devices = selected
            if not self._selected_devices:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._devices_schema(current_devices),
                    errors={"base": "no_devices_selected"},
                )
            self._current_device_index = 0
            return await self.async_step_device_config()

        return self.async_show_form(
            step_id="init",
            data_schema=self._devices_schema(current_devices),
        )

    async def async_step_device_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure each selected device."""
        if user_input is not None:
            entity_id = self._selected_devices[self._current_device_index]
            device_config = {
                CONF_DEVICE_ENTITY_ID: entity_id,
                CONF_DEVICE_NAME: self._discovered_devices.get(entity_id, entity_id),
                CONF_ADHOC_CAP: user_input.get(CONF_ADHOC_CAP, DEFAULT_ADHOC_CAP),
                CONF_ADHOC_LIFT_TIME: user_input.get(
                    CONF_ADHOC_LIFT_TIME, DEFAULT_ADHOC_LIFT_TIME
                ),
                CONF_SCHEDULE_ENABLED: user_input.get(CONF_SCHEDULE_ENABLED, False),
                CONF_SCHEDULE_START: user_input.get(
                    CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START
                ),
                CONF_SCHEDULE_END: user_input.get(
                    CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END
                ),
                CONF_SCHEDULE_CAP: user_input.get(
                    CONF_SCHEDULE_CAP, DEFAULT_SCHEDULE_CAP
                ),
                CONF_CAP_FLOOR: user_input.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR),
            }
            self._device_configs.append(device_config)
            self._current_device_index += 1

            if self._current_device_index >= len(self._selected_devices):
                # Update the config entry with new data
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={CONF_DEVICES: self._device_configs},
                )
                return self.async_create_entry(title="", data={})

        entity_id = self._selected_devices[self._current_device_index]
        device_name = self._discovered_devices.get(entity_id, entity_id)

        # Load existing config for this device if available
        existing = self._get_existing_config(entity_id)

        return self.async_show_form(
            step_id="device_config",
            data_schema=self._device_config_schema(existing),
            description_placeholders={
                "device_name": device_name,
                "device_number": str(self._current_device_index + 1),
                "device_total": str(len(self._selected_devices)),
            },
        )

    def _get_existing_config(self, entity_id: str) -> dict[str, Any]:
        """Get existing config for a device if it was previously configured."""
        for dev in self.config_entry.data.get(CONF_DEVICES, []):
            if dev[CONF_DEVICE_ENTITY_ID] == entity_id:
                return dev
        return {}

    def _devices_schema(self, default: list[str] | None = None) -> vol.Schema:
        """Build device selection schema with optional defaults."""
        return vol.Schema(
            {
                vol.Required("devices", default=default or []): cv.multi_select(
                    self._discovered_devices
                ),
            }
        )

    def _device_config_schema(self, existing: dict[str, Any] | None = None) -> vol.Schema:
        """Build per-device configuration schema with existing values."""
        existing = existing or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_ADHOC_CAP,
                    default=int(existing.get(CONF_ADHOC_CAP, DEFAULT_ADHOC_CAP) * 100)
                    if isinstance(existing.get(CONF_ADHOC_CAP), float)
                    else int(DEFAULT_ADHOC_CAP * 100),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                vol.Required(
                    CONF_ADHOC_LIFT_TIME,
                    default=existing.get(CONF_ADHOC_LIFT_TIME, DEFAULT_ADHOC_LIFT_TIME),
                ): str,
                vol.Required(
                    CONF_SCHEDULE_ENABLED,
                    default=existing.get(CONF_SCHEDULE_ENABLED, False),
                ): bool,
                vol.Required(
                    CONF_SCHEDULE_START,
                    default=existing.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START),
                ): str,
                vol.Required(
                    CONF_SCHEDULE_END,
                    default=existing.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END),
                ): str,
                vol.Required(
                    CONF_SCHEDULE_CAP,
                    default=int(existing.get(CONF_SCHEDULE_CAP, DEFAULT_SCHEDULE_CAP) * 100)
                    if isinstance(existing.get(CONF_SCHEDULE_CAP), float)
                    else int(DEFAULT_SCHEDULE_CAP * 100),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                vol.Required(
                    CONF_CAP_FLOOR,
                    default=int(existing.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR) * 100)
                    if isinstance(existing.get(CONF_CAP_FLOOR), float)
                    else int(DEFAULT_CAP_FLOOR * 100),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            }
        )
