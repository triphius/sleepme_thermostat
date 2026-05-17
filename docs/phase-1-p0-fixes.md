# Phase 1 — P0 Fixes Plan

**Status:** Drafted 2026-05-16, awaiting maintainer approval before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md), [`phase-0-foundation.md`](./phase-0-foundation.md).

## Goal

Close every P0 audit finding (#1–#9, plus the related #26 close-method removal) in a single focused PR. After this phase:

1. The integration loads, reloads, and unloads cleanly on the live HA host.
2. Two SleepMe devices can be configured side-by-side without clobbering each other.
3. A rotated/invalidated API token surfaces as a user-actionable reauth prompt rather than silent stale data.
4. The transport layer behaves correctly under 429s (honors `Retry-After`, monotonically increasing backoff, no `UnboundLocalError`, no concurrency races).
5. The coordinator participates in HA's standard error/auth lifecycle (`UpdateFailed`, `ConfigEntryAuthFailed`) instead of swallowing exceptions and serving stale data forever.
6. The Phase 0 `xfail` regression trap (unload test) flips to a real pass, and the `expected_lingering_timers` fixture is removed.

Phase 1 explicitly does NOT touch `climate.py`'s verify-after-command loop (Phase 3), sensor `state→native_value` migration (Phase 2), options flow (Phase 2), or `strings.json` migration (Phase 2).

## Scope

| Audit # | File | Change |
|---|---|---|
| 1  | `__init__.py`      | Remove `_LOGGER.debug(f"API Token: {api_token}")`; redact any other secret-shaped log lines. |
| 2  | `sleepme_api.py`   | Move `asyncio.Lock()` to `__init__`; guard deque mutation and rate-limit wait correctly. |
| 3  | `sleepme_api.py`   | Track explicit attempt counter; backoff = `base * 2**(attempt-1)`; honor `Retry-After` on 429. |
| 4  | `sleepme_api.py`   | `initial_backoff` must be defined on every path that reaches `await asyncio.sleep(backoff_time)`. |
| 5  | `sleepme_api.py`   | GET-under-rate-limit: **raise `SleepMeRateLimited`**; do not silently return `{}`, do not queue. |
| 6  | `update_manager.py`| Raise `UpdateFailed` on transient errors; raise `ConfigEntryAuthFailed` on 401/403. Drop the silent last-good-status fallback. |
| 7  | `__init__.py`      | Add `async_unload_entry`; tear down coordinator + clear `hass.data[DOMAIN][entry.entry_id]`. |
| 8  | `__init__.py` + all platforms | Key `hass.data[DOMAIN]` by `entry.entry_id`; update every read site in `climate.py`, `binary_sensor.py`, `sensor.py`. |
| 9  | `config_flow.py`   | Add `async_step_reauth` + `async_step_reauth_confirm`; update entry data via `async_update_reload_and_abort`. |
| 26 | `sleepme_api.py`   | Delete `SleepMeAPI.close()` — `client` is HA's shared httpx instance. |
| —  | `tests/test_init.py`, `tests/conftest.py` | Flip unload `xfail` → pass; delete `expected_lingering_timers` fixture. |
| —  | `tests/`           | Add regression tests for reauth flow, coordinator auth-failure path, transport backoff/`Retry-After`. |

## Deliverables

### 1. Token-leak fix

**File:** `custom_components/sleepme_thermostat/__init__.py`

Drop these lines outright (lines 33–39):

```python
_LOGGER.debug(f"API URL: {api_url}")
_LOGGER.debug(f"API Token: {api_token}")
_LOGGER.debug(f"Device ID: {device_id}")
_LOGGER.debug(f"Firmware Version: {firmware_version}")
_LOGGER.debug(f"MAC Address: {mac_address}")
_LOGGER.debug(f"Model: {model}")
_LOGGER.debug(f"Serial Number: {serial_number}")
```

Replace with one line that logs *only* what's safe and useful:

```python
_LOGGER.debug(
    "Setting up entry %s for device %s (model=%s, fw=%s)",
    entry.entry_id, device_id, model, firmware_version,
)
```

Also audit:
- `sleepme_api.py:56` logs `params` and `data` — `data` for a PATCH does NOT contain the token (it contains setpoint/status). Token only appears in `headers["Authorization"]`. Keep `params`/`data` logs (useful for debugging), do not log `headers`.
- `config_flow.py:33` — `_LOGGER.debug(f"User input received: {user_input}")` logs the token from the form schema. Replace with `_LOGGER.debug("User submitted api token (length=%d)", len(user_input.get("api_token", "")))`.

**Diff shape:** ~10 lines removed, ~3 lines added in `__init__.py`; ~1 line changed in `config_flow.py`. No new files.

**API-budget impact:** none.

---

### 2. `async_unload_entry` + entry_id-keyed `hass.data`

**File:** `custom_components/sleepme_thermostat/__init__.py`

**Current storage shape (broken for multi-device):**
```python
hass.data[DOMAIN]["sleepme_controller"] = sleepme_controller       # global; clobbered
hass.data[DOMAIN][f"{device_id}_update_manager"] = update_manager  # per-device, OK
hass.data[DOMAIN]["device_info"] = {...}                           # global; clobbered
hass.data[DOMAIN][device_id] = thermostat                          # set in climate.py
```

**New storage shape:**
```python
hass.data[DOMAIN][entry.entry_id] = {
    "client": SleepMeClient,
    "coordinator": SleepMeUpdateManager,
    "device_info": {...},   # firmware_version, mac_address, model, serial_number
}
```

The per-platform `hass.data[DOMAIN][device_id] = thermostat` cross-platform handle goes away in Phase 2 (audit #10). For Phase 1, *do not* introduce it under `entry.entry_id` — the binary_sensor/sensor platforms can read `device_info` directly from the dict.

**Paste-ready `async_setup_entry`:**

```python
PLATFORMS = ["climate", "binary_sensor", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SleepMe Thermostat from a config entry."""
    api_url    = entry.data.get("api_url") or API_URL
    api_token  = entry.data["api_token"]
    device_id  = entry.data["device_id"]

    if not api_token or not device_id:
        raise ConfigEntryNotReady("API token or device ID missing from entry data")

    client = SleepMeClient(hass, api_url, api_token, device_id)
    coordinator = SleepMeUpdateManager(hass, api_url, api_token, device_id)

    # First refresh - propagates ConfigEntryAuthFailed / ConfigEntryNotReady.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "device_info": {
            "firmware_version": entry.data.get("firmware_version"),
            "mac_address":      entry.data.get("mac_address"),
            "model":            entry.data.get("model"),
            "serial_number":    entry.data.get("serial_number"),
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Entry %s set up for device %s", entry.entry_id, device_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
```

Notes:
- `coordinator.async_config_entry_first_refresh()` is what makes `ConfigEntryAuthFailed` from `_async_update_data` propagate as a reauth trigger; no extra plumbing needed in `__init__.py`.
- The `return False` on missing data is upgraded to `raise ConfigEntryNotReady` (audit #19) — small enough to ride along here; it's required anyway for `async_config_entry_first_refresh` semantics.
- The `coordinator`'s `DataUpdateCoordinator` base class handles its own polling-timer teardown when `async_unload_platforms` succeeds; we do not need to manually cancel `coordinator._unsub_refresh`.

**Cross-platform read sites (audit #8 fan-out):**

| File | Current | New |
|---|---|---|
| `climate.py:29`         | `coordinator = hass.data[DOMAIN][f"{device_id}_update_manager"]` | `coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]` |
| `climate.py:34`         | `hass.data[DOMAIN][device_id] = thermostat` | **delete this line** — `binary_sensor.py` and `sensor.py` get `device_info` from `entry.data` instead (see below). |
| `binary_sensor.py:13`   | `coordinator = hass.data[DOMAIN][f"{device_id}_update_manager"]` | `coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]` |
| `binary_sensor.py:17–25`| `thermostat = hass.data[DOMAIN].get(device_id); …persistent_notification.create…` | **delete this whole block.** Build a local `device_info` dict from `hass.data[DOMAIN][entry.entry_id]["device_info"]` and pass to the entity constructors directly. |
| `binary_sensor.py:45,65`| `self._attr_device_info = thermostat.device_info` | `self._attr_device_info = build_device_info(device_id, name, device_info_dict)` — a small helper. (The longer audit #10 cleanup — full `device_info` rebuild per platform — stays Phase 2. For Phase 1, only enough to get rid of the cross-platform handle.) |
| `sensor.py:13,17–25,55,75,96,116,137` | Same pattern as `binary_sensor.py`. | Same fix. |

A pragmatic compromise: keep the existing `thermostat.device_info` shape, but build that dict inside binary_sensor / sensor from `entry.data` + the stored `device_info` dict, not by reaching into the climate entity. New helper at the top of each platform:

```python
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
```

Yes, this duplicates the same helper across three platforms in Phase 1. Phase 2 (audit #10/#22) deduplicates. The cost of doing it once now and dedup-later is lower than the cost of building a shared utility in the same PR as the storage-shape change.

**Diff shape:** `__init__.py` ~30 lines added / ~20 removed (net +10). `climate.py` ~3 lines changed. `binary_sensor.py` ~15 lines changed (deletion + helper). `sensor.py` ~25 lines changed (5 entity classes × 5 lines each, mostly mechanical).

**API-budget impact:** none.

---

### 3. Coordinator: `UpdateFailed` + `ConfigEntryAuthFailed`

**File:** `custom_components/sleepme_thermostat/update_manager.py`

**Current behavior:** swallows every exception, falls back to `_last_valid_status`, returns `{}` on cold start. The entity stays "available," shows stale data, never tells the user anything is wrong.

**New behavior:** let HA's framework manage backoff and reauth. The coordinator's only job is fetch-or-fail-loudly.

**Paste-ready `_async_update_data`:**

```python
import httpx
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class SleepMeUpdateManager(DataUpdateCoordinator):
    """Manages data updates for SleepMe devices."""

    def __init__(self, hass, api_url, token, device_id):
        self.client = SleepMeClient(hass, api_url, token, device_id)
        self.device_id = device_id
        super().__init__(
            hass,
            _LOGGER,
            name=f"SleepMe Update Manager {device_id}",
            update_interval=timedelta(seconds=20),
        )

    async def _async_update_data(self) -> dict:
        try:
            device_status = await self.client.get_device_status()
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise ConfigEntryAuthFailed("Invalid or revoked SleepMe token") from err
            raise UpdateFailed(f"HTTP {err.response.status_code} from SleepMe API") from err
        except (httpx.RequestError, httpx.TimeoutException) as err:
            raise UpdateFailed(f"Cannot reach SleepMe API: {err}") from err
        except SleepMeRateLimited as err:
            # See deliverable 4. Transport raised this; HA backs off next interval.
            raise UpdateFailed("SleepMe API rate-limited; will retry next interval") from err
        except ValueError as err:
            # SleepMeAPI.handle_error currently raises ValueError("invalid_token") and
            # ValueError("cannot_connect"). Map them.
            if str(err) == "invalid_token":
                raise ConfigEntryAuthFailed("Invalid SleepMe token") from err
            raise UpdateFailed(str(err)) from err

        if not device_status:
            # After deliverable 4, an empty dict from the client should be impossible;
            # keep one defensive line anyway.
            raise UpdateFailed("Empty device status from SleepMe API")

        return {
            "status":  device_status.get("status", {}),
            "control": device_status.get("control", {}),
            "about":   device_status.get("about", {}),
        }
```

Drop `self._last_valid_status` entirely — the framework's `coordinator.last_update_success` + `coordinator.data` already give every consumer the right thing. Stale-data fallback was the root cause of "the integration looks healthy but nothing actually works."

Two upstream consequences that the coordinator can trust:
- `sleepme.py:get_device_status()` currently silently returns `{}` on unexpected response shapes. Tighten it: raise `UpdateFailed`-bait (e.g. let the underlying exception propagate). Concretely: change `if isinstance(response, dict): return response` else `return {}` to `if isinstance(response, dict): return response` else `raise ValueError(f"unexpected response: {response!r}")`.
- `sleepme.py:set_temp_level()` and `set_device_status()` are called from `climate.py`, not the coordinator. Phase 1 leaves their behavior alone (silent `{}` on empty response); Phase 3 reworks the climate command path entirely.

**Diff shape:** `update_manager.py` ~25 lines changed (mostly net negative). `sleepme.py` ~3 lines changed in `get_device_status`.

**API-budget impact:**
- **Per-minute idle:** unchanged. Coordinator still polls every 20s.
- **429 behavior:** *better.* Today's swallow-and-return-stale means the coordinator runs the next poll on schedule, hitting the rate limiter again; combined with the broken backoff inside the transport, this produces cascading 429s. With `UpdateFailed`, HA's `DataUpdateCoordinator` halves the polling rate after consecutive failures (built-in `_unsub_refresh` reschedule), naturally reducing pressure. Net effect: fewer API calls under sustained throttling, not more.
- **401/403 behavior:** *much better.* Today: poll forever, log an error every 20s, never recover. New: one call → reauth banner → user re-enters token → entry reloads → polling resumes.

---

### 4. Transport layer: lock + backoff + `Retry-After` + unbound-var + `close()` removal + GET-under-limit policy

**File:** `custom_components/sleepme_thermostat/sleepme_api.py`

This is the biggest single rewrite in Phase 1. Five bugs and one policy decision in the same file. Rewrite `SleepMeAPI` end-to-end; do not patch around the existing structure.

**Policy decision (audit #5): GET-under-rate-limit.**

Choose **(a) raise**, specifically a new `SleepMeRateLimited` exception that the coordinator catches and translates to `UpdateFailed`. Rationale:

- The maintainer's strong preference: "do not burn calls." Option (b), queueing inside the transport, can hold a coroutine for up to 60 seconds while the framework above (climate command path with its own retry-with-verify loop) is *also* timing out and retrying. That's the worst case: stacked latency without saving any API budget.
- The coordinator already has a rescheduling cadence (20s default, with HA's exponential reduction after failures). It is cheaper to let HA's framework decide when to retry than to invent a transport-level queue.
- The transport never knows whether a given GET is the coordinator's poll (drop is fine, framework will retry) or a one-shot like `get_claimed_devices()` (drop is bad, user gets stuck). Raising lets the caller decide.
- For `get_claimed_devices()` specifically (config flow), `SleepMeRateLimited` should surface as `cannot_connect` with a clear log line — the user can retry the config flow manually. That's better than silent `{}` → "no devices found" → user confused.

Same policy for PATCH requests under rate limit: raise rather than wait. The climate verify-after-command loop in Phase 1 still catches `Exception` and retries; the *real* climate refactor is Phase 3.

**Paste-ready `SleepMeAPI` rewrite:**

```python
"""HTTP transport for the SleepMe developer API.

Responsibilities:
- Authorize requests with bearer token.
- Rate-limit (sliding window, concurrency-safe via instance lock).
- Retry on 429 + 5xx with monotonically increasing backoff, honoring Retry-After.
- Surface auth failures (401/403) and connection failures as typed exceptions.

Does NOT:
- Queue requests when rate-limited. Raises SleepMeRateLimited; caller decides.
- Manage its own httpx client lifecycle. The client is HA's shared instance.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from email.utils import parsedate_to_datetime

import httpx
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

_LOGGER = logging.getLogger(__name__)

MAX_REQUESTS_PER_MINUTE = 9
RATE_LIMIT_WINDOW = 60          # seconds
DEFAULT_RETRIES = 3
BACKOFF_BASE_429 = 30           # seconds
BACKOFF_BASE_5XX = 10           # seconds
BACKOFF_BASE_TIMEOUT = 10       # seconds
BACKOFF_CEILING = 600           # seconds (10 min); Retry-After can exceed this -- we honor it anyway


class SleepMeAPIError(Exception):
    """Base for typed transport errors."""


class SleepMeAuthError(SleepMeAPIError):
    """401/403 from the API. Coordinator should raise ConfigEntryAuthFailed."""


class SleepMeRateLimited(SleepMeAPIError):
    """Local rate-limiter would have blocked the request. Caller decides retry."""


class SleepMeConnectionError(SleepMeAPIError):
    """Network-level failure. Coordinator should raise UpdateFailed."""


class SleepMeAPI:
    def __init__(
        self,
        hass: HomeAssistant,
        api_url: str,
        token: str,
        max_requests_per_minute: int = MAX_REQUESTS_PER_MINUTE,
    ) -> None:
        self.api_url = api_url
        self.token = token
        self.client = get_async_client(hass)
        self._request_times: deque[float] = deque(maxlen=max_requests_per_minute)
        self._lock = asyncio.Lock()  # instance-level — fixes audit #2

    # NOTE: no close() method — see audit #26. The httpx client is shared and
    # owned by HA.

    async def api_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        input_headers: dict | None = None,
        retries: int = DEFAULT_RETRIES,
    ):
        """Send one request with retry-on-transient-error.

        Raises:
            SleepMeAuthError on 401/403.
            SleepMeRateLimited if local rate limiter would block (no queueing).
            SleepMeConnectionError on network/timeout.
            httpx.HTTPStatusError on non-retriable HTTP errors (4xx other than 401/403/429).
        """
        attempt = 1
        while True:
            await self._enforce_local_rate_limit(method, endpoint)
            try:
                return await self._perform_request(
                    method, endpoint, params=params, data=data, input_headers=input_headers
                )
            except httpx.HTTPStatusError as err:
                status = err.response.status_code
                if status in (401, 403):
                    raise SleepMeAuthError(f"{status} from {endpoint}") from err
                if status == 429 and attempt <= retries:
                    backoff = self._compute_backoff(BACKOFF_BASE_429, attempt, err.response)
                    _LOGGER.warning(
                        "429 on %s %s; attempt %d/%d, sleeping %.1fs",
                        method, endpoint, attempt, retries, backoff,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                if status in (500, 502, 503, 504) and attempt <= retries:
                    backoff = self._compute_backoff(BACKOFF_BASE_5XX, attempt, err.response)
                    _LOGGER.warning(
                        "HTTP %d on %s %s; attempt %d/%d, sleeping %.1fs",
                        status, method, endpoint, attempt, retries, backoff,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                # Non-retriable / out of retries: let caller see the original exception.
                raise
            except httpx.TimeoutException as err:
                if attempt > retries:
                    raise SleepMeConnectionError(f"timeout on {endpoint}") from err
                backoff = BACKOFF_BASE_TIMEOUT * (2 ** (attempt - 1))
                _LOGGER.warning(
                    "Timeout on %s %s; attempt %d/%d, sleeping %.1fs",
                    method, endpoint, attempt, retries, backoff,
                )
                await asyncio.sleep(min(backoff, BACKOFF_CEILING))
                attempt += 1
            except httpx.RequestError as err:
                # DNS, connection refused, etc. Not worth retrying within this call;
                # coordinator's next poll will retry.
                raise SleepMeConnectionError(f"request error on {endpoint}: {err}") from err

    async def _enforce_local_rate_limit(self, method: str, endpoint: str) -> None:
        """Either record the current request or raise SleepMeRateLimited.

        Sliding window: if the deque is full and the oldest entry is within the
        60s window, we are at capacity. Per the deliberate policy (audit #5),
        we do not queue. The caller -- coordinator for GET, climate command path
        for PATCH -- decides what to do.
        """
        async with self._lock:
            now = time.monotonic()
            # Drop entries older than the window so the deque reflects reality.
            while self._request_times and now - self._request_times[0] >= RATE_LIMIT_WINDOW:
                self._request_times.popleft()

            if len(self._request_times) >= self._request_times.maxlen:
                wait = RATE_LIMIT_WINDOW - (now - self._request_times[0])
                _LOGGER.warning(
                    "Local rate limit hit on %s %s; would need to wait %.1fs. Rejecting.",
                    method, endpoint, wait,
                )
                raise SleepMeRateLimited(
                    f"{method} {endpoint}: local rate-limiter at capacity"
                )

            self._request_times.append(now)

    async def _perform_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None,
        data: dict | None,
        input_headers: dict | None,
    ):
        headers = dict(input_headers or {})
        headers["Authorization"] = f"Bearer {self.token}"
        response = await self.client.request(
            method,
            f"{self.api_url}/{endpoint}",
            headers=headers,
            json=data,
            params=params,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _compute_backoff(base: int, attempt: int, response: httpx.Response) -> float:
        """Resolve backoff seconds.

        Honors the server-provided Retry-After (integer seconds or HTTP-date).
        Falls back to base * 2**(attempt-1), capped at BACKOFF_CEILING.
        """
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                return float(int(ra))
            except ValueError:
                try:
                    target = parsedate_to_datetime(ra).timestamp()
                    return max(0.0, target - time.time())
                except (TypeError, ValueError):
                    _LOGGER.debug("Unparsable Retry-After: %r", ra)
        return min(base * (2 ** (attempt - 1)), BACKOFF_CEILING)
```

**Behavioral diff summary (audit ## 2, 3, 4, 5, 26):**

| # | Before | After |
|---|---|---|
| 2 | `async with asyncio.Lock():` — fresh lock per call, locks nothing. | `self._lock` created in `__init__`; sliding-window deque mutation is critical-section-protected. |
| 3 | `initial_backoff * 2**(retries-1)` with `retries` decrementing 3→1: produced 120/60/30s. | `base * 2**(attempt-1)` with `attempt` incrementing 1→3: produces 30/60/120s. Plus `Retry-After` override. |
| 4 | `initial_backoff` referenced before assignment for HTTPStatusError codes outside `{403, 429, 500, 502, 503, 504}`. | Variable replaced by explicit per-status branching. Non-matched statuses no longer reach the `await asyncio.sleep(backoff_time)` line. |
| 5 | GET-under-rate-limit → silent `return {}`. | GET-under-rate-limit → `raise SleepMeRateLimited`. Coordinator translates to `UpdateFailed`. |
| 26 | `close()` would close HA's shared httpx client. | Method removed. |

**Caller adjustments:**

- `sleepme.py:get_claimed_devices()` and `get_device_status()` currently swallow `ValueError("cannot_connect")` and `ValueError("invalid_token")` raised by the old `handle_error`. With the new typed exceptions, update `sleepme.py` to let `SleepMeAuthError` / `SleepMeConnectionError` / `SleepMeRateLimited` propagate. Coordinator catches them.
- `config_flow.py:async_step_user` catches `ValueError("invalid_token")`. Update it to catch `SleepMeAuthError` directly. Keep the existing string-based fallback for backward compat with the one transitional release (or just delete it — Phase 1 is the right time, since `sleepme_api.py` no longer raises bare `ValueError`).

**Diff shape:** `sleepme_api.py` is essentially rewritten — ~110 lines deleted, ~180 added (net +70). `sleepme.py` ~15 lines changed. `config_flow.py` ~5 lines changed. New exception classes are co-located in `sleepme_api.py`; do not introduce a separate `exceptions.py` in Phase 1.

**API-budget impact:**
- **Per-user-action delta:** 0 calls in the common case (no rate limit hit). When the local rate-limiter is at capacity, the user action now *fails fast* instead of waiting up to 60s. Phase 3 fixes the user-facing behavior of "set temperature failed because rate-limited" — Phase 1 just stops burning calls on doomed retries.
- **Per-minute idle delta:** 0 calls in steady state. Under 429-from-server, behavior is dominated by `Retry-After`. Old code: `30 → 60 → 120` (computed as `120, 60, 30` due to inverted math) before giving up = 3 wasted calls in 210s. New code: honors `Retry-After` (server's actual recovery window) up to 3 retries = at most 3 calls during the server's recovery window. If `Retry-After` says 300s, we wait 300s instead of retrying every 30s. **This is the biggest budget win in Phase 1.**
- **429 behavior:** strictly fewer wasted calls. Cannot be worse than today; in practice will be measurably better.

---

### 5. Reauth flow

**File:** `custom_components/sleepme_thermostat/config_flow.py`

**Trigger path:**
1. Coordinator's `_async_update_data` catches 401/403 → raises `ConfigEntryAuthFailed`.
2. HA framework moves the entry to `SETUP_ERROR` and dispatches `entry.async_start_reauth(hass)`.
3. HA looks up the config flow class on the integration, calls `async_step_reauth(entry_data)`.
4. User sees a repair-flow banner ("SleepMe Thermostat needs to re-authenticate"). Click → form.
5. User enters new token. We validate against the API. On success: update entry data, reload, dismiss.

**Paste-ready additions to `SleepMeThermostatConfigFlow`:**

```python
from homeassistant.config_entries import ConfigEntry, SOURCE_REAUTH


class SleepMeThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    def __init__(self) -> None:
        self.api_token: str = ""
        self.claimed_devices: list = []
        self._reauth_entry: ConfigEntry | None = None

    # ---- existing async_step_user / async_step_select_device unchanged ----

    async def async_step_reauth(self, entry_data: dict) -> FlowResult:
        """Begin reauth — token was rejected by the API."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> FlowResult:
        """Prompt for a new API token and validate it."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None

        if user_input is not None:
            new_token = user_input["api_token"]
            client = SleepMeClient(self.hass, API_URL, new_token)
            try:
                # Cheapest possible validation: list claimed devices.
                # We also confirm the existing device_id is still in the list,
                # so a user pasting a different account's token can't silently
                # break the existing entry.
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
            except (SleepMeConnectionError, SleepMeRateLimited, HTTPStatusError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("api_token"): str}),
            errors=errors,
        )
```

**Translation file additions (`translations/en.json` and `es.json`):**

```json
{
  "config": {
    "step": {
      "reauth_confirm": {
        "title": "Re-authenticate SleepMe Dock Pro",
        "description": "Your SleepMe API token is no longer valid. Enter a new token to reconnect.",
        "data": { "api_token": "API Token" }
      }
    },
    "error": {
      "device_not_found_for_token": "This token does not have access to the originally configured device."
    },
    "abort": {
      "reauth_successful": "Re-authentication was successful."
    }
  }
}
```

(`strings.json` migration is Phase 2 — for Phase 1, edit `en.json`/`es.json` directly to match the existing pattern.)

**Diff shape:** `config_flow.py` ~50 lines added, ~5 changed. Translation files ~15 lines added each.

**API-budget impact per reauth event:** 1 GET (`get_claimed_devices`) per token attempt. This is unavoidable — we have to confirm the token works before persisting it.

---

### 6. Tests covering the above

**Phase 1 test scope is deliberately narrow** — Phase 4 is the full testing phase. The rule for Phase 1 is: every behavior we fix must have at least one regression test, sized so that the next dormant period can't silently undo the work.

**New tests:**

1. **`tests/test_init.py::test_unload_entry`** — flip the existing `xfail` to a real assertion. No body changes needed beyond removing the `pytest.xfail(...)` line.

2. **`tests/test_init.py::test_multi_entry_isolation`** — set up two `MockConfigEntry` instances with distinct `entry_id` / `device_id`; assert both reach `LOADED`; assert `hass.data[DOMAIN]` has two distinct keys; unload one and assert the other is still loaded.

3. **`tests/test_coordinator.py`** (new file). Three tests:
   - `test_auth_failed_raises_reauth`: mock `client.get_device_status` to raise `httpx.HTTPStatusError` with status 401; assert `ConfigEntryAuthFailed` propagates from `_async_update_data` and `entry.state` ends in `SETUP_ERROR`; assert reauth flow has been started (`hass.config_entries.flow.async_progress_by_handler(DOMAIN)` is non-empty with `source == "reauth"`).
   - `test_transient_failure_raises_update_failed`: mock client to raise `httpx.TimeoutException`; assert `UpdateFailed` propagates; assert `coordinator.last_update_success is False`.
   - `test_rate_limited_raises_update_failed`: mock client to raise `SleepMeRateLimited`; same assertions.

4. **`tests/test_config_flow.py`** (new file). Three tests:
   - `test_happy_path` (small): two-step user flow → reaches `CREATE_ENTRY`. Verifies the existing flow still works after the typed-exception changes in deliverable 4.
   - `test_user_step_invalid_token`: `get_claimed_devices` raises `SleepMeAuthError`; assert form re-shows with `errors["base"] == "invalid_token"`.
   - `test_reauth_flow`: set up an entry, trigger `async_start_reauth`, submit form with new token, assert entry data updated and entry reloaded.

5. **`tests/test_sleepme_api.py`** (new file). Three tests, no real network:
   - `test_backoff_progression_monotonically_increases`: mock `client.request` to return a 429 response with no `Retry-After`; assert `asyncio.sleep` is called with 30, then 60, then 120 (use `patch("asyncio.sleep", AsyncMock())` and inspect call_args_list).
   - `test_honors_retry_after_integer`: mock 429 with `Retry-After: 7`; assert next `asyncio.sleep` is called with 7.
   - `test_get_under_rate_limit_raises`: fill the deque manually (`api._request_times.extend([time.monotonic()] * 9)`); call `api_request("GET", ...)`; assert raises `SleepMeRateLimited`.

**`tests/conftest.py` cleanup:** delete the `expected_lingering_timers` fixture entirely. After `async_unload_entry` lands, the coordinator's timer is canceled on unload, so the lingering-timer guard is correct as-is. If a test still trips it, that's a real bug to fix, not to suppress.

**Diff shape:**
- `tests/conftest.py`: ~10 lines deleted (the fixture).
- `tests/test_init.py`: ~3 lines changed (xfail removal), ~30 lines added (`test_multi_entry_isolation`).
- `tests/test_coordinator.py`: new, ~80 lines.
- `tests/test_config_flow.py`: new, ~120 lines.
- `tests/test_sleepme_api.py`: new, ~100 lines.

Approximate total: ~350 new test LOC. This is right-sized for Phase 1 — covers every Phase 1 behavior change, defers the broader sensor/climate coverage to Phase 4.

---

### 7. Lift Phase 0 workarounds

Two small but important loose ends:

1. **`tests/conftest.py` — delete the `expected_lingering_timers` fixture.** Covered in deliverable 6. Doc comment in the fixture today says "Phase 1 lands the unload and this fixture should be removed."
2. **`tests/test_init.py::test_unload_entry` — flip the `xfail` to a real pass.** Covered in deliverable 6.

3. **Pre-commit `files: ^tests/` scoping — defer flipping to Phase 2.** Justification: Phase 1 produces a mechanically dense diff inside `custom_components/` (transport rewrite + storage-shape change + reauth). Layering a "ruff/black format everything" reformat-only commit on top of that PR makes the diff hard to review and risks losing review attention to formatting rather than correctness. The right move: land Phase 1 as a behavior-only PR; Phase 2 opens with a single format-only commit (`ruff --fix custom_components/`, `black custom_components/`) followed by `files:` removal.

## API-call-budget analysis

| Scenario | Today | After Phase 1 | Delta |
|---|---|---|---|
| Idle, no errors, 1 device, 20s poll | 3 GET/min | 3 GET/min | 0 |
| Idle, no errors, 2 devices, 20s poll | 6 GET/min (but second device clobbered hass.data, second poll may also fail invisibly) | 6 GET/min, both polls real | now correctly accounts for the second device; not a regression |
| User drags slider once | 1 PATCH + (up to 3 GET in verify loop) | 1 PATCH + (up to 3 GET in verify loop) — *Phase 3 fixes this* | 0 in Phase 1 |
| Sustained 429 from server, no `Retry-After` | 30 + 60 + 120 = ~3 retries over 210s, then `{}` returned (silent fail) → coordinator retries 20s later | 30 + 60 + 120 = same 3 retries, then `UpdateFailed` → HA framework backs off polling (e.g. doubles interval) | Fewer wasted calls; framework handles long-tail backoff. |
| Sustained 429 from server, with `Retry-After: 300` | Ignored; 3 retries at 30/60/120s = 3 calls during the server's 300s recovery window — likely all 429 | Honored: first retry waits 300s; only 1 wasted call instead of 3 | **-2 calls per throttle event.** |
| Invalid token | Coordinator silently returns stale data forever; user sees no error; integration polls every 20s = 3 GET/min indefinitely | One GET → `ConfigEntryAuthFailed` → reauth banner → polling halted until user resolves | **Down to 0 calls/min after first failure.** |
| Reauth flow itself | N/A (no flow exists) | 1 GET per submitted token attempt | +1–N per reauth event (rare) |

**Net Phase 1 budget impact:**
- Steady state: 0 delta.
- Under 429 with `Retry-After`: strictly fewer calls.
- Under 401/403: dramatic reduction (poll stops until reauth).
- Per user action: 0 delta. The big climate-side win is Phase 3.

## Cross-platform read-site changes

Every file that reads `hass.data[DOMAIN]` needs updating. Full list:

| File | Line(s) | Current read | New read |
|---|---|---|---|
| `__init__.py` | 17, 46, 49, 53 | Sets `hass.data[DOMAIN]["sleepme_controller"]`, `hass.data[DOMAIN][f"{device_id}_update_manager"]`, `hass.data[DOMAIN]["device_info"]` | Sets `hass.data[DOMAIN][entry.entry_id] = {"client": ..., "coordinator": ..., "device_info": ...}` |
| `climate.py` | 29 | `hass.data[DOMAIN][f"{device_id}_update_manager"]` | `hass.data[DOMAIN][entry.entry_id]["coordinator"]` |
| `climate.py` | 34 | `hass.data[DOMAIN][device_id] = thermostat` | **delete** |
| `binary_sensor.py` | 13 | `hass.data[DOMAIN][f"{device_id}_update_manager"]` | `hass.data[DOMAIN][entry.entry_id]["coordinator"]` |
| `binary_sensor.py` | 17 | `hass.data[DOMAIN].get(device_id)` (the thermostat handle) | **delete** — read `device_info` dict from `hass.data[DOMAIN][entry.entry_id]["device_info"]` instead |
| `sensor.py` | 13 | same as binary_sensor.py:13 | same |
| `sensor.py` | 17 | same as binary_sensor.py:17 | same |

`binary_sensor.py` and `sensor.py` keep the same constructor signatures (`coordinator, thermostat, device_id, name`) for Phase 1, but `thermostat` becomes "a small `_device_info(...)` dict built locally" rather than "the climate entity." Phase 2 does the full constructor-signature cleanup (audit #10).

## Validation steps against live device

Maintainer's two devices (`Dock Pro Ramon`, `Dock Pro Chiva`) are currently `disabled_by: user`. The validation matrix below assumes both are re-enabled in sequence.

**Phase 1 validation checklist (executed by maintainer, against `100.88.154.98`):**

1. `make deploy-restart HA_HOST=100.88.154.98` — confirm `ha core restart` completes; tail `home-assistant.log` for `Entry <id> set up for device <device_id>` and absence of `Traceback`.
2. **Token-leak check.** Set log level for `custom_components.sleepme_thermostat` to `debug`. Reload entry. `grep -i "api token\|bearer" /config/home-assistant.log`. Expected: zero matches.
3. **Multi-device check.** Re-enable both `Dock Pro Ramon` and `Dock Pro Chiva`. Confirm both appear in `/config/.storage/core.config_entries` with state `loaded`. Confirm both have working `climate.*` entities reading distinct temperatures (i.e. one entry isn't shadowing the other — that's the multi-device clobber regression).
4. **Unload check.** Settings → Devices & Services → SleepMe → ... → "Delete" on `Dock Pro Chiva`; re-add via the existing flow. Confirm no `ha core restart` is needed. Confirm `Dock Pro Ramon` stays loaded throughout. This is the live-host version of `test_unload_entry`.
5. **Reauth check.** In the HA UI, edit the `Dock Pro Ramon` entry (or use `homeassistant.dev_tools` to corrupt `entry.data["api_token"]` directly — easier than rotating a real token). Wait one coordinator cycle (≤20s). Expect:
   - A repair-flow notification appears.
   - Clicking it opens the "Re-authenticate SleepMe Dock Pro" form (English text matches the new translation key).
   - Entering the *original* (valid) token submits → form closes → entry reloads → entities resume.
6. **Rate-limit dry run.** This is the hardest one to test in production without burning real API budget. Plan: rather than triggering real 429s, write a temporary test fixture that monkey-patches `SleepMeAPI.client.request` to return a `httpx.Response(429, headers={"Retry-After": "5"})` for the next N calls. Run in the test suite, not against live API. If a maintainer wants live confirmation, the cheapest path is to set `MAX_REQUESTS_PER_MINUTE = 2` in `const.py` as a temporary override and watch the local rate limiter kick in — confirms `SleepMeRateLimited` → `UpdateFailed` path end-to-end.
7. **Token-leak in logs (post-reauth).** After step 5, re-grep the log for the token value. Confirm the new (or pasted-back) token does not appear.

**Order of re-enabling devices:**
- Step 1: enable `Dock Pro Ramon` first; complete checks 1–5 against the single device.
- Step 2: enable `Dock Pro Chiva`; verify check 3 (multi-device isolation).
- Step 3: with both running, repeat check 5 (reauth) on `Dock Pro Chiva` to confirm reauth works per-entry, not globally.

## Acceptance / exit criteria

Every box must be checked before Phase 1 is declared done.

- [ ] `ruff check tests` and `black --check tests` pass.
- [ ] `mypy custom_components/sleepme_thermostat` passes (advisory mode unchanged from Phase 0).
- [ ] `pytest` passes including new tests in `test_coordinator.py`, `test_config_flow.py`, `test_sleepme_api.py`, and `test_init.py::test_multi_entry_isolation`.
- [ ] `tests/test_init.py::test_unload_entry` is no longer marked `xfail` and passes as a normal test.
- [ ] `tests/conftest.py` no longer defines `expected_lingering_timers`.
- [ ] `grep -i "api token\|bearer" custom_components/sleepme_thermostat/` returns no `_LOGGER.debug(...)` lines that interpolate the token.
- [ ] `SleepMeAPI.close()` is removed from `sleepme_api.py`.
- [ ] `SleepMeAPI._lock` is created in `__init__`, not inside `api_request`.
- [ ] Backoff progression test asserts 30/60/120 (monotonically increasing).
- [ ] `Retry-After` test asserts honored.
- [ ] `update_manager._async_update_data` raises `ConfigEntryAuthFailed` on 401/403 and `UpdateFailed` otherwise; no `try/except: return last_status` fallback remains.
- [ ] `__init__.py` defines `async_unload_entry`; `hass.data[DOMAIN]` is keyed by `entry.entry_id`.
- [ ] `climate.py`, `binary_sensor.py`, `sensor.py` read from `hass.data[DOMAIN][entry.entry_id]["coordinator"]`.
- [ ] `config_flow.py` has `async_step_reauth` + `async_step_reauth_confirm`; `en.json` and `es.json` updated.
- [ ] Maintainer ran the live-device validation checklist above (token redaction, multi-device, unload, reauth) — all 7 steps green.
- [ ] `docs/ROADMAP.md` Phase 1 table flipped ⬜ → ✅.
- [ ] HACS validate workflow, hassfest, CodeQL, and the Phase 0 `Test` workflow all green on the PR.

## Risks and open questions

1. **Coordinator's stale-data semantics.** Removing `_last_valid_status` means that on a single failed poll, `coordinator.data` is briefly `None` until the next successful one. `CoordinatorEntity` handles this — entities go `available=False` and re-render when data arrives. Phase 2 may want to revisit "should we hold last-good for X seconds before going unavailable?" but Phase 1 should not paper over the framework's behavior.

2. **`SleepMeAPI.api_request` retry loop now blocks inside the lock.** It doesn't — the lock is held only inside `_enforce_local_rate_limit`. *Double-check during implementation* that the `asyncio.sleep` calls for 429/timeout retries are outside the `async with self._lock` block. If a retry sleeps while holding the lock, every other in-flight request to the SleepMe API stalls.

3. **`Retry-After` precedence over local rate limiter.** If the server says "wait 300s" via `Retry-After`, we sleep 300s inside `api_request`. During that sleep, the local deque is *not* cleared — so a concurrent caller could hit the local rate limiter and raise `SleepMeRateLimited`. This is actually fine: the server is asking us to stop, so we should *also* be locally throttling. Document this in the transport docstring.

4. **`get_claimed_devices()` retries=1.** Today's config-flow call uses `retries=1`. With typed exceptions, `SleepMeAuthError` short-circuits — so retries only matter for 429/5xx during config flow. Decision: keep config-flow's retries=1; user can re-click the form.

5. **HA Core version of `ConfigEntryAuthFailed`.** Available since HA 2022.4. The pin (HA 2026.5.x) is well past that. No risk.

6. **Backwards-compatible config entry version.** `VERSION = 3` today. Phase 1 does not change `entry.data` schema. No `async_migrate_entry` needed. Phase 5 may remove `api_url` and `name` (audit P2 list), at which point version bumps.

7. **Two devices, shared rate limiter.** Each `SleepMeAPI` instance has its own `_request_times` deque. With two devices, we have two independent rate limiters → could collectively hit the per-account server-side rate limit. Out of scope for Phase 1; Phase 4/5 could share the deque across instances if observed in practice.

## Out of scope (explicit)

| Item | Phase |
|---|---|
| `climate.py` verify-after-command retry loop removal | 3 |
| Optimistic state + `async_request_refresh` after PATCH | 3 |
| `ServiceValidationError` on out-of-range temperatures | 3 |
| `min_temp` 12.5 → 12.78 | 3 |
| Sensor `state` → `native_value` migration | 2 |
| `_attr_has_entity_name = True` adoption | 2 |
| Options flow (poll interval) | 2 |
| `strings.json` source-of-truth migration | 2 |
| `async_step_import` removal | 2 |
| `hass.components.persistent_notification.create` replacement | 2 (already deleted in Phase 1 via the cross-platform handle removal, but the broader pattern audit stays Phase 2) |
| `diagnostics.py` platform | 5 |
| `round_half_up` deduplication | 3 |
| Flipping pre-commit `files: ^tests/` to full repo | 2 |
| Coverage gate at ≥ 75% | 4 |
| Multi-version HA test matrix | 4 |
| Logging f-string → lazy `%s` everywhere | 2 (Phase 1 only changes lines it's already touching) |
| Sharing rate-limiter deque across `SleepMeAPI` instances | 4/5 if needed |
