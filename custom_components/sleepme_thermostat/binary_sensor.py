"""Binary sensors for SleepMe Dock Pro: water-level-low + connected."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _device_info(device_id: str, name: str, info: dict) -> dict:
    return {
        "identifiers": {(DOMAIN, device_id)},
        "name": f"Dock Pro {name}",
        "manufacturer": "SleepMe",
        "model": info.get("model"),
        "sw_version": info.get("firmware_version"),
        "connections": {("mac", info.get("mac_address"))},
        "serial_number": info.get("serial_number"),
    }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up SleepMe Thermostat binary sensors from a config entry."""
    device_id = entry.data.get("device_id")
    name = entry.data.get("name")
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    device_info = _device_info(device_id, name, entry_data["device_info"])

    async_add_entities(
        [
            WaterLevelLowSensor(coordinator, device_id, name, device_info),
            DeviceConnectedBinarySensor(coordinator, device_id, name, device_info),
        ]
    )


class WaterLevelLowSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: water level low."""

    _attr_device_class = "problem"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"Dock Pro {name} Water Level"
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_low"
        self._attr_device_info = device_info

    @property
    def is_on(self):
        """Return true if the water level is low."""
        return self.coordinator.data["status"].get("is_water_low")


class DeviceConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: device connectivity."""

    _attr_device_class = "connectivity"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"Dock Pro {name} Connected"
        self._attr_unique_id = f"{DOMAIN}_{device_id}_connected"
        self._attr_device_info = device_info

    @property
    def is_on(self):
        """Return true if the device is connected."""
        return self.coordinator.data["status"].get("is_connected")
