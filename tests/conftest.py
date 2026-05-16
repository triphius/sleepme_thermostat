"""Global fixtures for sleepme_thermostat tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the sleepme_thermostat custom integration in tests."""
    yield


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """Phase 0: tolerate lingering timers because the integration has no
    async_unload_entry yet (audit #7). The DataUpdateCoordinator's polling
    timer survives teardown. Phase 1 lands the unload and this fixture
    should be removed so the lingering-timer check protects future regressions.
    """
    return True


@pytest.fixture
def mock_sleepme_client() -> Generator[AsyncMock]:
    """Mock SleepMeClient so no real network calls happen.

    Patches both import sites:
      - custom_components.sleepme_thermostat.SleepMeClient   (used by __init__.py)
      - custom_components.sleepme_thermostat.update_manager.SleepMeClient
    so the coordinator's internal instantiation is also caught.
    """
    healthy_status = {
        "status": {
            "water_temperature_c": 22.0,
            "is_water_low": False,
            "is_connected": True,
        },
        "control": {
            "set_temperature_c": 22.0,
            "thermal_control_status": "standby",
            "brightness_level": 50,
            "display_temperature_unit": "c",
            "time_zone": "America/Mexico_City",
        },
        "about": {
            "firmware_version": "0.0.0-test",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "TEST-SERIAL",
            "ip_address": "192.168.1.100",
            "lan_address": "192.168.1.100",
        },
    }
    with (
        patch(
            "custom_components.sleepme_thermostat.SleepMeClient",
            autospec=True,
        ) as mock_init,
        patch(
            "custom_components.sleepme_thermostat.update_manager.SleepMeClient",
            autospec=True,
        ) as mock_um,
    ):
        for mock_cls in (mock_init, mock_um):
            instance = mock_cls.return_value
            instance.get_device_status = AsyncMock(return_value=healthy_status)
            instance.get_claimed_devices = AsyncMock(return_value=[])
            instance.set_temp_level = AsyncMock(return_value={})
            instance.set_device_status = AsyncMock(return_value={})
        yield mock_init.return_value
