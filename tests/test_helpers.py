"""Tests for the shared helpers module."""

from __future__ import annotations

from custom_components.sleepme_thermostat.const import DOMAIN
from custom_components.sleepme_thermostat.helpers import (
    build_device_info,
    round_half_up,
)


def test_round_half_up_rounds_to_half_degree():
    assert round_half_up(20.0) == 20.0
    assert round_half_up(20.2) == 20.0
    assert round_half_up(20.3) == 20.5
    assert round_half_up(20.7) == 20.5
    assert round_half_up(20.8) == 21.0
    assert round_half_up(-1.0) == -1.0


def test_build_device_info_shape():
    info = {
        "model": "Dock Pro",
        "firmware_version": "1.2.3",
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "serial_number": "SN-1",
    }
    # Phase 5: build_device_info now accepts the full display name verbatim
    # (callers pass entry.title), so "Dock Pro - Ramon" goes in unchanged.
    out = build_device_info("dev-1", "Dock Pro - Ramon", info)
    assert out["identifiers"] == {(DOMAIN, "dev-1")}
    assert out["name"] == "Dock Pro - Ramon"
    assert out["manufacturer"] == "SleepMe"
    assert out["model"] == "Dock Pro"
    assert out["sw_version"] == "1.2.3"
    assert out["serial_number"] == "SN-1"
    # connections uses the CONNECTION_NETWORK_MAC constant
    conn_set = out["connections"]
    assert len(conn_set) == 1
    conn_type, conn_value = next(iter(conn_set))
    assert conn_type == "mac"
    assert conn_value == "aa:bb:cc:dd:ee:ff"


def test_build_device_info_handles_missing_keys():
    """Missing keys flow through as None — HA tolerates this."""
    out = build_device_info("dev-2", "Dock Pro - Chiva", {})
    assert out["model"] is None
    assert out["sw_version"] is None
    assert out["serial_number"] is None
