"""Device payloads derived from the contract's canonical example device.

The pinned artifact's ``StatusResponse`` and ``ConfigResponse`` schema
examples are the base state; the keyword arguments express the scenarios
tests drive. Every payload is validated against its generated model, so a
payload can only break when the contract itself changed.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from custom_components.streamline.models import (
    ConfigResponse,
    CoredumpResponse,
    ErrorResponse,
    StatusResponse,
)

DEVICE_URL = "http://device.local"

_SCHEMAS = json.loads(Path(os.environ["STREAMLINE_OPENAPI"]).read_text())["components"]["schemas"]
_STATUS_EXAMPLE: dict[str, Any] = _SCHEMAS["StatusResponse"]["example"]
_CONFIG_EXAMPLE: dict[str, Any] = _SCHEMAS["ConfigResponse"]["example"]


def device_status(
    *,
    name: str = "Living Room StreamLine",
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
    payload = copy.deepcopy(_STATUS_EXAMPLE)
    payload["device_name"] = name
    payload["auth_required"] = admin_required
    payload["configuration_writable"] = writable
    if not passthrough_capable:
        payload["capabilities"]["analog_passthrough"] = None
    payload["analog_passthrough"] = {
        "active": passthrough_enabled,
        "enabled": passthrough_enabled,
        "fault": None,
    }
    payload["metrics"]["playing"] = playing
    payload["metrics"]["peak_abs_left"] = peak
    payload["metrics"]["peak_abs_right"] = peak // 2
    payload["ota"]["busy"] = ota_busy
    payload["ota"]["phase"] = ota_phase
    payload["ota"]["latest_version"] = latest_version
    payload["diagnostics"]["last_ota"] = last_ota
    payload["target"]["transport"] = transport
    StatusResponse.model_validate(payload)
    return payload


def device_settings(
    *, name: str = "Living Room StreamLine", schedule: str = "daily"
) -> dict[str, Any]:
    """Return one complete persisted settings payload."""
    payload = copy.deepcopy(_CONFIG_EXAMPLE)
    payload["device_name"] = name
    payload["auto_update_schedule"] = schedule
    ConfigResponse.model_validate(payload)
    return payload


def device_coredump(*, present: bool = False, size_bytes: int = 0) -> dict[str, Any]:
    """Return one crash dump status payload.

    The contract carries no example for this schema, so the payload is built
    from its fields and validated against the generated model.
    """
    payload = {"present": present, "size_bytes": size_bytes}
    CoredumpResponse.model_validate(payload)
    return payload


def error_response(message: str) -> dict[str, str]:
    """Return one device error payload."""
    payload = {"error": message}
    ErrorResponse.model_validate(payload)
    return payload
