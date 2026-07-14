"""Shared setup helpers for Home Assistant integration behavior tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.streamline.const import CONF_ADMIN_KEY, CONF_DEVICE_URL, DOMAIN

from .device_payloads import DEVICE_URL, device_settings, device_status, error_response

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

ADMIN_KEY = "admin-key-1234"


def stub_device(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: dict[str, Any] | None = None,
    unlock_status: int = 200,
    settings: dict[str, Any] | None = None,
) -> None:
    """Stub coordinator reads and initial authentication."""
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=status or device_status())
    aioclient_mock.get(f"{DEVICE_URL}/api/settings", json=settings or device_settings())
    aioclient_mock.post(
        f"{DEVICE_URL}/api/unlock",
        status=unlock_status,
        json={"ok": True} if unlock_status == 200 else error_response("invalid admin key"),
    )
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/check", status=202, json={"started": True})


async def setup_integration(
    hass: HomeAssistant, *, admin_key: str | None = ADMIN_KEY
) -> MockConfigEntry:
    """Set up one mocked device entry."""
    data = {CONF_DEVICE_URL: DEVICE_URL}
    if admin_key is not None:
        data[CONF_ADMIN_KEY] = admin_key
    entry = MockConfigEntry(domain=DOMAIN, title="Living Room StreamLine", data=data)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def state_of(hass: HomeAssistant, entity_id: str) -> str:
    """Return the state of an entity that must exist."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state
