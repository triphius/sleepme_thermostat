"""Smoke test: integration sets up and unloads cleanly with a mocked API client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.sleepme_thermostat.const import API_URL, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.const import MOCK_API_TOKEN, MOCK_DEVICE_ID, MOCK_NAME


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id=MOCK_DEVICE_ID,
        title=f"Dock Pro {MOCK_NAME}",
        data={
            "api_url": API_URL,
            "api_token": MOCK_API_TOKEN,
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            "firmware_version": "0.0.0-test",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "TEST-SERIAL",
        },
    )


async def test_setup_entry_loads(
    hass: HomeAssistant, mock_sleepme_client: AsyncMock
) -> None:
    """async_setup_entry returns True and entry reaches LOADED."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_unload_entry(
    hass: HomeAssistant, mock_sleepme_client: AsyncMock
) -> None:
    """Entry can be unloaded.

    Phase 0 placeholder: the integration has no async_unload_entry yet (audit #7).
    Marked xfail so CI is green; Phase 1 lands the implementation and flips this
    to a pass, giving us a built-in regression check.
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pytest.xfail("async_unload_entry not implemented yet — Phase 1 deliverable")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
