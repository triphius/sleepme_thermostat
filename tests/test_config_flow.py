"""Config flow tests: happy path, invalid token, reauth."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.sleepme_thermostat.const import API_URL, DOMAIN
from custom_components.sleepme_thermostat.sleepme_api import (
    SleepMeAuthError,
    SleepMeConnectionError,
)
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.const import MOCK_API_TOKEN, MOCK_DEVICE_ID, MOCK_NAME


@pytest.fixture
def mock_flow_client():
    """Patch the SleepMeClient used by config_flow."""
    with patch(
        "custom_components.sleepme_thermostat.config_flow.SleepMeClient",
        autospec=True,
    ) as mock_cls:
        instance = mock_cls.return_value
        instance.get_claimed_devices = AsyncMock(
            return_value=[{"id": MOCK_DEVICE_ID, "name": MOCK_NAME}]
        )
        instance.get_device_status = AsyncMock(
            return_value={
                "about": {
                    "firmware_version": "1.0",
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "model": "Dock Pro",
                    "serial_number": "SN-1",
                }
            }
        )
        yield instance


async def test_happy_path(hass: HomeAssistant, mock_flow_client: AsyncMock) -> None:
    """User flow reaches CREATE_ENTRY with expected data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": MOCK_API_TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_id": MOCK_DEVICE_ID}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Dock Pro {MOCK_NAME}"
    assert result["data"]["api_token"] == MOCK_API_TOKEN
    assert result["data"]["device_id"] == MOCK_DEVICE_ID
    assert result["data"]["model"] == "Dock Pro"


async def test_user_step_invalid_token(
    hass: HomeAssistant, mock_flow_client: AsyncMock
) -> None:
    """SleepMeAuthError on the user step surfaces as errors['base']='invalid_token'."""
    mock_flow_client.get_claimed_devices.side_effect = SleepMeAuthError("403")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": "bad-token"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_token"}


async def test_user_step_cannot_connect(
    hass: HomeAssistant, mock_flow_client: AsyncMock
) -> None:
    """Connection failure surfaces as errors['base']='cannot_connect'."""
    mock_flow_client.get_claimed_devices.side_effect = SleepMeConnectionError("dns")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": MOCK_API_TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow(hass: HomeAssistant, mock_flow_client: AsyncMock) -> None:
    """Reauth: existing entry, new token validated, entry updated and aborted as success."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_reauth",
        version=3,
        unique_id=MOCK_DEVICE_ID,
        title=f"Dock Pro {MOCK_NAME}",
        data={
            "api_url": API_URL,
            "api_token": "old-token",
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            "firmware_version": "1.0",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "SN-1",
        },
    )
    entry.add_to_hass(hass)

    # Start the reauth flow as if HA's framework triggered it.
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Submit a new token; mock_flow_client.get_claimed_devices returns the same device_id.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": "new-token"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_token"] == "new-token"


async def test_reauth_token_for_other_account(
    hass: HomeAssistant, mock_flow_client: AsyncMock
) -> None:
    """Token that doesn't have access to the configured device_id is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_other_acct",
        version=3,
        unique_id=MOCK_DEVICE_ID,
        title=f"Dock Pro {MOCK_NAME}",
        data={
            "api_url": API_URL,
            "api_token": "old-token",
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            "firmware_version": "1.0",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "SN-1",
        },
    )
    entry.add_to_hass(hass)

    # New token returns a *different* device list — doesn't include our device_id.
    mock_flow_client.get_claimed_devices.return_value = [
        {"id": "other-device", "name": "Other"}
    ]

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": "different-account-token"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "device_not_found_for_token"}
    assert entry.data["api_token"] == "old-token"  # unchanged


async def test_reauth_invalid_token(
    hass: HomeAssistant, mock_flow_client: AsyncMock
) -> None:
    """SleepMeAuthError on the reauth step surfaces as invalid_token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_invalid",
        version=3,
        unique_id=MOCK_DEVICE_ID,
        title=f"Dock Pro {MOCK_NAME}",
        data={
            "api_url": API_URL,
            "api_token": "old-token",
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            "firmware_version": "1.0",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "SN-1",
        },
    )
    entry.add_to_hass(hass)

    mock_flow_client.get_claimed_devices.side_effect = SleepMeAuthError("403")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_token": "still-bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}
