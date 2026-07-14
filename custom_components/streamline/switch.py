"""Local analog output control for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .entity import StreamLineWritableEntity
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add analog passthrough when the current or a later board supports it."""
    if entry.runtime_data.status.capabilities.analog_passthrough is not None:
        async_add_entities([StreamLineAnalogPassthroughSwitch(entry)])
        return

    remove_listener: Callable[[], None] | None = None

    @callback
    def remove_capability_listener() -> None:
        nonlocal remove_listener
        if remove_listener is not None:
            remove_listener()
            remove_listener = None

    @callback
    def add_supported_entity() -> None:
        if entry.runtime_data.status.capabilities.analog_passthrough is None:
            return
        async_add_entities([StreamLineAnalogPassthroughSwitch(entry)])
        remove_capability_listener()

    remove_listener = entry.runtime_data.async_add_listener(add_supported_entity)
    entry.async_on_unload(remove_capability_listener)


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
