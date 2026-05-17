"""Diagnostic sensors for SleepMe Dock Pro: IP, LAN, brightness, display unit, time zone."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
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
        "connections": {(CONNECTION_NETWORK_MAC, info.get("mac_address"))},
        "serial_number": info.get("serial_number"),
    }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up SleepMe Thermostat diagnostic sensors from a config entry."""
    device_id = entry.data.get("device_id")
    name = entry.data.get("name")
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    device_info = _device_info(device_id, name, entry_data["device_info"])

    async_add_entities(
        [
            IPAddressSensor(coordinator, device_id, name, device_info),
            LANAddressSensor(coordinator, device_id, name, device_info),
            BrightnessLevelSensor(coordinator, device_id, name, device_info),
            DisplayTemperatureUnitSensor(coordinator, device_id, name, device_info),
            TimeZoneSensor(coordinator, device_id, name, device_info),
        ]
    )


class _SleepMeDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Common base for diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, name, device_info, *, suffix, label):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = label
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{suffix}"
        self._attr_device_info = device_info


class IPAddressSensor(_SleepMeDiagnosticSensor):
    """IP address of the device."""

    _attr_icon = "mdi:ip"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="ip_address",
            label="IP Address",
        )

    @property
    def native_value(self):
        return self.coordinator.data["about"].get("ip_address")


class LANAddressSensor(_SleepMeDiagnosticSensor):
    """LAN address of the device."""

    _attr_icon = "mdi:lan"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="lan_address",
            label="LAN Address",
        )

    @property
    def native_value(self):
        return self.coordinator.data["about"].get("lan_address")


class BrightnessLevelSensor(_SleepMeDiagnosticSensor):
    """Display brightness in percent."""

    _attr_icon = "mdi:brightness-6"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="brightness_level",
            label="Brightness Level",
        )

    @property
    def native_value(self):
        return self.coordinator.data["control"].get("brightness_level")


class DisplayTemperatureUnitSensor(_SleepMeDiagnosticSensor):
    """Display temperature unit (C / F)."""

    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="display_temperature_unit",
            label="Display Temperature Unit",
        )

    @property
    def native_value(self):
        unit = self.coordinator.data["control"].get("display_temperature_unit")
        return unit.upper() if unit else None


class TimeZoneSensor(_SleepMeDiagnosticSensor):
    """Configured time zone."""

    _attr_icon = "mdi:earth"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="time_zone",
            label="Time Zone",
        )

    @property
    def native_value(self):
        return self.coordinator.data["control"].get("time_zone")
