"""Audio input selection for StreamLine devices."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .const import UPDATE_SCHEDULES
from .entity import StreamLineWritableEntity
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry
    from .models import StatusResponse


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the device input selector."""
    async_add_entities([StreamLineInputSelect(entry), StreamLineUpdateScheduleSelect(entry)])


class StreamLineInputSelect(StreamLineWritableEntity, SelectEntity):
    """Select one board-advertised audio input."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "input"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "input")

    @property
    def options(self) -> list[str]:
        """Return input labels in board order."""
        return list(_input_options(self.coordinator.status))

    @property
    def current_option(self) -> str | None:
        """Return the label of the active input."""
        selected = self.coordinator.status.audio.input_line
        return next(
            (
                label
                for label, line in _input_options(self.coordinator.status).items()
                if line == selected
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Select an input while preserving the level controls."""
        line = _input_options(self.coordinator.status)[option]
        try:
            await self.coordinator.async_set_audio(input_line=line)
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc


class StreamLineUpdateScheduleSelect(StreamLineWritableEntity, SelectEntity):
    """Configure the device's autonomous firmware update cadence."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "automatic_update_schedule"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "automatic_update_schedule")
        self._attr_options = list(UPDATE_SCHEDULES)

    @property
    def current_option(self) -> str:
        """Return the persisted update schedule."""
        return self.coordinator.settings.auto_update_schedule.root

    async def async_select_option(self, option: str) -> None:
        """Persist a supported automatic update schedule."""
        try:
            await self.coordinator.async_set_update_schedule(option)
        except (StreamLineApiError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc


def _input_options(status: StatusResponse) -> dict[str, int]:
    """Map unique display labels to device-owned input line identifiers."""
    inputs = status.capabilities.input_lines
    label_counts = Counter(item.label for item in inputs)
    options: dict[str, int] = {}
    for item in inputs:
        label = item.label if label_counts[item.label] == 1 else f"{item.label} ({item.line})"
        while label in options:
            label = f"{label} ({item.line})"
        options[label] = item.line
    return options
