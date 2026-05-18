"""Binary sensors for SleepMe Dock Pro: water-level-low + connected."""

from __future__ import annotations

import logging
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

from .const import DOMAIN
from .helpers import build_device_info

if TYPE_CHECKING:
    from .update_manager import SleepMeUpdateManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SleepMe Thermostat binary sensors from a config entry."""
    device_id: str = entry.data["device_id"]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    device_info = build_device_info(device_id, entry.title, entry_data["device_info"])

    async_add_entities(
        [
            WaterLevelLowSensor(coordinator, device_id, device_info),
            DeviceConnectedBinarySensor(coordinator, device_id, device_info),
        ]
    )


class WaterLevelLowSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: water level low."""

    _attr_has_entity_name = True
    _attr_name = "Water Level"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_low"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        """Return true if the water level is low."""
        return self.coordinator.data["status"].get("is_water_low")


class DeviceConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: device connectivity."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_connected"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is connected."""
        return self.coordinator.data["status"].get("is_connected")
