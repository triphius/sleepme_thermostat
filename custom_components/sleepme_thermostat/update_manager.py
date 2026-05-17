"""DataUpdateCoordinator for SleepMe devices.

Translates transport-layer typed exceptions into HA framework exceptions:
- 401/403 (SleepMeAuthError) -> ConfigEntryAuthFailed (triggers reauth flow)
- transient/rate-limit/connection -> UpdateFailed (HA backs off polling)

No stale-data fallback: if a poll fails, HA's framework handles the entity
availability semantics (CoordinatorEntity flips to unavailable until the next
successful update).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .sleepme import SleepMeClient
from .sleepme_api import (
    SleepMeAuthError,
    SleepMeConnectionError,
    SleepMeRateLimited,
)

_LOGGER = logging.getLogger(__name__)


class SleepMeUpdateManager(DataUpdateCoordinator):
    """Manages data updates for a single SleepMe device."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_url: str,
        token: str,
        device_id: str,
    ) -> None:
        self.client = SleepMeClient(hass, api_url, token, device_id)
        self.device_id = device_id
        super().__init__(
            hass,
            _LOGGER,
            name=f"SleepMe Update Manager {device_id}",
            update_interval=timedelta(seconds=20),
        )

    async def _async_update_data(self) -> dict:
        """Fetch the latest device status. Raise typed framework exceptions on failure."""
        try:
            device_status = await self.client.get_device_status()
        except SleepMeAuthError as err:
            raise ConfigEntryAuthFailed("Invalid or revoked SleepMe API token") from err
        except SleepMeRateLimited as err:
            raise UpdateFailed(
                "SleepMe API rate-limited; will retry next interval"
            ) from err
        except SleepMeConnectionError as err:
            raise UpdateFailed(f"Cannot reach SleepMe API: {err}") from err
        except httpx.HTTPStatusError as err:
            # Non-401/403/429/5xx HTTP errors that transport let through.
            raise UpdateFailed(
                f"HTTP {err.response.status_code} from SleepMe API"
            ) from err
        except ValueError as err:
            raise UpdateFailed(str(err)) from err

        return {
            "status": device_status.get("status", {}),
            "control": device_status.get("control", {}),
            "about": device_status.get("about", {}),
        }
