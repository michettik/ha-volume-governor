"""Config flow for Volume Governor integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ENTITY_ID,
    CONF_DEVICE_NAME,
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
    DAY_NAMES,
)

_LOGGER = logging.getLogger(__name__)

DAY_OPTIONS = {str(k): v for k, v in DAY_NAMES.items()}


def _discover_audio_devices(hass: HomeAssistant) -> dict[str, str]:
    """Find all media_player entities that support volume_set."""
    devices: dict[str, str] = {}
    states = hass.states.async_all("media_player")

    for state in states:
        features = state.attributes.get("supported_features", 0)
        if features & MediaPlayerEntityFeature.VOLUME_SET:
            friendly_name = state.attributes.get("friendly_name", state.entity_id)
            devices[state.entity_id] = friendly_name

    return devices


class VolumeGovernorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volume Governor."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize."""
        self._discovered_devices: dict[str, str] = {}
        self._selected_devices: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Discover and select devices."""
        existing = self._async_current_entries()
        if existing:
            return self.async_abort(reason="already_configured")

        self._discovered_devices = _discover_audio_devices(self.hass)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
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
            return await self.async_step_schedule()

        return self.async_show_form(
            step_id="user",
            data_schema=self._devices_schema(),
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Configure the governance schedule."""
        if user_input is not None:
            # Parse day selections
            selected_days_raw = user_input.get(CONF_SCHEDULE_DAYS, {})
            if isinstance(selected_days_raw, dict):
                selected_days = [int(k) for k, v in selected_days_raw.items() if v]
            else:
                selected_days = [int(d) for d in selected_days_raw]

            # Build device list with names
            device_list = []
            for entity_id in self._selected_devices:
                device_list.append({
                    CONF_DEVICE_ENTITY_ID: entity_id,
                    CONF_DEVICE_NAME: self._discovered_devices.get(entity_id, entity_id),
                })

            data = {
                CONF_DEVICES: device_list,
                CONF_SCHEDULE_DAYS: selected_days,
                CONF_SCHEDULE_START: user_input.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START),
                CONF_SCHEDULE_END: user_input.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END),
                CONF_DEFAULT_CAP: user_input.get(CONF_DEFAULT_CAP, 30) / 100.0,
                CONF_CAP_FLOOR: user_input.get(CONF_CAP_FLOOR, 10) / 100.0,
            }

            return self.async_create_entry(
                title="Volume Governor",
                data=data,
            )

        return self.async_show_form(
            step_id="schedule",
            data_schema=self._schedule_schema(),
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

    def _schedule_schema(self) -> vol.Schema:
        """Build the schedule configuration schema."""
        default_days = [str(d) for d in DEFAULT_SCHEDULE_DAYS]
        return vol.Schema(
            {
                vol.Required(
                    CONF_SCHEDULE_DAYS, default=default_days
                ): cv.multi_select(DAY_OPTIONS),
                vol.Required(
                    CONF_SCHEDULE_START, default=DEFAULT_SCHEDULE_START
                ): str,
                vol.Required(
                    CONF_SCHEDULE_END, default=DEFAULT_SCHEDULE_END
                ): str,
                vol.Required(
                    CONF_DEFAULT_CAP, default=int(DEFAULT_CAP * 100)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                vol.Required(
                    CONF_CAP_FLOOR, default=int(DEFAULT_CAP_FLOOR * 100)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            }
        )


class VolumeGovernorOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Volume Governor (reconfigure)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry
        self._discovered_devices: dict[str, str] = {}
        self._selected_devices: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - device selection."""
        self._discovered_devices = _discover_audio_devices(self.hass)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

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
            return await self.async_step_schedule()

        return self.async_show_form(
            step_id="init",
            data_schema=self._devices_schema(current_devices),
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure schedule."""
        if user_input is not None:
            selected_days_raw = user_input.get(CONF_SCHEDULE_DAYS, {})
            if isinstance(selected_days_raw, dict):
                selected_days = [int(k) for k, v in selected_days_raw.items() if v]
            else:
                selected_days = [int(d) for d in selected_days_raw]

            device_list = []
            for entity_id in self._selected_devices:
                device_list.append({
                    CONF_DEVICE_ENTITY_ID: entity_id,
                    CONF_DEVICE_NAME: self._discovered_devices.get(entity_id, entity_id),
                })

            new_data = {
                CONF_DEVICES: device_list,
                CONF_SCHEDULE_DAYS: selected_days,
                CONF_SCHEDULE_START: user_input.get(
                    CONF_SCHEDULE_START, self.config_entry.data.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START)
                ),
                CONF_SCHEDULE_END: user_input.get(
                    CONF_SCHEDULE_END, self.config_entry.data.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END)
                ),
                CONF_DEFAULT_CAP: user_input.get(CONF_DEFAULT_CAP, 30) / 100.0,
                CONF_CAP_FLOOR: user_input.get(CONF_CAP_FLOOR, 10) / 100.0,
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        # Pre-fill with existing values
        existing = self.config_entry.data
        current_days = [str(d) for d in existing.get(CONF_SCHEDULE_DAYS, DEFAULT_SCHEDULE_DAYS)]
        current_cap = existing.get(CONF_DEFAULT_CAP, DEFAULT_CAP)
        current_floor = existing.get(CONF_CAP_FLOOR, DEFAULT_CAP_FLOOR)

        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCHEDULE_DAYS, default=current_days
                    ): cv.multi_select(DAY_OPTIONS),
                    vol.Required(
                        CONF_SCHEDULE_START,
                        default=existing.get(CONF_SCHEDULE_START, DEFAULT_SCHEDULE_START),
                    ): str,
                    vol.Required(
                        CONF_SCHEDULE_END,
                        default=existing.get(CONF_SCHEDULE_END, DEFAULT_SCHEDULE_END),
                    ): str,
                    vol.Required(
                        CONF_DEFAULT_CAP,
                        default=int(current_cap * 100) if isinstance(current_cap, float) else 30,
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
                    vol.Required(
                        CONF_CAP_FLOOR,
                        default=int(current_floor * 100) if isinstance(current_floor, float) else 10,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                }
            ),
        )

    def _devices_schema(self, default: list[str] | None = None) -> vol.Schema:
        """Build device selection schema with optional defaults."""
        return vol.Schema(
            {
                vol.Required("devices", default=default or []): cv.multi_select(
                    self._discovered_devices
                ),
            }
        )
