"""Entity behavior tests across polling and authenticated controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE

from .device_payloads import DEVICE_URL, device_status
from .integration_setup import setup_integration, state_of, stub_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

PLAYING_SENSOR = "binary_sensor.living_room_streamline_playing"
PEAK_SENSOR = "sensor.living_room_streamline_peak_level"
WIFI_SENSOR = "sensor.living_room_streamline_wi_fi_signal"
HEALTH_SENSOR = "sensor.living_room_streamline_health"
ENCRYPTION_SENSOR = "sensor.living_room_streamline_pcm_encryption"
OTA_SENSOR = "sensor.living_room_streamline_ota_status"
INPUT_SELECT = "select.living_room_streamline_input"
UPDATE_SCHEDULE_SELECT = "select.living_room_streamline_automatic_update_schedule"
GAIN_NUMBER = "number.living_room_streamline_input_gain"
ATTENUATION_NUMBER = "number.living_room_streamline_adc_attenuation"
PASSTHROUGH_SWITCH = "switch.living_room_streamline_analog_passthrough"
FIRMWARE_UPDATE = "update.living_room_streamline_firmware"


async def test_entities_report_device_state_and_limits(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    await setup_integration(hass)

    assert state_of(hass, PLAYING_SENSOR) == STATE_ON
    assert state_of(hass, PEAK_SENSOR) == "50.0"
    assert state_of(hass, WIFI_SENSOR) == "-55"
    assert state_of(hass, HEALTH_SENSOR) == "ok"
    assert state_of(hass, ENCRYPTION_SENSOR) == "disabled"
    assert state_of(hass, OTA_SENSOR) == "idle"
    assert state_of(hass, INPUT_SELECT) == "Line 2 — 3.5 mm jack"
    assert state_of(hass, UPDATE_SCHEDULE_SELECT) == "daily"
    assert state_of(hass, GAIN_NUMBER) == "0"
    assert state_of(hass, ATTENUATION_NUMBER) == "9"
    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_OFF
    assert state_of(hass, FIRMWARE_UPDATE) == STATE_OFF

    gain = hass.states.get(GAIN_NUMBER)
    attenuation = hass.states.get(ATTENUATION_NUMBER)
    assert gain is not None
    assert attenuation is not None
    assert gain.attributes["max"] == 100
    assert attenuation.attributes["max"] == 48
    firmware = hass.states.get(FIRMWARE_UPDATE)
    assert firmware is not None
    installed = device_status()["firmware_version"]
    assert firmware.attributes["installed_version"] == installed
    assert firmware.attributes["latest_version"] == installed
    assert firmware.attributes["auto_update"] is True


async def test_read_only_entry_keeps_monitoring_and_disables_controls(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)

    await setup_integration(hass, admin_key=None)

    assert state_of(hass, PLAYING_SENSOR) == STATE_ON
    assert state_of(hass, INPUT_SELECT) == STATE_UNAVAILABLE
    assert state_of(hass, GAIN_NUMBER) == STATE_UNAVAILABLE
    assert state_of(hass, PASSTHROUGH_SWITCH) == STATE_UNAVAILABLE
    assert state_of(hass, UPDATE_SCHEDULE_SELECT) == STATE_UNAVAILABLE
    assert state_of(hass, FIRMWARE_UPDATE) == STATE_UNAVAILABLE
    assert {call[1].path for call in aioclient_mock.mock_calls} == {
        "/api/settings",
        "/api/status",
    }


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
        "adc_attenuation_db": "9",
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
        {"entity_id": INPUT_SELECT, "option": "Line 1 — header pins"},
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


async def test_duplicate_input_labels_remain_individually_selectable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    status = device_status()
    status["capabilities"]["input_lines"] = [
        {"label": "Line", "line": 1},
        {"label": "Line", "line": 2},
    ]
    stub_device(aioclient_mock, status=status)
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/audio", json={"ok": True})
    await setup_integration(hass)

    input_select = hass.states.get(INPUT_SELECT)
    assert input_select is not None
    assert input_select.state == "Line (2)"
    assert input_select.attributes["options"] == ["Line (1)", "Line (2)"]

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": INPUT_SELECT, "option": "Line (1)"},
        blocking=True,
    )

    update = next(
        call for call in aioclient_mock.mock_calls if call[1].path == "/api/settings/audio"
    )
    assert update[2]["input_line"] == "1"


async def test_passthrough_switch_follows_board_capability(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock, status=device_status(passthrough_capable=False))

    await setup_integration(hass)

    assert hass.states.get(PASSTHROUGH_SWITCH) is None


async def test_update_schedule_is_persisted_and_refreshed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    stub_device(aioclient_mock)
    aioclient_mock.post(f"{DEVICE_URL}/api/settings/firmware", json={"ok": True})
    await setup_integration(hass)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": UPDATE_SCHEDULE_SELECT, "option": "weekly"},
        blocking=True,
    )

    update = next(
        call for call in aioclient_mock.mock_calls if call[1].path == "/api/settings/firmware"
    )
    assert update[2] == {"auto_update_schedule": "weekly"}
    assert state_of(hass, UPDATE_SCHEDULE_SELECT) == "weekly"


async def test_firmware_update_entity_starts_guarded_ota_install(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    status = device_status(latest_version="0.6.2", ota_phase="update-available")
    stub_device(aioclient_mock, status=status)
    aioclient_mock.post(f"{DEVICE_URL}/api/ota/update", status=202, json={"started": True})
    await setup_integration(hass)

    assert state_of(hass, FIRMWARE_UPDATE) == STATE_ON
    await hass.services.async_call(
        "update", "install", {"entity_id": FIRMWARE_UPDATE}, blocking=True
    )

    assert any(call[1].path == "/api/ota/update" for call in aioclient_mock.mock_calls)


async def test_encryption_and_ota_diagnostics_are_visible(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    status = device_status(
        transport="tls-psk",
        last_ota="v0.6.1: installed 0.6.2; rebooting",
        ota_busy=True,
        ota_phase="downloading",
    )
    status["ota"]["bytes_total"] = 1000
    status["ota"]["bytes_written"] = 250
    status["ota"]["message"] = "downloading firmware"
    stub_device(aioclient_mock, status=status)
    await setup_integration(hass)

    assert state_of(hass, ENCRYPTION_SENSOR) == "enabled"
    assert state_of(hass, OTA_SENSOR) == "downloading"
    ota = hass.states.get(OTA_SENSOR)
    firmware = hass.states.get(FIRMWARE_UPDATE)
    assert ota is not None
    assert firmware is not None
    assert ota.attributes["last_attempt"] == "v0.6.1: installed 0.6.2; rebooting"
    assert ota.attributes["message"] == "downloading firmware"
    assert firmware.attributes["in_progress"] is True
    assert firmware.attributes["update_percentage"] == 25.0


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
