"""Config flow for SleepMe Thermostat."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.data_entry_flow import FlowResult

from .const import API_URL, DOMAIN
from .sleepme import SleepMeClient
from .sleepme_api import (
    SleepMeAuthError,
    SleepMeConnectionError,
    SleepMeRateLimited,
)

_LOGGER = logging.getLogger(__name__)


class SleepMeThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SleepMe Thermostat."""

    VERSION = 3

    def __init__(self) -> None:
        self.api_token: str = ""
        self.claimed_devices: list = []
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    def _schema(api_token: str = "") -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("api_token", default=api_token): str,
            }
        )

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "User submitted api token (length=%d)",
                len(user_input.get("api_token", "")),
            )
            self.api_token = user_input.get("api_token")

            client = SleepMeClient(self.hass, API_URL, self.api_token)

            try:
                self.claimed_devices = await client.get_claimed_devices()
                if not self.claimed_devices:
                    errors["base"] = "no_devices_found"
                else:
                    return await self.async_step_select_device()
            except SleepMeAuthError:
                errors["base"] = "invalid_token"
            except (SleepMeRateLimited, SleepMeConnectionError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error fetching claimed devices")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(self.api_token),
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None) -> FlowResult:
        """Step 2: select a device from the list of claimed devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input["device_id"]
            name = self.context["claimed_devices_dict"][device_id]

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            client = SleepMeClient(self.hass, API_URL, self.api_token, device_id)

            try:
                device_status = await client.get_device_status()
                return self.async_create_entry(
                    title=f"Dock Pro {name}",
                    data={
                        "api_url": API_URL,
                        "api_token": self.api_token,
                        "device_id": device_id,
                        "name": name,
                        "firmware_version": device_status.get("about", {}).get(
                            "firmware_version"
                        ),
                        "mac_address": device_status.get("about", {}).get(
                            "mac_address"
                        ),
                        "model": device_status.get("about", {}).get("model"),
                        "serial_number": device_status.get("about", {}).get(
                            "serial_number"
                        ),
                    },
                )
            except SleepMeAuthError:
                errors["base"] = "invalid_token"
            except (SleepMeRateLimited, SleepMeConnectionError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Error fetching device status")
                errors["base"] = "cannot_fetch_device_info"

        if self.claimed_devices:
            self.context["claimed_devices_dict"] = {
                device["id"]: device["name"] for device in self.claimed_devices
            }
        else:
            errors["base"] = "no_devices_found"

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): vol.In(
                        self.context["claimed_devices_dict"]
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Reauth triggered by coordinator raising ConfigEntryAuthFailed."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> FlowResult:
        """Prompt for a new API token and validate it against the API."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None

        if user_input is not None:
            new_token = user_input["api_token"]
            client = SleepMeClient(self.hass, API_URL, new_token)
            try:
                claimed = await client.get_claimed_devices()
                existing_device_id = self._reauth_entry.data["device_id"]
                if not any(d.get("id") == existing_device_id for d in claimed):
                    errors["base"] = "device_not_found_for_token"
                else:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data={**self._reauth_entry.data, "api_token": new_token},
                        reason="reauth_successful",
                    )
            except SleepMeAuthError:
                errors["base"] = "invalid_token"
            except (SleepMeRateLimited, SleepMeConnectionError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("api_token"): str}),
            errors=errors,
        )
