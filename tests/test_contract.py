"""Compatibility policy for the StreamLine device API contract."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streamline.api import StreamLineDeviceClient
from custom_components.streamline.const import BUTTON_ACTIONS, UPDATE_SCHEDULES

from .device_payloads import device_coredump, device_settings, device_status
from .digest_device import DigestDevice

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ADMIN_KEY = "admin-key-1234"
OPENAPI: dict[str, Any] = json.loads(Path(os.environ["STREAMLINE_OPENAPI"]).read_text())
TRANSLATIONS: dict[str, Any] = json.loads(
    Path("custom_components/streamline/translations/en.json").read_text()
)

SUPPORTED_OPERATIONS = {
    "get_coredump",
    "get_settings",
    "get_status",
    "ota_check",
    "ota_update",
    "restart",
    "set_analog_passthrough",
    "set_audio",
    "set_button",
    "set_firmware",
    "set_stream",
    "unlock",
}

INTENTIONALLY_UNSUPPORTED_OPERATIONS = {
    "activate_transport_key": "transport encryption requires the coordinated bridge workflow",
    "discard_transport_key": "transport encryption requires the coordinated bridge workflow",
    "factory_reset": "destructive device recovery stays in the device console",
    "get_audio_profiles": "audio profile authoring stays in the device console",
    "get_boards": "board selection stays in the device console",
    "get_coredump_image": "a crash dump is an ELF image for espcoredump.py, not a device control",
    "get_health": "device status already embeds the health report",
    "get_logs": "the device log is console diagnostics, not a Home Assistant capability",
    "get_metrics": "device status already embeds the metrics used by Home Assistant",
    "get_openapi": "this development endpoint is not a Home Assistant capability",
    "ota_rollback": "firmware recovery stays in the device console",
    "post_coredump_erase": "crash dump triage stays in the device console",
    "recover_transport": "transport recovery requires the coordinated bridge workflow",
    "retire_transport_key": "transport encryption requires the coordinated bridge workflow",
    "rollback_transport_key": "transport encryption requires the coordinated bridge workflow",
    "set_admin_key": "credential management stays in the device console",
    "set_audio_profile": "audio profile authoring stays in the device console",
    "set_audio_profiles": "audio profile authoring stays in the device console",
    "set_board": "board selection stays in the device console",
    "set_led": "board LED role assignment stays in the device console",
    "set_name": "device identity stays in the device console",
    "set_target": "bridge destination setup stays in the device console",
    "set_transport_mode": "transport encryption requires the coordinated bridge workflow",
    "set_wifi": "network commissioning stays in the device console",
    "stage_transport_key": "transport encryption requires the coordinated bridge workflow",
    "verify_transport_key": "transport encryption requires the coordinated bridge workflow",
}


def _operations() -> dict[str, dict[str, Any]]:
    return {
        operation["operationId"]: operation
        for path in OPENAPI["paths"].values()
        for operation in path.values()
    }


def _requires_digest(operation: dict[str, Any]) -> bool:
    """Return whether the contract gates one operation behind the admin key."""
    return any("digest_auth" in rule for rule in operation.get("security") or [])


def _success_status(operation: dict[str, Any]) -> int:
    """Return the one non-error status the contract declares for an operation."""
    return min(int(status) for status in operation["responses"] if status.startswith("2"))


def test_every_device_operation_has_an_explicit_integration_disposition() -> None:
    assert not SUPPORTED_OPERATIONS & INTENTIONALLY_UNSUPPORTED_OPERATIONS.keys()
    assert set(_operations()) == SUPPORTED_OPERATIONS | INTENTIONALLY_UNSUPPORTED_OPERATIONS.keys()
    assert all(INTENTIONALLY_UNSUPPORTED_OPERATIONS.values())


def test_update_schedule_options_and_translations_match_openapi() -> None:
    contract_options = OPENAPI["components"]["schemas"]["AutoUpdateScheduleRequest"]["enum"]
    translations = TRANSLATIONS["entity"]["select"]["automatic_update_schedule"]["state"]

    assert set(UPDATE_SCHEDULES) == set(contract_options)
    assert set(translations) == set(contract_options)


def _declared_translation_keys() -> dict[str, set[str]]:
    """Collect every entity translation key each platform module declares."""
    declared: dict[str, set[str]] = {}
    for module in Path("custom_components/streamline").glob("*.py"):
        platform = module.stem
        if platform not in TRANSLATIONS["entity"]:
            continue
        declared[platform] = {
            value
            for node in ast.walk(ast.parse(module.read_text()))
            if (value := _assigned_translation_key(node)) is not None
        }
    return declared


def _assigned_translation_key(node: ast.AST) -> str | None:
    """Return the translation key one node names, as a keyword or an attribute."""
    match node:
        case ast.keyword(arg="translation_key", value=ast.Constant(value=str() as key)):
            return key
        case ast.Assign(
            targets=[ast.Name(id="_attr_translation_key")], value=ast.Constant(value=str() as key)
        ):
            return key
        case _:
            return None


def test_every_entity_translation_is_declared_and_every_declaration_translated() -> None:
    """Neither an unnamed entity nor a translation nothing consumes."""
    declared = _declared_translation_keys()

    assert declared.keys() == TRANSLATIONS["entity"].keys()
    for platform, keys in declared.items():
        assert keys == set(TRANSLATIONS["entity"][platform]), platform


def test_button_action_options_and_translations_match_openapi() -> None:
    contract_options = OPENAPI["components"]["schemas"]["ButtonAction"]["enum"]
    translations = TRANSLATIONS["entity"]["select"]["button_action"]["state"]

    assert set(BUTTON_ACTIONS) == set(contract_options)
    assert set(translations) == set(contract_options)


def _operation_payload(operation_id: str) -> dict[str, Any]:
    """Return a contract-shaped response body for one supported operation."""
    match operation_id:
        case "get_status":
            return device_status()
        case "get_settings":
            return device_settings()
        case "get_coredump":
            return device_coredump()
        case "ota_check" | "ota_update":
            return {"started": True}
        case _:
            return {"ok": True}


async def test_every_client_operation_matches_openapi_contract(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """Pin hand-written method, path, and authentication facts to OpenAPI.

    The device answers each operation the way the contract declares it, so a
    call can only succeed by using the method and path OpenAPI names and by
    proving the admin key wherever OpenAPI requires ``digest_auth``.
    """
    operations = _operations()
    async with DigestDevice(ADMIN_KEY) as served_device:
        for path, methods in OPENAPI["paths"].items():
            for method, operation in methods.items():
                if operation["operationId"] not in SUPPORTED_OPERATIONS:
                    continue
                served_device.route(
                    method,
                    path,
                    payload=_operation_payload(operation["operationId"]),
                    authenticated=_requires_digest(operation),
                    status=_success_status(operation),
                )

        device = StreamLineDeviceClient(async_get_clientsession(hass), served_device.url, ADMIN_KEY)
        await device.async_get_status()
        await device.async_get_settings()
        await device.async_get_coredump()
        await device.async_unlock()
        await device.async_set_audio(2, 25, 3)
        await device.async_set_analog_passthrough(True)
        await device.async_set_stream(False)
        await device.async_set_button("key1", "cycle_input")
        await device.async_set_update_schedule("weekly")
        await device.async_check_firmware_update()
        await device.async_install_firmware_update()
        await device.async_restart()

        observed = {
            OPENAPI["paths"][path][method.lower()]["operationId"]
            for method, path in served_device.served_requests
        }
        digest_paths = sorted(
            path
            for path, methods in OPENAPI["paths"].items()
            for operation in methods.values()
            if operation["operationId"] in SUPPORTED_OPERATIONS and _requires_digest(operation)
        )
        assert sorted(set(served_device.authenticated_paths)) == digest_paths

    exercised_methods = {
        "async_check_firmware_update",
        "async_get_coredump",
        "async_get_settings",
        "async_get_status",
        "async_install_firmware_update",
        "async_restart",
        "async_set_analog_passthrough",
        "async_set_audio",
        "async_set_button",
        "async_set_stream",
        "async_set_update_schedule",
        "async_unlock",
    }

    public_methods = {name for name in dir(StreamLineDeviceClient) if name.startswith("async_")}
    assert public_methods == exercised_methods
    assert observed == SUPPORTED_OPERATIONS
    assert observed <= operations.keys()
