"""Constants for the StreamLine Home Assistant integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "streamline"
CONF_DEVICE_URL = "device_url"
CONF_ADMIN_KEY = "admin_key"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
UPDATE_INTERVAL = timedelta(seconds=5)
