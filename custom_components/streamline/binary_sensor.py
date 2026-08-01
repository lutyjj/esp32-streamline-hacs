"""Playback and device-integrity states for StreamLine devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import StreamLineEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry, StreamLineData


@dataclass(frozen=True, kw_only=True)
class StreamLineBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one boolean read from the device poll."""

    value_fn: Callable[[StreamLineData], bool]
    available_fn: Callable[[StreamLineData], bool] = lambda _data: True


BINARY_SENSORS: tuple[StreamLineBinarySensorDescription, ...] = (
    StreamLineBinarySensorDescription(
        key="playing",
        translation_key="playing",
        device_class=BinarySensorDeviceClass.SOUND,
        value_fn=lambda data: data.status.metrics.playing,
    ),
    StreamLineBinarySensorDescription(
        key="crash_dump",
        translation_key="crash_dump",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.coredump is not None and data.coredump.present,
        available_fn=lambda data: data.coredump is not None,
    ),
    StreamLineBinarySensorDescription(
        key="signed_updates",
        translation_key="signed_updates",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.status.ota.signed_updates,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the device playback and integrity sensors."""
    async_add_entities(StreamLineBinarySensor(entry, description) for description in BINARY_SENSORS)


class StreamLineBinarySensor(StreamLineEntity, BinarySensorEntity):
    """Expose one boolean from the shared poll."""

    entity_description: StreamLineBinarySensorDescription

    def __init__(
        self, entry: StreamLineConfigEntry, description: StreamLineBinarySensorDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Report unavailable while the device cannot answer for this state."""
        return super().available and self.entity_description.available_fn(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        """Return the current value without I/O."""
        return self.entity_description.value_fn(self.coordinator.data)
