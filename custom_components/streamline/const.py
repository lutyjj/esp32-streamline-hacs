"""Constants for the StreamLine Home Assistant integration."""

from datetime import timedelta
from typing import cast, get_args

from homeassistant.const import Platform

from .models import AutoUpdateScheduleRequest, ButtonAction

DOMAIN = "streamline"
CONF_DEVICE_URL = "device_url"
CONF_ADMIN_KEY = "admin_key"

UPDATE_SCHEDULES = cast(
    "tuple[str, ...]", get_args(AutoUpdateScheduleRequest.model_fields["root"].annotation)
)
BUTTON_ACTIONS = cast("tuple[str, ...]", get_args(ButtonAction.model_fields["root"].annotation))

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
UPDATE_INTERVAL = timedelta(seconds=5)
