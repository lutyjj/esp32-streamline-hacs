"""Audio input selection for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
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
    """Add the device input selector."""
    async_add_entities([StreamLineInputSelect(entry)])


class StreamLineInputSelect(StreamLineWritableEntity, SelectEntity):
    """Select one board-advertised audio input."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "input"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "input")

    @property
    def options(self) -> list[str]:
        """Return input labels in board order."""
        return [option.label for option in self.coordinator.data.capabilities.input_lines]

    @property
    def current_option(self) -> str | None:
        """Return the label of the active input."""
        selected = self.coordinator.data.audio.input_line
        return next(
            (
                option.label
                for option in self.coordinator.data.capabilities.input_lines
                if option.line == selected
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Select an input while preserving the level controls."""
        line = next(
            item.line
            for item in self.coordinator.data.capabilities.input_lines
            if item.label == option
        )
        try:
            await self.coordinator.async_set_audio(input_line=line)
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
