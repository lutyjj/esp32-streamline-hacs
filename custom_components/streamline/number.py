"""Audio level controls for StreamLine devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfSoundPressure
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
    """Add gain and attenuation controls."""
    async_add_entities([StreamLineInputGain(entry), StreamLineAdcAttenuation(entry)])


class StreamLineInputGain(StreamLineWritableEntity, NumberEntity):
    """Control device input gain."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_translation_key = "input_gain"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "input_gain")

    @property
    def native_value(self) -> float:
        """Return the active input gain."""
        return self.coordinator.status.audio.input_gain

    @property
    def native_max_value(self) -> float:
        """Return the selected board's gain limit."""
        return self.coordinator.status.capabilities.input_gain_max

    async def async_set_native_value(self, value: float) -> None:
        """Set input gain while preserving the other audio controls."""
        try:
            await self.coordinator.async_set_audio(input_gain=round(value))
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc


class StreamLineAdcAttenuation(StreamLineWritableEntity, NumberEntity):
    """Control device ADC attenuation."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_translation_key = "adc_attenuation"

    def __init__(self, entry: StreamLineConfigEntry) -> None:
        super().__init__(entry, "adc_attenuation")

    @property
    def native_value(self) -> float:
        """Return the active ADC attenuation."""
        return self.coordinator.status.audio.adc_attenuation_db

    @property
    def native_max_value(self) -> float:
        """Return the selected board's attenuation limit."""
        return self.coordinator.status.capabilities.adc_atten_max_db

    async def async_set_native_value(self, value: float) -> None:
        """Set ADC attenuation while preserving the other audio controls."""
        try:
            await self.coordinator.async_set_audio(adc_attenuation_db=round(value))
        except StreamLineApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
