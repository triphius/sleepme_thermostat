"""Tests for the SleepMeClient wrapper (sleepme.py).

Patches SleepMeAPI at the call boundary so we exercise the wrapper's:
  - half-degree rounding on set_temp_level
  - response-shape validation on get_device_status / get_claimed_devices
  - status whitelist on set_device_status
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.sleepme_thermostat.sleepme import SleepMeClient
from homeassistant.core import HomeAssistant


@pytest.fixture
def client(hass: HomeAssistant) -> Generator[SleepMeClient]:
    with patch(
        "custom_components.sleepme_thermostat.sleepme.SleepMeAPI",
        autospec=True,
    ) as mock_api_cls:
        mock_api_cls.return_value.api_request = AsyncMock()
        c = SleepMeClient(hass, "https://api.test/v1", "tok", "dev-1")
        yield c


async def test_set_temp_level_rounds_to_half(client: SleepMeClient) -> None:
    """24.3 -> 24.5 in PATCH payload."""
    client.api.api_request.return_value = {"ok": True}
    await client.set_temp_level(24.3)
    call = client.api.api_request.call_args
    assert call.args == ("PATCH", "devices/dev-1")
    assert call.kwargs["data"] == {"set_temperature_c": 24.5}


async def test_set_temp_level_passes_sentinel(client: SleepMeClient) -> None:
    """-1 (MAX COOL) survives round_half_up because rounding -1 is -1."""
    client.api.api_request.return_value = {"ok": True}
    await client.set_temp_level(-1)
    call = client.api.api_request.call_args
    assert call.kwargs["data"]["set_temperature_c"] == -1


async def test_set_device_status_rejects_unknown(client: SleepMeClient) -> None:
    with pytest.raises(ValueError, match=r"active.*standby"):
        await client.set_device_status("paused")


async def test_set_device_status_active(client: SleepMeClient) -> None:
    client.api.api_request.return_value = {"ok": True}
    await client.set_device_status("active")
    call = client.api.api_request.call_args
    assert call.args == ("PATCH", "devices/dev-1")
    assert call.kwargs["data"] == {"thermal_control_status": "active"}


async def test_set_device_status_standby(client: SleepMeClient) -> None:
    client.api.api_request.return_value = {"ok": True}
    await client.set_device_status("standby")
    call = client.api.api_request.call_args
    assert call.kwargs["data"] == {"thermal_control_status": "standby"}


async def test_get_claimed_devices_rejects_non_list(client: SleepMeClient) -> None:
    client.api.api_request.return_value = {"unexpected": "shape"}
    with pytest.raises(ValueError, match="unexpected response"):
        await client.get_claimed_devices()


async def test_get_device_status_rejects_non_dict(client: SleepMeClient) -> None:
    client.api.api_request.return_value = ["wrong", "shape"]
    with pytest.raises(ValueError, match="unexpected response"):
        await client.get_device_status()


async def test_get_claimed_devices_happy(client: SleepMeClient) -> None:
    client.api.api_request.return_value = [{"id": "dev-1", "name": "Ramon"}]
    result = await client.get_claimed_devices()
    assert result == [{"id": "dev-1", "name": "Ramon"}]


async def test_get_device_status_happy(client: SleepMeClient) -> None:
    payload = {"status": {}, "control": {}, "about": {}}
    client.api.api_request.return_value = payload
    result = await client.get_device_status()
    assert result == payload
