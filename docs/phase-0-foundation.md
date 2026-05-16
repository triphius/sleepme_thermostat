# Phase 0 — Foundation Plan

**Status:** Drafted 2026-05-16, awaiting maintainer answers to open questions before execution.
**Companion docs:** [`AUDIT.md`](./AUDIT.md), [`ROADMAP.md`](./ROADMAP.md).

## Goal

Stand up the lint/format/type/test/CI scaffolding the rest of the roadmap depends on, **without changing any integration behavior**. After this phase, every subsequent PR runs `ruff`, `black --check`, `mypy`, and `pytest` in CI; the maintainer has a one-command path to sync the working tree onto the live HA OS host for end-to-end validation against the real Dock Pro.

Boundary: this phase touches repo-root scaffolding, `tests/`, CI, and docs only. The single allowed change inside `custom_components/sleepme_thermostat/` is **none by default** — initial ruff/black/mypy runs are configured to be *advisory* (CI green even if they find issues in existing code) so we can adopt tooling first and clean up in Phase 1+. Two strict-from-day-one exceptions: hassfest and the new smoke test must pass.

## Deliverables

### 1. `pyproject.toml`

**Location:** `pyproject.toml` at repo root.

**Pinning strategy.** Match a recent stable Home Assistant Core release. As of 2026-05-16 the safe HA Core target is **2026.4.x** (Python 3.13). `pytest-homeassistant-custom-component` ships versions aligned 1:1 with HA Core — pick the latest patch in the matching minor (e.g. `0.13.x` for HA 2026.4 — version-resolved in CI by `pip install homeassistant==2026.4.* pytest-homeassistant-custom-component`).

**Judgment calls (pick / alternative):**
- Ruff version `>=0.5,<1.0` / alt: hard-pin to `0.5.7`. Pick the range — pre-commit autoupdate handles drift.
- Black version `>=24.10` / alt: omit and let ruff format. Keep black; HA core uses black, matches downstream contributors' muscle memory.
- mypy strictness: `--ignore-missing-imports` + `disable_error_code = ["import-untyped"]` for now / alt: full `--strict`. Pick the lax mode — the existing code will produce hundreds of mypy errors otherwise, defeating the "no behavior change" rule.
- Python target: `3.13` / alt: `3.12`. Pick 3.13 to match HA Core 2026.x; `pytest-homeassistant-custom-component` requires it.

**File content (paste-ready):**

```toml
[project]
name = "sleepme_thermostat"
version = "0.0.0"
description = "Home Assistant custom integration for SleepMe Dock Pro"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.13"

[tool.ruff]
target-version = "py313"
line-length = 88
src = ["custom_components", "tests"]
extend-exclude = [
    ".github",
    "docs",
]

[tool.ruff.lint]
# Phase 0 baseline = HA Core's commonly used set, minus rules that would
# require touching integration code today. Phase 1+ tightens this.
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes
    "W",    # pycodestyle warnings
    "I",    # isort
    "B",    # flake8-bugbear
    "UP",   # pyupgrade
    "RUF",  # ruff-specific
]
ignore = [
    "E501",  # line length — handled by black/formatter
    "B008",  # function calls in arg defaults — common HA pattern
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]  # assert is fine in tests

[tool.ruff.format]
# Use ruff's formatter for tests only; black still owns custom_components/.
# This keeps a single source of truth for tests while letting black-on-HA-code
# stay aligned with HA Core's own formatter.

[tool.black]
target-version = ["py313"]
line-length = 88
include = '(custom_components/sleepme_thermostat|tests)/.*\.py$'

[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true
follow_imports = "silent"
warn_unused_ignores = true
warn_redundant_casts = true
# Phase 0 is intentionally lenient. Phase 4 ("Testing") tightens this:
# - enable disallow_untyped_defs
# - enable strict optional
disable_error_code = ["import-untyped"]
exclude = [
    "tests/",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "-p", "no:cacheprovider",
]
norecursedirs = [".git", ".github", "custom_components"]

[tool.coverage.run]
source = ["custom_components/sleepme_thermostat"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

**Rationale recap:**

| Choice | Why |
|---|---|
| `requires-python = ">=3.13"` | HA Core 2026.4 requires 3.13. |
| ruff rule set | Matches the HA Core `pyproject.toml` baseline minus opinionated rules that would require code edits inside `custom_components/`. |
| `line-length = 88` | Black's default and HA Core's. |
| `black` kept | HA Core formats with `ruff format`; we keep black to avoid auto-reformatting the entire `custom_components/` tree in this phase. Phase 1 can migrate to `ruff format` once the code is cleaned up. |
| mypy lenient | Keep CI green during Phase 0; tighten in Phase 4. |
| `asyncio_mode = "auto"` | Required by `pytest-homeassistant-custom-component`. |
| `branch = true` | Coverage will gate at ≥ 75 % starting Phase 4. |

### 2. `tests/` skeleton

**Directory layout:**

```
tests/
├── __init__.py                  # empty
├── conftest.py                  # pulls in pytest-homeassistant-custom-component fixtures
├── const.py                     # shared test constants (fake token, device id, etc.)
├── fixtures/
│   └── device_status.json       # canned API response for a healthy Dock Pro
└── test_init.py                 # the Phase 0 smoke test
```

**`requirements_test.txt`** (sibling to `pyproject.toml`, used by CI):

```
# Pin to HA Core 2026.4.x. Bump when we bump HA target.
homeassistant==2026.4.4
pytest-homeassistant-custom-component==0.13.250
pytest==8.3.4
pytest-asyncio==0.24.0
pytest-cov==6.0.0
```

Exact patch versions are stand-ins — CI resolves the matched pair via `pip install -r requirements_test.txt`. If `pytest-homeassistant-custom-component` 0.13.250 doesn't exist for the HA pin chosen, pick the matching version from <https://pypi.org/project/pytest-homeassistant-custom-component/#history>.

**`tests/conftest.py`:**

```python
"""Global fixtures for sleepme_thermostat tests."""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the sleepme_thermostat custom integration in tests."""
    yield


@pytest.fixture
def mock_sleepme_client() -> Generator[AsyncMock, None, None]:
    """Mock SleepMeClient so no real network calls happen."""
    with patch(
        "custom_components.sleepme_thermostat.SleepMeClient",
        autospec=True,
    ) as mock_cls:
        instance = mock_cls.return_value
        instance.get_device_status = AsyncMock(
            return_value={
                "status": {
                    "water_temperature_c": 22.0,
                    "is_water_low": False,
                    "is_connected": True,
                },
                "control": {
                    "set_temperature_c": 22.0,
                    "thermal_control_status": "standby",
                },
                "about": {
                    "firmware_version": "0.0.0-test",
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "model": "Dock Pro",
                    "serial_number": "TEST-SERIAL",
                },
            }
        )
        instance.get_claimed_devices = AsyncMock(return_value=[])
        yield instance
```

**`tests/const.py`:**

```python
"""Test constants."""
MOCK_API_TOKEN = "test-token-not-real"  # noqa: S105 - test fixture
MOCK_DEVICE_ID = "test-device-id"
MOCK_NAME = "Test Bedroom"
```

**`tests/test_init.py` (smoke test):**

```python
"""Smoke test: integration sets up and unloads cleanly with a mocked API client."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sleepme_thermostat.const import API_URL, DOMAIN
from tests.const import MOCK_API_TOKEN, MOCK_DEVICE_ID, MOCK_NAME


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id=MOCK_DEVICE_ID,
        title=f"Dock Pro {MOCK_NAME}",
        data={
            "api_url": API_URL,
            "api_token": MOCK_API_TOKEN,
            "device_id": MOCK_DEVICE_ID,
            "name": MOCK_NAME,
            "firmware_version": "0.0.0-test",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "model": "Dock Pro",
            "serial_number": "TEST-SERIAL",
        },
    )


@pytest.mark.asyncio
async def test_setup_entry_loads(
    hass: HomeAssistant, mock_sleepme_client: AsyncMock
) -> None:
    """async_setup_entry returns True and entry reaches LOADED."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.asyncio
async def test_unload_entry(
    hass: HomeAssistant, mock_sleepme_client: AsyncMock
) -> None:
    """Entry can be unloaded.

    NOTE: as of Phase 0 the integration has no async_unload_entry (audit #7).
    This test is marked xfail so CI is green; Phase 1 lands the implementation
    and flips the xfail to a pass, giving us a built-in regression check.
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pytest.xfail("async_unload_entry not implemented yet — Phase 1 deliverable")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
```

**Why this shape:**
- One real assertion (load), one `xfail` placeholder (unload). Establishes both fixture mechanics today and the regression trap for Phase 1.
- `MockConfigEntry` is the canonical `pytest-homeassistant-custom-component` fixture.
- `mock_sleepme_client` patches at the import site (`custom_components.sleepme_thermostat.SleepMeClient`), so both `async_setup_entry` and `SleepMeUpdateManager`'s internal `SleepMeClient` instantiation get the mock — verify on the first CI run; if the latter binds via `from .sleepme import SleepMeClient` and dodges the patch, add a second `patch("custom_components.sleepme_thermostat.update_manager.SleepMeClient", ...)`.

### 3. `LICENSE`

**Location:** `LICENSE` at repo root.
**Choice:** MIT, matching README's claim. Copyright holder: Ramon Sampayo (the repo owner). Year: 2024 – present.

```
MIT License

Copyright (c) 2024-2026 Ramon Sampayo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 4. pre-commit config

**Location:** `.pre-commit-config.yaml` at repo root.

**Pick:** ruff + black + standard whitespace hooks. Skip mypy in pre-commit (too slow / too many false positives in Phase 0); mypy runs in CI only.

```yaml
# Run with: pre-commit run --all-files
# Install hooks: pre-commit install
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-yaml
      - id: check-toml
      - id: check-json
        exclude: ^\.vscode/
      - id: end-of-file-fixer
        exclude: ^custom_components/sleepme_thermostat/translations/
      - id: trailing-whitespace
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ["--maxkb=500"]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        # Phase 0: only lint tests/ — leave custom_components/ as-is until Phase 1.
        files: ^tests/
      - id: ruff-format
        files: ^tests/

  - repo: https://github.com/psf/black
    rev: 24.10.0
    hooks:
      - id: black
        files: ^tests/

  - repo: https://github.com/codespell-project/codespell
    rev: v2.3.0
    hooks:
      - id: codespell
        args: ["--ignore-words-list=hass,nd"]
        exclude: ^(custom_components/sleepme_thermostat/translations/|tests/fixtures/)
```

**Note on `files: ^tests/` scoping.** This is the deliberate "no behavior change" guard for Phase 0. The maintainer can run `ruff check custom_components/` or `black --check custom_components/` locally to *survey* what would change. Phase 1's plan will open with "remove the `files: ^tests/` scoping after applying the formatter once."

### 5. CI changes

**Decision:** add a new `test.yml` workflow. Do not merge into `validate.yml`.

Reasoning:
- `validate.yml` runs hassfest + HACS validation — both fast (~30s). Mixing pytest (1–3 min cold) into the same job slows feedback.
- Separate workflows → separate GitHub status checks, which Phase 4 will gate as required.
- `validate` is the job name HACS users grep for in badges; don't rename it.

**`validate.yml` change** (only one line — the hassfest pin from §6):

```diff
   validate:
     name: hassfest
     runs-on: "ubuntu-latest"
     steps:
         - uses: "actions/checkout@v4"
-        - uses: "home-assistant/actions/hassfest@master"
+        - uses: "home-assistant/actions/hassfest@<pinned-sha-or-tag>"  # see §6
```

**New `.github/workflows/test.yml`:**

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  lint:
    name: Lint & format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install ruff==0.8.4 black==24.10.0
      - name: ruff check (tests only in Phase 0)
        run: ruff check tests
      - name: black --check (tests only in Phase 0)
        run: black --check tests

  typecheck:
    name: mypy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install mypy==1.13.0
      - run: pip install -r requirements_test.txt
      - name: mypy (advisory in Phase 0)
        # `|| true` keeps the job green while we adopt mypy. Drop the suffix in Phase 4.
        run: mypy custom_components/sleepme_thermostat || true

  pytest:
    name: pytest (HA ${{ matrix.ha-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        ha-version: ["2026.4"]   # add more in Phase 4
        python-version: ["3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -r requirements_test.txt
      - run: pytest --cov --cov-report=term-missing
```

### 6. hassfest pin

**Pick:** pin to a **commit SHA**, not a tag. `home-assistant/actions` does not cut SemVer tags for the hassfest action; the canonical upstream guidance is to pin to a SHA, with a comment naming the date.

**Maintainer's steps:**

1. `git ls-remote https://github.com/home-assistant/actions` — copy the current `refs/heads/master` SHA.
2. Verify against <https://github.com/home-assistant/actions/commits/master/> and pick the most recent commit that's been on master ≥ 7 days.
3. Substitute into `validate.yml`:
   ```yaml
   - uses: "home-assistant/actions/hassfest@<40-char-sha>"  # master @ YYYY-MM-DD
   ```

Also pin `hacs/action@main` → `hacs/action@<sha>` in the same PR (same rationale).

Optional `dependabot.yml` (can land Phase 1 if you'd rather defer):

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

## Deploy workflow to HA OS host

Goal: a 5-second loop from "save file locally" → "watch the integration reload on the device."

**Approach (in use):** SSH + `rsync`, via the HA OS **"Advanced SSH & Web Terminal"** community add-on (Frenck). Maintainer kept the default port (22), uses `hassio` user with key auth.

**HA host (maintainer's setup):**
- Host: `100.88.154.98` (Tailscale; works from anywhere)
- Port: `22`
- User: `hassio`
- Key: `~/.ssh/id_ed25519_ha`
- HA `/config` is mounted at `/homeassistant` inside the addon container.

**Deploy command (from this repo's root):**

```bash
make deploy-restart HA_HOST=100.88.154.98
```

Or directly:

```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/id_ed25519_ha -p 22" \
  --exclude '__pycache__' --exclude '*.pyc' \
  custom_components/sleepme_thermostat/ \
  hassio@100.88.154.98:/homeassistant/custom_components/sleepme_thermostat/

ssh -i ~/.ssh/id_ed25519_ha -p 22 hassio@100.88.154.98 'bash -lc "ha core restart"'
```

**Reload on the HA side:**

| Option | How | When |
|---|---|---|
| HA UI: Settings → Devices & Services → SleepMe → "..." → Reload | Click | Code-only changes that don't touch `manifest.json` / `config_flow` structure |
| Full restart | From SSH&WebTerminal: `ha core restart` | After `manifest.json` changes, new platforms, `VERSION` bump, dependency changes |

**Today the integration has no `async_unload_entry`** (audit #7). The UI "Reload" doesn't actually reload it cleanly — it'll leave stale objects in `hass.data`. **Until Phase 1 lands, use `ha core restart` after every deploy.**

The repo ships a `Makefile` with these defaults baked in — see the file at repo root.

Usage: `make deploy-restart HA_HOST=100.88.154.98`.

## Acceptance / exit criteria

Every box must be checked before Phase 0 is declared done. None require touching `custom_components/sleepme_thermostat/`.

- [ ] `LICENSE` exists at repo root and matches README's MIT claim.
- [ ] `pyproject.toml` exists at repo root.
- [ ] `requirements_test.txt` exists at repo root.
- [ ] `.pre-commit-config.yaml` exists at repo root.
- [ ] `tests/` directory exists with `__init__.py`, `conftest.py`, `const.py`, `test_init.py`, `fixtures/`.
- [ ] `pre-commit run --all-files` passes locally on a clean checkout.
- [ ] `pytest` from repo root passes locally against the HA pin (one passing, one `xfail`).
- [ ] `.github/workflows/test.yml` exists with three jobs: `lint`, `typecheck`, `pytest`.
- [ ] All three jobs green on the Phase 0 PR.
- [ ] `validate.yml`'s hassfest step references a commit SHA, not `@master`.
- [ ] `hacs/action` in `validate.yml` references a commit SHA, not `@main`.
- [ ] Existing `validate` (HACS / hassfest) and `CodeQL` workflows still pass.
- [ ] No file under `custom_components/sleepme_thermostat/` is modified by this PR (verify: `git diff --stat origin/main..HEAD -- custom_components/`).
- [ ] Maintainer ran `make deploy-restart` (or equivalent) against the live Dock Pro host and confirmed the integration still loads with no log regressions.
- [ ] `docs/ROADMAP.md` Phase 0 table flipped ⬜ → ✅.

## Risks and open questions

1. **Deploy mechanism — which SSH path do you actually use today?**
   Options: (a) "SSH & Web Terminal" community add-on, (b) official "SSH server" core add-on (port 22, more locked down), (c) Samba/SMB mount of `\\<host>\config`, (d) "Studio Code Server" add-on. The plan assumes (a). If (c), the Makefile becomes `cp -a ... /Volumes/config/...` and the restart step needs a different transport.

2. **HA Core version target.** Plan pins `2026.4.x`. If your live Dock Pro instance runs older HA Core, drop the pin to match.

3. **Mock-patch site for `SleepMeClient`.** Smoke test patches at `custom_components.sleepme_thermostat.SleepMeClient` (where `__init__.py` imports it). `update_manager.py` imports it independently. If the second instantiation slips past the mock on first CI run, add a second `patch()` line.

4. **`enable_custom_integrations` fixture.** Expects integration at `custom_components/<domain>/` with valid manifest. We have both. If hassfest passes against the pinned SHA, this fixture will too.

5. **Codespell on translations.** Spanish translations would hit false positives — excluded via `exclude: ^custom_components/sleepme_thermostat/translations/`.

6. **`hassfest` SHA churn.** SHA pinning means no free upstream fixes. The Dependabot snippet handles it; you need to opt in.

7. **No code edits today vs. "do it once."** Alternative: run `ruff --fix` + `black` over `custom_components/` once, accept a large mechanical diff, get lint-clean code from day one. Audit forbids that ("must not change integration behavior"). You may prefer to land a *separate* format-only commit before Phase 1.

## Out of scope (explicit)

- Any fix to any P0/P1 audit finding. All belong to Phase 1+.
- Changes to `custom_components/sleepme_thermostat/**` source files — except optionally the token-leak fix (audit #1) as a separate hot-fix commit.
- Coverage gates. Phase 0 reports; Phase 4 enforces ≥ 75%.
- Multi-version HA test matrix. Phase 0 ships one; Phase 4 expands.
- `diagnostics.py`, `strings.json` migration, options flow, reauth flow — Phase 2 / 5.
- Performance / rate-limit measurements against the live Dock Pro — Phase 1 acceptance.
- Replacing `black` with `ruff format` over `custom_components/` — after Phase 1.
- Renaming the existing `validate` workflow — stays as is, minus the action pin.
