"""Volume Governor integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import VolumeGovernorCoordinator

_LOGGER = logging.getLogger(__name__)

VolumeGovernorConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: VolumeGovernorConfigEntry
) -> bool:
    """Set up Volume Governor from a config entry."""
    coordinator = VolumeGovernorCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VolumeGovernorConfigEntry
) -> bool:
    """Unload a config entry."""
    coordinator: VolumeGovernorCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_teardown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: VolumeGovernorConfigEntry
) -> None:
    """Handle options update — skip reload if just a cap slider change."""
    coordinator: VolumeGovernorCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator and coordinator._skip_reload:
        coordinator._skip_reload = False
        return
    await hass.config_entries.async_reload(entry.entry_id)
