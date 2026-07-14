"""Local analog output control for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .entity import StreamLineWritableEntity
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add analog passthrough when the selected board supports it."""
    if entry.runtime_data.status.capabilities.analog_passthrough is not None:
        async_add_entities([StreamLineAnalogPassthroughSwitch(entry)])


class StreamLineAnalogPassthroughSwitch(StreamLineWritableEntity, SwitchEntity):
    """Control the board's local analog output route."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "analog_passthrough"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "analog_passthrough")

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
