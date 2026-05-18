# Phase 5 — Polish & Release Plan

**Status:** Drafted 2026-05-17, awaiting maintainer approval before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md), [`phase-0-foundation.md`](./phase-0-foundation.md), [`phase-1-p0-fixes.md`](./phase-1-p0-fixes.md), [`phase-2-modernization.md`](./phase-2-modernization.md), [`phase-3-climate-refactor.md`](./phase-3-climate-refactor.md), [`phase-4-testing.md`](./phase-4-testing.md).

## Goal

Take the integration from "refactor complete" to "v4.0.0 release ready." Concretely, after Phase 5:

1. HA's *Download diagnostics* button works for any SleepMe entry — token redacted, coordinator snapshot included, structure stable across releases.
2. `entry.data` has no dead state. `api_url` and `name` are removed; reads fall back to constants / `entry.title`. Old v3 entries auto-migrate.
3. Spanish translation is back in sync with `strings.json`.
4. `manifest.json` advertises `quality_scale: silver` and `loggers`, version bumps to `4.0.0`.
5. README earns its top spot in the HACS store: badges, troubleshooting, an example automation, a version-support matrix.
6. Two new tests cover diagnostics + migration. Coverage stays ≥ 80 %.

Phase 5 is the **final phase of the audit-driven refactor.** It does not touch `climate.py`'s runtime path, the transport layer, or the testing matrix.

## Cross-cutting concern: API budget per user action

**Phase 5 is zero impact on the API call budget.** No transport, coordinator, or climate code paths change. Diagnostics is in-process, the schema migration runs once at HA startup against in-memory state, and the manifest/README changes are inert at runtime.

## Scope

| Source | File | Current | Phase 5 action |
|---|---|---|---|
| Audit P2 | new `diagnostics.py` | no diagnostics platform | Add `async_get_config_entry_diagnostics` with token redaction. |
| Audit P2 | `__init__.py`, `config_flow.py`, `climate.py`, `binary_sensor.py`, `sensor.py`, `helpers.py` | `entry.data["api_url"]` always equals `API_URL`; `entry.data["name"]` duplicates entry.title suffix. Config flow `VERSION = 3`. | Drop both keys on new entries; `async_migrate_entry` rewrites old v3 entries; bump config flow `VERSION = 4`. |
| Audit P2 | `translations/es.json` | Missing `data_description` blocks added in Phase 2. | Add the three missing keys (translated). |
| Audit P2 | `manifest.json` | No `quality_scale`, no `loggers`. Version `3.2.2`. | Add `quality_scale: "silver"`, `loggers: [...]`. Bump `version` to `4.0.0`. |
| Audit P2 | `README.md` | 67 lines. No CI badges, no troubleshooting, no example automation. | Rewrite to ≤ 200 lines with badges, feature list, troubleshooting, automation example, version matrix. |
| Implicit gap | `tests/test_diagnostics.py` (new) | none | 2 tests: redaction + structure. |
| Implicit gap | `tests/test_init.py` | v3 fixture only | Add `test_migrate_entry_v3_to_v4`. |

## Deliverables

### 1. Diagnostics platform

**File:** `custom_components/sleepme_thermostat/diagnostics.py` (new, ~50 LOC). HA discovers `diagnostics.py` automatically.

```python
"""Diagnostics support for SleepMe Thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT: set[str] = {
    "api_token",
    "mac_address",
    "serial_number",
    "ip_address",
    "lan_address",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a redacted diagnostic snapshot for a SleepMe config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    coordinator_payload: dict[str, Any] = {}
    if coordinator is not None:
        coordinator_payload = {
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                repr(coordinator.last_exception)
                if coordinator.last_exception is not None
                else None
            ),
            "data": coordinator.data or {},
        }

    return {
        "entry": {
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "device_info": async_redact_data(
            dict(entry_data.get("device_info", {})), TO_REDACT
        ),
        "coordinator": async_redact_data(coordinator_payload, TO_REDACT),
    }
```

Defensive redaction of MAC/IP/LAN/serial — easier to share diagnostics verbatim.

### 2. `entry.data` schema migration v3 → v4

**Files:** `config_flow.py`, `__init__.py`, `helpers.py`, `climate.py`, `binary_sensor.py`, `sensor.py`, `tests/test_init.py`, `tests/test_config_flow.py`.

**Decision: `build_device_info` accepts the full display name (`entry.title`)**, dropping the `"Dock Pro "` prefix composition from `helpers.py`. Cleaner and matches HA's device-registry convention.

#### config_flow.py

```diff
-    VERSION = 3
+    VERSION = 4
```

```diff
                 return self.async_create_entry(
                     title=f"Dock Pro {name}",
                     data={
-                        "api_url": API_URL,
                         "api_token": self.api_token,
                         "device_id": device_id,
-                        "name": name,
                         "firmware_version": ...
                     },
                 )
```

#### __init__.py — add async_migrate_entry

```python
async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    v3 -> v4: drop `api_url` and `name` (both dead state).
    """
    _LOGGER.debug(
        "Migrating SleepMe entry %s from version %s", entry.entry_id, entry.version
    )

    if entry.version < 4:
        new_data = {k: v for k, v in entry.data.items() if k not in ("api_url", "name")}
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)
        _LOGGER.info(
            "Migrated SleepMe entry %s to schema v4 (dropped api_url, name)",
            entry.entry_id,
        )

    return True
```

Simplify async_setup_entry: use `API_URL` constant directly; no more `entry.data["api_url"]`.

#### helpers.py — drop "Dock Pro " prefix

```diff
-def build_device_info(device_id: str, name: str, info: dict) -> DeviceInfo:
+def build_device_info(device_id: str, display_name: str, info: dict) -> DeviceInfo:
     return DeviceInfo(
         identifiers={(DOMAIN, device_id)},
-        name=f"Dock Pro {name}",
+        name=display_name,
         ...
     )
```

#### Platforms — pass `entry.title`

```diff
-    name: str = entry.data["name"]
     ...
-    device_info = build_device_info(device_id, name, entry_data["device_info"])
+    device_info = build_device_info(
+        device_id, entry.title, entry_data["device_info"]
+    )
```

Entity constructors (binary_sensor, sensor) drop their unused `name` parameter (5 sensor classes + 2 binary sensor classes = 7 call sites).

#### Tests

```python
async def test_migrate_entry_v3_to_v4(hass, mock_sleepme_client):
    """A v3 entry auto-migrates to v4: api_url and name removed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            "api_url": API_URL,
            "api_token": MOCK_API_TOKEN,
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            # ... other v3 fields
        },
        ...
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 4
    assert "api_url" not in entry.data
    assert "name" not in entry.data
```

Also: `test_happy_path` asserts no `api_url`/`name` in newly created entries.

### 3. ES translation re-sync

Three missing `data_description` blocks. Add to `translations/es.json`:

```diff
       "user": {
         "data": { "api_token": "Token de API" }
+        ,"data_description": {
+          "api_token": "Ingresa el token de API proporcionado por SleepMe."
+        }
       },
       "select_device": {
         "data": { "device_id": "ID del Dispositivo" }
+        ,"data_description": {
+          "device_id": "Selecciona uno de los dispositivos detectados."
+        }
       },
       "reauth_confirm": {
         "data": { "api_token": "Token de API" }
+        ,"data_description": {
+          "api_token": "Pega un token nuevo generado en la sección Developer API de SleepMe."
+        }
       }
```

Key-set parity check (run locally before commit):

```bash
python -c "
import json
en = json.load(open('custom_components/sleepme_thermostat/translations/en.json'))
es = json.load(open('custom_components/sleepme_thermostat/translations/es.json'))

def flat(d, prefix=''):
    out = set()
    for k, v in d.items():
        path = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            out |= flat(v, path)
        else:
            out.add(path)
    return out

print('Missing in ES:', sorted(flat(en) - flat(es)))
print('Missing in EN:', sorted(flat(es) - flat(en)))
"
```

### 4. quality_scale: silver

Silver requirements check (all met after Phases 0–4 + Phase 5 deliverables 1 + 2):

| Silver requirement | Status |
|---|---|
| `_attr_has_entity_name = True` | ✅ Phase 2 |
| Reauth flow | ✅ Phase 1 |
| Options flow | ✅ Phase 2 |
| `ConfigEntryAuthFailed`, `UpdateFailed` | ✅ Phase 1 |
| Test coverage ≥ 80% | ✅ Phase 4 (89%) |
| `device_info` complete | ✅ |
| Unique IDs on every entity | ✅ |
| Translation files (en + es) | ✅ after deliverable 3 |
| `strings.json` source of truth | ✅ Phase 2 |
| Diagnostics platform | ✅ deliverable 1 |
| `loggers` in manifest | ✅ deliverable 5 |
| `async_unload_entry` | ✅ Phase 1 |
| `async_migrate_entry` | ✅ deliverable 2 |

**Gold** is out of reach: requires device discovery (zeroconf/SSDP), but SleepMe is cloud-only.

### 5. manifest.json updates

```diff
 {
   "domain": "sleepme_thermostat",
   "name": "SleepMe Thermostat",
   "codeowners": ["@rsampayo", "@mikesalz","@derekcentrico"],
   "config_flow": true,
   "dependencies": [],
   "documentation": "https://github.com/rsampayo/sleepme_thermostat",
   "integration_type": "device",
   "iot_class": "cloud_polling",
   "issue_tracker": "https://github.com/rsampayo/sleepme_thermostat/issues",
+  "loggers": ["custom_components.sleepme_thermostat"],
+  "quality_scale": "silver",
   "requirements": [],
-  "version": "3.2.2"
+  "version": "4.0.0"
 }
```

### 6. README polish

Target: ≤ 200 lines. Sections:

```
# SleepMe Dock Pro Integration
[badges]
> One-sentence summary

## Features
## Requirements
## Installation (HACS / manual)
## Configuration
## Entities (table)
## Example automation: cool at bedtime
## Troubleshooting
## Tested against
## Contributing
## License
```

Badges (top of file):
- HACS Custom Repository
- Quality Scale (silver)
- License (MIT)
- Test workflow status
- Validate HACS status
- CodeQL status
- Ruff

Troubleshooting bullets cover: reauth flow, rate-limit handling, scan_interval tuning, downloading diagnostics, log verbosity.

### 7. Version bump to 4.0.0

Rationale baked into deliverable 5's manifest diff. Major bump signals cumulative behavior change across phases:
- Phase 1: reauth flow, unload, multi-device fix.
- Phase 2: has_entity_name (UI label composition changed).
- Phase 3: slider semantics (optimistic state).
- Phase 5: entry.data schema (auto-migrated).

Tag `v4.0.0`. Release notes link to each `phase-N-*.md` doc.

### 8. Tests

`tests/test_diagnostics.py`:
- `test_diagnostics_redacts_token` — `diag["entry"]["data"]["api_token"] == "**REDACTED**"`; other keys survive.
- `test_diagnostics_structure` — top-level keys are `entry`/`device_info`/`coordinator`; coordinator payload has expected fields.

`tests/test_init.py::test_migrate_entry_v3_to_v4` — set up a v3 entry, assert migration to v4 happened on setup.

**Coverage delta:** `diagnostics.py` 0 → ~95%; migration path covered.

## Validation against live device

| # | Step | Pass criterion |
|---|------|----------------|
| 1 | `pytest --cov-fail-under=80` locally | Green. |
| 2 | `pre-commit run --all-files` | Green. |
| 3 | All CI matrix jobs | Green. |
| 4 | `make deploy-restart HA_HOST=100.88.154.98` | Exit 0. |
| 5 | Entity registry continuity (`before.txt` / `after.txt`) | `diff -q` empty. |
| 6 | Migration log line | `"Migrated SleepMe entry <id> to schema v4"` appears once per existing entry. |
| 7 | Storage inspection | `api_url` and `name` absent from `.storage/core.config_entries` sleepme entries; `version: 4`. |
| 8 | "Download diagnostics" | JSON downloads; `api_token == "**REDACTED**"`; `coordinator.data` shape correct. |
| 9 | Options flow still works | No regression. |
| 10 | Reauth still works | No regression. |
| 11 | README badges render on GitHub | All images load. |
| 12 | HACS panel shows v4.0.0 | After tag push. |

## Acceptance / exit criteria

- [ ] `diagnostics.py` exists; redaction set documented.
- [ ] `manifest.json` has `quality_scale: "silver"`, `loggers`, `version: "4.0.0"`.
- [ ] `config_flow.py` `VERSION = 4`; no `api_url` or `name` in new entries.
- [ ] `async_migrate_entry` covers v3 → v4.
- [ ] `build_device_info` accepts full display name; "Dock Pro " composition removed.
- [ ] All platforms pass `entry.title` to `build_device_info`.
- [ ] Entity constructors no longer take `name` parameter.
- [ ] `translations/es.json` parity with EN; key-set diff empty.
- [ ] `README.md` ≤ 200 lines; full Phase 5 outline.
- [ ] `tests/test_diagnostics.py` (2 tests) + `test_migrate_entry_v3_to_v4` exist and pass.
- [ ] `pytest --cov-fail-under=80` green.
- [ ] Live-host validation 4–10 done; results in PR description.
- [ ] All CI jobs green.
- [ ] `docs/ROADMAP.md` Phase 5 row flipped ⬜ → ✅.
- [ ] Git tag `v4.0.0` + release notes.

## Risks and open questions

1. **Redacting MAC/serial/IP** — defensible default (easier to share verbatim), but hides identifiers during real debugging. **Decision: redact by default.** Narrow to `{"api_token"}` only if maintainer disagrees.

2. **Disabled entries don't migrate until enabled.** Both test-host entries (`Ramon`, `Chiva`) are `disabled_by: user`. Migration fires when re-enabled or on next HA restart with them enabled.

3. **`async_redact_data` sentinel string drift.** Currently `"**REDACTED**"` in HA core. Test asserts the literal; if HA changes it, CI catches the divergence.

4. **README badge URLs** assume `rsampayo/sleepme_thermostat`. Quality Scale badge is hand-rolled.

5. **`hass.data` shape for half-loaded entries** — diagnostics function handles missing-entry case via `.get(entry.entry_id, {})`. No crash on `SETUP_RETRY` entries.

## Out of scope (explicit)

| Item | Decision |
|---|---|
| `TypedDict` for `device_info` payload | Optional Phase 6. Strict mypy already type-checks it. |
| Drop `RUF012` from ignore list | Wait for HA framework change. |
| Upgrade `ruff` version | Separate `chore(deps)` PR. |
| Multi-device discovery / zeroconf for Gold | SleepMe is cloud-only. |
| Python 3.12 in matrix | Deferred. |
| HA `dev` channel in matrix | Deferred. |
| Coverage threshold > 80% | Phase 4 settled. |

## Optional Phase 6 follow-ups

1. **`TypedDict` for device_info payload.** Strong typing for the `entry_data["device_info"]` dict that flows through the integration.
2. **CI EN/ES key-set parity check** as a workflow job.
3. **Drop `E731` from ruff ignore** (Phase 3 verify-loop is gone; the lambdas it justified no longer exist).
4. **Per-integration `quality_scale.yaml`** enumerating evaluated criteria.
5. **Re-audit** — refresh `AUDIT.md` after a release shipping cycle; many P1 findings now closed.
