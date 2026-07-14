"""Async client for the StreamLine device API."""

from __future__ import annotations

from contextlib import suppress
from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientTimeout
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
    ErrorResponse,
    StatusResponse,
)

if TYPE_CHECKING:
    from aiohttp import ClientResponse, ClientSession

REQUEST_TIMEOUT = ClientTimeout(total=10)


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
        self._admin_key = admin_key or None

    @property
    def device_url(self) -> str:
        """Return the normalized device root URL."""
        return str(self._base_url)

    @property
    def has_admin_key(self) -> bool:
        """Return whether authenticated device control is possible."""
        return self._admin_key is not None

    async def async_get_status(self) -> StatusResponse:
        """Read device status, metrics, and capabilities."""
        return await self._request("GET", "/api/status", StatusResponse)

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

    async def _request[ModelT: BaseModel](
        self,
        method: str,
        path: str,
        response_model: type[ModelT],
        *,
        authenticated: bool = False,
        form: BaseModel | None = None,
    ) -> ModelT:
        headers: dict[str, str] = {}
        if authenticated:
            if self._admin_key is None:
                raise StreamLineAuthenticationError("a device admin key is required")
            headers["Authorization"] = f"Bearer {self._admin_key}"
        try:
            async with self._session.request(
                method,
                self._base_url.with_path(path),
                headers=headers,
                data=_form_data(form) if form is not None else None,
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
