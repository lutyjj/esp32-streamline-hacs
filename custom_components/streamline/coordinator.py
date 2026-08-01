"""One shared device poll behind every StreamLine entity."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BUTTON_ACTIONS, DOMAIN, UPDATE_INTERVAL, UPDATE_SCHEDULES
from .errors import StreamLineApiError, StreamLineAuthenticationError
from .models import (
    AutoUpdateScheduleRequest,
    ButtonAction,
    ButtonActionStatus,
    ConfigResponse,
    CoredumpResponse,
    StatusResponse,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from homeassistant.core import HomeAssistant

    from .api import StreamLineDeviceClient

LOGGER = logging.getLogger(__name__)
SETTINGS_REFRESH_POLLS = 60


@dataclass(frozen=True)
class StreamLineData:
    """Status and slow-changing settings from one device."""

    status: StatusResponse
    settings: ConfigResponse
    # None until an authenticated read succeeds: the crash dump is admin-key
    # gated, and a device that cannot report one still runs every other entity.
    coredump: CoredumpResponse | None


class StreamLineCoordinator(DataUpdateCoordinator[StreamLineData]):
    """Poll one StreamLine device for every entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: StreamLineDeviceClient,
    ) -> None:
        super().__init__(
            hass,
            logger=LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self._entry = entry
        self.client = client
        self._validate_auth = client.has_admin_key
        self._settings: ConfigResponse | None = None
        self._settings_poll_count = 0
        self._coredump: CoredumpResponse | None = None

    @property
    def settings(self) -> ConfigResponse:
        """Return settings loaded during the first successful refresh."""
        return self.data.settings

    @property
    def status(self) -> StatusResponse:
        """Return the latest device status."""
        return self.data.status

    async def _async_update_data(self) -> StreamLineData:
        try:
            status = await self.client.async_get_status()
            if self._validate_auth:
                await self.client.async_unlock()
                self._validate_auth = False
            if self._settings is None or self._settings_poll_count >= SETTINGS_REFRESH_POLLS:
                self._settings = await self.client.async_get_settings()
                self._coredump = await self._async_read_coredump()
                self._settings_poll_count = 0
            else:
                self._settings_poll_count += 1
        except StreamLineAuthenticationError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except StreamLineApiError as exc:
            raise UpdateFailed(str(exc)) from exc
        assert self._settings is not None
        return StreamLineData(status=status, settings=self._settings, coredump=self._coredump)

    async def _async_read_coredump(self) -> CoredumpResponse | None:
        """Read the crash dump status, which only the admin key can see.

        A device that refuses this read still serves every other entity, so a
        failure leaves the crash-dump sensor unavailable instead of failing
        the poll. A rejected key is not swallowed: it belongs to reauth.
        """
        if not self.client.has_admin_key:
            return None
        try:
            return await self.client.async_get_coredump()
        except StreamLineAuthenticationError:
            raise
        except StreamLineApiError as exc:
            LOGGER.debug("Device did not report crash dump status: %s", exc)
            return None

    async def async_set_audio(
        self,
        *,
        input_line: int | None = None,
        input_gain: int | None = None,
        adc_attenuation_db: int | None = None,
    ) -> None:
        """Update selected audio controls while preserving the rest."""
        current = self.status.audio
        await self._async_authenticated_call(
            self.client.async_set_audio(
                current.input_line if input_line is None else input_line,
                current.input_gain if input_gain is None else input_gain,
                current.adc_attenuation_db if adc_attenuation_db is None else adc_attenuation_db,
            )
        )
        await self.async_request_refresh()

    async def async_set_analog_passthrough(self, enabled: bool) -> None:
        """Update local analog output and refresh every entity."""
        await self._async_authenticated_call(self.client.async_set_analog_passthrough(enabled))
        await self.async_request_refresh()

    async def async_set_stream(self, enabled: bool) -> None:
        """Pause or resume streaming and refresh every entity."""
        await self._async_authenticated_call(self.client.async_set_stream(enabled))
        await self.async_request_refresh()

    async def async_restart(self) -> None:
        """Reboot the device."""
        await self._async_authenticated_call(self.client.async_restart())

    async def async_set_button(self, button_id: str, action: str) -> None:
        """Assign one board button an action and update its cached settings."""
        if action not in BUTTON_ACTIONS:
            raise ValueError(f"unsupported button action: {action}")
        await self._async_authenticated_call(self.client.async_set_button(button_id, action))
        assigned = ButtonActionStatus(id=button_id, action=ButtonAction.model_validate(action))
        self._settings = self.settings.model_copy(
            update={
                "button_actions": [
                    assigned if current.id == button_id else current
                    for current in self.settings.button_actions
                ]
            }
        )
        self._publish_settings()

    async def async_set_update_schedule(self, schedule: str) -> None:
        """Update the automatic firmware schedule and its cached settings."""
        if schedule not in UPDATE_SCHEDULES:
            raise ValueError(f"unsupported update schedule: {schedule}")
        await self._async_authenticated_call(self.client.async_set_update_schedule(schedule))
        self._settings = self.settings.model_copy(
            update={
                "auto_update_schedule": AutoUpdateScheduleRequest.model_validate(schedule),
            }
        )
        self._publish_settings()

    async def async_check_firmware_update(self) -> None:
        """Start a firmware update check and refresh its reported phase."""
        await self._async_authenticated_call(self.client.async_check_firmware_update())
        await self.async_request_refresh()

    async def async_install_firmware_update(self) -> None:
        """Start the latest firmware install and refresh its reported phase."""
        await self._async_authenticated_call(self.client.async_install_firmware_update())
        await self.async_request_refresh()

    def _publish_settings(self) -> None:
        """Show a persisted settings write without waiting for the next poll."""
        assert self._settings is not None
        self.async_set_updated_data(
            StreamLineData(status=self.status, settings=self._settings, coredump=self.data.coredump)
        )

    async def _async_authenticated_call(self, request: Awaitable[object]) -> None:
        """Start reauthentication when a device rejects a saved admin key."""
        try:
            await request
        except StreamLineAuthenticationError:
            self._entry.async_start_reauth(self.hass)
            raise


type StreamLineConfigEntry = ConfigEntry[StreamLineCoordinator]
