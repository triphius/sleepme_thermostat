# SleepMe Dock Pro + Tracker Integration

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom_Repository-41BDF5.svg)](https://github.com/hacs/default)
[![Quality Scale](https://img.shields.io/badge/Quality_Scale-silver-c0c0c0.svg)](https://www.home-assistant.io/docs/quality_scale/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Test](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/test.yml/badge.svg)](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/test.yml)
[![Validate HACS](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/validate.yml/badge.svg)](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/validate.yml)
[![CodeQL](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/codeql.yml/badge.svg)](https://github.com/rsampayo/sleepme_thermostat/actions/workflows/codeql.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> A Home Assistant custom integration for **SleepMe Dock Pro and Tracker** devices. Dock Pro climate control, Tracker occupancy sensing, connectivity entities, and diagnostic/environmental sensors — all backed by the [sleep.me developer API](https://docs.developer.sleep.me/api/).

## Features

- Set bed temperature (13–48°C, half-degree steps, plus `Max Cool` / `Max Heat` presets per API contract).
- Turn the device on/off via HVAC mode.
- Sleep Tracker occupancy via `status.user_detected` for “in bed / out of bed” automations.
- Water-level-low binary sensor for proactive alerts.
- Connectivity binary sensor for both Dock Pro and Tracker devices.
- Dock Pro sensors: IP, LAN, brightness, display unit, time zone, firmware, water level.
- Tracker sensors: IP, LAN, firmware, environment humidity, environment temperature, bed temperature, last connected/disconnected, uptime.
- Configurable polling interval (10–300 s).
- Reauth flow when the API token rotates — no integration removal needed.
- Multi-device support: configure multiple Dock Pros and Trackers under one HA install.
- Long-term statistics for brightness.

## Requirements

- Home Assistant Core **2026.1** or newer (tested on 2026.1, 2026.3, 2026.5).
- A sleep.me account with at least one Dock Pro or Tracker device.
- A developer API token (generated in the sleep.me account portal, free).

## Installation

### HACS (recommended)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/rsampayo/sleepme_thermostat`, category *Integration*.
2. Install **SleepMe Thermostat**.
3. Restart Home Assistant.
4. *Settings → Devices & Services → Add Integration → SleepMe Thermostat*.

### Manual

1. Download the repository.
2. Copy `custom_components/sleepme_thermostat/` into `<config>/custom_components/`.
3. Restart Home Assistant.
4. Add the integration via the UI.

## Configuration

1. Generate an API token: sleep.me website → account → *Developer API* → *Create new token*.
2. *Settings → Devices & Services → Add Integration → SleepMe Thermostat*.
3. Paste the token; pick the device from the discovered list.

To tune the polling cadence: *Settings → Devices & Services → SleepMe Thermostat → Configure → Poll interval*.

## Entities created

| Platform       | Entity                       | Notes                              |
|----------------|------------------------------|------------------------------------|
| climate        | Dock Pro *{name}*            | Dock Pro only; target temp, on/off, Max Cool/Heat |
| binary_sensor  | Water Level                  | Dock Pro only; device class: PROBLEM |
| binary_sensor  | Connected                    | Dock Pro + Tracker; device class: CONNECTIVITY |
| binary_sensor  | Occupied                     | Tracker only; device class: OCCUPANCY |
| sensor         | IP Address                   | Diagnostic |
| sensor         | LAN Address                  | Diagnostic |
| sensor         | Firmware Version             | Diagnostic |
| sensor         | Brightness Level (%)         | Dock Pro only; diagnostic, in long-term statistics |
| sensor         | Display Temperature Unit     | Dock Pro only; diagnostic |
| sensor         | Time Zone                    | Dock Pro only; diagnostic |
| sensor         | Water Level                  | Dock Pro only; diagnostic |
| sensor         | Environment Humidity         | Tracker only |
| sensor         | Environment Temperature      | Tracker only |
| sensor         | Bed Temperature              | Tracker only |
| sensor         | Last Connected               | Tracker only; diagnostic |
| sensor         | Last Disconnected            | Tracker only; diagnostic |
| sensor         | Uptime                       | Tracker only; diagnostic |

## Example automation: cool the bed at bedtime

```yaml
automation:
  - alias: SleepMe — cool bed at bedtime
    trigger:
      - platform: time
        at: "22:30:00"
    action:
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.dock_pro_ramon
        data:
          hvac_mode: auto
      - service: climate.set_temperature
        target:
          entity_id: climate.dock_pro_ramon
        data:
          temperature: 18
```

## Troubleshooting

**"API token rejected" / reauth banner keeps appearing.**
Tokens can be rotated or revoked in the sleep.me developer portal. When that happens, the integration triggers a reauth prompt on *Settings → Devices & Services*. Click *Reauthenticate*, paste a fresh token, done. No HA restart needed.

**"Cannot connect to SleepMe API."**
The sleep.me API is aggressively rate-limited. Transient failures are normal — the integration honors `Retry-After` and recovers on the next poll. If the entity stays unavailable for more than a few minutes, check the log under `custom_components.sleepme_thermostat`.

**Polling too aggressive / not aggressive enough.**
The default poll interval is **20 seconds**. To change it: *Settings → Devices & Services → SleepMe Thermostat → Configure*. Acceptable range 10–300 s. Lower values feel snappier but consume more of your per-minute API budget.

**Sharing a bug report.**
Open the device page in *Settings → Devices & Services*, click ⋮, choose *Download diagnostics*. The downloaded JSON has your API token (and MAC, IP, serial) redacted. Attach it to a GitHub issue.

**Adjusting log verbosity.**
The integration registers one logger: `custom_components.sleepme_thermostat`. Use *Settings → System → Logs* or the `logger.set_level` service to bump it to debug temporarily.

## Tested against

| HA Core   | Python | Status |
|-----------|--------|--------|
| 2026.1.x  | 3.13   | tested |
| 2026.3.x  | 3.14   | tested |
| 2026.5.x  | 3.14   | tested |

Older HA versions may work but are not in the CI matrix.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

When editing translations, edit `custom_components/sleepme_thermostat/strings.json` first (the source of truth), then copy verbatim to `custom_components/sleepme_thermostat/translations/en.json`. CI fails if the two files diverge. Other language files (e.g. `es.json`) are hand-maintained from `strings.json`.

## License

[MIT](LICENSE).
