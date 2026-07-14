"""Entity behavior tests across coordinator polls and source changes."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.streamline.const import CONF_API_TOKEN, CONF_BRIDGE_URL, DOMAIN

from .bridge_payloads import (
    BRIDGE_URL,
    SOURCE,
    bridge_status,
    error_response,
    recording_capabilities,
    recording_list,
    recording_result,
    recording_snapshot,
    source_snapshot,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

TOKEN = "api-token-1234"
STREAMING_SENSOR = "binary_sensor.streamline_source_192_0_2_10_audio_streaming"
PEAK_SENSOR = "sensor.streamline_source_192_0_2_10_peak_level"
LISTENERS_SENSOR = "sensor.streamline_source_192_0_2_10_listeners"
RECORDING_SWITCH = "switch.streamline_source_192_0_2_10_recording"


def stub_bridge(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
    recordings: dict[str, Any] | None = None,
) -> None:
    """Stub one coordinator poll."""
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=status or bridge_status())
    aioclient_mock.get(
        f"{BRIDGE_URL}/api/recordings/capabilities",
        json=capabilities or recording_capabilities(),
    )
    aioclient_mock.get(f"{BRIDGE_URL}/api/recordings", json=recordings or recording_list())


async def setup_integration(hass: HomeAssistant, *, token: str | None = TOKEN) -> MockConfigEntry:
    """Set up one mocked integration entry."""
    data = {CONF_BRIDGE_URL: BRIDGE_URL}
    if token is not None:
        data[CONF_API_TOKEN] = token
    entry = MockConfigEntry(domain=DOMAIN, title="bridge.local", data=data)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def poll_once(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Advance past one coordinator interval and settle the poll."""
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def state_of(hass: HomeAssistant, entity_id: str) -> str:
    """Return the state of an entity that must exist."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_source_entities_report_bridge_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock)

    await setup_integration(hass)

    assert state_of(hass, STREAMING_SENSOR) == STATE_ON
    assert state_of(hass, PEAK_SENSOR) == "50.0"
    assert state_of(hass, LISTENERS_SENSOR) == "1"
    assert state_of(hass, RECORDING_SWITCH) == STATE_OFF


async def test_tokenless_entry_is_read_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock)

    await setup_integration(hass, token=None)

    assert state_of(hass, STREAMING_SENSOR) == STATE_ON
    assert state_of(hass, RECORDING_SWITCH) == STATE_UNAVAILABLE
    assert all(call[1].path == "/status" for call in aioclient_mock.mock_calls)


async def test_switch_is_unavailable_without_recording_storage(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock, capabilities=recording_capabilities(enabled=False))

    await setup_integration(hass)

    assert state_of(hass, RECORDING_SWITCH) == STATE_UNAVAILABLE


async def test_switch_starts_and_stops_source_recording(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_bridge(aioclient_mock)
    aioclient_mock.post(f"{BRIDGE_URL}/api/recordings", json=recording_result(recording_snapshot()))
    await setup_integration(hass)

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": RECORDING_SWITCH}, blocking=True
    )
    start = next(
        call
        for call in aioclient_mock.mock_calls
        if call[0] == "POST" and call[1].path == "/api/recordings"
    )
    assert start[2]["source"] == SOURCE
    assert start[2]["title"].startswith("Recording ")

    aioclient_mock.clear_requests()
    stub_bridge(aioclient_mock, recordings=recording_list(active=[recording_snapshot()]))
    aioclient_mock.post(
        f"{BRIDGE_URL}/api/recordings/rec-1/stop",
        json=recording_result(recording_snapshot(state="complete", file_name="rec-1.wav")),
    )
    await hass.config_entries.async_reload(
        next(iter(hass.config_entries.async_entries(DOMAIN))).entry_id
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": RECORDING_SWITCH}, blocking=True
    )
    assert any(call[1].path == "/api/recordings/rec-1/stop" for call in aioclient_mock.mock_calls)


async def test_sources_are_added_and_removed_across_polls(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    stub_bridge(aioclient_mock)
    await setup_integration(hass)

    aioclient_mock.clear_requests()
    stub_bridge(
        aioclient_mock,
        status=bridge_status({SOURCE: source_snapshot(), "192.0.2.20": source_snapshot(clients=0)}),
    )
    await poll_once(hass, freezer)
    assert state_of(hass, "binary_sensor.streamline_source_192_0_2_20_audio_streaming") == STATE_ON

    aioclient_mock.clear_requests()
    stub_bridge(aioclient_mock, status=bridge_status({}))
    await poll_once(hass, freezer)
    assert state_of(hass, STREAMING_SENSOR) == STATE_UNAVAILABLE


async def test_rejected_token_starts_reauth_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BRIDGE_URL}/status", json=bridge_status())
    aioclient_mock.get(f"{BRIDGE_URL}/api/recordings/capabilities", json=recording_capabilities())
    aioclient_mock.get(
        f"{BRIDGE_URL}/api/recordings",
        status=401,
        json=error_response("unauthorized", "Enter the API token configured on this bridge."),
    )

    entry = await setup_integration(hass)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    reauth_flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
    assert len(reauth_flows) == 1
