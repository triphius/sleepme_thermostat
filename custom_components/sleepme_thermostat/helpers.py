"""Shared helpers used across multiple platforms."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import (
    DEVICE_TYPE_DOCK_PRO,
    DEVICE_TYPE_TRACKER,
    DOCK_PRO_MODELS,
    DOMAIN,
    TRACKER_MODELS,
)

_LEGACY_ENTITY_NAME_PREFIXES = (
    "Chilipad Dock Pro - ",
    "Chilipad Dock - ",
    "Chilipad Tracker - ",
    "SleepMe Dock Pro - ",
    "SleepMe Tracker - ",
    "Dock Pro - ",
    "Dock Pro ",
    "Tracker - ",
    "Tracker ",
)


def round_half_up(n: float) -> float:
    """Round a number to the nearest .0 or .5."""
    return round(n * 2) / 2


def build_device_info(device_id: str, display_name: str, info: dict) -> DeviceInfo:
    """Construct the device_info dict shared by every platform.

    `display_name` is the full user-facing device name (e.g. "Dock Pro - Ramon").
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
    return (
        "SleepMe Tracker"
        if get_device_type(model) == DEVICE_TYPE_TRACKER
        else "SleepMe Dock Pro"
    )


def format_entry_title(model: str | None, name: str) -> str:
    """Return the config-entry title for the device."""
    return f"{get_device_title_prefix(model)} - {name}"


def normalize_entity_registry_display_name(
    hass: HomeAssistant,
    platform: str,
    unique_id: str,
    label: str,
) -> None:
    """Normalize legacy generated entity names without changing entity IDs.

    Early builds stored some entity names with the full device name prefix
    baked in. With `has_entity_name=True`, the clean/original form should just
    be the per-entity label (for example, "Connected"), letting HA compose the
    full display name from the device and entity names automatically.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is None:
        return

    entry = registry.async_get(entity_id)
    if entry is None:
        return

    updates: dict[str, object] = {"has_entity_name": True}

    if entry.original_name != label:
        updates["original_name"] = label

    if _looks_like_generated_legacy_name(entry.name, label):
        updates["name"] = None

    if len(updates) > 1 or entry.has_entity_name is not True:
        registry.async_update_entity(entity_id, **updates)


def _looks_like_generated_legacy_name(name: str | None, label: str) -> bool:
    """Return True if a stored name looks like an old auto-generated full name."""
    if name is None or name == label:
        return False

    return name.endswith(f" {label}") and any(
        name.startswith(prefix) for prefix in _LEGACY_ENTITY_NAME_PREFIXES
    )
