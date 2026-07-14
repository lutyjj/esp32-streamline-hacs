"""UI configuration for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from yarl import URL

from .api import StreamLineDeviceClient, normalize_device_url
from .const import CONF_ADMIN_KEY, CONF_DEVICE_URL, DOMAIN
from .errors import (
    StreamLineApiError,
    StreamLineAuthenticationError,
    StreamLineCannotConnect,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
DEFAULT_DEVICE_URL = "http://streamline.local"


class StreamLineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one StreamLine device."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create an entry for one verified device URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, title, errors = await self._async_validated_data(user_input)
            if not errors:
                self._async_abort_entries_match({CONF_DEVICE_URL: data[CONF_DEVICE_URL]})
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the device URL or admin key after verification."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, _title, errors = await self._async_validated_data(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or entry.data),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start the repair flow for a rejected admin key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify and save a replacement admin key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, _title, errors = await self._async_validated_data({**entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_ADMIN_KEY): TOKEN_SELECTOR}),
            errors=errors,
        )

    async def _async_validated_data(
        self, user_input: Mapping[str, Any]
    ) -> tuple[dict[str, str], str, dict[str, str]]:
        """Verify device access and return normalized entry data."""
        try:
            device_url = normalize_device_url(str(user_input.get(CONF_DEVICE_URL, "")))
        except StreamLineApiError:
            return {}, "", {CONF_DEVICE_URL: "invalid_url"}
        admin_key = str(user_input.get(CONF_ADMIN_KEY, "")).strip()
        client = StreamLineDeviceClient(
            async_get_clientsession(self.hass), device_url, admin_key or None
        )
        try:
            status = await client.async_get_status()
            if admin_key:
                await client.async_unlock()
        except StreamLineAuthenticationError:
            return {}, "", {CONF_ADMIN_KEY: "invalid_auth"}
        except StreamLineCannotConnect:
            return {}, "", {"base": "cannot_connect"}
        except StreamLineApiError:
            return {}, "", {"base": "invalid_response"}
        data = {CONF_DEVICE_URL: device_url}
        if admin_key:
            data[CONF_ADMIN_KEY] = admin_key
        title = status.device_name.strip() or _entry_title(device_url)
        return data, title, {}


def _schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DEVICE_URL, default=defaults.get(CONF_DEVICE_URL, DEFAULT_DEVICE_URL)
            ): str,
            vol.Optional(CONF_ADMIN_KEY, default=defaults.get(CONF_ADMIN_KEY, "")): TOKEN_SELECTOR,
        }
    )


def _entry_title(device_url: str) -> str:
    return URL(device_url).host or device_url
