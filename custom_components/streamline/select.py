"""Audio input selection for StreamLine devices."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .const import BUTTON_ACTIONS, LED_ROLES, UPDATE_SCHEDULES
from .entity import StreamLineWritableEntity, add_entities_when_supported
from .errors import StreamLineApiError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry
    from .models import (
        AudioProfileCatalog,
        ButtonCapabilityStatus,
        LedCapabilityStatus,
        StatusResponse,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add input, profile, schedule, button, and LED selectors."""
    async_add_entities([StreamLineInputSelect(entry), StreamLineUpdateScheduleSelect(entry)])
    add_entities_when_supported(entry, async_add_entities, _audio_profile_entities)
    add_entities_when_supported(entry, async_add_entities, _button_entities)
    add_entities_when_supported(entry, async_add_entities, _led_entities)


def _audio_profile_entities(entry: StreamLineConfigEntry) -> Iterable[Entity]:
    if not entry.runtime_data.audio_profiles.profiles:
        return ()
    return (StreamLineAudioProfileSelect(entry),)


def _button_entities(entry: StreamLineConfigEntry) -> Iterable[Entity]:
    return [
        StreamLineButtonActionSelect(entry, button)
        for button in entry.runtime_data.status.capabilities.buttons
    ]


def _led_entities(entry: StreamLineConfigEntry) -> Iterable[Entity]:
    return [
        StreamLineLedRoleSelect(entry, led) for led in entry.runtime_data.status.capabilities.leds
    ]


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


class StreamLineButtonActionSelect(StreamLineWritableEntity, SelectEntity):
    """Assign the action one physical board button fires on a press."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "button_action"

    def __init__(self, entry: StreamLineConfigEntry, button: ButtonCapabilityStatus) -> None:
        super().__init__(entry, f"button:{button.id}")
        self._button_id = button.id
        self._attr_options = list(BUTTON_ACTIONS)
        self._attr_translation_placeholders = {"button": button.label}

    @property
    def available(self) -> bool:
        """Report unavailable once a board stops advertising this button."""
        return super().available and any(
            button.id == self._button_id for button in self.coordinator.status.capabilities.buttons
        )

    @property
    def current_option(self) -> str | None:
        """Return the button's effective action."""
        return next(
            (
                assigned.action.root
                for assigned in self.coordinator.settings.button_actions
                if assigned.id == self._button_id
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Assign this button a new action."""
        try:
            await self.coordinator.async_set_button(self._button_id, option)
        except (StreamLineApiError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc


class StreamLineLedRoleSelect(StreamLineWritableEntity, SelectEntity):
    """Assign the behavior of one physical board LED."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "led_role"

    def __init__(self, entry: StreamLineConfigEntry, led: LedCapabilityStatus) -> None:
        super().__init__(entry, f"led:{led.id}")
        self._led_id = led.id
        self._attr_options = list(LED_ROLES)
        self._attr_translation_placeholders = {"led": led.label}

    @property
    def available(self) -> bool:
        """Report unavailable once a board stops advertising this LED."""
        return super().available and any(
            led.id == self._led_id for led in self.coordinator.status.capabilities.leds
        )

    @property
    def current_option(self) -> str | None:
        """Return the LED's effective role."""
        return next(
            (
                assigned.role.root
                for assigned in self.coordinator.settings.led_roles
                if assigned.id == self._led_id
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Assign this LED a new role."""
        try:
            await self.coordinator.async_set_led(self._led_id, option)
        except (StreamLineApiError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc


class StreamLineAudioProfileSelect(StreamLineWritableEntity, SelectEntity):
    """Select one saved audio profile on the device."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "audio_profile"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "audio_profile")

    @property
    def available(self) -> bool:
        """Report unavailable when the device has no saved audio profiles."""
        return super().available and bool(self.coordinator.audio_profiles.profiles)

    @property
    def options(self) -> list[str]:
        """Return saved audio profile names in catalog order."""
        return list(_audio_profile_options(self.coordinator.audio_profiles))

    @property
    def current_option(self) -> str | None:
        """Return the display name of the active audio profile, or None for custom settings."""
        selected = self.coordinator.audio_profiles.active_profile_id
        if selected is None:
            return None
        return next(
            (
                label
                for label, profile_id in _audio_profile_options(
                    self.coordinator.audio_profiles
                ).items()
                if profile_id == selected
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Activate a saved audio profile."""
        profile_id = _audio_profile_options(self.coordinator.audio_profiles)[option]
        try:
            await self.coordinator.async_set_audio_profile(profile_id)
        except (StreamLineApiError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc


def _input_options(status: StatusResponse) -> dict[str, int]:
    """Map unique display labels to device-owned input line identifiers."""
    return _unique_options((item.label, item.line) for item in status.capabilities.input_lines)


def _audio_profile_options(catalog: AudioProfileCatalog) -> dict[str, str]:
    """Map unique display names to device-owned audio profile identifiers."""
    return _unique_options((profile.name, profile.id) for profile in catalog.profiles)


def _unique_options[IdT](items: Iterable[tuple[str, IdT]]) -> dict[str, IdT]:
    """Disambiguate duplicate display labels with their device-owned identifiers."""
    pairs = list(items)
    label_counts = Counter(label for label, _ in pairs)
    options: dict[str, IdT] = {}
    for raw_label, identifier in pairs:
        label = raw_label if label_counts[raw_label] == 1 else f"{raw_label} ({identifier})"
        while label in options:
            label = f"{label} ({identifier})"
        options[label] = identifier
    return options
