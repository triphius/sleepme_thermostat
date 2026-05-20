"""Binary sensors for SleepMe Dock Pro and Tracker devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_TRACKER, DOMAIN
from .helpers import (
    build_device_info,
    get_device_type,
    normalize_entity_registry_display_name,
)

if TYPE_CHECKING:
    from .update_manager import SleepMeUpdateManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SleepMe binary sensors from a config entry."""
    device_id: str = entry.data["device_id"]
    data = entry.runtime_data
    device_info = build_device_info(device_id, entry.title, data.device_info)

    entities: list[BinarySensorEntity] = [
        DeviceConnectedBinarySensor(data.coordinator, device_id, device_info)
    ]
    normalize_entity_registry_display_name(
        hass,
        "binary_sensor",
        f"{DOMAIN}_{device_id}_connected",
        "Connected",
    )
    if get_device_type(entry.data.get("model")) == DEVICE_TYPE_TRACKER:
        normalize_entity_registry_display_name(
            hass,
            "binary_sensor",
            f"{DOMAIN}_{device_id}_occupied",
            "Occupied",
        )
        entities.append(UserDetectedBinarySensor(data.coordinator, device_id, device_info))
    else:
        normalize_entity_registry_display_name(
            hass,
            "binary_sensor",
            f"{DOMAIN}_{device_id}_water_low",
            "Water Level",
        )
        entities.append(WaterLevelLowSensor(data.coordinator, device_id, device_info))

    async_add_entities(entities)


class _SleepMeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Common base for coordinator-backed binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
        *,
        suffix: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{suffix}"
        self._attr_name = label
        self._attr_device_info = device_info


class WaterLevelLowSensor(_SleepMeBinarySensor):
    """Binary sensor: water level low."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            device_info,
            suffix="water_low",
            label="Water Level",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the water level is low."""
        return self.coordinator.data["status"].get("is_water_low")


class DeviceConnectedBinarySensor(_SleepMeBinarySensor):
    """Binary sensor: device connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            device_info,
            suffix="connected",
            label="Connected",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is connected."""
        return self.coordinator.data["connectivity"].get(
            "is_connected",
            self.coordinator.data["status"].get("is_connected"),
        )


class UserDetectedBinarySensor(_SleepMeBinarySensor):
    """Binary sensor: tracker occupancy / user detection."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            device_info,
            suffix="occupied",
            label="Occupied",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the tracker detects a user in bed."""
        return self.coordinator.data["status"].get("user_detected")
