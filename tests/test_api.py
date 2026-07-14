"""Contract tests for the device API client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientConnectionError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.streamline.api import StreamLineDeviceClient, normalize_device_url
from custom_components.streamline.errors import (
    StreamLineApiError,
    StreamLineAuthenticationError,
    StreamLineCannotConnect,
)

from .device_payloads import DEVICE_URL, device_settings, device_status, error_response

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

ADMIN_KEY = "admin-key-1234"


def client(hass: HomeAssistant, key: str | None = None) -> StreamLineDeviceClient:
    """Create a client using Home Assistant's shared session."""
    return StreamLineDeviceClient(async_get_clientsession(hass), DEVICE_URL, key)


async def test_status_parses_into_generated_model(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=device_status())

    status = await client(hass).async_get_status()

    assert status.device_name == "Living Room StreamLine"
    assert status.metrics.playing is True


async def test_audio_update_sends_bearer_key_and_form(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})

    await client(hass, ADMIN_KEY).async_set_audio(2, 25, 3)

    method, _url, body, headers = aioclient_mock.mock_calls[0]
    assert method == "POST"
    assert body == {"input_line": "2", "input_gain": "25", "adc_attenuation_db": "3"}
    assert headers["Authorization"] == f"Bearer {ADMIN_KEY}"


async def test_passthrough_boolean_is_lowercase_form_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/analog-passthrough", json={"ok": True})

    await client(hass, ADMIN_KEY).async_set_analog_passthrough(True)

    assert aioclient_mock.mock_calls[0][2] == {"enabled": "true"}


async def test_update_operations_use_generated_forms_and_bearer_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{DEVICE_URL}/api/settings", json=device_settings())
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/firmware", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/check", status=202, json={"started": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/update", status=202, json={"started": True})

    device = client(hass, ADMIN_KEY)
    settings = await device.async_get_settings()
    await device.async_set_update_schedule("weekly")
    await device.async_check_firmware_update()
    await device.async_install_firmware_update()

    assert settings.auto_update_schedule.root == "daily"
    assert aioclient_mock.mock_calls[1][2] == {"auto_update_schedule": "weekly"}
    assert all(
        call[3]["Authorization"] == f"Bearer {ADMIN_KEY}" for call in aioclient_mock.mock_calls[1:]
    )


async def test_authenticated_call_without_key_fails_before_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    with pytest.raises(StreamLineAuthenticationError):
        await client(hass).async_unlock()

    assert not aioclient_mock.mock_calls


async def test_unauthorized_response_maps_to_authentication_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{DEVICE_URL}/api/unlock",
        status=401,
        json=error_response("invalid admin key"),
    )

    with pytest.raises(StreamLineAuthenticationError, match="invalid admin key"):
        await client(hass, ADMIN_KEY).async_unlock()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"unexpected": True}, "invalid StatusResponse"),
        ("<html>proxy error</html>", "invalid JSON"),
    ],
)
async def test_invalid_device_response_is_api_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict[str, bool] | str,
    expected: str,
) -> None:
    if isinstance(response, str):
        aioclient_mock.get(f"{DEVICE_URL}/api/status", text=response)
    else:
        aioclient_mock.get(f"{DEVICE_URL}/api/status", json=response)

    with pytest.raises(StreamLineApiError, match=expected):
        await client(hass).async_get_status()


async def test_connection_failure_maps_to_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{DEVICE_URL}/api/status", exc=ClientConnectionError("refused"))

    with pytest.raises(StreamLineCannotConnect):
        await client(hass).async_get_status()


async def test_additive_device_fields_are_forward_compatible(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    payload = device_status()
    payload["future_field"] = "ignored"
    payload["metrics"]["future_metric"] = 1
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=payload)

    status = await client(hass).async_get_status()

    assert status.metrics.packets == 42


def test_normalize_device_url_canonicalizes_root() -> None:
    assert normalize_device_url(" http://device.local/ ") == "http://device.local"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "device.local",
        "ftp://device.local",
        "http://user:secret@device.local",
        "http://device.local/api",
        "http://device.local?token=x",
        "http://device.local#status",
    ],
)
def test_normalize_device_url_rejects_non_root_urls(value: str) -> None:
    with pytest.raises(StreamLineApiError):
        normalize_device_url(value)
