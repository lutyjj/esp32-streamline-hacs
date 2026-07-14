"""Contract tests for the bridge API client."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from aiohttp import ClientConnectionError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streamline.api import StreamLineBridgeClient, normalize_bridge_url
from custom_components.streamline.errors import (
    StreamLineApiError,
    StreamLineAuthenticationError,
    StreamLineCannotConnect,
)

from .bridge_payloads import (
    BRIDGE_URL,
    SOURCE,
    bridge_status,
    error_response,
    recording_capabilities,
    recording_list,
    recording_result,
    recording_snapshot,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

TOKEN = "api-token-1234"
OPENAPI: dict[str, Any] = json.loads(Path(os.environ["STREAMLINE_OPENAPI"]).read_text())


def client(hass: HomeAssistant, token: str | None = None) -> StreamLineBridgeClient:
    """Create a client using Home Assistant's shared session."""
    return StreamLineBridgeClient(async_get_clientsession(hass), BRIDGE_URL, token)


async def test_status_parses_into_the_generated_model(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=bridge_status())

    status = await client(hass).async_get_status()

    assert status.sources[SOURCE].lifecycle.state == "connected"


async def test_additive_bridge_fields_are_forward_compatible(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    payload = bridge_status()
    payload["future_field"] = "ignored"
    payload["sources"][SOURCE]["future_metric"] = 1
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=payload)

    status = await client(hass).async_get_status()

    assert status.sources[SOURCE].clients == 1


async def test_start_recording_sends_token_and_generated_request_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BRIDGE_URL}/api/recordings", json=recording_result(recording_snapshot()))

    recording = await client(hass, TOKEN).async_start_recording(SOURCE, "Test recording")

    assert recording.id == "rec-1"
    method, _url, body, headers = aioclient_mock.mock_calls[0]
    assert method == "POST"
    assert body == {"source": SOURCE, "title": "Test recording"}
    assert headers["Authorization"] == f"Bearer {TOKEN}"


async def test_authenticated_call_without_token_fails_before_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    with pytest.raises(StreamLineAuthenticationError):
        await client(hass).async_get_recordings()

    assert not aioclient_mock.mock_calls


async def test_unauthorized_response_maps_to_authentication_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BRIDGE_URL}/api/unlock",
        status=401,
        json=error_response("unauthorized", "Enter the API token configured on this bridge."),
    )

    with pytest.raises(StreamLineAuthenticationError, match="Enter the API token"):
        await client(hass, TOKEN).async_unlock()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"unexpected": True}, "invalid BridgeStatus"),
        ("<html>proxy error</html>", "invalid JSON"),
    ],
)
async def test_invalid_bridge_response_is_an_api_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict[str, bool] | str,
    expected: str,
) -> None:
    if isinstance(response, str):
        aioclient_mock.get(f"{BRIDGE_URL}/status", text=response)
    else:
        aioclient_mock.get(f"{BRIDGE_URL}/status", json=response)

    with pytest.raises(StreamLineApiError, match=expected):
        await client(hass).async_get_status()


async def test_connection_failure_maps_to_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BRIDGE_URL}/status", exc=ClientConnectionError("refused"))

    with pytest.raises(StreamLineCannotConnect):
        await client(hass).async_get_status()


async def test_every_client_operation_matches_the_openapi_contract(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pin hand-written method, path, and authentication facts to OpenAPI."""
    recording_id = "rec-1"
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=bridge_status())
    aioclient_mock.post(f"{BRIDGE_URL}/api/unlock", json={"ok": True})
    aioclient_mock.get(f"{BRIDGE_URL}/api/recordings/capabilities", json=recording_capabilities())
    aioclient_mock.get(f"{BRIDGE_URL}/api/recordings", json=recording_list())
    aioclient_mock.post(f"{BRIDGE_URL}/api/recordings", json=recording_result(recording_snapshot()))
    aioclient_mock.post(
        f"{BRIDGE_URL}/api/recordings/{recording_id}/stop",
        json=recording_result(recording_snapshot()),
    )

    bridge = client(hass, TOKEN)
    await bridge.async_get_status()
    await bridge.async_unlock()
    await bridge.async_get_recording_capabilities()
    await bridge.async_get_recordings()
    await bridge.async_start_recording(SOURCE, "Test recording")
    await bridge.async_stop_recording(recording_id)
    exercised = {
        "async_get_status",
        "async_unlock",
        "async_get_recording_capabilities",
        "async_get_recordings",
        "async_start_recording",
        "async_stop_recording",
    }

    public = {name for name in dir(StreamLineBridgeClient) if name.startswith("async_")}
    assert public == exercised
    for method, url, _body, headers in aioclient_mock.mock_calls:
        path = url.path.replace(recording_id, "{recording_id}")
        operation = OPENAPI["paths"][path][method.lower()]
        requires_bearer = any("bearer_auth" in rule for rule in operation.get("security") or [])
        assert ("Authorization" in (headers or {})) == requires_bearer, (method, path)


def test_normalize_bridge_url_canonicalizes_the_root() -> None:
    assert normalize_bridge_url(" http://bridge.local:8088/ ") == "http://bridge.local:8088"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "bridge.local:8088",
        "ftp://bridge.local",
        "http://user:secret@bridge.local:8088",
        "http://bridge.local:8088/api",
        "http://bridge.local:8088?token=x",
        "http://bridge.local:8088#status",
    ],
)
def test_normalize_bridge_url_rejects_non_root_urls(value: str) -> None:
    with pytest.raises(StreamLineApiError):
        normalize_bridge_url(value)
