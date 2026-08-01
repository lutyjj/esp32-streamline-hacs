"""Device actions for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
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
    """Add the device restart control."""
    async_add_entities([StreamLineRestartButton(entry)])


class StreamLineRestartButton(StreamLineWritableEntity, ButtonEntity):
    """Reboot the device."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "restart"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "restart")

    async def async_press(self) -> None:
        """Ask the device to reboot."""
        try:
            await self.coordinator.async_restart()
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
