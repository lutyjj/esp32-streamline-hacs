"""Playback state for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import StreamLineEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the device playback sensor."""
    async_add_entities([StreamLinePlayingSensor(entry)])


class StreamLinePlayingSensor(StreamLineEntity, BinarySensorEntity):
    """Report whether signal detection is streaming audio."""

    _attr_device_class = BinarySensorDeviceClass.SOUND
    _attr_translation_key = "playing"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "playing")

    @property
    def is_on(self) -> bool:
        """Return the device's signal-gate state."""
        return self.coordinator.data.metrics.playing
