"""Runtime capability and credential lifecycle behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from custom_components.streamline.coordinator import StreamLineData
from custom_components.streamline.models import AudioProfileCatalog, StatusResponse

from .device_payloads import (
    DEVICE_URL,
    device_audio_profiles,
    device_settings,
    device_status,
    error_response,
)
from .integration_setup import setup_integration, state_of, stub_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

AUDIO_PROFILE_SELECT = "select.living_room_streamline_audio_profile"
GAIN_NUMBER = "number.living_room_streamline_input_gain"
PASSTHROUGH_SWITCH = "switch.living_room_streamline_analog_passthrough"
STATUS_LED_ROLE_SELECT = "select.living_room_streamline_status_light_d4_role"


async def test_passthrough_entity_tracks_board_capability_changes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock, status=device_status(passthrough_capable=False))
    entry = await setup_integration(hass)
    coordinator = entry.runtime_data

    assert hass.states.get(PASSTHROUGH_SWITCH) is None

    coordinator.async_set_updated_data(
        StreamLineData(
            status=StatusResponse.model_validate(device_status(passthrough_capable=True)),
            settings=coordinator.settings,
            audio_profiles=coordinator.audio_profiles,
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_OFF

    coordinator.async_set_updated_data(
        StreamLineData(
            status=StatusResponse.model_validate(device_status(passthrough_capable=False)),
            settings=coordinator.settings,
            audio_profiles=coordinator.audio_profiles,
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_UNAVAILABLE


async def test_audio_profile_entity_tracks_saved_profile_catalog(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock, audio_profiles=device_audio_profiles(profiles=[]))
    entry = await setup_integration(hass)
    coordinator = entry.runtime_data

    assert hass.states.get(AUDIO_PROFILE_SELECT) is None

    coordinator.async_set_updated_data(
        StreamLineData(
            status=coordinator.status,
            settings=coordinator.settings,
            audio_profiles=AudioProfileCatalog.model_validate(device_audio_profiles()),
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, AUDIO_PROFILE_SELECT) == "Vinyl"

    coordinator.async_set_updated_data(
        StreamLineData(
            status=coordinator.status,
            settings=coordinator.settings,
            audio_profiles=AudioProfileCatalog.model_validate(device_audio_profiles(profiles=[])),
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, AUDIO_PROFILE_SELECT) == STATE_UNAVAILABLE


async def test_audio_profile_clears_when_device_poll_reports_changed_audio_levels(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)
    entry = await setup_integration(hass)
    coordinator = entry.runtime_data

    assert state_of(hass, AUDIO_PROFILE_SELECT) == "Vinyl"

    changed_status = device_status()
    changed_status["audio"]["input_gain"] = 35
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=changed_status)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert state_of(hass, AUDIO_PROFILE_SELECT) == STATE_UNKNOWN


async def test_board_capability_change_refreshes_led_roles_and_audio_profiles(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    initial_status = device_status()
    initial_status["capabilities"]["leds"] = []
    initial_settings = device_settings()
    initial_settings["led_roles"] = []
    stub_device(
        aioclient_mock,
        status=initial_status,
        settings=initial_settings,
        audio_profiles=device_audio_profiles(),
    )
    entry = await setup_integration(hass)
    coordinator = entry.runtime_data

    assert hass.states.get(STATUS_LED_ROLE_SELECT) is None
    assert state_of(hass, AUDIO_PROFILE_SELECT) == "Vinyl"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=device_status())
    aioclient_mock.get(f"{DEVICE_URL}/api/settings", json=device_settings())
    aioclient_mock.get(
        f"{DEVICE_URL}/api/audio-profiles",
        json=device_audio_profiles(profiles=[]),
    )
    aioclient_mock.get(f"{DEVICE_URL}/api/coredump", json={"present": False, "size_bytes": 0})
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/led", json={"ok": True})

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert state_of(hass, STATUS_LED_ROLE_SELECT) == "status"
    assert state_of(hass, AUDIO_PROFILE_SELECT) == STATE_UNAVAILABLE

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": STATUS_LED_ROLE_SELECT, "option": "off"},
        blocking=True,
    )

    assert state_of(hass, STATUS_LED_ROLE_SELECT) == "off"


async def test_rejected_control_write_starts_reauthentication(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)
    aioclient_mock.post(
        f"{DEVICE_URL}/api/settings/audio",
        status=401,
        json=error_response("invalid admin key"),
    )
    await setup_integration(hass)

    with pytest.raises(HomeAssistantError, match="invalid admin key"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": GAIN_NUMBER, "value": 40},
            blocking=True,
        )

    reauth_flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
    assert len(reauth_flows) == 1
