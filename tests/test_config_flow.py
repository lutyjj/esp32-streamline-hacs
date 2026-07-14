"""Configuration, reconfigure, and reauthentication flow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from aiohttp import ClientConnectionError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.streamline.const import CONF_ADMIN_KEY, CONF_DEVICE_URL, DOMAIN

from .device_payloads import DEVICE_URL, device_status, error_response

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

ADMIN_KEY = "admin-key-1234"


def stub_device(aioclient_mock: AiohttpClientMocker) -> None:
    """Stub the config-flow device calls."""
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=device_status())
    aioclient_mock.post(f"{DEVICE_URL}/api/unlock", json={"ok": True})


async def submit_user_flow(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, Any]:
    """Start and submit a user config flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        return dict(await hass.config_entries.flow.async_configure(result["flow_id"], user_input))


async def test_user_flow_verifies_key_and_uses_device_name(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    result = await submit_user_flow(
        hass, {CONF_DEVICE_URL: f"{DEVICE_URL}/", CONF_ADMIN_KEY: ADMIN_KEY}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room StreamLine"
    assert result["data"] == {CONF_DEVICE_URL: DEVICE_URL, CONF_ADMIN_KEY: ADMIN_KEY}
    assert [call[1].path for call in aioclient_mock.mock_calls] == [
        "/api/status",
        "/api/unlock",
    ]


async def test_user_flow_without_key_only_checks_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    result = await submit_user_flow(hass, {CONF_DEVICE_URL: DEVICE_URL, CONF_ADMIN_KEY: ""})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_DEVICE_URL: DEVICE_URL}
    assert len(aioclient_mock.mock_calls) == 1


async def test_user_flow_rejects_non_root_url_without_network_call(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    result = await submit_user_flow(hass, {CONF_DEVICE_URL: "device.local"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DEVICE_URL: "invalid_url"}
    assert not aioclient_mock.mock_calls


async def test_user_flow_reports_connection_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{DEVICE_URL}/api/status", exc=ClientConnectionError("refused"))

    result = await submit_user_flow(hass, {CONF_DEVICE_URL: DEVICE_URL})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_reports_rejected_key_on_key_field(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=device_status())
    aioclient_mock.post(
        f"{DEVICE_URL}/api/unlock",
        status=401,
        json=error_response("invalid admin key"),
    )

    result = await submit_user_flow(hass, {CONF_DEVICE_URL: DEVICE_URL, CONF_ADMIN_KEY: "bad-key"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ADMIN_KEY: "invalid_auth"}


async def test_user_flow_aborts_for_configured_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE_URL: DEVICE_URL}).add_to_hass(hass)
    stub_device(aioclient_mock)

    result = await submit_user_flow(hass, {CONF_DEVICE_URL: DEVICE_URL})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_rejected_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_URL: DEVICE_URL, CONF_ADMIN_KEY: "stale-key"},
    )
    entry.add_to_hass(hass)
    stub_device(aioclient_mock)

    result = await entry.start_reauth_flow(hass)
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADMIN_KEY: ADMIN_KEY}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ADMIN_KEY] == ADMIN_KEY


async def test_reconfigure_replaces_device_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE_URL: "http://old.local"})
    entry.add_to_hass(hass)
    stub_device(aioclient_mock)

    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_URL: DEVICE_URL}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_DEVICE_URL: DEVICE_URL}
