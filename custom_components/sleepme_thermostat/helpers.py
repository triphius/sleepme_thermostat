"""Shared helpers used across multiple platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DOMAIN


def round_half_up(n: float) -> float:
    """Round a number to the nearest .0 or .5."""
    return round(n * 2) / 2


def build_device_info(device_id: str, name: str, info: dict) -> DeviceInfo:
    """Construct the device_info dict shared by every platform."""
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=f"Dock Pro {name}",
        manufacturer="SleepMe",
        model=info.get("model"),
        sw_version=info.get("firmware_version"),
        connections={(CONNECTION_NETWORK_MAC, info.get("mac_address", ""))},
        serial_number=info.get("serial_number"),
    )
