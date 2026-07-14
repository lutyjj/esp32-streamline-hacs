"""Current device payloads, each checked against its generated model."""

from __future__ import annotations

from typing import Any

from custom_components.streamline.models import ConfigResponse, ErrorResponse, StatusResponse

DEVICE_URL = "http://device.local"


def device_status(
    *,
    playing: bool = True,
    peak: int = 16384,
    admin_required: bool = True,
    writable: bool = True,
    passthrough_capable: bool = True,
    passthrough_enabled: bool = False,
    latest_version: str = "",
    ota_busy: bool = False,
    ota_phase: str = "idle",
    transport: str = "cleartext",
    last_ota: str = "",
) -> dict[str, Any]:
    """Return one complete device status payload."""
    payload: dict[str, Any] = {
        "analog_passthrough": {
            "active": passthrough_enabled,
            "enabled": passthrough_enabled,
            "fault": None,
        },
        "audio": {
            "adc_attenuation_db": 3,
            "bits_per_sample": 16,
            "channels": 2,
            "input_gain": 25,
            "input_line": 2,
            "sample_rate": 48000,
        },
        "auth_required": admin_required,
        "capabilities": {
            "adc_atten_max_db": 12,
            "analog_passthrough": (
                {"label": "Line output", "output_line": 1} if passthrough_capable else None
            ),
            "board": "AudioKit v2.2",
            "board_id": "esp32-audiokit-v2-2",
            "codec": {"driver": "es8388", "i2c_address": 16},
            "input_gain_max": 100,
            "input_lines": [
                {"label": "Line 1", "line": 1},
                {"label": "Line 2", "line": 2},
            ],
            "pins": {
                "i2c": {"scl": 32, "sda": 33},
                "i2s": {"bclk": 27, "din": 35, "mclk": 0, "ws": 25},
            },
            "status_led": {"active_low": True, "gpio": 22},
        },
        "config_source": "nvs",
        "configuration_writable": writable,
        "device_name": "Living Room StreamLine",
        "diagnostics": {
            "last_fallback": "",
            "last_ota": last_ota,
            "reset_reason": "software",
        },
        "firmware_version": "0.6.1",
        "health": {"checks": [], "status": "ok"},
        "indicator": {"available": True, "state": "idle"},
        "metrics": {
            "bytes": 4096,
            "clip_threshold_abs": 32000,
            "clipped_samples_total": 2,
            "network_errors_total": 1,
            "noise_floor": 21,
            "packets": 42,
            "peak_abs_left": peak,
            "peak_abs_right": peak // 2,
            "playing": playing,
            "queue_depth": 0,
            "queue_drops_total": 0,
            "read_errors": 0,
            "reconnects_total": 1,
            "rms_left": 100,
            "rms_right": 80,
            "sequence": 42,
            "short_reads": 0,
            "tls_handshake_failures_total": 0,
        },
        "mode": "provisioned",
        "ota": {
            "busy": ota_busy,
            "bytes_total": 0,
            "bytes_written": 0,
            "latest_version": latest_version,
            "message": "",
            "phase": ota_phase,
            "rollback_available": False,
            "rollback_version": "",
        },
        "target": {
            "target_host": "bridge.local",
            "target_port": 39000,
            "transport": transport,
        },
        "web_server": True,
        "wifi": {
            "ap_ip": "",
            "hostname": "streamline.local",
            "rssi": -54,
            "ssid": "example-network",
            "sta_ip": "192.0.2.10",
            "status": "connected",
        },
    }
    StatusResponse.model_validate(payload)
    return payload


def device_settings(*, schedule: str = "daily") -> dict[str, Any]:
    """Return one complete persisted settings payload."""
    payload: dict[str, Any] = {
        "adc_attenuation_db": 3,
        "analog_passthrough_enabled": False,
        "auto_update_schedule": schedule,
        "config_source": "nvs",
        "device_name": "Living Room StreamLine",
        "input_gain": 25,
        "input_line": 2,
        "ssid": "example-network",
        "target_host": "bridge.local",
        "target_port": 39000,
        "transport": {
            "active_key_id": None,
            "contract_version": 1,
            "mode": "cleartext",
            "pending_key_id": None,
            "pending_verified": False,
            "rollback_key_id": None,
        },
    }
    ConfigResponse.model_validate(payload)
    return payload


def error_response(message: str) -> dict[str, str]:
    """Return one device error payload."""
    payload = {"error": message}
    ErrorResponse.model_validate(payload)
    return payload
