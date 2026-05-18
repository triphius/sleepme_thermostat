# SleepMe Thermostat — Roadmap

**Last updated:** 2026-05-16
**Companion docs:** [`AUDIT.md`](./AUDIT.md) (findings reference), `docs/phase-N-*.md` (per-phase implementation plans, created as we go).

This is the living plan. Update statuses here as work lands. Detailed step-by-step plans for each phase are produced via the Plan agent before execution and committed alongside this file.

---

## Goal

Take the dormant `sleepme_thermostat` integration to a state where:

1. P0 bugs (rate-limiter race, inverted backoff, token leak, no unload, multi-device clobbering) are gone.
2. It conforms to current Home Assistant integration conventions (DataUpdateCoordinator error model, reauth, options flow, `has_entity_name`, `native_value`, etc.).
3. API call volume per user action is minimized — see "Cross-cutting concern: API budget" below.
4. There is a real test suite and lint/format/type tooling.
5. Validated end-to-end against the maintainer's own Dock Pro device.

## Cross-cutting concern: API budget

The sleep.me developer API rate-limits aggressively. Historical pain: cascading 429s → long unpredictable latency between user action and physical response.

**Every phase below must report its expected delta in API calls per user action and per minute of idle operation.** Acceptance for any phase that touches the transport/coordinator/climate layers includes a measurement against the real device.

Decisions baked into the roadmap because of this:

- Replace the climate verify-after-command loop with optimistic state + reliance on the next coordinator poll.
- Honor `Retry-After` on 429 instead of fixed backoff curves.
- Make poll interval user-configurable via options flow; default may move from 20s to a sleep-realistic 30–60s.
- Coalesce/debounce rapid user inputs (temperature slider drags) before they become API calls.

## Status legend

- ⬜ Not started
- 🟡 In progress
- ✅ Done
- 🔵 Blocked
- ❌ Decided against

## Phases

### Phase 0 — Tooling & test foundation

Set the scaffolding so every subsequent phase ships with tests, lint, and CI. **Detailed plan: [`phase-0-foundation.md`](./phase-0-foundation.md).**

| Status | Item |
|--------|------|
| ✅ | Add `pyproject.toml` with ruff + black + mypy config (Python 3.14 / HA 2026.5.x) |
| ✅ | Add `tests/` skeleton with `pytest-homeassistant-custom-component` and smoke test (1 pass + 1 xfail = unload regression check) |
| ✅ | Add `LICENSE` (MIT, matching README) |
| ✅ | Add pre-commit config (scoped to `tests/` for Phase 0; expands in Phase 1) |
| ✅ | Add `Test` CI workflow with `lint`, `typecheck`, `pytest` jobs |
| ✅ | Pin `hassfest@master` → `f6f29a7` (master @ 2026-04-07) |
| ✅ | Pin `hacs/action@main` → `dcb30e7` (main @ 2026-01-26) |
| ✅ | Document deploy workflow to HA OS host (rsync + `ha core restart`) in `phase-0-foundation.md` and `Makefile` |
| ✅ | Add `Makefile` with `deploy`, `restart`, `deploy-restart`, `test`, `lint`, `typecheck` targets |
| ✅ | Update `.gitignore` for venv / cache dirs |
| ✅ | Deploy verified against live HA host (PR #38): rsync was unreliable in the SSH addon → switched to tar-over-ssh with sudo; integration imports cleanly. Both `Dock Pro Ramon` and `Dock Pro Chiva` config entries are currently `disabled_by: user` (user re-enables when ready to runtime-validate). |
| ✅ | All CI green on PR #38: Test (lint, mypy, pytest), Validate HACS (hassfest x2, HACS Action x2), CodeQL (Analyze + CodeQL). 9/9 checks pass. |
| ⬜ | **Maintainer action:** review PR #38 and merge to `main`. |

**Exit criteria:** `ruff`, `black --check`, `mypy`, and `pytest` all pass green in CI. No code-behavior changes yet.

**API-budget impact:** none.

---

### Phase 1 — P0 fixes

The blocking-correctness pass. **Detailed plan: [`phase-1-p0-fixes.md`](./phase-1-p0-fixes.md).**

| Status | Item | Audit ref |
|--------|------|-----------|
| ⬜ | Strip API token (and any other secret) from logs | #1 |
| ⬜ | Fix rate limiter: instance-level `asyncio.Lock`, guard deque + wait | #2 |
| ⬜ | Fix backoff: monotonically increase with attempt number; honor `Retry-After` on 429 | #3 |
| ⬜ | Eliminate unbound-variable path in `handle_error` | #4 |
| ⬜ | Decide GET-under-rate-limit policy (drop vs. queue vs. raise) and implement | #5 |
| ⬜ | Coordinator: raise `UpdateFailed` on errors, `ConfigEntryAuthFailed` on 401/403 | #6 |
| ⬜ | Add `async_unload_entry` | #7 |
| ⬜ | Key `hass.data` by `entry.entry_id` | #8 |
| ⬜ | Add reauth flow | #9 |
| ⬜ | Remove `SleepMeAPI.close()` (would close HA's shared client) | #26 |

**Exit criteria:**

- All audit P0 items closed.
- Integration installs, reloads, and unloads cleanly on the test device.
- Token does not appear in DEBUG logs.
- Invalid token triggers reauth flow rather than silent stale-data.
- Pull/refresh under simulated 429 honors `Retry-After`.

**API-budget impact:** neutral-to-positive (no new calls; better behavior under throttling).

---

### Phase 2 — HA modernization

Bring the integration in line with current HA conventions. **Detailed plan: [`phase-2-modernization.md`](./phase-2-modernization.md).**

| Status | Item | Audit ref |
|--------|------|-----------|
| ⬜ | Add options flow (poll interval, future settings) | — |
| ⬜ | Adopt `_attr_has_entity_name = True` everywhere | #14 |
| ⬜ | Migrate sensors from `state` → `native_value`; add `state_class` where appropriate | #12, #13 |
| ⬜ | Build `device_info` directly in each platform from entry data — remove cross-platform borrowing | #10 |
| ⬜ | Replace deprecated `hass.components.persistent_notification.create` | #11 |
| ⬜ | Move translations to `strings.json` source + regenerate locale files | — |
| ⬜ | Drop `async_step_import` dead code | #21 |
| ⬜ | Use `CONNECTION_NETWORK_MAC` constant | #25 |
| ⬜ | Switch logging to lazy `%s` formatting | #23 |
| ⬜ | `__init__.py` raises `ConfigEntryNotReady` instead of returning False | #19 |

**Exit criteria:** Entities show clean names under the device. No HA deprecation warnings in logs. Options flow lets the maintainer change poll interval at runtime.

**API-budget impact:** neutral, except that options flow exposes poll interval — which is the single biggest dial on idle call volume.

---

### Phase 3 — Climate refactor (the rate-limit win)

This is where the historical latency problem actually gets fixed. **Detailed plan: [`phase-3-climate-refactor.md`](./phase-3-climate-refactor.md).**

| Status | Item | Audit ref |
|--------|------|-----------|
| ⬜ | Rip out `_async_api_command_with_retry` verify-after-command loop | #15 |
| ⬜ | After successful PATCH, write expected state optimistically + `async_request_refresh()` once | #15 |
| ⬜ | Raise `ServiceValidationError` for out-of-range temps instead of silent return | #16 |
| ⬜ | Track preset mode explicitly; stop encoding "in preset" as `target_temperature is None` | #17 |
| ⬜ | Move `min_temp` to 12.78°C to match documented hardware range | #18 |
| ⬜ | Remove redundant `extra_state_attributes` already covered by binary sensors | #24 |
| ⬜ | Deduplicate `round_half_up` into a single utility module | #22 |

**Exit criteria:**

- Per-user-action call cost is one PATCH (best case) or PATCH + one GET (with refresh), not the current PATCH + multiple GETs and retries.
- Median UI-visible latency between "drag temp slider" and "card shows new setpoint" drops measurably on the test device.
- No regression in observed setpoint vs. requested setpoint.

**API-budget impact:** significant reduction per user action.

---

### Phase 4 — Testing

**Detailed plan: [`phase-4-testing.md`](./phase-4-testing.md).**

| Status | Item |
|--------|------|
| ⬜ | Unit tests for `SleepMeAPI` rate limiter (concurrency + 429 + Retry-After) |
| ⬜ | Unit tests for error classification in `handle_error` |
| ⬜ | Coordinator tests: success, transient failure (UpdateFailed), auth failure (ConfigEntryAuthFailed) |
| ⬜ | Config flow tests: happy path, invalid token, no devices, reauth |
| ⬜ | Climate tests: set_temperature, set_hvac_mode, set_preset_mode, out-of-range rejection |
| ⬜ | Coverage target ≥ 75% on `custom_components/sleepme_thermostat/` |

**Exit criteria:** CI runs the test suite and blocks merges on failure.

---

### Phase 5 — Polish

**Detailed plan: [`phase-5-polish.md`](./phase-5-polish.md).**

| Status | Item |
|--------|------|
| ⬜ | Add `diagnostics.py` for HA's "Download diagnostics" button |
| ⬜ | Drop `api_url` and `name` from `entry.data` |
| ⬜ | Sync ES translation against EN |
| ⬜ | Add `quality_scale: silver` to manifest (assuming Silver criteria are met by this point) |
| ⬜ | README polish: badges, troubleshooting, example automations |

**Exit criteria:** Ready to cut a clean release (e.g., v4.0.0).

---

## Open questions

- **Poll interval default.** 20s today. With one device under one user account on the live API, is 30s acceptable? 60s? Decision deferred until Phase 2 options flow is built and we can A/B against the real device.
- **GET-under-rate-limit policy.** Today: silently discard with `{}`. Options: queue (delay), raise `UpdateFailed`, or drop with a coordinator-visible warning. Decision is part of Phase 1's detailed plan.
- **Should we adopt the more active fork** (derekcentrico's branch) **as the new baseline before refactoring?** Or refactor in-place and cherry-pick from forks? Worth comparing before starting Phase 1.
- **HVACMode.AUTO vs. HEAT_COOL.** Semantic call. Decision can ride along with Phase 3.

## Decisions log

(Capture every "we decided X because Y" here as we go, with date.)

- *2026-05-16:* Roadmap structured by priority phase rather than by file/feature, because P0 items cross multiple files and need to ship together to clear the "is this safe to publish?" bar.
- *2026-05-16:* Phase 3 (the rate-limit win) deliberately sits behind Phase 1, so the verify-loop removal lands against a stable base instead of mixed with bug fixes.
- *2026-05-17:* SleepMe API docs at <https://docs.developer.sleep.me/api/> confirm `set_temperature_c` accepts `-1.0` (MAX COLD), `13.0–48.0` in half-degree steps, or `999.0` (MAX HEAT). Sentinels are part of the API contract, not an integration hack. Phase 3 will use Design A (sentinels survive the API roundtrip; no `RestoreEntity` needed). Temperature bounds corrected from the audit's guessed `12.5–46.5` to the documented `13.0–48.0`.
