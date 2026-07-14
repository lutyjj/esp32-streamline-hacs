"""Constants for the StreamLine Home Assistant integration."""

from datetime import timedelta
from typing import cast, get_args

from homeassistant.const import Platform

from .models import AutoUpdateScheduleRequest

DOMAIN = "streamline"
CONF_DEVICE_URL = "device_url"
CONF_ADMIN_KEY = "admin_key"

UPDATE_SCHEDULES = cast(
    "tuple[str, ...]", get_args(AutoUpdateScheduleRequest.model_fields["root"].annotation)
)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
UPDATE_INTERVAL = timedelta(seconds=5)
