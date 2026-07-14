"""Firmware update control for StreamLine devices."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import StreamLineWritableEntity
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry

LOGGER = logging.getLogger(__name__)
FIRMWARE_RELEASE_URL = "https://github.com/lutyjj/esp32-streamline/releases/tag/v{}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add firmware update control."""
    async_add_entities([StreamLineFirmwareUpdate(entry)])


class StreamLineFirmwareUpdate(StreamLineWritableEntity, UpdateEntity):
    """Check for and install the device's latest firmware release."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_title = "ESP32 StreamLine"
    _attr_translation_key = "firmware"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "firmware")

    @property
    def installed_version(self) -> str:
        """Return the running firmware version."""
        return self.coordinator.status.firmware_version

    @property
    def latest_version(self) -> str:
        """Return the checked release, or the running version until a check completes."""
        return self.coordinator.status.ota.latest_version or self.installed_version

    @property
    def release_url(self) -> str:
        """Link to the firmware release selected by the device."""
        return FIRMWARE_RELEASE_URL.format(self.latest_version)

    @property
    def auto_update(self) -> bool:
        """Return whether the device autonomously installs releases."""
        return self.coordinator.settings.auto_update_schedule.root != "disabled"

    @property
    def in_progress(self) -> bool:
        """Return whether an update operation is active."""
        return self.coordinator.status.ota.busy

    @property
    def update_percentage(self) -> float | None:
        """Return install progress once the device knows the image size."""
        ota = self.coordinator.status.ota
        if not ota.busy or ota.bytes_total == 0:
            return None
        return round(ota.bytes_written * 100 / ota.bytes_total, 1)

    @override
    async def async_added_to_hass(self) -> None:
        """Start one non-destructive release check when the writable entity loads."""
        await super().async_added_to_hass()
        if not self.available:
            return
        try:
            await self.coordinator.async_check_firmware_update()
        except StreamLineApiError as exc:
            LOGGER.debug("Initial firmware update check was not accepted: %s", exc)

    @override
    async def async_update(self) -> None:
        """Run a fresh device-side release check for manual entity refreshes."""
        if not self.enabled or not self.available:
            return
        try:
            await self.coordinator.async_check_firmware_update()
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc

    @override
    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install the latest release through the device's guarded OTA path."""
        if version not in {None, self.latest_version}:
            raise HomeAssistantError("the device can only install its latest release")
        try:
            await self.coordinator.async_install_firmware_update()
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
