"""Constants for the StreamLine Home Assistant integration."""

from datetime import timedelta
from typing import Literal

from homeassistant.const import Platform

DOMAIN = "streamline"
CONF_DEVICE_URL = "device_url"
CONF_ADMIN_KEY = "admin_key"

type UpdateSchedule = Literal["disabled", "daily", "weekly"]
UPDATE_SCHEDULES: tuple[UpdateSchedule, ...] = ("disabled", "daily", "weekly")

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
UPDATE_INTERVAL = timedelta(seconds=5)
