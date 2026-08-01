"""Async client for the StreamLine device API."""

from __future__ import annotations

from contextlib import suppress
from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientTimeout, DigestAuthMiddleware
from pydantic import BaseModel, ValidationError
from yarl import URL

from .errors import (
    StreamLineApiError,
    StreamLineAuthenticationError,
    StreamLineCannotConnect,
)
from .models import (
    Ack,
    AnalogPassthroughSettingsRequest,
    AudioSettingsRequest,
    AutoUpdateScheduleRequest,
    ButtonAction,
    ButtonSettingsRequest,
    ConfigResponse,
    CoredumpResponse,
    ErrorResponse,
    FirmwareSettingsRequest,
    StatusResponse,
    StreamRequest,
)

if TYPE_CHECKING:
    from aiohttp import ClientMiddlewareType, ClientResponse, ClientSession

REQUEST_TIMEOUT = ClientTimeout(total=10)
# The device's single owner account. It answers an authenticated request with
# an RFC 7616 digest challenge, so the admin key is the password of the one
# username the firmware accepts and never crosses the network itself.
ADMIN_USERNAME = "admin"


class StreamLineDeviceClient:
    """Call one device with Home Assistant's shared HTTP session."""

    def __init__(
        self,
        session: ClientSession,
        device_url: str,
        admin_key: str | None = None,
    ) -> None:
        self._session = session
        self._base_url = URL(normalize_device_url(device_url))
        # One middleware for this device's lifetime: it carries the challenge
        # and the nonce count the firmware requires to strictly increase.
        self._digest_auth = DigestAuthMiddleware(ADMIN_USERNAME, admin_key) if admin_key else None

    @property
    def device_url(self) -> str:
        """Return the normalized device root URL."""
        return str(self._base_url)

    @property
    def has_admin_key(self) -> bool:
        """Return whether authenticated device control is possible."""
        return self._digest_auth is not None

    async def async_get_status(self) -> StatusResponse:
        """Read device status, metrics, and capabilities."""
        return await self._request("GET", "/api/status", StatusResponse)

    async def async_get_settings(self) -> ConfigResponse:
        """Read persisted device settings."""
        return await self._request("GET", "/api/settings", ConfigResponse)

    async def async_get_coredump(self) -> CoredumpResponse:
        """Read whether a panic left a crash dump on the device."""
        return await self._request("GET", "/api/coredump", CoredumpResponse, authenticated=True)

    async def async_unlock(self) -> Ack:
        """Validate the configured device admin key."""
        return await self._request("POST", "/api/unlock", Ack, authenticated=True)

    async def async_set_audio(
        self, input_line: int, input_gain: int, adc_attenuation_db: int
    ) -> Ack:
        """Apply the complete audio-control tuple."""
        return await self._request(
            "POST",
            "/api/settings/audio",
            Ack,
            authenticated=True,
            form=AudioSettingsRequest(
                input_line=input_line,
                input_gain=input_gain,
                adc_attenuation_db=adc_attenuation_db,
            ),
        )

    async def async_set_analog_passthrough(self, enabled: bool) -> Ack:
        """Enable or disable the board's local analog output."""
        return await self._request(
            "POST",
            "/api/settings/analog-passthrough",
            Ack,
            authenticated=True,
            form=AnalogPassthroughSettingsRequest(enabled=enabled),
        )

    async def async_set_stream(self, enabled: bool) -> Ack:
        """Pause or resume streaming to the bridge."""
        return await self._request(
            "POST",
            "/api/stream",
            Ack,
            authenticated=True,
            form=StreamRequest(enabled=enabled),
        )

    async def async_set_button(self, button_id: str, action: str) -> Ack:
        """Assign one board button, named by its capabilities id, a new action."""
        return await self._request(
            "POST",
            "/api/settings/button",
            Ack,
            authenticated=True,
            form=ButtonSettingsRequest(id=button_id, action=ButtonAction.model_validate(action)),
        )

    async def async_restart(self) -> Ack:
        """Ask the device to reboot."""
        return await self._request("POST", "/api/restart", Ack, authenticated=True)

    async def async_set_update_schedule(self, schedule: str) -> Ack:
        """Set the device's automatic firmware update schedule."""
        return await self._request(
            "POST",
            "/api/settings/firmware",
            Ack,
            authenticated=True,
            form=FirmwareSettingsRequest(
                auto_update_schedule=AutoUpdateScheduleRequest.model_validate(schedule)
            ),
        )

    async def async_check_firmware_update(self) -> Ack:
        """Ask the device to check its firmware release source."""
        return await self._request("POST", "/api/ota/check", Ack, authenticated=True)

    async def async_install_firmware_update(self) -> Ack:
        """Ask the device to install its latest firmware release."""
        return await self._request("POST", "/api/ota/update", Ack, authenticated=True)

    async def _request[ModelT: BaseModel](
        self,
        method: str,
        path: str,
        response_model: type[ModelT],
        *,
        authenticated: bool = False,
        form: BaseModel | None = None,
    ) -> ModelT:
        middlewares: tuple[ClientMiddlewareType, ...] = ()
        if authenticated:
            if self._digest_auth is None:
                raise StreamLineAuthenticationError("a device admin key is required")
            middlewares = (self._digest_auth,)
        try:
            async with self._session.request(
                method,
                self._base_url.with_path(path),
                data=_form_data(form) if form is not None else None,
                middlewares=middlewares,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status >= HTTPStatus.BAD_REQUEST:
                    raise await _response_error(response)
                payload: object = await response.json(content_type=None)
        except StreamLineApiError:
            raise
        except (ClientError, TimeoutError) as exc:
            raise StreamLineCannotConnect("could not connect to the StreamLine device") from exc
        except ValueError as exc:
            raise StreamLineApiError("device returned invalid JSON") from exc
        return _validate(response_model, payload)


def _form_data(model: BaseModel) -> dict[str, str]:
    """Encode a generated request model as an HTML form."""
    values = model.model_dump(mode="json")
    return {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in values.items()
    }


async def _response_error(response: ClientResponse) -> StreamLineApiError:
    """Map one device error response to the matching client error."""
    message = f"device request failed with HTTP {response.status}"
    with suppress(StreamLineApiError, ClientError, ValueError):
        message = _validate(ErrorResponse, await response.json(content_type=None)).error
    if response.status == HTTPStatus.UNAUTHORIZED:
        return StreamLineAuthenticationError(message)
    return StreamLineApiError(message)


def _validate[ModelT: BaseModel](model: type[ModelT], payload: object) -> ModelT:
    """Parse one device payload with its OpenAPI-generated model."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise StreamLineApiError(f"device returned an invalid {model.__name__}") from exc


def normalize_device_url(value: str) -> str:
    """Parse and canonicalize one device root URL."""
    try:
        url = URL(value.strip())
    except ValueError as exc:
        raise StreamLineApiError("enter a valid device URL") from exc
    if (
        url.scheme not in {"http", "https"}
        or url.host is None
        or url.user is not None
        or url.password is not None
        or url.query_string
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise StreamLineApiError("enter an HTTP or HTTPS device root URL without a path or query")
    return str(url.with_path("")).rstrip("/")
