"""SleepMe Thermostat custom integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    API_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .sleepme import SleepMeClient
from .update_manager import SleepMeUpdateManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = ["climate", "binary_sensor", "sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SleepMe Thermostat component (YAML hook — unused)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SleepMe Thermostat from a config entry."""
    api_url = entry.data.get("api_url") or API_URL
    api_token = entry.data.get("api_token")
    device_id = entry.data.get("device_id")

    if not api_token or not device_id:
        raise ConfigEntryNotReady("API token or device ID missing from entry data")

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    client = SleepMeClient(hass, api_url, api_token, device_id)
    coordinator = SleepMeUpdateManager(
        hass, api_url, api_token, device_id, scan_interval=scan_interval
    )

    # First refresh propagates ConfigEntryAuthFailed (-> reauth flow) and
    # ConfigEntryNotReady (-> HA retries setup) without further plumbing.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "device_info": {
            "firmware_version": entry.data.get("firmware_version"),
            "mac_address": entry.data.get("mac_address"),
            "model": entry.data.get("model"),
            "serial_number": entry.data.get("serial_number"),
        },
    }

    # Reload on options change. async_on_unload registers the unsubscribe so
    # it fires automatically during async_unload_entry.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug(
        "Entry %s set up for device %s (model=%s, fw=%s)",
        entry.entry_id,
        device_id,
        entry.data.get("model"),
        entry.data.get("firmware_version"),
    )
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
