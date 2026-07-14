"""Entity bases shared by every StreamLine platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StreamLineCoordinator

if TYPE_CHECKING:
    from .coordinator import StreamLineConfigEntry


class StreamLineEntity(CoordinatorEntity[StreamLineCoordinator]):
    """Entity backed by one StreamLine device status poll."""

    _attr_has_entity_name = True

    def __init__(self, entry: StreamLineConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{entry.entry_id}:{key}"
        self._device_identifier = entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the physical StreamLine device."""
        status = self.coordinator.data
        return DeviceInfo(
            configuration_url=self.coordinator.client.device_url,
            identifiers={(DOMAIN, self._device_identifier)},
            manufacturer="ESP32 StreamLine",
            model=status.capabilities.board,
            name=status.device_name,
            sw_version=status.firmware_version,
        )


class StreamLineWritableEntity(StreamLineEntity):
    """Entity that requires a writable device and saved admin key."""

    @property
    def available(self) -> bool:
        """Report unavailable when authenticated configuration is impossible."""
        return (
            super().available
            and self.coordinator.client.has_admin_key
            and self.coordinator.data.configuration_writable
        )
