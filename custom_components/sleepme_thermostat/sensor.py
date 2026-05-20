"""Sensors for SleepMe Dock Pro and Tracker devices."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DEVICE_TYPE_TRACKER, DOMAIN
from .helpers import build_device_info, get_device_type

if TYPE_CHECKING:
    from .update_manager import SleepMeUpdateManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SleepMe sensors from a config entry."""
    device_id: str = entry.data["device_id"]
    data = entry.runtime_data
    device_info = build_device_info(device_id, entry.title, data.device_info)

    entities: list[SensorEntity] = [
        IPAddressSensor(data.coordinator, device_id, device_info),
        LANAddressSensor(data.coordinator, device_id, device_info),
        FirmwareVersionSensor(data.coordinator, device_id, device_info),
    ]

    if get_device_type(entry.data.get("model")) == DEVICE_TYPE_TRACKER:
        entities.extend(
            [
                EnvironmentHumiditySensor(data.coordinator, device_id, device_info),
                EnvironmentTemperatureSensor(data.coordinator, device_id, device_info),
                BedTemperatureSensor(data.coordinator, device_id, device_info),
                LastConnectedAtSensor(data.coordinator, device_id, device_info),
                LastDisconnectedAtSensor(data.coordinator, device_id, device_info),
                UptimeSensor(data.coordinator, device_id, device_info),
            ]
        )
    else:
        entities.extend(
            [
                BrightnessLevelSensor(data.coordinator, device_id, device_info),
                DisplayTemperatureUnitSensor(data.coordinator, device_id, device_info),
                TimeZoneSensor(data.coordinator, device_id, device_info),
                WaterLevelSensor(data.coordinator, device_id, device_info),
            ]
        )

    async_add_entities(entities)


class _SleepMeSensor(CoordinatorEntity, SensorEntity):
    """Common base for coordinator-backed sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SleepMeUpdateManager,
        device_id: str,
        device_info: DeviceInfo,
        *,
        suffix: str,
        label: str,
        entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = label
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{suffix}"
        self._attr_device_info = device_info
        self._attr_entity_category = entity_category


class IPAddressSensor(_SleepMeSensor):
    """IP address of the device."""

    _attr_icon = "mdi:ip"

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
            suffix="ip_address",
            label="IP Address",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["about"].get("ip_address")


class LANAddressSensor(_SleepMeSensor):
    """LAN address of the device."""

    _attr_icon = "mdi:lan"

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
            suffix="lan_address",
            label="LAN Address",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["about"].get("lan_address")


class FirmwareVersionSensor(_SleepMeSensor):
    """Reports the current device firmware version."""

    _attr_icon = "mdi:chip"

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
            suffix="firmware_version",
            label="Firmware Version",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["about"].get("firmware_version")


class BrightnessLevelSensor(_SleepMeSensor):
    """Display brightness in percent."""

    _attr_icon = "mdi:brightness-6"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="brightness_level",
            label="Brightness Level",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["control"].get("brightness_level")


class DisplayTemperatureUnitSensor(_SleepMeSensor):
    """Display temperature unit (C / F)."""

    _attr_icon = "mdi:thermometer"

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
            suffix="display_temperature_unit",
            label="Display Temperature Unit",
        )

    @property
    def native_value(self) -> str | int | None:
        unit = self.coordinator.data["control"].get("display_temperature_unit")
        return unit.upper() if unit else None


class TimeZoneSensor(_SleepMeSensor):
    """Configured time zone."""

    _attr_icon = "mdi:earth"

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
            suffix="time_zone",
            label="Time Zone",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["control"].get("time_zone")


class WaterLevelSensor(_SleepMeSensor):
    """Continuous water-level percent."""

    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="water_level",
            label="Water Level",
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["status"].get("water_level")


class EnvironmentHumiditySensor(_SleepMeSensor):
    """Tracker humidity measurement."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="environment_humidity",
            label="Environment Humidity",
            entity_category=None,
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["status"].get("environment_humidity")


class EnvironmentTemperatureSensor(_SleepMeSensor):
    """Tracker ambient temperature measurement."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="environment_temperature",
            label="Environment Temperature",
            entity_category=None,
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["status"].get("environment_temperature_c")


class BedTemperatureSensor(_SleepMeSensor):
    """Tracker bed temperature measurement."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="bed_temperature",
            label="Bed Temperature",
            entity_category=None,
        )

    @property
    def native_value(self) -> str | int | None:
        return self.coordinator.data["status"].get("bed_temperature_c")


class _TrackerTimestampSensor(_SleepMeSensor):
    """Base class for tracker timestamp diagnostics."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def _timestamp_value(self, key: str) -> datetime | None:
        value = self.coordinator.data["connectivity"].get(key)
        if not value:
            return None
        return dt_util.parse_datetime(value)


class LastConnectedAtSensor(_TrackerTimestampSensor):
    """Last time the tracker was seen connected to SleepMe."""

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
            suffix="last_connected_at",
            label="Last Connected",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._timestamp_value("last_connected_at")


class LastDisconnectedAtSensor(_TrackerTimestampSensor):
    """Last time the tracker was seen disconnected from SleepMe."""

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
            suffix="last_disconnected_at",
            label="Last Disconnected",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._timestamp_value("last_disconnected_at")


class UptimeSensor(_SleepMeSensor):
    """Tracker connection uptime in seconds."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT

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
            suffix="uptime",
            label="Uptime",
        )

    @property
    def native_value(self) -> Any:
        return self.coordinator.data["connectivity"].get("uptime")
