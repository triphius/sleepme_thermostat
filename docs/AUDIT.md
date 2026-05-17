# SleepMe Thermostat — Quality Audit

**Date:** 2026-05-16
**Subject:** `custom_components/sleepme_thermostat/` at commit `6477b77`
**Status:** Reference document. Findings here are the baseline used to populate `ROADMAP.md`. Update this doc only when re-auditing the codebase (not when fixing individual items — track that in `ROADMAP.md`).

---

## 1. Goal of this effort

The integration is published to HACS and has real users, but went dormant after being written with mixed technical expertise. Before we add features or cut another release, we want a clear, honest picture of:

- Where we stand (what works, what's brittle, what's broken).
- What separates the current state from "I'd put my name on this in production."
- A phased, priority-driven path to get there — not a refactor-everything-at-once rewrite.

Validation target throughout: the maintainer's own SleepMe Dock Pro device running against a live Home Assistant install.

## 2. The central design constraint: API rate limiting

The sleep.me developer API is aggressively rate limited. Historically the integration suffered cascading 429s — once throttled, retries piled up, and the user-observable latency between "set temperature on the dashboard" and "Dock Pro actually responding" grew long and unpredictable.

**Every refactor decision below is filtered through one question: does this increase or decrease API call volume?** Anywhere we currently spend extra calls (verify-after-command loops, redundant refreshes, fixed retry curves that don't honor `Retry-After`), we should be looking to remove them or make them strictly optional.

## 3. Architecture snapshot

```
custom_components/sleepme_thermostat/
├── __init__.py          # setup_entry; stores client + coordinator in hass.data (not entry_id-keyed)
├── manifest.json        # version 3.2.2, integration_type=device, iot_class=cloud_polling
├── const.py             # API URL, preset sentinels (-1, 999)
├── config_flow.py       # 2-step: token → device picker; VERSION = 3; no reauth, no options
├── sleepme_api.py       # HTTP transport: rate limit (broken) + retry/backoff (inverted)
├── sleepme.py           # SleepMeClient: high-level API methods
├── update_manager.py    # DataUpdateCoordinator (20s poll); swallows errors silently
├── climate.py           # ClimateEntity + per-command retry-with-verify loop (up to ~5min)
├── binary_sensor.py     # water_low + connected — borrows device_info from climate
├── sensor.py            # IP, LAN, brightness, display unit, time zone — uses deprecated state
└── translations/        # en.json, es.json (no strings.json source)
```

**Layering:** transport → client → coordinator → entities. Sound on paper. Two structural issues:

1. `binary_sensor.py` and `sensor.py` reach into `hass.data[DOMAIN][device_id]` to copy `device_info` from the climate entity — creating setup-order coupling.
2. `hass.data` storage is keyed globally (not by `entry.entry_id`), so a second Dock Pro on the same HA instance would clobber the first.

## 4. Strengths

- ✅ Clean separation of API transport vs. client vs. coordinator.
- ✅ Uses `DataUpdateCoordinator` — the canonical HA pattern.
- ✅ Unique IDs on every entity.
- ✅ Device registry grouping works (one device → many entities).
- ✅ 2-step config flow with device discovery (no manual device-ID entry).
- ✅ Two-language translations (en, es).
- ✅ HACS validation + hassfest + CodeQL in CI.
- ✅ HACS-compatible directory structure with `hacs.json`.
- ✅ Uses HA's shared httpx client via `get_async_client`.
- ✅ Sets `unique_id` and aborts duplicate configuration.

## 5. Findings

### P0 — Security / blocking

| # | File:Line | Issue |
|---|---|---|
| 1 | `__init__.py:34` | **API token logged in plain text** at DEBUG level (`_LOGGER.debug(f"API Token: {api_token}")`). Credential leak whenever debug logging is enabled. |
| 2 | `sleepme_api.py:24` | **`asyncio.Lock()` instantiated inside the call.** A fresh lock per invocation locks nothing — the rate limiter is not concurrency-safe. |
| 3 | `sleepme_api.py:96` | **Backoff math is inverted.** With `retries=3`, first backoff is `30 × 2² = 120s`, then 60s, then 30s — decreasing instead of increasing. |
| 4 | `sleepme_api.py:96` | **`initial_backoff` can be referenced before assignment** for errors that fall through the `if/elif` chain → `UnboundLocalError`. |
| 5 | `sleepme_api.py:32` | **GET requests silently discarded under rate limit** (returns `{}`). Setup-time `get_claimed_devices()` could fail invisibly. |
| 6 | `update_manager.py:53` | **All exceptions swallowed** in `_async_update_data`. Should raise `UpdateFailed`. Auth failures (401/403) should raise `ConfigEntryAuthFailed` to trigger reauth. |
| 7 | `__init__.py` | **No `async_unload_entry`.** Cannot reload or remove the integration without restarting HA. |
| 8 | `__init__.py:46-58` | **`hass.data` not keyed by `entry.entry_id`.** Two devices on one HA would overwrite each other's controller and `device_info`. |
| 9 | `config_flow.py` | **No reauth flow.** If the SleepMe token rotates, the user must delete and re-add the integration. |

### P1 — Correctness / UX

| # | File:Line | Issue |
|---|---|---|
| 10 | `binary_sensor.py:17`, `sensor.py:17` | Cross-platform coupling: pulling `device_info` from the climate entity creates a setup-order dependency. Build `device_info` from entry data directly. |
| 11 | `binary_sensor.py:21`, `sensor.py:21` | `hass.components.persistent_notification.create(...)` — **deprecated API**, emits warnings / will break. |
| 12 | `sensor.py` (all classes) | Uses `state` property — **deprecated** for `SensorEntity`. Use `native_value`. |
| 13 | `sensor.py:82-101` | `BrightnessLevelSensor` lacks `state_class = MEASUREMENT` so it won't appear in long-term statistics. |
| 14 | All entities | Missing `_attr_has_entity_name = True`. Entities get long names like "Dock Pro Bedroom IP Address" instead of clean "IP Address" under "Dock Pro Bedroom". |
| 15 | `climate.py:65-104` | **Verify-after-command loop blocks up to ~5 minutes** per service call (3 × ~127s). Burns extra API calls and produces a long UI spinner. *Direct hit on the rate-limit problem.* |
| 16 | `climate.py:177-180` | Out-of-range temp silently returns; should raise `ServiceValidationError`. |
| 17 | `climate.py:122-128, 225-229` | Preset detection via magic sentinel values (-1, 999) is brittle; `target_temperature` returns `None` to signal "in preset", which collides with "unknown". |
| 18 | `climate.py:107-112` | `min_temp=12.5` is slightly below the documented 12.78°C (55°F) bound. |
| 19 | `__init__.py:24-43` | Returns `False` on missing data; should raise `ConfigEntryNotReady`. |
| 20 | `manifest.json` | Missing `quality_scale`, `loggers`. |
| 21 | `config_flow.py:120-122` | `async_step_import` is dead code (YAML import deprecated). |
| 22 | `climate.py`, `sleepme.py` | `round_half_up` duplicated across modules. |
| 23 | Throughout | All logging uses f-strings. Use lazy `%s` so messages aren't formatted when log level is off. |
| 24 | `climate.py:158-162` | `extra_state_attributes` duplicates what's already exposed as binary sensors. |
| 25 | `climate.py:51` | `connections={("mac", ...)}` should use `CONNECTION_NETWORK_MAC`. |
| 26 | `sleepme_api.py:104-108` | `close()` would close HA's **shared** httpx client. Bug if ever invoked — remove the method. |

### P2 — Polish / quality scale

- No `strings.json` source — translations are written to `en.json`/`es.json` directly. Modern HA generates language files from `strings.json`.
- No `diagnostics.py` (no "Download diagnostics" button in HA UI).
- No `tests/` directory. Required for HA quality scale Silver and above.
- No `pyproject.toml`, no ruff/black/mypy, no pre-commit.
- No `LICENSE` file (README claims MIT).
- `api_url` stored in `entry.data` but always equal to the same constant — dead state.
- `name` stored in `entry.data` duplicates `entry.title`.
- HACS validate workflow uses `hassfest@master` — should be a pinned tag.

## 6. Verdict

The integration is **not ready for a production-quality release** at v3.2.2. Each P0 item is small (most are <1h fixes), but together they need a focused refactor pass. A single-device user on a quiet network won't hit most of them — which explains why the project survived dormant for so long — but the SleepMe Thermostat brand should not be on this in its current state.

## 7. What this audit does not cover

- Real-device latency/throughput measurements. Will be done as part of Phase 1 acceptance, against the maintainer's Dock Pro.
- The sleep.me API contract beyond what's exercised by the current client. We have not, for example, characterized actual 429 `Retry-After` header behavior.
- Comparison with the more active forks of this integration (e.g. derekcentrico's branch). Worth a follow-up.

## 8. Re-audit triggers

Refresh this document when:
- Any P0 or P1 finding is closed or invalidated.
- HA breaks an API the integration depends on.
- We pick up significant changes from upstream forks.
