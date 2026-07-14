"""Compatibility policy for the StreamLine device API contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streamline.api import StreamLineDeviceClient
from custom_components.streamline.const import UPDATE_SCHEDULES

from .device_payloads import DEVICE_URL, device_settings, device_status

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

ADMIN_KEY = "admin-key-1234"
OPENAPI: dict[str, Any] = json.loads(Path(os.environ["STREAMLINE_OPENAPI"]).read_text())
TRANSLATIONS: dict[str, Any] = json.loads(
    Path("custom_components/streamline/translations/en.json").read_text()
)

SUPPORTED_OPERATIONS = {
    "get_settings",
    "get_status",
    "ota_check",
    "ota_update",
    "set_analog_passthrough",
    "set_audio",
    "set_firmware",
    "unlock",
}

INTENTIONALLY_UNSUPPORTED_OPERATIONS = {
    "activate_transport_key": "transport encryption requires the coordinated bridge workflow",
    "discard_transport_key": "transport encryption requires the coordinated bridge workflow",
    "factory_reset": "destructive device recovery stays in the device console",
    "get_audio_profiles": "audio profile authoring stays in the device console",
    "get_boards": "board selection stays in the device console",
    "get_health": "device status already embeds the health report",
    "get_metrics": "device status already embeds the metrics used by Home Assistant",
    "get_openapi": "this development endpoint is not a Home Assistant capability",
    "ota_rollback": "firmware recovery stays in the device console",
    "recover_transport": "transport recovery requires the coordinated bridge workflow",
    "restart": "the integration exposes no restart control",
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


def test_every_device_operation_has_an_explicit_integration_disposition() -> None:
    assert not SUPPORTED_OPERATIONS & INTENTIONALLY_UNSUPPORTED_OPERATIONS.keys()
    assert set(_operations()) == SUPPORTED_OPERATIONS | INTENTIONALLY_UNSUPPORTED_OPERATIONS.keys()
    assert all(INTENTIONALLY_UNSUPPORTED_OPERATIONS.values())


def test_update_schedule_options_and_translations_match_openapi() -> None:
    contract_options = OPENAPI["components"]["schemas"]["AutoUpdateScheduleRequest"]["enum"]
    translations = TRANSLATIONS["entity"]["select"]["automatic_update_schedule"]["state"]

    assert set(UPDATE_SCHEDULES) == set(contract_options)
    assert set(translations) == set(contract_options)


async def test_every_client_operation_matches_openapi_contract(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pin hand-written method, path, and authentication facts to OpenAPI."""
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=device_status())
    aioclient_mock.get(f"{DEVICE_URL}/api/settings", json=device_settings())
    aioclient_mock.post(f"{DEVICE_URL}/api/unlock", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/analog-passthrough", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/firmware", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/check", status=202, json={"started": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/update", status=202, json={"started": True})

    device = StreamLineDeviceClient(async_get_clientsession(hass), DEVICE_URL, ADMIN_KEY)
    await device.async_get_status()
    await device.async_get_settings()
    await device.async_unlock()
    await device.async_set_audio(2, 25, 3)
    await device.async_set_analog_passthrough(True)
    await device.async_set_update_schedule("weekly")
    await device.async_check_firmware_update()
    await device.async_install_firmware_update()
    exercised_methods = {
        "async_check_firmware_update",
        "async_get_settings",
        "async_get_status",
        "async_install_firmware_update",
        "async_set_analog_passthrough",
        "async_set_audio",
        "async_set_update_schedule",
        "async_unlock",
    }

    public_methods = {name for name in dir(StreamLineDeviceClient) if name.startswith("async_")}
    assert public_methods == exercised_methods

    observed_operations = set()
    operations = _operations()
    for method, url, _body, headers in aioclient_mock.mock_calls:
        operation = OPENAPI["paths"][url.path][method.lower()]
        observed_operations.add(operation["operationId"])
        requires_bearer = any("bearer_auth" in rule for rule in operation.get("security") or [])
        assert ("Authorization" in (headers or {})) == requires_bearer, (method, url.path)

    assert observed_operations == SUPPORTED_OPERATIONS
    assert observed_operations <= operations.keys()
