"""Diagnostics support for SleepMe Thermostat.

Exposed through HA's "Download diagnostics" UI on the device page.

The api_token is redacted; everything else (coordinator data, entry options,
device info) is included verbatim so support requests carry enough state to
reproduce a bug without follow-up. MAC, IP, LAN, serial are also redacted by
default to make the output safer to paste verbatim into a GitHub issue —
narrow `TO_REDACT` if you need them visible during real debugging.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT: set[str] = {
    "api_token",
    "mac_address",
    "serial_number",
    "ip_address",
    "lan_address",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a redacted diagnostic snapshot for a SleepMe config entry."""
    data = getattr(entry, "runtime_data", None)

    coordinator_payload: dict[str, Any] = {}
    device_info: dict[str, Any] = {}
    if data is not None:
        coordinator = data.coordinator
        coordinator_payload = {
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                repr(coordinator.last_exception)
                if coordinator.last_exception is not None
                else None
            ),
            "data": coordinator.data or {},
        }
        device_info = dict(data.device_info)

    return {
        "entry": {
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "device_info": async_redact_data(device_info, TO_REDACT),
        "coordinator": async_redact_data(coordinator_payload, TO_REDACT),
    }
