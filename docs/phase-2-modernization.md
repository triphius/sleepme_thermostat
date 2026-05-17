# Phase 2 — HA Modernization Plan

**Status:** Drafted 2026-05-17, awaiting maintainer approval before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md), [`phase-0-foundation.md`](./phase-0-foundation.md), [`phase-1-p0-fixes.md`](./phase-1-p0-fixes.md).

## Goal

Bring `sleepme_thermostat` in line with current HA integration conventions without changing observable behavior on the climate command path or the transport layer. Concretely, after Phase 2:

1. Entities follow `_attr_has_entity_name = True` — the HA UI composes "Device + entity" labels automatically. Entity IDs are unchanged.
2. The user can change the coordinator poll interval at runtime via the integration's "Configure" menu (options flow). No restart required.
3. `BrightnessLevelSensor` produces long-term statistics (`state_class = MEASUREMENT`).
4. Dead code (`async_step_import`) is gone and `device_info["connections"]` uses the canonical `CONNECTION_NETWORK_MAC` constant.
5. The two remaining f-string logger calls in `climate.py` use lazy `%s`.
6. Lint/format runs against the whole repo, not just `tests/`. Phase 2 opens with a single mechanically generated format-only commit so the behavior diff and the format diff are reviewable independently.
7. `strings.json` decision is made and documented (recommendation: **adopt** as source of truth; auto-mirror `translations/en.json` via a CI diff check).
8. Audit items #11, #12, and #19 are verified closed by Phase 1 — Phase 2 does not re-do that work.

Phase 2 explicitly does NOT touch the climate verify-after-command retry loop (Phase 3), add a diagnostics platform (Phase 5), add a coverage gate or HA matrix (Phase 4), change the `entry.data` schema (Phase 5), or switch `black` → `ruff format` (deferred to Phase 4).

## Scope

Audit items reconciled against current code on `main` (post-Phase-1):

| Audit # | File | Current state on `main` | Phase 2 action |
|---|---|---|---|
| — | new | n/a | **Add options flow** — single setting (`scan_interval`, default 20s, range 10–300s). |
| 14 | climate, binary_sensor, sensor | All three platforms set `self._attr_name = f"Dock Pro {name} {suffix}"`. No `has_entity_name`. | Set `_attr_has_entity_name = True`; rename to just the suffix (or `None` for climate). |
| 13 | sensor.py | `BrightnessLevelSensor` has `_attr_native_unit_of_measurement = "%"` but no `state_class`. | Add `_attr_state_class = SensorStateClass.MEASUREMENT`. |
| 12 | sensor.py | All sensor classes use `native_value`. | **Closed by Phase 1.** Verify only. |
| 11 | binary_sensor.py, sensor.py | No `persistent_notification` references anywhere. | **Closed by Phase 1.** Verify only. |
| 21 | config_flow.py | `async_step_import` does not exist. | **Closed by Phase 1.** Verify only. |
| 25 | climate.py:53, sensor.py:23, binary_sensor.py:23 | `"connections": {("mac", info.get("mac_address"))}` — string literal in all three. | Import `CONNECTION_NETWORK_MAC`; use the constant. |
| 19 | __init__.py:36 | `raise ConfigEntryNotReady(...)` already present. | **Closed by Phase 1.** Verify only. |
| 23 | climate.py:181, climate.py:184 | Two f-string `_LOGGER` calls remain. | Convert to `%s` placeholders. |
| — | new | `translations/en.json` is edited directly. No `strings.json`. | **Recommendation:** add `strings.json` as source-of-truth; `translations/en.json` becomes a manual mirror with a CI diff check. |
| — | tooling | `.pre-commit-config.yaml` has `files: ^tests/` on ruff/black hooks. CI lints only `tests/`. | One format-only commit applies `ruff --fix` + `black` to `custom_components/`. Second commit drops the `files:` filter and updates CI. |
| — | tooling | `black` 24.10.0 pinned. | **Keep `black` through Phase 2.** Migration to `ruff format` deferred to Phase 4. |
| — | new | No diagnostics platform. | **Out of scope** — Phase 5. |

## Deliverables

### 1. Pre-commit scope flip (format-only opening commit + filter removal)

**Files:** `.pre-commit-config.yaml`, `.github/workflows/test.yml`, every `.py` under `custom_components/sleepme_thermostat/`.

**Commit sequence inside the Phase 2 PR.** The PR should land as a sequence of small, individually reviewable commits. The first commit is mechanically generated and zero-behavior.

| # | Commit subject | Files touched | Notes |
|---|---|---|---|
| 1 | `chore(format): apply ruff --fix + black to custom_components/` | All `.py` under `custom_components/sleepme_thermostat/` | Mechanically generated. No behavior change. |
| 2 | `ci: drop tests/-only scoping; lint+format the whole repo` | `.pre-commit-config.yaml`, `.github/workflows/test.yml` | Delete `files: ^tests/` from ruff/ruff-format/black hooks. Update lint job to `ruff check .` and `black --check .`. |
| 3 | `feat(config): options flow for scan_interval` | `__init__.py`, `config_flow.py`, `update_manager.py`, `const.py`, translations, `tests/test_config_flow.py` | Deliverable 2. |
| 4 | `feat(entity): adopt _attr_has_entity_name across platforms` | `climate.py`, `binary_sensor.py`, `sensor.py` | Deliverable 3. |
| 5 | `feat(sensor): state_class=MEASUREMENT on BrightnessLevelSensor` | `sensor.py` | Deliverable 4. |
| 6 | `refactor: CONNECTION_NETWORK_MAC; lazy %s logging` | `climate.py`, `sensor.py`, `binary_sensor.py` | Deliverables 6 + 7. |
| 7 | `chore(i18n): strings.json source-of-truth` | New `strings.json`, regenerated `translations/en.json`, README doc note | Deliverable 8. Only if recommendation accepted. |

Step 1 reproducible by maintainer with:

```bash
ruff check --fix custom_components/
black custom_components/
git add custom_components/ && git commit -m "chore(format): apply ruff --fix + black"
```

Step 2 — exact diff against `.pre-commit-config.yaml`:

```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
-       files: ^tests/
      - id: ruff-format
-       files: ^tests/

  - repo: https://github.com/psf/black
    rev: 24.10.0
    hooks:
      - id: black
-       files: ^tests/
```

Exact diff against `.github/workflows/test.yml`:

```yaml
   lint:
     ...
-      - name: ruff check (tests only in Phase 0)
-        run: ruff check tests
-      - name: black --check (tests only in Phase 0)
-        run: black --check tests
+      - name: ruff check
+        run: ruff check .
+      - name: black --check
+        run: black --check .
```

**Expected diff shape:**
- Commit 1: mechanical, large but trivial. Best-guess ~150 lines of whitespace/quote/import-order changes across 7 files.
- Commit 2: ~6 lines in `.pre-commit-config.yaml`, ~6 lines in `.github/workflows/test.yml`.

**API-budget impact:** none.

**Gotcha.** If `ruff format` and `black` disagree on any line, run `ruff format` first then `black`. Phase 2 keeps `black` as authoritative; `ruff format` stays scoped to `tests/` via per-target config until Phase 4 migrates everything to `ruff format`.

---

### 2. Options flow (scan_interval)

**Files:** `config_flow.py` (add `async_get_options_flow` + new `OptionsFlowHandler`), `__init__.py` (read option + register update listener), `update_manager.py` (accept `scan_interval` in constructor), `const.py` (new constants), translations, `tests/test_config_flow.py`.

**Behavior contract.**

1. Default `scan_interval`: 20 seconds. Stored at `entry.options["scan_interval"]`.
2. Allowed range: 10–300s. Validator rejects out-of-range with form error `invalid_scan_interval`.
3. Change takes effect by **reloading the entry**, not by mutating a live coordinator. The reload path is already exercised by the reauth flow.
4. No restart required. UX: Settings → Devices & Services → SleepMe → Configure → enter value → save.

**New `const.py` constants:**

```python
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 20
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300
```

**Paste-ready `__init__.py` additions:**

```python
from .const import (
    API_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SleepMe Thermostat from a config entry."""
    api_url = entry.data.get("api_url") or API_URL
    api_token = entry.data.get("api_token")
    device_id = entry.data.get("device_id")

    if not api_token or not device_id:
        raise ConfigEntryNotReady("API token or device ID missing from entry data")

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    client = SleepMeClient(hass, api_url, api_token, device_id)
    coordinator = SleepMeUpdateManager(
        hass, api_url, api_token, device_id, scan_interval=scan_interval
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "device_info": { ... },  # unchanged
    }

    # Reload entry on options change. async_on_unload registers the unsubscribe
    # so it fires automatically during async_unload_entry.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
```

**Paste-ready `update_manager.py` change:**

```python
class SleepMeUpdateManager(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        api_url: str,
        token: str,
        device_id: str,
        scan_interval: int = 20,
    ) -> None:
        self.client = SleepMeClient(hass, api_url, token, device_id)
        self.device_id = device_id
        super().__init__(
            hass,
            _LOGGER,
            name=f"SleepMe Update Manager {device_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
```

**Paste-ready `config_flow.py` additions:**

```python
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


class SleepMeThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    # ... existing methods unchanged ...

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SleepMeOptionsFlowHandler(config_entry)


class SleepMeOptionsFlowHandler(OptionsFlow):
    """Options flow: poll interval only (Phase 2)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            value = user_input[CONF_SCAN_INTERVAL]
            if not MIN_SCAN_INTERVAL <= value <= MAX_SCAN_INTERVAL:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
```

**Translation additions (`translations/en.json`):**

```json
"options": {
  "step": {
    "init": {
      "title": "SleepMe Dock Pro options",
      "description": "Adjust how often Home Assistant polls the SleepMe API for this device. Lower values feel more responsive but consume more of your per-minute API budget.",
      "data": {
        "scan_interval": "Poll interval (seconds)"
      }
    }
  },
  "error": {
    "invalid_scan_interval": "Poll interval must be between 10 and 300 seconds."
  }
}
```

(And the Spanish equivalent in `es.json`.)

**Expected diff shape:**
- `__init__.py`: +5 lines (option read), +5 lines (update listener + register).
- `update_manager.py`: +1 parameter, ~3 lines changed.
- `config_flow.py`: +60 lines (new options flow class + static method).
- `const.py`: +4 lines.
- `translations/en.json` + `es.json`: ~12 lines each.
- `tests/test_config_flow.py`: +50 lines (new test).

**API-budget impact:**
- **Per scan-interval change:** 1 GET (first refresh after reload).
- **Per minute idle, default (20s):** unchanged at 3 GET/min.
- **Per minute idle, user-tuned to 60s:** 1 GET/min — **the single biggest dial on idle call volume**, exposed exactly because of this audit recommendation.

**Deferred to Phase 3.** Once Phase 3 ships, the options flow may grow:
- "Max retries on 429" (3 today, settable 0–5).
- "Coalesce slider drags" toggle for the climate path.

---

### 3. `_attr_has_entity_name` adoption

**Files:** `climate.py`, `binary_sensor.py`, `sensor.py`.

**HA convention.** When an entity sets `_attr_has_entity_name = True`:
- HA composes the friendly name as `f"{device.name} {entity._attr_name}"` automatically.
- If `_attr_name` is `None`, HA uses `device.name` directly — used for the *primary* entity of a device.
- Entity IDs are *not* affected. The entity registry preserves the slug from first creation.

**Which entity is the "primary"?** The climate entity. So `SleepMeThermostat` gets `_attr_name = None`; everything else gets a suffix.

**Paste-ready pattern — `climate.py`:**

```python
class SleepMeThermostat(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None  # climate inherits device name → friendly_name == "Dock Pro Ramon"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_thermostat"
        self._previous_target_temperature = None
        self._attr_device_info = { ... }  # unchanged

    # Delete the `name` property entirely. _attr_name = None drives it.
```

Note: delete the `@property def name(self)` and `self._name` attribute. Both become dead code.

**Paste-ready pattern — `binary_sensor.py`:**

```python
class WaterLevelLowSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Water Level"          # was: f"Dock Pro {name} Water Level"
    _attr_device_class = "problem"

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_low"
        self._attr_device_info = device_info


class DeviceConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = "connectivity"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, name, device_info):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_connected"
        self._attr_device_info = device_info
```

The `name` constructor parameter becomes unused on these classes. **Keep it in the signature** so the platform `async_setup_entry` doesn't change shape this pass.

**Paste-ready pattern — `sensor.py`:** the `_SleepMeDiagnosticSensor` base shrinks. The `label` parameter becomes the `_attr_name`:

```python
class _SleepMeDiagnosticSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, name, device_info, *, suffix, label):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = label                                # just the suffix
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{suffix}"
        self._attr_device_info = device_info
```

**Migration risk note for changelog.** Worth one line in the release notes:

> v3.3.0 modernizes how HA labels SleepMe entities. The visible name of each entity in the UI is unchanged; the entity_ids you use in automations are unchanged.

**Expected diff shape:**
- `climate.py`: ~10 lines changed.
- `binary_sensor.py`: ~8 lines changed.
- `sensor.py`: ~4 lines changed in the base class.

**API-budget impact:** none.

---

### 4. `state_class = MEASUREMENT` on `BrightnessLevelSensor`

**File:** `sensor.py`.

**Paste-ready:**

```python
from homeassistant.components.sensor import SensorEntity, SensorStateClass

class BrightnessLevelSensor(_SleepMeDiagnosticSensor):
    """Display brightness in percent."""

    _attr_icon = "mdi:brightness-6"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT  # new
    ...
```

**Why only `BrightnessLevelSensor`** and not the others: the rest are string-valued (`MEASUREMENT` is a numeric state class).

**Expected diff shape:** 2 lines added.

**API-budget impact:** none.

---

### 5. Drop `async_step_import` dead code

**Status: closed by Phase 1.** Verified at `config_flow.py` — there is no `async_step_import` method. No-op for Phase 2.

**Verification step before declaring closed:**

```bash
grep -n 'async_step_import' custom_components/sleepme_thermostat/config_flow.py
# Expected: no matches.
```

---

### 6. `CONNECTION_NETWORK_MAC` constant

**Files:** `climate.py`, `binary_sensor.py`, `sensor.py`.

**Paste-ready pattern** (apply identically to all three files):

```python
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

# ...
"connections": {(CONNECTION_NETWORK_MAC, info.get("mac_address"))},
```

**Side note (deferred).** The `_device_info` helper is duplicated across `binary_sensor.py` and `sensor.py`. Dedup is a Phase 3 nice-to-have alongside `round_half_up` consolidation. Phase 2 keeps the duplication.

**Expected diff shape:** 3 imports + 3 dict-key changes = ~6 lines.

**API-budget impact:** none.

---

### 7. Lazy `%s` logging (only where not already done)

**File:** `climate.py` only.

**Already done by Phase 1.** Every `_LOGGER` call elsewhere in `custom_components/` uses `%s`.

Two remaining matches in `climate.py`:

```python
# climate.py:181 (current)
_LOGGER.warning(f"[Device {self._device_id}] Temperature {target_temp}C is out of range.")

# climate.py:184 (current)
_LOGGER.info(f"[Device {self._device_id}] Setting target temperature to {target_temp}C")
```

**Paste-ready replacement:**

```python
# climate.py:181 (new)
_LOGGER.warning(
    "[Device %s] Temperature %sC is out of range.",
    self._device_id, target_temp,
)

# climate.py:184 (new)
_LOGGER.info(
    "[Device %s] Setting target temperature to %sC",
    self._device_id, target_temp,
)
```

**Do not lint-sweep beyond logger calls.** The codebase contains many other f-strings (URLs, exception messages). Those should stay f-strings.

**Expected diff shape:** 2 logger calls changed, ~10 lines total.

**API-budget impact:** none.

---

### 8. `strings.json` migration — recommendation

**Recommendation: option (a) — adopt `strings.json` as source of truth; `translations/en.json` becomes a manual mirror with a CI diff check.**

**Background.** HA Core's translation pipeline uses `strings.json` as the source-of-truth; Lokalise emits language files. For **custom components published via HACS**, this pipeline is not available. Three real options:

| Option | What it looks like | Pros | Cons |
|---|---|---|---|
| **(a)** | Add `strings.json` at the integration root. Keep `translations/en.json` identical to `strings.json` (CI check: `diff -q`). Translate `es.json` from `strings.json`. | Aligns with core HA. Future-proofs. One source of English. | Adds a CI step. Mild churn. |
| (b) | Status quo. Edit `translations/en.json` directly. | Zero work. | Audit flagged it. Drift from convention. |
| (c) | `strings.json` plus a generated `translations/en.json` via custom script. | Most idiomatic. | Most work. Tooling undocumented for custom components. |

**Recommendation:** Adopt **(a)**. Phase 2 commit:

1. Copy current `translations/en.json` to `strings.json` at the integration root.
2. Add a CI step: `diff -q custom_components/sleepme_thermostat/strings.json custom_components/sleepme_thermostat/translations/en.json`.
3. README addition: "When editing translations, edit `strings.json` first, then copy to `translations/en.json`."
4. `translations/es.json` is hand-maintained; it does not block CI.

CI step:

```yaml
  i18n-check:
    name: strings.json mirrors en.json
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: diff -q custom_components/sleepme_thermostat/strings.json custom_components/sleepme_thermostat/translations/en.json
```

**Defer-this-to-later alternative:** If the maintainer prefers, **skip this deliverable in Phase 2** and revisit in Phase 5 alongside ES translation re-sync. The audit item is borderline P2.

**Expected diff shape:**
- New `strings.json`: ~50 lines.
- New CI job: ~8 lines.
- README addition: ~5 lines.

**API-budget impact:** none.

---

### 9. Tests covering the above

Phase 2 test scope is tight. Phase 4 is the dedicated testing phase.

**New tests in `tests/test_config_flow.py`:**

1. `test_options_flow_happy_path` — set up an entry, open options flow, submit `{CONF_SCAN_INTERVAL: 60}`, assert `result["type"] is FlowResultType.CREATE_ENTRY` and `entry.options[CONF_SCAN_INTERVAL] == 60`. Assert entry got reloaded (`coordinator.update_interval == timedelta(seconds=60)`).
2. `test_options_flow_rejects_out_of_range` — submit `{CONF_SCAN_INTERVAL: 5}`, assert form re-shows with `errors[CONF_SCAN_INTERVAL] == "invalid_scan_interval"`. Same with `301`.

**New test in `tests/test_init.py`:**

3. `test_options_change_reloads_entry` — set up an entry; mutate `entry.options[CONF_SCAN_INTERVAL]` via `hass.config_entries.async_update_entry(entry, options=...)`; await; assert the new coordinator was instantiated with the new interval.

**Expected diff shape:** `tests/test_config_flow.py` +60 lines, `tests/test_init.py` +25 lines.

**API-budget impact:** none.

---

## Cross-cutting verification

Before opening the Phase 2 PR, verify Phase 1's silent closures of audit items #11, #12, and #19:

```bash
# #11 — persistent_notification.create gone
grep -rn 'persistent_notification' custom_components/sleepme_thermostat/
# Expected: zero matches.

# #12 — state property gone from SensorEntity subclasses
grep -n 'def state' custom_components/sleepme_thermostat/sensor.py
# Expected: zero matches.

# #19 — ConfigEntryNotReady raised in __init__.py
grep -n 'ConfigEntryNotReady\|return False' custom_components/sleepme_thermostat/__init__.py
# Expected: at least one `raise ConfigEntryNotReady`; zero `return False` on missing data.

# #21 — async_step_import is dead code → removed
grep -n 'async_step_import' custom_components/sleepme_thermostat/config_flow.py
# Expected: zero matches.

# #23 — f-string logger calls remaining (the ones Phase 2 will fix)
grep -rn '_LOGGER\.' custom_components/sleepme_thermostat/ | grep 'f"'
# Expected before Phase 2: 2 matches in climate.py.
# Expected after Phase 2: 0 matches.
```

These greps belong in the PR description, run before commit and re-run after, with the output pasted in.

---

## Validation steps against live device

**Live host:** `100.88.154.98` (Tailscale). Deploy: `make deploy-restart HA_HOST=100.88.154.98`. Both `Dock Pro Ramon` and `Dock Pro Chiva` enabled (post-Phase-1).

**Pre-deploy: capture entity_ids.**

The single most important live check is **entity registry continuity**:

```bash
ssh hassio@100.88.154.98 'jq ".data.entities[] | select(.platform == \"sleepme_thermostat\") | .entity_id" /homeassistant/.storage/core.entity_registry' > /tmp/before.txt
```

After deploy:

```bash
ssh hassio@100.88.154.98 'jq ".data.entities[] | select(.platform == \"sleepme_thermostat\") | .entity_id" /homeassistant/.storage/core.entity_registry' > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
# Expected: zero diff lines.
```

**Validation matrix.**

1. `pytest` passes locally — both existing 20 tests and the 3 new ones.
2. `pre-commit run --all-files` clean (running against the whole tree for the first time).
3. `make deploy-restart HA_HOST=100.88.154.98` succeeds. Tail log; expect zero deprecation warnings for `sleepme_thermostat`.
4. **Entity friendly names.** Device card shows entities by short name: "Water Level", "Connected", "IP Address", etc. Climate entity is the device-level entity.
5. **Entity IDs unchanged** (verified by diff above).
6. **Options flow.** Configure → set to 60s → save → entry reloads → 1 GET/min on that entry. `entry.options["scan_interval"] == 60` in storage. `5` rejected with form error.
7. **Brightness statistics.** Settings → Developer Tools → Statistics → search "brightness". Expected: listed (was not, before Phase 2).
8. **Reauth + multi-device unchanged.** Re-run Phase 1's reauth check on `Dock Pro Chiva`. Expected: no regression.

If `binary_sensor.dock_pro_ramon_water_level` shows up in `after.txt` as `binary_sensor.water_level`, an automation breakage is imminent. Roll back and reinvestigate.

---

## Acceptance / exit criteria

- [ ] `ruff check .` and `black --check .` pass against the entire repo.
- [ ] `mypy custom_components/sleepme_thermostat` continues to pass (advisory mode).
- [ ] `pytest` passes including 3 new tests.
- [ ] `pre-commit run --all-files` clean.
- [ ] `grep -rn 'persistent_notification' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `grep -rn '_LOGGER\..*f"' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `grep -rn '"mac"' custom_components/sleepme_thermostat/` returns zero matches for the string literal in `connections=`.
- [ ] `grep -rn 'async_step_import' custom_components/sleepme_thermostat/` returns zero matches.
- [ ] `BrightnessLevelSensor` has `_attr_state_class = SensorStateClass.MEASUREMENT`.
- [ ] `SleepMeThermostat` has `_attr_has_entity_name = True` and `_attr_name = None`.
- [ ] All `BinarySensorEntity` and `SensorEntity` subclasses have `_attr_has_entity_name = True` and a *suffix-only* `_attr_name`.
- [ ] `SleepMeThermostatConfigFlow.async_get_options_flow` returns `SleepMeOptionsFlowHandler`; HA UI shows a "Configure" button.
- [ ] `entry.options[CONF_SCAN_INTERVAL]` round-trips through the options flow.
- [ ] On the live host, entity_ids before and after the deploy diff is empty.
- [ ] Set scan_interval=60 → entry reloads → log shows 1 GET/min on that entry.
- [ ] No `[deprecat]` lines mentioning `sleepme_thermostat` in `home-assistant.log` after a fresh restart.
- [ ] If strings.json was adopted: `i18n-check` CI step passes; files are byte-identical.
- [ ] `docs/ROADMAP.md` Phase 2 table flipped ⬜ → ✅.
- [ ] HACS validate, hassfest, CodeQL, and the `Test` workflow all green on the PR.

---

## Risks and open questions

1. **`black` and `ruff format` disagreeing on `climate.py`.** The pre-Phase-2 `climate.py` predates Phase 1's polish. Mitigation: in commit 1, run `black` only (not `ruff format`) over `custom_components/`. `ruff format` stays scoped to `tests/` until Phase 4's migration.

2. **HA's `_attr_name = None` semantics on `ClimateEntity`.** Documented HA behavior since 2023.9. Phase 2's HA pin (2026.4+) is safely past that.

3. **Options-change reload race.** `entry.async_on_unload(entry.add_update_listener(_async_update_listener))` fires after options write. Two reloads in flight is theoretically possible; HA Core's `async_reload` is idempotent-by-state.

4. **`strings.json` adoption vs. hassfest behavior.** hassfest currently ignores `strings.json` in custom components. CI diff-check is the canary.

5. **Brightness `state_class = MEASUREMENT` backfill.** HA backfills LTS only from the moment `state_class` is set. Pre-Phase-2 brightness history won't appear in stats.

6. **`scan_interval` lower bound at 10s.** At 10s × 2 devices = 12 GET/min — over the 9/min local cap. Result: `SleepMeRateLimited` raised on every other poll. Mitigation: the description text says "Lower values feel more responsive but consume more of your per-minute API budget." Phase 3 can revisit per-account rate-limit sharing.

7. **The `name` constructor parameter on sensor/binary_sensor classes becomes unused.** Ruff `ARG002` is not currently enabled. If enabled in Phase 4, prefix with `_`.

---

## Out of scope (explicit)

| Item | Phase |
|---|---|
| Climate verify-after-command retry-loop removal | 3 |
| Optimistic state writes + single refresh after PATCH | 3 |
| `ServiceValidationError` on out-of-range temperatures | 3 |
| `min_temp` 12.5 → 12.78 | 3 |
| `round_half_up` deduplication | 3 |
| `_device_info` helper deduplication across platforms | 3 |
| `extra_state_attributes` removal from climate entity | 3 |
| Preset-mode encoding refactor (sentinels → explicit state) | 3 |
| Diagnostics platform (`diagnostics.py`) | 5 |
| Drop `api_url` and `name` from `entry.data` | 5 |
| Sync ES translation against EN | 5 |
| `quality_scale: silver` in manifest | 5 |
| Multi-version HA test matrix | 4 |
| Coverage gate at ≥ 75% | 4 |
| `black` → `ruff format` migration | 4 |
| Sharing rate-limiter deque across `SleepMeAPI` instances | 4/5 if needed |
| Coalesce/debounce slider drags before PATCH | 3 |
| `loggers` / `quality_scale` keys in `manifest.json` (audit #20) | 5 |
| Lint-sweep f-strings outside logger calls | never (intentional) |
