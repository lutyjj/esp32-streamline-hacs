"""Entity bases shared by every StreamLine platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StreamLineCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        status = self.coordinator.status
        return DeviceInfo(
            configuration_url=self.coordinator.client.device_url,
            identifiers={(DOMAIN, self._device_identifier)},
            manufacturer="ESP32 StreamLine",
            model=status.capabilities.board,
            name=status.device_name,
            sw_version=status.firmware_version,
        )


def add_entities_when_supported(
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build: Callable[[StreamLineConfigEntry], Iterable[Entity]],
) -> None:
    """Add board-dependent entities now, or on the poll that first reports them.

    A board's capabilities are runtime state: selecting another board through
    the device console changes them under a running entry.
    """
    if entities := list(build(entry)):
        async_add_entities(entities)
        return

    remove_listener: Callable[[], None] | None = None

    @callback
    def stop_watching() -> None:
        nonlocal remove_listener
        if remove_listener is not None:
            remove_listener()
            remove_listener = None

    @callback
    def add_when_reported() -> None:
        if entities := list(build(entry)):
            async_add_entities(entities)
            stop_watching()

    remove_listener = entry.runtime_data.async_add_listener(add_when_reported)
    entry.async_on_unload(stop_watching)


class StreamLineWritableEntity(StreamLineEntity):
    """Entity that requires a writable device and saved admin key."""

    @property
    def available(self) -> bool:
        """Report unavailable when authenticated configuration is impossible."""
        return (
            super().available
            and self.coordinator.client.has_admin_key
            and self.coordinator.status.configuration_writable
        )
