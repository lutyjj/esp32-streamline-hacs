"""One shared device poll behind every StreamLine entity."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
from .errors import StreamLineApiError, StreamLineAuthenticationError
from .models import StatusResponse

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import StreamLineDeviceClient
LOGGER = logging.getLogger(__name__)


class StreamLineCoordinator(DataUpdateCoordinator[StatusResponse]):
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
        self.client = client
        self._validate_auth = client.has_admin_key

    async def _async_update_data(self) -> StatusResponse:
        try:
            status = await self.client.async_get_status()
            if self._validate_auth:
                await self.client.async_unlock()
                self._validate_auth = False
        except StreamLineAuthenticationError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except StreamLineApiError as exc:
            raise UpdateFailed(str(exc)) from exc
        return status

    async def async_set_audio(
        self,
        *,
        input_line: int | None = None,
        input_gain: int | None = None,
        adc_attenuation_db: int | None = None,
    ) -> None:
        """Update selected audio controls while preserving the rest."""
        current = self.data.audio
        await self.client.async_set_audio(
            current.input_line if input_line is None else input_line,
            current.input_gain if input_gain is None else input_gain,
            current.adc_attenuation_db if adc_attenuation_db is None else adc_attenuation_db,
        )
        await self.async_request_refresh()

    async def async_set_analog_passthrough(self, enabled: bool) -> None:
        """Update local analog output and refresh every entity."""
        await self.client.async_set_analog_passthrough(enabled)
        await self.async_request_refresh()


type StreamLineConfigEntry = ConfigEntry[StreamLineCoordinator]
