# Phase 4 — Testing Maturity Plan

**Status:** Drafted 2026-05-17, awaiting maintainer approval before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md), [`phase-0-foundation.md`](./phase-0-foundation.md), [`phase-1-p0-fixes.md`](./phase-1-p0-fixes.md), [`phase-2-modernization.md`](./phase-2-modernization.md), [`phase-3-climate-refactor.md`](./phase-3-climate-refactor.md).

## Goal

Make the test suite robust enough to support ongoing maintenance. Concretely, after Phase 4:

1. CI enforces a coverage floor on `custom_components/sleepme_thermostat/` — measured, not guessed.
2. The pytest matrix exercises four HA Core releases spanning ~12 months, catching deprecations before they reach users.
3. `black` is gone; `ruff format` is the single source of truth for formatting.
4. mypy is no longer advisory: `disallow_untyped_defs`, `disallow_incomplete_defs`, `check_untyped_defs`, and `strict_optional` are on, the `|| true` suffix in CI is dropped, and the gaps in `sensor.py` / `binary_sensor.py` / `climate.py` / `__init__.py` are closed with real annotations.
5. Test gaps in `sleepme.py` and `update_manager.py` are filled.
6. The Phase 0 promise — "coverage gate at ≥ 75 %, deferred to Phase 4" — is delivered.

Phase 4 does not change runtime behavior. Every change is in `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/test.yml`, `requirements_test.txt`, and `tests/` — plus the minimum annotation additions inside `custom_components/sleepme_thermostat/` required to clear strict mypy.

## Cross-cutting concern: API budget per user action

**Phase 4 is zero-impact on the API call budget.** No transport, coordinator, or climate code paths change. The only edits inside `custom_components/sleepme_thermostat/` are type annotations on existing functions.

## Scope

| Source | File | Current | Phase 4 action |
|---|---|---|---|
| Phase 0 deferred | `test.yml` | `pytest --cov` reports but does not enforce | Add `--cov-fail-under=<measured baseline>` after preflight measurement. |
| Phase 0 deferred | `test.yml` | Matrix has one HA version (`2026.5`). | Extend to four: `2025.10`, `2026.1`, `2026.3`, `2026.5`. |
| Phase 2 deferred | `pyproject.toml`, `.pre-commit-config.yaml`, `test.yml` | `black` 24.10.0 owns formatting on `custom_components/`; `ruff format` scoped to `tests/`. | Switch to `ruff format` repo-wide. Drop `black`. |
| Phase 0 deferred | `pyproject.toml`, `test.yml` | mypy lenient + `\|\| true` in CI. | Enable strict flags. Drop `\|\| true`. Add annotations to silence errors. |
| Implicit gap | `tests/` | No tests of `sleepme.py` client wrapper methods. | New `tests/test_sleepme.py` with ~6 tests. |
| Implicit gap | `tests/test_coordinator.py` | Covers error translation. | Add happy-path test that `_async_update_data` returns the three-key dict. |
| Implicit gap | `tests/test_climate.py` | Covers happy path + sentinel preset + transport failure. | Add optimistic-window-expiry test, `current_temperature` test, `available` test. |

## Deliverables

### 1. Coverage baseline measurement (preflight)

**First action of Phase 4.** Numbers drive every other gate.

**Maintainer commands (local):**

```bash
pip install -r requirements_test.txt
pytest --cov --cov-report=term-missing --cov-report=html
```

**Outputs to paste into the PR description:**

- Overall coverage percentage.
- The per-file table (lines, missing, branch, partial, coverage %).
- Per-file "missing lines" for any file < 80 %.

**Decision rule for the gate threshold (deliverable 2):**

| Measured overall coverage | Action | Resulting gate |
|---|---|---|
| ≥ 85 % | Set gate at 80 %. | `--cov-fail-under=80` |
| 80–85 % | Set gate at 75 % per ROADMAP. | `--cov-fail-under=75` |
| 75–80 % | Fill `sleepme.py` gap (deliverable 6.1) first, re-measure. | `--cov-fail-under=75` |
| < 75 % | Spec a "coverage backfill" sub-deliverable before flipping any gate on. | TBD |

Paste the chosen threshold into commit 2's CI yaml. **Do not pick a number until the preflight run reports.**

### 2. Coverage gate

**Files:** `.github/workflows/test.yml`, `pyproject.toml`.

```toml
[tool.coverage.report]
fail_under = 75       # set per deliverable 1's measurement
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

CI change:

```yaml
      - name: Run tests with coverage gate
        run: pytest --cov --cov-report=term-missing --cov-fail-under=75
```

**Matrix interaction:** each matrix job runs the gate independently. Do not aggregate.

### 3. HA version matrix

**File:** `.github/workflows/test.yml`.

| HA Core version | Released | p-h-c-c version (verify at PyPI) | Python |
|---|---|---|---|
| `2025.10.x` | Oct 2025 | look up at <https://pypi.org/project/pytest-homeassistant-custom-component/#history> | 3.13 |
| `2026.1.x` | Jan 2026 | look up | 3.13 |
| `2026.3.x` | Mar 2026 | look up | 3.14 |
| `2026.5.x` | May 2026 | `0.13.331` (current) | 3.14 |

**Paste-ready `pytest` job:**

```yaml
  pytest:
    name: pytest (HA ${{ matrix.ha-version }}, py${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - ha-version: "2025.10"
            phcc-version: "0.13.230"   # VERIFY
            python-version: "3.13"
          - ha-version: "2026.1"
            phcc-version: "0.13.270"   # VERIFY
            python-version: "3.13"
          - ha-version: "2026.3"
            phcc-version: "0.13.300"   # VERIFY
            python-version: "3.14"
          - ha-version: "2026.5"
            phcc-version: "0.13.331"
            python-version: "3.14"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: requirements_test.txt
      - name: Install matrix-specific HA + phcc
        run: |
          pip install --upgrade-strategy eager \
            homeassistant==${{ matrix.ha-version }}.* \
            pytest-homeassistant-custom-component==${{ matrix.phcc-version }} \
            pytest-cov==7.1.0
      - name: Run tests with coverage gate
        run: pytest --cov --cov-report=term-missing --cov-fail-under=75
```

`requirements_test.txt` stays as-is, pinned to newest HA for local dev.

**Rationale for matrix choices:**

- 4 versions, not more: each entry adds ~3min of pytest cold-start.
- Skip beta channel: phcc only ships against released HA versions.
- Why include `2025.10`? HA's official support window is ~12 months.
- Why not `2025.6` (12 months back)? Adding it would require Python 3.12 in the matrix, doubling axes.

### 4. black → ruff format migration

**Commit sequence:**

| # | Commit subject | Files |
|---|---|---|
| 1 | `chore(format): ruff format -- replacing black` | All `.py` in `custom_components/` and `tests/`. |
| 2 | `ci: drop black; ruff format owns formatting` | `pyproject.toml`, `.pre-commit-config.yaml`, `test.yml`. |

**Step 1 — measure the diff first:**

```bash
ruff format --check --diff custom_components/ tests/ > /tmp/ruff_format_diff.txt
wc -l /tmp/ruff_format_diff.txt   # share in PR description; should be small
```

**If the diff exceeds ~50 LOC or touches climate optimistic-state in any non-trivial way, stop and investigate.** Recovery path: keep `black` for one more release; defer the migration to Phase 5.

**Then apply:**

```bash
ruff format custom_components/ tests/
git add custom_components/ tests/ && git commit -m "chore(format): ruff format -- replacing black"
```

**Step 2 — `pyproject.toml` changes:**

- Keep `[tool.ruff]` and `[tool.ruff.lint]` as-is.
- Keep `[tool.ruff.format]` block (now repo-wide, no scope restriction).
- Delete `[tool.black]` block entirely.

**`.pre-commit-config.yaml`:**

```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
        # REMOVED: files: ^tests/

# DELETED entire black block.
```

**`test.yml` lint job:**

```yaml
      - run: pip install ruff==0.8.4
      - name: ruff check
        run: ruff check .
      - name: ruff format --check
        run: ruff format --check custom_components tests
```

### 5. mypy tightening

**Preflight: measure first.**

```bash
mypy custom_components/sleepme_thermostat \
  --disallow-untyped-defs \
  --disallow-incomplete-defs \
  --check-untyped-defs \
  --strict-optional \
  --ignore-missing-imports \
  --no-incremental > /tmp/mypy_strict.txt 2>&1
wc -l /tmp/mypy_strict.txt
grep '^custom_components' /tmp/mypy_strict.txt | awk -F: '{print $1}' | sort | uniq -c | sort -rn
```

**Expected error landscape: 20–30 errors, mostly in `sensor.py` and `binary_sensor.py` (entity `__init__` parameter types, `native_value`/`is_on` return types).**

**`pyproject.toml`:**

```toml
[tool.mypy]
python_version = "3.14"
ignore_missing_imports = true
follow_imports = "silent"
warn_unused_ignores = true
warn_redundant_casts = true
# Phase 4: tighten.
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
strict_optional = true
disable_error_code = ["import-untyped"]
exclude = [
    "tests/",
]
```

**`test.yml` typecheck job:** drop `|| true` suffix.

**Annotation patterns to apply:**

```python
# sensor.py / binary_sensor.py — async_setup_entry pattern
from collections.abc import Callable
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None: ...
```

```python
# sensor.py base — __init__
def __init__(
    self,
    coordinator: SleepMeUpdateManager,
    device_id: str,
    name: str,
    device_info: dict[str, Any],
    *,
    suffix: str,
    label: str,
) -> None: ...

@property
def native_value(self) -> str | None: ...
```

```python
# binary_sensor.py — is_on
@property
def is_on(self) -> bool | None:
    return self.coordinator.data["status"].get("is_water_low")
```

**Cycle-free coordinator type import:**

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .update_manager import SleepMeUpdateManager
```

**Risk:** if `disallow_untyped_defs` surfaces structural mypy errors on HA's own `CoordinatorEntity` superclass, prefer `# type: ignore[override]` over weakening flags.

### 6. Test gap fills

#### 6.1 `sleepme.py` — direct client tests (new file `tests/test_sleepme.py`)

The client wrapper is currently exercised only through the mocked coordinator. ~80 LOC.

Tests:
- `test_set_temp_level_rounds_to_half` — 24.3 → 24.5 in PATCH payload.
- `test_set_temp_level_passes_sentinel_unrounded` — -1 (MAX COOL) survives.
- `test_set_device_status_rejects_unknown` — ValueError for "paused".
- `test_set_device_status_active` — PATCH body is correct.
- `test_get_claimed_devices_rejects_non_list` — ValueError on wrong shape.
- `test_get_device_status_rejects_non_dict` — ValueError on wrong shape.
- `test_get_claimed_devices_happy` — returns the list.

**Coverage delta:** `sleepme.py` from ~30–60 % to ~95 %.

#### 6.2 `update_manager.py` — happy-path test

Append to `tests/test_coordinator.py`:

```python
async def test_async_update_data_happy_path(hass, mock_sleepme_client):
    """Happy path: returns the three-key dict."""
    # ... assert last_update_success is True
    # ... assert set(coord.data.keys()) == {"status", "control", "about"}


async def test_async_update_data_value_error_maps_to_update_failed(hass, mock_failing_client):
    """ValueError from the client -> SETUP_RETRY."""
    mock_failing_client.side_effect = ValueError("unexpected response: 'foo'")
    # ... assert entry.state is ConfigEntryState.SETUP_RETRY
```

**Coverage delta:** `update_manager.py` from ~75–85 % to ~95 %.

#### 6.3 `climate.py` — uncovered branches

Append to `tests/test_climate.py`:

- `test_optimistic_window_expires` — fast-forward past 30s; coordinator value wins.
- `test_current_temperature_passthrough` — reads from `coordinator.data["status"]`.
- `test_available_false_when_coordinator_unsuccessful` — flips when `last_update_success=False`.
- `test_available_false_when_disconnected` — flips when `is_connected=False`.

**Coverage delta:** `climate.py` from ~70–85 % to ~90+ %.

#### 6.4 Optional: Hypothesis property test for `_compute_backoff`

Add `hypothesis==6.119.4` to `requirements_test.txt`.

Tests:
- `test_compute_backoff_handles_arbitrary_retry_after` — no input string crashes; falls back to base.
- `test_compute_backoff_no_retry_after_is_monotonic` — backoff non-decreasing up to ceiling.

**Decision:** include if comfortable with one new dependency; skip otherwise (defer to Phase 5 if a bug surfaces).

### 7. CI workflow refinements

Already covered in deliverables 3 and 4. Three small tightenings:

1. **pip cache keyed on `requirements_test.txt`** (via `cache-dependency-path`).
2. **`--upgrade-strategy eager`** for transitive pin freshness.
3. **`ruff format --check`** enforced in CI (not just pre-commit).

## Acceptance / exit criteria

- [ ] Preflight `pytest --cov` output attached to PR description.
- [ ] Coverage gate threshold chosen per the decision rule; documented in PR description.
- [ ] `pyproject.toml` has `[tool.coverage.report] fail_under = <threshold>`.
- [ ] `test.yml` `pytest` invocation passes `--cov-fail-under=<threshold>`.
- [ ] Matrix has 4 HA versions: `2025.10`, `2026.1`, `2026.3`, `2026.5`. All green.
- [ ] Each matrix entry's `phcc-version` verified at PyPI.
- [ ] `pip install --upgrade-strategy eager` used.
- [ ] `cache-dependency-path: requirements_test.txt` added.
- [ ] `pyproject.toml` no longer has `[tool.black]`.
- [ ] `.pre-commit-config.yaml` no longer has the `black` hook; ruff hooks no longer have `files: ^tests/`.
- [ ] `test.yml` runs `ruff format --check`, not `black --check`.
- [ ] `pyproject.toml` `[tool.mypy]` has the 4 strict flags.
- [ ] `test.yml` `typecheck` step has no `|| true`.
- [ ] `mypy custom_components/sleepme_thermostat` exits 0 locally.
- [ ] `tests/test_sleepme.py` exists with ≥ 6 tests.
- [ ] `tests/test_coordinator.py` has happy-path test.
- [ ] `tests/test_climate.py` has the 4 new tests.
- [ ] Hypothesis tests included **or** explicitly deferred in PR description.
- [ ] `docs/ROADMAP.md` Phase 4 row flipped ⬜ → ✅.
- [ ] All CI workflows green.

## Risks and open questions

1. **Preflight coverage may surprise.** If < 75 %, deliverable 6 must land first.
2. **Older HA versions may have incompatible test fixtures.** If a test fails only on `2025.10`, fix forward with a shim or drop that row.
3. **Python 3.13/3.14 split.** HA 2026.4 was the cutover. Pin phcc patches that support 3.13 on older rows.
4. **`ruff format` vs. `black` divergence.** If diff exceeds 50 LOC on `climate.py`, stop and investigate before committing.
5. **mypy error count uncertain.** Preflight is mandatory before locking strict flags.
6. **Coverage gate × matrix interaction.** Each job's gate is independent; that's intentional.

## Out of scope (explicit)

| Item | Phase |
|---|---|
| `diagnostics.py` platform | 5 |
| Drop `api_url` and `name` from `entry.data` | 5 |
| Sync ES translation against EN | 5 |
| `quality_scale: silver` in manifest | 5 |
| README polish | 5 |
| Refactor `device_info` to `TypedDict` | 5 |
| HA `dev` / beta channel in matrix | never |
| Python 3.12 in matrix | 5 only if needed |
| Coverage threshold > 80 % | 5 |
