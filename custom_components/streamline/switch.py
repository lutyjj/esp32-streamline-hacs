"""Streaming and local analog output switches for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .entity import StreamLineWritableEntity, add_entities_when_supported
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add streaming control, and analog passthrough on a board that has it."""
    async_add_entities([StreamLineStreamSwitch(entry)])
    add_entities_when_supported(entry, async_add_entities, _passthrough_entities)


def _passthrough_entities(entry: StreamLineConfigEntry) -> Iterable[Entity]:
    if entry.runtime_data.status.capabilities.analog_passthrough is None:
        return ()
    return (StreamLineAnalogPassthroughSwitch(entry),)


class StreamLineStreamSwitch(StreamLineWritableEntity, SwitchEntity):
    """Pause or resume the device's audio stream to the bridge."""

    _attr_translation_key = "streaming"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "streaming")

    @property
    def is_on(self) -> bool:
        """Return whether the device is streaming to the bridge."""
        return self.coordinator.status.stream.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume streaming to the bridge."""
        await self._async_set_stream(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause streaming to the bridge."""
        await self._async_set_stream(False)

    async def _async_set_stream(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_stream(enabled)
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc


class StreamLineAnalogPassthroughSwitch(StreamLineWritableEntity, SwitchEntity):
    """Control the board's local analog output route."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "analog_passthrough"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "analog_passthrough")

    @property
    def available(self) -> bool:
        """Report unavailable when the selected board has no local output."""
        return (
            super().available
            and self.coordinator.status.capabilities.analog_passthrough is not None
        )

    @property
    def is_on(self) -> bool:
        """Return the configured passthrough state."""
        return self.coordinator.status.analog_passthrough.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable local analog passthrough."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable local analog passthrough."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_analog_passthrough(enabled)
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
