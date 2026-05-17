I have all the context I need. Now I'll produce the Phase 3 plan.

---

# Phase 3 — Climate Refactor Plan

**Status:** Drafted 2026-05-17, awaiting maintainer approval before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md), [`phase-0-foundation.md`](./phase-0-foundation.md), [`phase-1-p0-fixes.md`](./phase-1-p0-fixes.md), [`phase-2-modernization.md`](./phase-2-modernization.md).

## Goal

Replace the climate command path's verify-after-command retry loop with a one-shot PATCH + optimistic state model. After Phase 3, dragging the temperature slider in the HA UI costs **1 PATCH** (happy path) — not the current PATCH + sleep(10) + GET + (optionally PATCH + sleep(127) + GET) × up to 3 attempts. Out-of-range values raise a clean `ServiceValidationError` instead of silently no-op-ing. Preset-mode encoding stops abusing sentinel temperatures (-1, 999) as control-plane signals. Two utility helpers (`round_half_up`, `build_device_info`) consolidate into a single module.

Phase 3 is the **biggest behavioral change of the audit**: the visible latency between user action and physical device response is bounded by the SleepMe API's own propagation time, not by integration retry curves.

Phase 3 explicitly does NOT touch transport / coordinator (Phase 1), options flow shape (Phase 2), diagnostics platform (Phase 5), `entry.data` schema drops (Phase 5), HA version matrix or coverage gate (Phase 4), `black → ruff format` migration (Phase 4), `quality_scale: silver` (Phase 5).

## Cross-cutting concern: API budget per user action

Today's path inside `SleepMeThermostat._async_api_command_with_retry`:

1. PATCH `/devices/{id}` (1 call)
2. `asyncio.sleep(10)` — `POST_COMMAND_DELAY`
3. `coordinator.async_request_refresh()` → GET (1 call)
4. Verify against `coordinator.data`; if false:
5. `asyncio.sleep(127)` — `RETRY_DELAY` — and goto 1, up to 3 attempts.

Worst case = **3 PATCH + 3 GET + ~5 min spinner per user action**.

Best case = **1 PATCH + 1 GET + 10 s spinner per user action**.

After Phase 3, both cases collapse to:

- Best case = **1 PATCH** (the next natural coordinator poll, which would have happened anyway, reconciles).
- "Snappy" case = **1 PATCH + 1 GET** (PATCH followed by one `async_request_refresh()` for faster UI feedback than the natural poll cadence). This is the target behavior.
- Worst case under transport failure = **1 PATCH** that raises `SleepMeRateLimited` / `SleepMeAuthError` / `SleepMeConnectionError` → `HomeAssistantError` toast in HA UI. No retry, no extra GET.

Every deliverable below reports its expected API-call delta. The phase-level summary table sits in §"API-call-budget analysis."

## Scope

Audit items reconciled against current `main` (post-Phase-1, post-Phase-2):

| Audit # | File | Current state | Phase 3 action |
|---|---|---|---|
| 15 | `climate.py:65–121, 188–240` | `_async_api_command_with_retry` runs `PATCH → sleep(10) → request_refresh → verify → sleep(127)`, up to 3 attempts. | **Delete** the helper. Replace command paths with: PATCH → optimistic write → `async_request_refresh()`. |
| 16 | `climate.py:196–204` | Out-of-range: `_LOGGER.warning(...)` then `return` — silent failure. | Raise `ServiceValidationError` with translation key `temperature_out_of_range`. |
| 17 | `climate.py:122–128 + 225–229 + 264–281`, `const.py:9–12` | `PRESET_TEMPERATURES = {MAX_COOL: -1, MAX_HEAT: 999}`. `_sanitize_temperature` returns `None` when set-point equals a sentinel. `target_temperature` returns `None` to signal "in preset", colliding with "unknown." `_determine_preset_mode` re-derives the preset from the same sentinel. | Track `_attr_preset_mode` explicitly. Persist across restart via `RestoreEntity`. PATCH payloads send the clamped real temperature, not -1/999. `target_temperature` returns the actual setpoint at all times. Sentinels in `const.py` are deleted; `PRESET_TEMPERATURES` becomes `PRESET_TARGET_TEMPERATURES = {MAX_COOL: <min>, MAX_HEAT: <max>}` (numeric, real). |
| 18 | `climate.py:124` | `min_temp` returns `12.5`. | Change to `12.78` (the documented hardware bound, 55 °F). |
| 22 | `climate.py:25–27`, `sleepme.py:19–21` | `round_half_up` defined identically in both. | Move to a new module `helpers.py`. Both files import from there. |
| 24 | `climate.py:177–181` | `extra_state_attributes` exposes `is_water_low` + `is_connected` — already separate binary_sensors. | **Delete** the property entirely. |
| — | `binary_sensor.py:17–26`, `sensor.py:17–26` | `_device_info()` helper duplicated in both files (Phase 2 deferred dedup). | Move to `helpers.py` as `build_device_info`. Both files plus `climate.py` import it. |
| 25 | `climate.py:13, 61` | `from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC` already imported and used. | **Verified closed.** No action. |

## Deliverables

### 1. Investigate SleepMe API behavior with sentinel values (preflight)

**STATUS: NO LONGER NEEDED.** The official API docs at <https://docs.developer.sleep.me/api/> document the sentinels explicitly:

> `set_temperature_c` accepts `-1.0`, half-degree increments in `13.0..48.0`, or `999.0`. `-1` = MAX COLD; `999` = MAX HEAT.

This is an API-contract feature, not an integration hack. **Design A from §5 is correct by spec.** No probe required. Decision recorded in `ROADMAP.md` decisions log.

**Original goal (preserved for historical context):** confirm whether the SleepMe developer API stores `-1` and `999` verbatim when sent in `set_temperature_c`, or clamps them to the physical bounds.

**Recon steps** (maintainer executes against the live Dock Pro before opening the Phase 3 PR; takes <5 min):

```bash
# Capture before-state.
ssh hassio@100.88.154.98 'curl -s -H "Authorization: Bearer <REDACTED>" \
  https://api.developer.sleep.me/v1/devices/<device_id>' | jq '.control.set_temperature_c'

# Send the sentinel.
ssh hassio@100.88.154.98 'curl -s -X PATCH \
  -H "Authorization: Bearer <REDACTED>" -H "Content-Type: application/json" \
  -d "{\"set_temperature_c\": -1}" \
  https://api.developer.sleep.me/v1/devices/<device_id>' | jq

# Wait ~20s for the device to settle. Capture after-state.
ssh hassio@100.88.154.98 'curl -s -H "Authorization: Bearer <REDACTED>" \
  https://api.developer.sleep.me/v1/devices/<device_id>' | jq '.control.set_temperature_c'
```

**Possible outcomes:**

| `set_temperature_c` after PATCH | Interpretation |
|---|---|
| `-1`                  | API stores the sentinel verbatim. *Design A is viable.* Design B still cleaner. |
| `12.78` (or similar)  | API clamps to physical min. *Design A is broken*; must use Design B. |
| HTTP 400              | API rejects sentinel outright. Must use Design B and PATCH a real clamped temp. |
| Same as before        | API ignored the request silently. Must use Design B. |

**Restore the device** after the probe:

```bash
# Reset to whatever the user had before the test.
ssh hassio@100.88.154.98 'curl -s -X PATCH \
  -H "Authorization: Bearer <REDACTED>" -H "Content-Type: application/json" \
  -d "{\"set_temperature_c\": <original_value>}" \
  https://api.developer.sleep.me/v1/devices/<device_id>'
```

**Document the outcome** in `docs/ROADMAP.md` Decisions log:

> *2026-MM-DD:* Confirmed SleepMe API behavior for `set_temperature_c=-1`: <verbatim | clamps to X | rejects with 400 | ignores>. Selected Design <A|B> for Phase 3 preset-mode encoding. See `docs/phase-3-climate-refactor.md` §5.

**API-budget impact:** 1 GET + 1 PATCH + 1 GET + 1 PATCH = 4 calls one-time, not per user action.

---

### 2. Optimistic state model for climate

**The crux of Phase 3.** After a successful PATCH, the entity should immediately reflect the requested state without waiting for the next coordinator poll. HA's `CoordinatorEntity` does not natively support this, so we layer optimistic state on top of `coordinator.data`.

**File:** `custom_components/sleepme_thermostat/climate.py`.

**State model added to `SleepMeThermostat`:**

```python
OPTIMISTIC_TIMEOUT = timedelta(seconds=30)
"""Window in which we trust the optimistic value over coordinator.data.

After this window expires, the coordinator's value wins regardless. Bounds the
"why doesn't the slider update" failure mode to 30 s on the user side."""


class SleepMeThermostat(CoordinatorEntity, ClimateEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_thermostat"
        self._attr_device_info = build_device_info(device_id, name, device_info)

        # Optimistic state -- one tuple per facet we can change.
        # Each is None when there's no pending optimistic value.
        self._optimistic_target_temp: float | None = None
        self._optimistic_target_temp_expires: datetime | None = None
        self._optimistic_hvac_mode: HVACMode | None = None
        self._optimistic_hvac_mode_expires: datetime | None = None

        # Preset-mode is purely local state -- never read from coordinator.data.
        # Restored from RestoreEntity on entry reload; default PRESET_NONE.
        self._attr_preset_mode: str = PRESET_NONE
        # Setpoint to restore when leaving a preset -- the previous user-target.
        self._previous_target_temperature: float | None = None
```

**Key properties — each reconciles optimistic and coordinator state:**

```python
@property
def target_temperature(self) -> float | None:
    """Optimistic value while we wait for the next poll to confirm.

    Reconciliation rules:
      1. If optimistic is None -> return coordinator value as-is.
      2. If coordinator now reports the same value the user asked for ->
         clear optimistic; return coordinator value.
      3. If the optimistic window has expired -> clear optimistic; trust the
         coordinator's current value (the server "wins").
      4. Otherwise -> return optimistic value.
    """
    server_value = self.coordinator.data["control"].get("set_temperature_c")
    if self._optimistic_target_temp is None:
        return server_value

    expected = round_half_up(self._optimistic_target_temp)
    if server_value == expected:
        self._optimistic_target_temp = None
        self._optimistic_target_temp_expires = None
        return server_value

    if self._optimistic_target_temp_expires is None \
            or utcnow() >= self._optimistic_target_temp_expires:
        self._optimistic_target_temp = None
        self._optimistic_target_temp_expires = None
        return server_value

    return self._optimistic_target_temp


@property
def hvac_mode(self) -> HVACMode:
    """Same optimistic-vs-server reconciliation, on HVAC mode."""
    server_mode = self._determine_hvac_mode(
        self.coordinator.data["control"].get("thermal_control_status")
    )
    if self._optimistic_hvac_mode is None:
        return server_mode
    if server_mode == self._optimistic_hvac_mode:
        self._optimistic_hvac_mode = None
        self._optimistic_hvac_mode_expires = None
        return server_mode
    if self._optimistic_hvac_mode_expires is None \
            or utcnow() >= self._optimistic_hvac_mode_expires:
        self._optimistic_hvac_mode = None
        self._optimistic_hvac_mode_expires = None
        return server_mode
    return self._optimistic_hvac_mode


@property
def preset_mode(self) -> str:
    """Preset mode is local state. Coordinator does not report it.

    If the underlying setpoint has been moved by another client (e.g. SleepMe
    app) to something that doesn't match the current preset's target, demote
    to PRESET_NONE on the next read.
    """
    if self._attr_preset_mode == PRESET_NONE:
        return PRESET_NONE
    expected_target = PRESET_TARGET_TEMPERATURES.get(self._attr_preset_mode)
    if expected_target is None:
        return PRESET_NONE
    # Honor optimistic temp -- if the user just set a preset, the next coord
    # poll won't have reported the target yet.
    actual_target = self.target_temperature
    if actual_target is not None and actual_target != expected_target:
        # Out-of-band setpoint change -- preset is no longer active.
        self._attr_preset_mode = PRESET_NONE
    return self._attr_preset_mode
```

**The new `async_set_temperature`:**

```python
async def async_set_temperature(self, **kwargs: Any) -> None:
    """Set new target temperature.

    One PATCH; optimistic write; one refresh. No verification loop.
    """
    target = kwargs.get(ATTR_TEMPERATURE)
    if target is None:
        # HA always sends ATTR_TEMPERATURE for single-setpoint climates; the old
        # `kwargs.get("temperature")` fallback was defensive cruft. Keep one
        # explicit check; raise ServiceValidationError for anyone calling the
        # service incorrectly.
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="missing_temperature",
        )

    # Validate range. Preset-driven temperatures already live inside the range
    # post-Design-B, so no special-casing.
    if not (self.min_temp <= target <= self.max_temp):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="temperature_out_of_range",
            translation_placeholders={
                "value": str(target),
                "min": str(self.min_temp),
                "max": str(self.max_temp),
            },
        )

    _LOGGER.info(
        "[Device %s] Setting target temperature to %sC", self._device_id, target,
    )
    try:
        await self.coordinator.client.set_temp_level(target)
    except SleepMeAuthError as err:
        # Coordinator's next poll will hit the same auth error and trigger
        # reauth. For this user action, surface a toast.
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="auth_failed",
        ) from err
    except SleepMeRateLimited as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="rate_limited",
        ) from err
    except SleepMeConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="cannot_connect",
        ) from err

    # PATCH succeeded. Write optimistic state.
    self._optimistic_target_temp = target
    self._optimistic_target_temp_expires = utcnow() + OPTIMISTIC_TIMEOUT
    # If the user explicitly set a temp, they are no longer "in a preset".
    if self._attr_preset_mode != PRESET_NONE:
        self._previous_target_temperature = self._attr_preset_mode_previous_target
        self._attr_preset_mode = PRESET_NONE
    self.async_write_ha_state()

    # Trigger one refresh so the optimistic state clears sooner than the
    # natural poll cadence. Coordinator's debounce coalesces back-to-back
    # request_refresh calls (audit win: a fast slider drag doesn't pile up GETs).
    await self.coordinator.async_request_refresh()
```

**`async_set_hvac_mode` follows the identical pattern**, optimistic on `_optimistic_hvac_mode`.

**`async_set_preset_mode` becomes purely local state plus, for non-`PRESET_NONE`, a PATCH to the preset's target temperature** (which is now a real number in [min_temp, max_temp]):

```python
async def async_set_preset_mode(self, preset_mode: str) -> None:
    """Set preset mode.

    Design B: preset_mode is local state. The PATCH sent to the API is the
    clamped real temperature corresponding to the preset.
    """
    if preset_mode not in self.preset_modes:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_preset",
            translation_placeholders={"value": preset_mode},
        )

    # Entering or switching presets: ensure device is on.
    if preset_mode != PRESET_NONE and self.hvac_mode == HVACMode.OFF:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    if preset_mode == PRESET_NONE:
        # Leaving a preset: restore previous setpoint if we have one. Otherwise
        # leave the setpoint where it is.
        if self._previous_target_temperature is not None:
            await self.async_set_temperature(
                **{ATTR_TEMPERATURE: self._previous_target_temperature}
            )
            self._previous_target_temperature = None
        self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()
        return

    # Entering a preset: remember the current setpoint as the "previous" for
    # the eventual PRESET_NONE.
    current = self.target_temperature
    if current is not None:
        self._previous_target_temperature = current

    target = PRESET_TARGET_TEMPERATURES[preset_mode]
    await self.coordinator.client.set_temp_level(target)
    # We've manipulated the device; update optimistic state directly without
    # routing through async_set_temperature (which would have cleared
    # _attr_preset_mode).
    self._optimistic_target_temp = target
    self._optimistic_target_temp_expires = utcnow() + OPTIMISTIC_TIMEOUT
    self._attr_preset_mode = preset_mode
    self.async_write_ha_state()
    await self.coordinator.async_request_refresh()
```

**`RestoreEntity` integration** — preset mode persists across HA restarts:

```python
async def async_added_to_hass(self) -> None:
    """Restore preset_mode from the last known state."""
    await super().async_added_to_hass()
    last_state = await self.async_get_last_state()
    if last_state is None:
        return
    last_preset = last_state.attributes.get("preset_mode")
    if last_preset in self.preset_modes:
        self._attr_preset_mode = last_preset
    last_previous = last_state.attributes.get("previous_target_temperature")
    if isinstance(last_previous, (int, float)):
        self._previous_target_temperature = float(last_previous)


@property
def extra_state_attributes(self) -> dict[str, Any]:
    """Persist `_previous_target_temperature` so RestoreEntity can recover it.

    NOTE: this replaces the dropped audit-#24 attributes. We do NOT re-add
    is_water_low or is_connected -- those live on dedicated binary_sensors.
    """
    if self._previous_target_temperature is None:
        return {}
    return {"previous_target_temperature": self._previous_target_temperature}
```

**Edge cases — explicit handling:**

| Case | Behavior |
|---|---|
| PATCH succeeds; next GET reports the *old* value (eventual consistency lag). | Optimistic value held for up to `OPTIMISTIC_TIMEOUT = 30 s`. Slider stays where the user put it. After the next GET *with the new value* lands, optimistic clears naturally. |
| PATCH succeeds; eventual GET *never* matches (e.g. device offline, propagation failed). | After 30 s, optimistic expires; slider snaps back to the coordinator's reported value. Better than the current behavior (slider stays where the user put it forever, hiding the failure). |
| User changes temp twice in quick succession (drag → drag). | Second PATCH overwrites `_optimistic_target_temp` with the new value and resets the expiry. First PATCH's GET reconciliation now compares against the second target — if it matches, great; if it doesn't (because the first PATCH hadn't propagated yet), the optimistic value (= the second target) wins. The coordinator's `async_request_refresh()` debounce (HA's `Debouncer` cooldown defaults to `REQUEST_REFRESH_DEFAULT_COOLDOWN = 10 s`) coalesces both refresh requests into at most one extra GET. *This is the small but real Phase 3 win on rapid-input load.* |
| PATCH raises `SleepMeRateLimited` (local rate-limiter at capacity). | Mapped to `HomeAssistantError` with translation key `rate_limited`. HA shows a toast: "SleepMe API is rate-limited; please retry in a moment." Optimistic state is NOT written — the slider snaps back to the server-reported value. |
| PATCH raises `SleepMeAuthError`. | Mapped to `HomeAssistantError` translation key `auth_failed`. Coordinator's next poll will hit the same 401/403 and trigger reauth via Phase 1's plumbing. |
| PATCH raises `SleepMeConnectionError`. | Mapped to `HomeAssistantError` translation key `cannot_connect`. |
| HVAC mode change + temp change called back-to-back. | Each manipulates its own optimistic facet (`_optimistic_hvac_mode` vs. `_optimistic_target_temp`). Two PATCHes, two `async_request_refresh()` calls — the second coalesces via coordinator debounce. Net: 2 PATCH + 1 GET. |
| Coordinator update lands while optimistic timer is in progress. | Reconciliation runs in the property getter — no event loop work needed. Coordinator updates trigger `async_write_ha_state` via `CoordinatorEntity.__init_subclass__`, so the property re-evaluates next render. |
| HA stops/restarts mid-PATCH (rare). | PATCH either landed on the API or didn't. On restart, `RestoreEntity` restores `_attr_preset_mode` and `_previous_target_temperature`. The optimistic temp/HVAC are intentionally NOT restored — they're an in-flight UI hint, not durable state. First poll after restart shows the actual server value. |

**API-budget impact (per user action, ignoring optional debounce coalescing):**

| Action | Today | After Phase 3 | Delta |
|---|---|---|---|
| `async_set_temperature` (happy) | 1 PATCH + 1 GET + (verification ok) = 2 calls + 10 s spinner | 1 PATCH + 1 GET = 2 calls + ~0 s spinner | **0 calls saved**, but **~10 s spinner removed.** |
| `async_set_temperature` (verification timing miss) | 1 PATCH + 1 GET + 127 s sleep + 1 PATCH + 1 GET = 4 calls + ~140 s spinner | 1 PATCH + 1 GET = 2 calls | **-2 calls per miss.** |
| `async_set_temperature` (worst case verification miss × 3) | 3 PATCH + 3 GET = 6 calls + ~5 min spinner | 1 PATCH + 1 GET = 2 calls | **-4 calls.** |
| `async_set_temperature` raises `SleepMeRateLimited` | 1 PATCH attempt + sleep(127) + 1 PATCH attempt + sleep(127) + 1 PATCH attempt = up to 3 rejected PATCHes burning budget | 1 PATCH attempt; `HomeAssistantError` toast | **-2 calls under throttle.** |
| Slider drag (3 rapid temp changes) | 3 PATCH + 3 GET (+ retries on misses) = 6+ calls | 3 PATCH + 1 GET (coordinator debounce coalesces) = 4 calls | **-2 calls.** |

**Diff shape:** `climate.py` is substantively rewritten. ~150 lines deleted (helper + per-command wrappers), ~180 added (optimistic state, new command methods, restore-entity hooks). Net +30. No new file in this deliverable.

---

### 3. ServiceValidationError on out-of-range

**File:** `climate.py`, `strings.json`, `translations/en.json`, `translations/es.json`.

**Currently** (lines 196–204):

```python
if (target_temp < self.min_temp or target_temp > self.max_temp) and (
    target_temp not in PRESET_TEMPERATURES.values()
):
    _LOGGER.warning("[Device %s] Temperature %sC is out of range.", ...)
    return
```

**After:**

```python
if not (self.min_temp <= target <= self.max_temp):
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="temperature_out_of_range",
        translation_placeholders={
            "value": str(target),
            "min": str(self.min_temp),
            "max": str(self.max_temp),
        },
    )
```

The `target_temp not in PRESET_TEMPERATURES.values()` exception goes away in Phase 3 because Design B never sends sentinel values through `async_set_temperature` — presets PATCH the real clamped target directly.

**Translation additions** to `strings.json` (and mirror in `translations/en.json`):

```json
"exceptions": {
  "temperature_out_of_range": {
    "message": "Temperature {value}°C is out of range. Must be between {min}°C and {max}°C."
  },
  "missing_temperature": {
    "message": "Temperature is required for set_temperature."
  },
  "invalid_preset": {
    "message": "Preset mode {value} is not supported."
  },
  "auth_failed": {
    "message": "SleepMe API token is invalid or revoked. Please re-authenticate."
  },
  "rate_limited": {
    "message": "SleepMe API is currently rate-limited. Please retry in a moment."
  },
  "cannot_connect": {
    "message": "Cannot reach the SleepMe API. Check your network and try again."
  }
}
```

**Spanish** (`translations/es.json`):

```json
"exceptions": {
  "temperature_out_of_range": {
    "message": "La temperatura {value}°C está fuera de rango. Debe estar entre {min}°C y {max}°C."
  },
  "missing_temperature": { "message": "Se requiere una temperatura para set_temperature." },
  "invalid_preset": { "message": "El preset {value} no es compatible." },
  "auth_failed": { "message": "El token de SleepMe es inválido o ha sido revocado. Reautentíquese." },
  "rate_limited": { "message": "La API de SleepMe está limitada por tasa. Reintente en un momento." },
  "cannot_connect": { "message": "No se puede conectar a la API de SleepMe. Verifique su red y reintente." }
}
```

The Phase 2 `i18n-check` CI step (if it was adopted) `diff -q`s `strings.json` against `translations/en.json` — keep them byte-identical. The Spanish file does not block CI.

**Diff shape:** `climate.py` -7 / +9 lines. Translation files +15 lines each.

**API-budget impact:** **negative.** Out-of-range never reaches PATCH; HA's service call layer rejects before transport touches the wire. -1 PATCH per misuse.

---

### 4. HomeAssistantError on transport failure

**File:** `climate.py`.

**Currently** (lines 82–93 of the helper): every exception during PATCH is logged as a warning, then retried. After all retries, `False` returns silently from the helper; the caller (climate command method) ignores the return value. **The user sees nothing.**

**After:** explicit try/except around the single PATCH in `async_set_temperature` / `async_set_hvac_mode` / `async_set_preset_mode`. Each typed transport exception maps to `HomeAssistantError` with a translation key (see deliverable 3 for the keys).

**Why not `ServiceValidationError`?** `ServiceValidationError` is for user-input validation. Transport failures are operational — `HomeAssistantError` is the right base. HA renders both as toasts; the semantic distinction lives in the type, not the UX.

**Pattern (paste-ready, identical across the three command methods):**

```python
try:
    await self.coordinator.client.set_temp_level(target)
except SleepMeAuthError as err:
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="auth_failed",
    ) from err
except SleepMeRateLimited as err:
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="rate_limited",
    ) from err
except SleepMeConnectionError as err:
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="cannot_connect",
    ) from err
```

**Note on `httpx.HTTPStatusError`.** Transport already maps 401/403/429/5xx through the typed exceptions. Any `httpx.HTTPStatusError` that escapes `SleepMeAPI.api_request` is a non-retriable 4xx (e.g. 400, 404). Catch as the final fallback:

```python
except httpx.HTTPStatusError as err:
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="api_error",
        translation_placeholders={"status": str(err.response.status_code)},
    ) from err
```

with an `api_error` translation key: `"SleepMe API returned HTTP {status}."`.

**Diff shape:** ~40 lines added across three command methods. No structural changes elsewhere.

**API-budget impact:** as in deliverable 2, eliminates the up-to-3 retries on rate-limited PATCH. **-2 calls under throttle per user action.**

---

### 5. Preset-mode encoding cleanup

**Design A vs. Design B summary** (recap from prompt):

| Aspect | Design A | Design B (recommended) |
|---|---|---|
| Sentinel values (-1, 999) sent to API? | Yes — kept verbatim. | No — PATCH always sends real clamped temps. |
| `_attr_preset_mode` source | Derived from `coordinator.data["control"]["set_temperature_c"]` (`-1 → MAX_COOL`, `999 → MAX_HEAT`). | Local entity state. Persisted via `RestoreEntity`. |
| Robustness if API clamps sentinels | Broken — preset is lost on the next GET. | Robust — preset is local; clamping is invisible. |
| Robustness if API rejects sentinels (HTTP 400) | Broken — PATCH fails, user sees error toast. | Robust — never sends invalid values. |
| Cleanup of `_sanitize_temperature` / `None`-as-signal | Required (still cleaner than today). | Required. |
| Out-of-band setpoint change (e.g. SleepMe app) | Updates preset automatically via setpoint match. | `preset_mode` property detects mismatch and demotes to `PRESET_NONE`. |
| Lines of code | Slightly less (no `RestoreEntity`). | Slightly more, but no edge-case landmines. |

**Recommendation flipped to Design A** based on the official API docs (see deliverable 1 status note). The sentinels `-1` and `999` are part of the SleepMe API contract: the server stores them verbatim and routes the device to its physical extreme. Design A is now strictly correct; Design B's `RestoreEntity` overhead is unnecessary because the server is the source of truth for preset state.

**Concrete changes for Design A:**

- Keep `PRESET_TEMPERATURES = {PRESET_MAX_COOL: -1, PRESET_MAX_HEAT: 999}` in `const.py`. These are documented API values, not integration sentinels.
- Drop the `_sanitize_temperature` / None-as-signal pattern: when the API returns `set_temperature_c == -1` we *know* it's MAX_COOL because that's literally what the docs say it means.
- Compute `preset_mode` directly from the coordinator's setpoint value with a tiny lookup:
  ```python
  @property
  def preset_mode(self) -> str:
      setpoint = self.coordinator.data["control"].get("set_temperature_c")
      for mode, sentinel in PRESET_TEMPERATURES.items():
          if setpoint == sentinel:
              return mode
      return PRESET_NONE
  ```
- `target_temperature` returns the coordinator value as-is, **including** when it's a sentinel — let HA's UI render the slider in its "preset" state. No `None` conversion required.
- No `RestoreEntity` needed.

**Original Design B section preserved below for historical context.**

---

### 5b. Design B (historical — superseded by Design A)

**Concrete changes for Design B:**

**`const.py`:**

```python
# Replace:
# PRESET_TEMPERATURES = {PRESET_MAX_COOL: -1, PRESET_MAX_HEAT: 999}
#
# With real clamped numeric targets that match min/max_temp on the climate entity.
# These MUST match SleepMeThermostat.min_temp / max_temp.
MIN_TEMP_C = 12.78
MAX_TEMP_C = 46.5

PRESET_MAX_COOL = "Max Cool"
PRESET_MAX_HEAT = "Max Heat"

PRESET_TARGET_TEMPERATURES = {
    PRESET_MAX_COOL: MIN_TEMP_C,
    PRESET_MAX_HEAT: MAX_TEMP_C,
}
```

Delete `PRESET_TEMPERATURES` from `const.py`. Grep for any remaining references:

```bash
grep -rn 'PRESET_TEMPERATURES' custom_components/sleepme_thermostat/
# Expected after Phase 3: zero matches.
```

**`climate.py`:**

- Delete `_sanitize_temperature` (the function and every call site).
- Delete `_determine_preset_mode` (replaced by the `preset_mode` property in deliverable 2).
- `target_temperature` returns the coordinator value as-is (no None-as-signal); see deliverable 2.
- `min_temp` returns `MIN_TEMP_C` (= 12.78). See deliverable 9.
- `max_temp` returns `MAX_TEMP_C` (= 46.5).
- `_attr_preset_mode` is initialized in `__init__` and mutated in `async_set_preset_mode` + `async_set_temperature` (the latter resets to `PRESET_NONE` if the user manually changes the setpoint).

**Diff shape:** `const.py` -2 / +6 lines. `climate.py` ~25 lines deleted (sanitize + preset determination + None-as-signal), ~15 lines added (preset_mode property + restore hooks; see deliverable 2). Net `climate.py` -10.

**API-budget impact:** none directly; this is encoding cleanup.

---

### 6. round_half_up consolidation

**Files:** new `helpers.py`; `climate.py`; `sleepme.py`.

**New `custom_components/sleepme_thermostat/helpers.py`:**

```python
"""Shared utilities for the sleepme_thermostat integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from .const import DOMAIN


def round_half_up(n: float) -> float:
    """Round a number to the nearest .0 or .5.

    Used by the climate entity (for verification — soon to be optimistic
    comparison) and by SleepMeClient.set_temp_level (for the value actually
    sent to the API; the API rejects fractional precision finer than .5).
    """
    return round(n * 2) / 2


def build_device_info(device_id: str, name: str, info: dict) -> dict:
    """Construct the HA device_info dict from entry data.

    Single source of truth for the dict shape across climate, binary_sensor,
    and sensor platforms. Phase 3 deduplication of audit #10 leftovers.
    """
    return {
        "identifiers": {(DOMAIN, device_id)},
        "name": f"Dock Pro {name}",
        "manufacturer": "SleepMe",
        "model": info.get("model"),
        "sw_version": info.get("firmware_version"),
        "connections": {(CONNECTION_NETWORK_MAC, info.get("mac_address"))},
        "serial_number": info.get("serial_number"),
    }
```

**`climate.py`:**

```python
# Delete the local round_half_up definition (lines 25-27).
# Import from helpers:
from .helpers import build_device_info, round_half_up
```

**`sleepme.py`:**

```python
# Delete the local round_half_up definition (lines 19-21).
# Import from helpers:
from .helpers import round_half_up
```

**Sanity check (grep after the change):**

```bash
grep -n 'def round_half_up' custom_components/sleepme_thermostat/
# Expected: 1 match (helpers.py only).
```

**Diff shape:** new `helpers.py` ~30 lines; `climate.py` -3 / +1; `sleepme.py` -3 / +1. Net +25.

**API-budget impact:** none.

---

### 7. build_device_info consolidation

Same helper module as deliverable 6. The function `build_device_info` defined in `helpers.py` is imported and called by:

- `climate.py` — replaces the inline dict construction at lines 55–63.
- `binary_sensor.py` — replaces the local `_device_info` helper at lines 17–26.
- `sensor.py` — replaces the local `_device_info` helper at lines 17–26.

**`climate.py` change:**

```python
def __init__(self, coordinator, device_id, name, device_info):
    super().__init__(coordinator)
    self._device_id = device_id
    self._attr_unique_id = f"{DOMAIN}_{device_id}_thermostat"
    self._attr_device_info = build_device_info(device_id, name, device_info)
    # (...optimistic state init — see deliverable 2...)
```

**`binary_sensor.py` and `sensor.py`:** delete the local `_device_info` definitions; import `build_device_info` from `helpers`; update the one call site in each `async_setup_entry` to use the new name.

```python
# binary_sensor.py / sensor.py — async_setup_entry:
device_info = build_device_info(device_id, name, entry_data["device_info"])
```

**Sanity check:**

```bash
grep -rn '"identifiers": {(DOMAIN' custom_components/sleepme_thermostat/
# Expected after Phase 3: 1 match (helpers.py only).
```

**Diff shape:** `binary_sensor.py` -10 / +2; `sensor.py` -10 / +2; `climate.py` -8 / +1. Net -23.

**API-budget impact:** none.

---

### 8. Drop extra_state_attributes (already covered by binary sensors)

**File:** `climate.py`.

**Currently** (lines 176–181):

```python
@property
def extra_state_attributes(self):
    return {
        "is_water_low": self.coordinator.data["status"].get("is_water_low"),
        "is_connected": self.coordinator.data["status"].get("is_connected"),
    }
```

Both are already first-class binary sensors: `binary_sensor.dock_pro_<name>_water_level` (device_class=`problem`) and `binary_sensor.dock_pro_<name>_connected` (device_class=`connectivity`). Exposing them as climate attributes duplicates state and creates a "where do I read this in automations?" choice for end users.

**After Phase 3:** the `extra_state_attributes` property is **redefined** to return `{"previous_target_temperature": ...}` for `RestoreEntity` persistence (see deliverable 2). It does NOT include `is_water_low` or `is_connected`.

```python
@property
def extra_state_attributes(self) -> dict[str, Any]:
    """Persist `_previous_target_temperature` so RestoreEntity can recover it."""
    if self._previous_target_temperature is None:
        return {}
    return {"previous_target_temperature": self._previous_target_temperature}
```

**Release-note note** for the changelog: "The `is_water_low` and `is_connected` attributes of `climate.dock_pro_*` are removed. Use the dedicated `binary_sensor.*_water_level` and `binary_sensor.*_connected` entities instead."

**Diff shape:** ~5 lines changed in `climate.py`. Replaces existing dict.

**API-budget impact:** none.

---

### 9. Temperature bounds 12.5/46.5 → 13.0/48.0

**Files:** `climate.py`, `const.py`.

**Currently** (`climate.py:124–128`):

```python
@property
def min_temp(self):
    return 12.5

@property
def max_temp(self):
    return 46.5
```

**After** (sourced from `const.py` constants):

```python
# const.py
MIN_TEMP_C = 13.0  # API contract minimum
MAX_TEMP_C = 48.0  # API contract maximum

# climate.py
@property
def min_temp(self) -> float:
    return MIN_TEMP_C


@property
def max_temp(self) -> float:
    return MAX_TEMP_C
```

**Rationale:** The official SleepMe API docs document the accepted range as `13.0..48.0` °C in half-degree increments. The audit guessed `12.78` from the README's "55 °F" (= 12.78 °C); the API docs clarify the actual bound is `13.0`. The audit didn't flag the upper bound — current `46.5` is below the documented `48.0` and unnecessarily restricts the user.

**Diff shape:** 2 properties touched in `climate.py`; 2 constants added to `const.py`.

**API-budget impact:** indirect win. With honest bounds, the slider can't request out-of-range values that the device would have silently clamped (under the old verify loop, that triggered up to 3 retries burning budget). Phase 3's optimistic model removes the retries anyway, so the practical delta is small post-Phase-3.

---

### 10. Tests

**New test files** to be added:

- `tests/test_climate.py` — new, ~250 lines, ~10 tests.
- `tests/test_helpers.py` — new, ~50 lines, ~2 tests.

**Existing test files touched:**

- `tests/conftest.py` — extend `mock_sleepme_client` to expose `set_temp_level` and `set_device_status` already (it does). No change.
- `tests/test_init.py` — no change.

**Critical test scenarios in `test_climate.py`:**

1. **`test_set_temperature_writes_optimistic_state`** — set up entry; get climate entity; mock `client.set_temp_level` to return `{}`; call `entity.async_set_temperature(temperature=20.5)`; immediately assert `entity.target_temperature == 20.5` (before any coordinator update). Assert `client.set_temp_level.await_args.args == (20.5,)`. Assert `coordinator.async_request_refresh` was awaited once.

2. **`test_set_temperature_optimistic_clears_on_matching_coordinator_value`** — set optimistic to 20.5; mutate `coordinator.data["control"]["set_temperature_c"] = 20.5`; assert `entity.target_temperature == 20.5` and `entity._optimistic_target_temp is None` after the read.

3. **`test_set_temperature_optimistic_holds_on_non_matching_coordinator_value`** — set optimistic to 20.5; coordinator reports 21.5; assert `entity.target_temperature == 20.5` (optimistic wins) and optimistic state remains set.

4. **`test_set_temperature_optimistic_expires_after_timeout`** — set optimistic to 20.5 with expiry in the past (use `freezegun` or directly set `_optimistic_target_temp_expires = utcnow() - timedelta(seconds=1)`); coordinator reports 21.5; assert `entity.target_temperature == 21.5` and `entity._optimistic_target_temp is None`.

5. **`test_set_temperature_out_of_range_raises_service_validation`** — call `async_set_temperature(temperature=200)`; assert `pytest.raises(ServiceValidationError)`; assert `translation_key == "temperature_out_of_range"`; assert `client.set_temp_level` was NOT called.

6. **`test_set_temperature_below_min_raises_service_validation`** — `async_set_temperature(temperature=10.0)`; same assertions. (Verifies 12.5 → 12.78 tightening, deliverable 9.)

7. **`test_set_temperature_rate_limited_raises_home_assistant_error`** — mock `client.set_temp_level` to raise `SleepMeRateLimited`; assert `pytest.raises(HomeAssistantError)`; assert no optimistic state was written; assert `coordinator.async_request_refresh` was NOT called.

8. **`test_set_temperature_auth_failed_raises_home_assistant_error`** — same pattern with `SleepMeAuthError`.

9. **`test_set_preset_max_cool_uses_local_state`** — call `entity.async_set_preset_mode("Max Cool")`; assert `entity.preset_mode == "Max Cool"`; assert `client.set_temp_level.await_args.args == (MIN_TEMP_C,)` (real number, not -1); manipulate `coordinator.data["control"]["set_temperature_c"] = MIN_TEMP_C` and re-read `preset_mode` — still "Max Cool".

10. **`test_set_preset_demotes_to_none_when_setpoint_diverges`** — call `async_set_preset_mode("Max Cool")`; later mutate `coordinator.data["control"]["set_temperature_c"]` to 25.0 (some unrelated value) — simulates someone changing the setpoint in the SleepMe app; assert `entity.preset_mode == PRESET_NONE`.

11. **`test_rapid_temperature_changes_coalesce_refreshes`** — call `async_set_temperature(temperature=20.0)` then immediately `async_set_temperature(temperature=21.0)`; assert `client.set_temp_level.await_count == 2`; assert `coordinator.async_request_refresh.await_count <= 2` (debounce — exact value depends on HA's `Debouncer` semantics; the load-bearing assertion is "doesn't pile up to 6 GETs").

12. **`test_restore_entity_recovers_preset_state`** — set up entry with `_attr_preset_mode = "Max Cool"`; unload; re-set up (simulating restart); assert `entity.preset_mode == "Max Cool"` after first read.

**Tests in `test_helpers.py`:**

13. **`test_round_half_up`** — table-driven: `[(12.0, 12.0), (12.5, 12.5), (12.74, 12.5), (12.78, 13.0), (12.25, 12.0), (12.26, 12.5)]`. (One slight curiosity: 12.78 rounds *up* to 13.0 — confirms why `MIN_TEMP_C = 12.78` is the **slider minimum**, not the minimum-after-rounding; that's fine and matches the existing transport behavior in `sleepme.py:set_temp_level`.)

14. **`test_build_device_info_dict_shape`** — pass a representative `info` dict; assert returned dict has exactly the expected keys and values; assert `connections` uses `CONNECTION_NETWORK_MAC` not the bare string `"mac"`.

**Test fixtures.** `tests/conftest.py:mock_sleepme_client` already returns `set_temp_level` and `set_device_status` as `AsyncMock`s — no change needed. For exception-raising tests, individual tests override `mock_sleepme_client.return_value.set_temp_level.side_effect = SleepMeRateLimited(...)`.

**Test entity-fetching pattern** (consistent across the file):

```python
async def _setup_entry(hass: HomeAssistant, mock_client: AsyncMock) -> SleepMeThermostat:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Retrieve the climate entity from the registry.
    state = hass.states.get(f"climate.dock_pro_{MOCK_NAME.lower().replace(' ', '_')}")
    assert state is not None
    # The entity itself (for property reads) lives in hass.data — pull the
    # platform's first entity.
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    # Implementation detail: climate platform stores entities in
    # hass.data[CLIMATE_DOMAIN].entities; alternatively, use
    # platform.entities iteration.
    return _get_climate_entity(hass, entry)
```

A small helper `_get_climate_entity` should be defined in `test_climate.py` that looks up the entity via `hass.data["entity_components"]["climate"].get_entity(entity_id)` (or the HA-provided equivalent for the pinned version).

**Diff shape:** `test_climate.py` new, ~250 lines. `test_helpers.py` new, ~50 lines. Total ~300 new LOC. Tracks Phase 3's prompt-stated target of ~12 tests.

**API-budget impact:** none (tests only).

---

## API-call-budget analysis (before/after summary)

| Scenario | Before Phase 3 | After Phase 3 | Delta |
|---|---|---|---|
| Idle, 1 device, 20 s poll | 3 GET/min | 3 GET/min | 0 |
| Slider drag (1 user action, happy path) | 1 PATCH + 1 GET + 10 s spinner | 1 PATCH + 1 GET + ~0 s spinner | 0 calls, **-10 s spinner** |
| Slider drag (verification miss × 1) | 2 PATCH + 2 GET + ~140 s spinner | 1 PATCH + 1 GET | **-2 calls, -140 s spinner** |
| Slider drag (worst case verification miss × 3) | 3 PATCH + 3 GET + ~5 min spinner | 1 PATCH + 1 GET | **-4 calls, -5 min spinner** |
| Slider drag under local rate-limit | 3 PATCH attempts burning budget + ~5 min spinner | 1 PATCH attempt + HomeAssistantError toast | **-2 calls** |
| Slider drag, out-of-range value | 0 PATCH (today: silent return) | 0 PATCH (today: silent), but **user sees an error** | 0 calls, **UX win** |
| Rapid slider drag (3 changes in 2 s) | 3 PATCH + up to 9 GET (3 verify cycles) | 3 PATCH + ≤2 GET (coordinator debounce) | **-7 calls** |
| Set preset MAX_COOL | 1 PATCH (with `-1` in body — may fail) + 1 GET + verify loop | 1 PATCH (with `MIN_TEMP_C` in body) + 1 GET | **No failures + 0–4 calls saved depending on past failures** |
| `RestoreEntity` add-on overhead | n/a | 0 new API calls; HA `restore_state` is local DB only | 0 |

**Net Phase 3 budget impact:** *significant reduction per user action.* The "0 calls saved on happy path" line is misleading without the spinner column — perceptual latency is the user-facing win even when call counts are unchanged.

---

## Validation steps against live device

**Live host:** `100.88.154.98` (Tailscale). Both `Dock Pro Ramon` and `Dock Pro Chiva` enabled, post-Phase-2.

**Pre-deploy: capture entity_ids** (same pattern as Phase 2's continuity check):

```bash
ssh hassio@100.88.154.98 'jq ".data.entities[] | select(.platform == \"sleepme_thermostat\") | .entity_id" /homeassistant/.storage/core.entity_registry' > /tmp/before.txt
```

**Validation matrix.**

1. **`pytest`** passes locally — existing tests + 14 new tests in `test_climate.py` and `test_helpers.py`.
2. **`pre-commit run --all-files`** clean.
3. **`make deploy-restart HA_HOST=100.88.154.98`** succeeds.
4. **Entity registry continuity** — same diff check as Phase 2:
   ```bash
   ssh hassio@100.88.154.98 'jq ".data.entities[] | select(.platform == \"sleepme_thermostat\") | .entity_id" /homeassistant/.storage/core.entity_registry' > /tmp/after.txt
   diff /tmp/before.txt /tmp/after.txt
   ```
   Expected: zero diff lines.

5. **Climate command latency (the single most important Phase 3 check):**
   - Open Developer Tools → Logs → set log level for `custom_components.sleepme_thermostat` to `info`.
   - From the dashboard, note the current target_temp on `Dock Pro Ramon`. Drag the slider to `(current + 2)°C`. Release. Note the wall-clock time.
   - Within 1 s, expect: log line `[Device <id>] Setting target temperature to <new>C`.
   - Within `scan_interval` seconds (default 20), expect: log line indicating coordinator GET returned (visible at `debug` level in `sleepme_api.py`).
   - Slider must remain at the new value for the entire window. It must NOT snap back at any point.
   - Compare perceptually against Phase 2 behavior (where the slider may have stayed pinned but the device took up to 5 min to respond). Expectation: physical device response time is now bounded by API propagation, not by integration retries.

6. **Out-of-range rejection:**
   - Developer Tools → Services → `climate.set_temperature` → entity `climate.dock_pro_ramon` → temperature `200`. Submit.
   - Expect: red error toast in the HA UI. English text: "Temperature 200°C is out of range. Must be between 12.78°C and 46.5°C."
   - Tail `home-assistant.log`: no PATCH was issued to the SleepMe API for this attempt.

7. **Below-min rejection** (verifies 12.78 tightening):
   - Same as above with temperature `12.5`. Expect: toast with the same min/max in the message.

8. **Rate-limit-during-command** (manual, ~2 min):
   - SSH into the live host. Edit `/homeassistant/custom_components/sleepme_thermostat/sleepme_api.py` temporarily: change `MAX_REQUESTS_PER_MINUTE = 9` to `MAX_REQUESTS_PER_MINUTE = 1`.
   - `ha core restart`.
   - On the dashboard, drag the slider twice in quick succession.
   - First PATCH succeeds. Second PATCH raises `SleepMeRateLimited` → `HomeAssistantError` → toast "SleepMe API is currently rate-limited. Please retry in a moment."
   - Tail log: no retry loop, no `asyncio.sleep(127)`, no extra GET beyond the first natural refresh.
   - Restore the file (`git checkout`), `ha core restart`.

9. **Preset mode round-trip:**
   - From the climate card, click "Max Cool" preset.
   - Slider snaps to `12.78` immediately (optimistic).
   - Within `scan_interval`, the coordinator's GET confirms `set_temperature_c == 12.78`.
   - Click "None" preset.
   - Slider returns to the value it was at before the preset.
   - In Developer Tools → States → `climate.dock_pro_ramon`, observe `attributes.preset_mode` transitions: `none → Max Cool → none`.
   - `previous_target_temperature` appears in `attributes` after the preset is set; gone after returning to "None".

10. **Preset persistence across restart:**
    - With `preset_mode == "Max Cool"` set, run `ha core restart`.
    - After restart, the `climate.dock_pro_ramon` state's `preset_mode` attribute remains `"Max Cool"` (RestoreEntity recovered it).
    - First coordinator poll lands; `target_temperature` reads `12.78`; preset stays `"Max Cool"`.

11. **Preset auto-demote on out-of-band change:**
    - With `preset_mode == "Max Cool"`, use the SleepMe phone app (or a direct curl) to change the setpoint to `25 °C`.
    - On the next coordinator poll (≤ `scan_interval`), observe `preset_mode` flip to `"none"` in the HA UI.

12. **Multi-device unchanged:**
    - Repeat steps 5 and 9 against `Dock Pro Chiva`. No regression. Each device's optimistic state is independent.

13. **Service-validation toasts are translated** (Spanish):
    - Settings → System → General → set HA language to Spanish.
    - Repeat step 6. Expect: "La temperatura 200°C está fuera de rango. Debe estar entre 12.78°C y 46.5°C."
    - Restore language to English.

The single most important check is **step 5** — the perceptual latency between user action and confirmed state. This is the entire reason Phase 3 exists. Document the wall-clock measurement in the PR description.

---

## Acceptance / exit criteria

Every box must be checked before Phase 3 is declared done.

- [ ] `ruff check .` and `black --check .` pass.
- [ ] `mypy custom_components/sleepme_thermostat` continues to pass (advisory).
- [ ] `pytest` passes including 14 new tests in `test_climate.py` (12) and `test_helpers.py` (2).
- [ ] `pre-commit run --all-files` clean.
- [ ] `grep -n '_async_api_command_with_retry' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `grep -rn 'POST_COMMAND_DELAY\|RETRY_DELAY\|RETRY_ATTEMPTS' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `grep -rn 'PRESET_TEMPERATURES' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `grep -rn 'def round_half_up' custom_components/sleepme_thermostat/` returns exactly 1 match (in `helpers.py`).
- [ ] `grep -rn 'def _device_info\|def build_device_info' custom_components/sleepme_thermostat/` returns exactly 1 match (`build_device_info` in `helpers.py`).
- [ ] `climate.py` has no `_sanitize_temperature` and no `_determine_preset_mode`.
- [ ] `climate.py:min_temp` returns `12.78` (sourced from `MIN_TEMP_C` in `const.py`).
- [ ] `climate.py:extra_state_attributes` does NOT contain `is_water_low` or `is_connected`.
- [ ] `climate.py:async_set_temperature` raises `ServiceValidationError` for out-of-range; raises `HomeAssistantError` for transport failures.
- [ ] `SleepMeThermostat` inherits from `RestoreEntity`; `async_added_to_hass` restores `_attr_preset_mode` and `_previous_target_temperature`.
- [ ] Translation files `strings.json`, `translations/en.json`, `translations/es.json` all have an `exceptions` block with keys: `temperature_out_of_range`, `missing_temperature`, `invalid_preset`, `auth_failed`, `rate_limited`, `cannot_connect`, `api_error`. (The Phase 2 `i18n-check` CI step, if adopted, byte-compares `strings.json` against `en.json`.)
- [ ] Maintainer ran preflight (deliverable 1) and recorded API behavior in `ROADMAP.md` Decisions log.
- [ ] Maintainer ran the 13-step live-device validation matrix; step 5 wall-clock latency improvement is documented in the PR description.
- [ ] On the live host, `before.txt` vs. `after.txt` diff is empty.
- [ ] `docs/ROADMAP.md` Phase 3 table flipped ⬜ → ✅.
- [ ] HACS validate, hassfest, CodeQL, and the `Test` workflow all green on the PR.

---

## Risks and open questions

1. **`RestoreEntity` + `CoordinatorEntity` MRO.** Both define `async_added_to_hass`; we must `await super().async_added_to_hass()` in our override so `CoordinatorEntity`'s subscription wiring still happens. HA Core combines these freely (see `climate.daikin`, `climate.tado`); double-check on first test run. If MRO conflicts, restructure with `class SleepMeThermostat(CoordinatorEntity, RestoreEntity, ClimateEntity)` — `CoordinatorEntity` must come first for `async_added_to_hass` to be reached via `super()`.

2. **Optimistic clearing on coordinator update — race window.** Between "user calls `async_set_temperature`" and "PATCH returns", the coordinator could already have fired a request_refresh from a different event (e.g. options-flow reload). If the GET completes during the PATCH, the next read of `target_temperature` may compare against an *old* coordinator value (pre-PATCH). The optimistic window (30 s) absorbs this; not a correctness bug, just slower convergence. Document inline.

3. **Coordinator debounce default.** HA's `DataUpdateCoordinator.async_request_refresh` uses a `Debouncer` with `cooldown = REQUEST_REFRESH_DEFAULT_COOLDOWN` (currently 10 s, immediate=False). Rapid back-to-back PATCHes coalesce into one GET 10 s after the last `async_request_refresh` call. That's actually what we want — it's the "rapid slider drag" budget win. *But* if the user expects sub-10s reconciliation on a single PATCH, they'll wait up to 10 s for the optimistic to clear. Acceptable given `OPTIMISTIC_TIMEOUT = 30 s > 10 s`. If desired, override the coordinator's debouncer in the constructor — out of scope for Phase 3.

4. **`previous_target_temperature` semantics on rapid preset toggles.** Cool → None → Cool → None → ... Each "enter preset" remembers the *current* setpoint at the time of the enter. If two enters happen back-to-back before any user setpoint change, the second enter captures the *preset target* itself as "previous" — leaving the preset goes back to the preset's target, not to the original user value. Fix: only update `_previous_target_temperature` when entering a preset *from* `PRESET_NONE`. Implementation detail noted in deliverable 2.

5. **`ServiceValidationError` translation rendering.** Available since HA 2024.4. The Phase 0–2 HA pin (`2026.4.x`) is well past that. No risk.

6. **`HomeAssistantError` with `translation_domain`.** Available since HA 2024.5. Same pin assurance.

7. **`RestoreEntity` for climate.** The HA framework `restore_state` integration is auto-loaded when any platform inherits from `RestoreEntity`. No new manifest dependency required.

8. **`async_write_ha_state` from a property reconciler.** Mutating `self._optimistic_target_temp = None` *inside* the `target_temperature` getter is a small layering smell — getters shouldn't mutate. Acceptable here because the mutation is idempotent and bounded. The alternative is to wire a `coordinator.async_add_listener(self._handle_coordinator_update)` callback that performs the reconciliation eagerly each time `coordinator.data` updates; `CoordinatorEntity` already wires this, and we can override `_handle_coordinator_update` to reconcile then call `super()`. The cleaner pattern:

   ```python
   @callback
   def _handle_coordinator_update(self) -> None:
       """Reconcile optimistic state against fresh coordinator data."""
       server_temp = self.coordinator.data["control"].get("set_temperature_c")
       if self._optimistic_target_temp is not None:
           expected = round_half_up(self._optimistic_target_temp)
           if server_temp == expected:
               self._optimistic_target_temp = None
               self._optimistic_target_temp_expires = None
       # ...same for hvac_mode...
       super()._handle_coordinator_update()
   ```

   **Recommendation:** use the callback override. It runs once per coordinator update (instead of once per property read), and keeps property getters pure. Update §2 implementation accordingly when writing the code — the property body simplifies to "return optimistic if set else server; expiry check still inside the getter."

9. **`HVACMode.AUTO` vs. `HEAT_COOL` (Roadmap open question).** Today's `hvac_modes` is `[OFF, AUTO]`. The roadmap noted Phase 3 may settle this. **Decision: keep `AUTO`.** The Dock Pro is a single-setpoint device that figures out heat-vs-cool internally; `AUTO` is the more honest mode. Phase 3 does not change `hvac_modes`.

10. **`set_temp_level` rounding side effect.** `sleepme.py:set_temp_level` already does `temp_c = round_half_up(temp_c)` before PATCH. Our optimistic comparison in `target_temperature` uses `round_half_up(self._optimistic_target_temp)` — they match. *But* if the user enters `20.7`, the API gets `20.5`, the coordinator reports `20.5`, and the optimistic reconciliation compares `20.5 == 20.5` → clears. Correct. If the user enters `20.7` but the server (for any reason) reports `20.0`, optimistic holds 20.7 for 30 s then snaps to 20.0. Correct UX.

11. **Test fixture leak.** The Phase 2 `mock_sleepme_client` mocks `SleepMeClient` at two import sites. Phase 3 tests rely on the same fixture; if a test imports `SleepMeClient` from a third site (e.g. `helpers.py`, which we added — but `helpers.py` doesn't import `SleepMeClient`), the mock won't catch it. Verify `helpers.py` imports cleanly; it should not pull `SleepMeClient`.

12. **Removed `extra_state_attributes` fields are breaking change for some users.** Any automation referencing `state_attr('climate.dock_pro_ramon', 'is_water_low')` will start returning `None` after Phase 3. Mitigation: explicit changelog line; the binary sensors `binary_sensor.dock_pro_ramon_water_level` and `binary_sensor.dock_pro_ramon_connected` cover the same information.

13. **Live-device step 5 is hard to A/B precisely** because the maintainer has already lived with the verify-after-command behavior. Suggested method: before deploying Phase 3, run one "drag the slider" and time it. Deploy Phase 3. Run the same drag again. The wall-clock difference is the user-visible win.

---

## Out of scope (explicit, with phase pointers)

| Item | Phase |
|---|---|
| Touch the transport / coordinator (`sleepme_api.py`, `update_manager.py`) | already settled in Phase 1 |
| Diagnostics platform (`diagnostics.py`) | 5 |
| Drop `api_url` and `name` from `entry.data` | 5 |
| Multi-version HA test matrix | 4 |
| Coverage gate at ≥ 75 % | 4 |
| `black` → `ruff format` migration | 4 |
| `quality_scale: silver` in manifest | 5 |
| `loggers`/`quality_scale` keys in manifest (audit #20) | 5 |
| Sync ES translation fully against EN | 5 (Phase 3 adds only the new exception keys to ES) |
| Sharing rate-limiter deque across `SleepMeAPI` instances | 4/5 if observed in practice |
| Coalesce/debounce slider drags more aggressively (beyond coordinator's default `Debouncer`) | future, only if the default isn't enough |
| Adding `hvac_action` for "heating" / "cooling" / "idle" indication on the climate card | future enhancement, not in audit |
| Restoring `_optimistic_target_temp` across HA restart | intentional non-goal — in-flight UI hints are not durable state |

---

### Critical Files for Implementation

- `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/climate.py` — substantively rewritten (deliverables 2, 3, 4, 5, 8, 9)
- `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/helpers.py` — new file (deliverables 6, 7)
- `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/const.py` — sentinel removal + new constants (deliverable 5)
- `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/binary_sensor.py` and `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/sensor.py` — `_device_info` dedup (deliverable 7)
- `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/strings.json` and `/Users/ramonsampayo/Documents/Proyectos/sleepme/sleepme_thermostat/custom_components/sleepme_thermostat/translations/en.json` and `es.json` — new `exceptions` block (deliverables 3, 4)
