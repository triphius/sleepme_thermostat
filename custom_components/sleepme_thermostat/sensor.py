"""Diagnostic sensors for SleepMe Dock Pro: IP, LAN, brightness, display unit, time zone."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorStateClass
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
    """Set up SleepMe Thermostat diagnostic sensors from a config entry."""
    device_id: str = entry.data["device_id"]
    name: str = entry.data["name"]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    device_info = build_device_info(device_id, name, entry_data["device_info"])

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

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
        *,
        suffix: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = label
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{suffix}"
        self._attr_device_info = device_info


class IPAddressSensor(_SleepMeDiagnosticSensor):
    """IP address of the device."""

    _attr_icon = "mdi:ip"

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="ip_address",
            label="IP Address",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["about"].get("ip_address")


class LANAddressSensor(_SleepMeDiagnosticSensor):
    """LAN address of the device."""

    _attr_icon = "mdi:lan"

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="lan_address",
            label="LAN Address",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["about"].get("lan_address")


class BrightnessLevelSensor(_SleepMeDiagnosticSensor):
    """Display brightness in percent."""

    _attr_icon = "mdi:brightness-6"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="brightness_level",
            label="Brightness Level",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["control"].get("brightness_level")


class DisplayTemperatureUnitSensor(_SleepMeDiagnosticSensor):
    """Display temperature unit (C / F)."""

    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="display_temperature_unit",
            label="Display Temperature Unit",
        )

    @property
    def native_value(self) -> str | int | None:
        unit = self.coordinator.data["control"].get("display_temperature_unit")
        return unit.upper() if unit else None


class TimeZoneSensor(_SleepMeDiagnosticSensor):
    """Configured time zone."""

    _attr_icon = "mdi:earth"

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator,
            device_id,
            name,
            device_info,
            suffix="time_zone",
            label="Time Zone",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["control"].get("time_zone")
