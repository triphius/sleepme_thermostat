"""Shared helpers used across multiple platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import (
    DEVICE_TYPE_DOCK_PRO,
    DEVICE_TYPE_TRACKER,
    DOCK_PRO_MODELS,
    DOMAIN,
    TRACKER_MODELS,
)


def round_half_up(n: float) -> float:
    """Round a number to the nearest .0 or .5."""
    return round(n * 2) / 2


def build_device_info(device_id: str, display_name: str, info: dict) -> DeviceInfo:
    """Construct the device_info dict shared by every platform.

    `display_name` is the full user-facing device name (e.g. "Dock Pro Ramon").
    Callers typically pass `entry.title`.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=display_name,
        manufacturer="SleepMe",
        model=info.get("model"),
        sw_version=info.get("firmware_version"),
        connections={(CONNECTION_NETWORK_MAC, info.get("mac_address", ""))},
        serial_number=info.get("serial_number"),
    )


def get_device_type(model: str | None) -> str:
    """Classify a SleepMe device from its API model string."""
    if model in TRACKER_MODELS:
        return DEVICE_TYPE_TRACKER
    if model in DOCK_PRO_MODELS:
        return DEVICE_TYPE_DOCK_PRO
    return DEVICE_TYPE_DOCK_PRO


def get_device_title_prefix(model: str | None) -> str:
    """Return the user-facing device title prefix."""
    return "Tracker" if get_device_type(model) == DEVICE_TYPE_TRACKER else "Dock Pro"
