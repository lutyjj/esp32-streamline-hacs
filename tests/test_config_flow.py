"""Configuration, reconfigure, and reauthentication flow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from aiohttp import ClientConnectionError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.streamline.const import CONF_API_TOKEN, CONF_BRIDGE_URL, DOMAIN

from .bridge_payloads import BRIDGE_URL, bridge_status, error_response

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

TOKEN = "api-token-1234"


def stub_bridge(aioclient_mock: AiohttpClientMocker) -> None:
    """Stub the config-flow bridge calls."""
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=bridge_status())
    aioclient_mock.post(f"{BRIDGE_URL}/api/unlock", json={"ok": True})


async def submit_user_flow(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, Any]:
    """Start and submit a user config flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        return dict(await hass.config_entries.flow.async_configure(result["flow_id"], user_input))


async def test_user_flow_verifies_token_and_normalizes_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock)

    result = await submit_user_flow(
        hass, {CONF_BRIDGE_URL: f"{BRIDGE_URL}/", CONF_API_TOKEN: TOKEN}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "bridge.local"
    assert result["data"] == {CONF_BRIDGE_URL: BRIDGE_URL, CONF_API_TOKEN: TOKEN}
    assert [call[1].path for call in aioclient_mock.mock_calls] == ["/status", "/api/unlock"]


async def test_user_flow_without_token_only_checks_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock)

    result = await submit_user_flow(hass, {CONF_BRIDGE_URL: BRIDGE_URL, CONF_API_TOKEN: ""})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_BRIDGE_URL: BRIDGE_URL}
    assert len(aioclient_mock.mock_calls) == 1


async def test_user_flow_rejects_non_root_url_without_network_call(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    result = await submit_user_flow(hass, {CONF_BRIDGE_URL: "bridge.local:8088"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_BRIDGE_URL: "invalid_url"}
    assert not aioclient_mock.mock_calls


async def test_user_flow_reports_connection_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BRIDGE_URL}/status", exc=ClientConnectionError("refused"))

    result = await submit_user_flow(hass, {CONF_BRIDGE_URL: BRIDGE_URL})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_reports_rejected_token_on_token_field(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=bridge_status())
    aioclient_mock.post(
        f"{BRIDGE_URL}/api/unlock",
        status=401,
        json=error_response("unauthorized", "Enter the API token configured on this bridge."),
    )

    result = await submit_user_flow(hass, {CONF_BRIDGE_URL: BRIDGE_URL, CONF_API_TOKEN: "bad"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_API_TOKEN: "invalid_auth"}


async def test_user_flow_aborts_for_configured_bridge(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    MockConfigEntry(domain=DOMAIN, data={CONF_BRIDGE_URL: BRIDGE_URL}).add_to_hass(hass)
    stub_bridge(aioclient_mock)

    result = await submit_user_flow(hass, {CONF_BRIDGE_URL: BRIDGE_URL})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_rejected_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BRIDGE_URL: BRIDGE_URL, CONF_API_TOKEN: "stale"}
    )
    entry.add_to_hass(hass)
    stub_bridge(aioclient_mock)

    result = await entry.start_reauth_flow(hass)
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: TOKEN}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == TOKEN


async def test_reconfigure_replaces_bridge_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BRIDGE_URL: "http://old.local:8088"})
    entry.add_to_hass(hass)
    stub_bridge(aioclient_mock)

    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.streamline.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BRIDGE_URL: BRIDGE_URL}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_BRIDGE_URL: BRIDGE_URL}
