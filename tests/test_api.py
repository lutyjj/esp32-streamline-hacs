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

from .device_payloads import DEVICE_URL, device_settings, device_status
from .digest_device import DigestDevice

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
    payload = device_status()
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=payload)

    status = await client(hass).async_get_status()

    assert status.device_name == payload["device_name"]
    assert status.metrics.playing is True


async def test_audio_update_sends_generated_form(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})

    await client(hass, ADMIN_KEY).async_set_audio(2, 25, 3)

    method, _url, body, _headers = aioclient_mock.mock_calls[0]
    assert method == "POST"
    assert body == {"input_line": "2", "input_gain": "25", "adc_attenuation_db": "3"}


async def test_passthrough_boolean_is_lowercase_form_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/analog-passthrough", json={"ok": True})

    await client(hass, ADMIN_KEY).async_set_analog_passthrough(True)

    assert aioclient_mock.mock_calls[0][2] == {"enabled": "true"}


async def test_update_operations_use_generated_forms(
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


async def test_authenticated_call_without_key_fails_before_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    with pytest.raises(StreamLineAuthenticationError):
        await client(hass).async_unlock()

    assert not aioclient_mock.mock_calls


async def test_authenticated_request_answers_the_device_digest_challenge(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """Prove the admin key against a device that really challenges for it."""
    async with DigestDevice(ADMIN_KEY) as device:
        device.route("POST", "/api/unlock", payload={"ok": True}, authenticated=True)
        await StreamLineDeviceClient(
            async_get_clientsession(hass), device.url, ADMIN_KEY
        ).async_unlock()

    assert device.authenticated_paths == ["/api/unlock"]


async def test_repeated_writes_keep_the_nonce_count_rising(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """A device that rejects a reused nonce count must still accept every write."""
    async with DigestDevice(ADMIN_KEY) as device:
        device.route("POST", "/api/unlock", payload={"ok": True}, authenticated=True)
        streamline = StreamLineDeviceClient(async_get_clientsession(hass), device.url, ADMIN_KEY)

        await streamline.async_unlock()
        await streamline.async_unlock()

    assert device.authenticated_paths == ["/api/unlock", "/api/unlock"]


async def test_expired_nonce_is_renewed_without_reauthentication(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """The device expires nonces hourly; a renewal must not surface as a failure."""
    async with DigestDevice(ADMIN_KEY) as device:
        device.route("POST", "/api/unlock", payload={"ok": True}, authenticated=True)
        streamline = StreamLineDeviceClient(async_get_clientsession(hass), device.url, ADMIN_KEY)
        await streamline.async_unlock()

        device.expire_nonce()
        await streamline.async_unlock()

    assert device.authenticated_paths == ["/api/unlock", "/api/unlock"]


async def test_wrong_admin_key_maps_to_authentication_error(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    async with DigestDevice(ADMIN_KEY) as device:
        device.route("POST", "/api/unlock", payload={"ok": True}, authenticated=True)
        streamline = StreamLineDeviceClient(async_get_clientsession(hass), device.url, "wrong-key")

        with pytest.raises(StreamLineAuthenticationError, match="invalid admin key"):
            await streamline.async_unlock()

    assert not device.authenticated_paths


async def test_reads_need_no_admin_key(hass: HomeAssistant, socket_enabled: None) -> None:
    async with DigestDevice(ADMIN_KEY) as device:
        device.route("GET", "/api/status", payload=device_status(), authenticated=False)
        status = await StreamLineDeviceClient(
            async_get_clientsession(hass), device.url
        ).async_get_status()

    assert status.metrics.playing is True


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

    assert status.metrics.packets == payload["metrics"]["packets"]


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
