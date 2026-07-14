"""Measurements and diagnostics for StreamLine devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory

from .entity import StreamLineEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry
    from .models import StatusResponse

PEAK_FULL_SCALE = 32768


@dataclass(frozen=True, kw_only=True)
class StreamLineSensorDescription(SensorEntityDescription):
    """Describe one value read from device status."""

    value_fn: Callable[[StatusResponse], str | int | float]


SENSORS: tuple[StreamLineSensorDescription, ...] = (
    StreamLineSensorDescription(
        key="peak_level",
        translation_key="peak_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: round(
            max(status.metrics.peak_abs_left, status.metrics.peak_abs_right)
            * 100
            / PEAK_FULL_SCALE,
            1,
        ),
    ),
    StreamLineSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.wifi.rssi,
    ),
    StreamLineSensorDescription(
        key="health",
        translation_key="health",
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "info", "blocking"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.health.status.root,
    ),
    StreamLineSensorDescription(
        key="network_errors",
        translation_key="network_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.metrics.network_errors_total,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamLineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add device measurement and diagnostic sensors."""
    async_add_entities(StreamLineSensor(entry, description) for description in SENSORS)


class StreamLineSensor(StreamLineEntity, SensorEntity):
    """Expose one status value from the shared poll."""

    entity_description: StreamLineSensorDescription

    def __init__(
        self, entry: StreamLineConfigEntry, description: StreamLineSensorDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float:
        """Return the current value without I/O."""
        return self.entity_description.value_fn(self.coordinator.data)
