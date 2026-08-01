"""Runtime capability and credential lifecycle behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError

from custom_components.streamline.coordinator import StreamLineData
from custom_components.streamline.models import StatusResponse

from .device_payloads import DEVICE_URL, device_status, error_response
from .integration_setup import setup_integration, state_of, stub_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

GAIN_NUMBER = "number.living_room_streamline_input_gain"
PASSTHROUGH_SWITCH = "switch.living_room_streamline_analog_passthrough"


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
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_OFF

    coordinator.async_set_updated_data(
        StreamLineData(
            status=StatusResponse.model_validate(device_status(passthrough_capable=False)),
            settings=coordinator.settings,
            coredump=coordinator.data.coredump,
        )
    )
    await hass.async_block_till_done()

    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_UNAVAILABLE


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
