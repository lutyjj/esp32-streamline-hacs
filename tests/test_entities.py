"""Entity behavior tests across polling and authenticated controls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.streamline.const import CONF_ADMIN_KEY, CONF_DEVICE_URL, DOMAIN

from .device_payloads import DEVICE_URL, device_status, error_response

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

ADMIN_KEY = "admin-key-1234"
PLAYING_SENSOR = "binary_sensor.living_room_streamline_playing"
PEAK_SENSOR = "sensor.living_room_streamline_peak_level"
WIFI_SENSOR = "sensor.living_room_streamline_wi_fi_signal"
HEALTH_SENSOR = "sensor.living_room_streamline_health"
INPUT_SELECT = "select.living_room_streamline_input"
GAIN_NUMBER = "number.living_room_streamline_input_gain"
ATTENUATION_NUMBER = "number.living_room_streamline_adc_attenuation"
PASSTHROUGH_SWITCH = "switch.living_room_streamline_analog_passthrough"


def stub_device(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: dict[str, Any] | None = None,
    unlock_status: int = 200,
) -> None:
    """Stub coordinator reads and initial authentication."""
    aioclient_mock.get(f"{DEVICE_URL}/api/status", json=status or device_status())
    aioclient_mock.post(
        f"{DEVICE_URL}/api/unlock",
        status=unlock_status,
        json={"ok": True} if unlock_status == 200 else error_response("invalid admin key"),
    )


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


async def test_entities_report_device_state_and_limits(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    await setup_integration(hass)

    assert state_of(hass, PLAYING_SENSOR) == STATE_ON
    assert state_of(hass, PEAK_SENSOR) == "50.0"
    assert state_of(hass, WIFI_SENSOR) == "-54"
    assert state_of(hass, HEALTH_SENSOR) == "ok"
    assert state_of(hass, INPUT_SELECT) == "Line 2"
    assert state_of(hass, GAIN_NUMBER) == "25"
    assert state_of(hass, ATTENUATION_NUMBER) == "3"
    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_OFF

    gain = hass.states.get(GAIN_NUMBER)
    attenuation = hass.states.get(ATTENUATION_NUMBER)
    assert gain is not None
    assert attenuation is not None
    assert gain.attributes["max"] == 100
    assert attenuation.attributes["max"] == 12


async def test_read_only_entry_keeps_monitoring_and_disables_controls(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    await setup_integration(hass, admin_key=None)

    assert state_of(hass, PLAYING_SENSOR) == STATE_ON
    assert state_of(hass, INPUT_SELECT) == STATE_UNAVAILABLE
    assert state_of(hass, GAIN_NUMBER) == STATE_UNAVAILABLE
    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_UNAVAILABLE
    assert all(call[1].path == "/api/status" for call in aioclient_mock.mock_calls)


async def test_audio_control_preserves_other_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})
    await setup_integration(hass)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": GAIN_NUMBER, "value": 40},
        blocking=True,
    )

    update = next(
        call for call in aioclient_mock.mock_calls if call[1].path == "/api/settings/audio"
    )
    assert update[2] == {
        "adc_attenuation_db": "3",
        "input_gain": "40",
        "input_line": "2",
    }


async def test_input_and_passthrough_controls_use_device_api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/analog-passthrough", json={"ok": True})
    await setup_integration(hass)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": INPUT_SELECT, "option": "Line 1"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PASSTHROUGH_SWITCH}, blocking=True
    )

    audio = next(
        call for call in aioclient_mock.mock_calls if call[1].path == "/api/settings/audio"
    )
    passthrough = next(
        call
        for call in aioclient_mock.mock_calls
        if call[1].path == "/api/settings/analog-passthrough"
    )
    assert audio[2]["input_line"] == "1"
    assert passthrough[2] == {"enabled": "true"}


async def test_passthrough_switch_follows_board_capability(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock, status=device_status(passthrough_capable=False))

    await setup_integration(hass)

    assert hass.states.get(PASSTHROUGH_SWITCH) is None


async def test_rejected_saved_key_starts_reauth_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock, unlock_status=401)

    entry = await setup_integration(hass)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    reauth_flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
    assert len(reauth_flows) == 1
