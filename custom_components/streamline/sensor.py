"""Measurements and diagnostics for StreamLine devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)

from .entity import StreamLineEntity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import StreamLineConfigEntry
    from .models import StatusResponse

PEAK_FULL_SCALE = 32768
OTA_PHASES = (
    "idle",
    "checking",
    "up-to-date",
    "update-available",
    "downloading",
    "verifying",
    "installed",
    "failed",
)


def _pcm_encryption_state(status: StatusResponse) -> str:
    """Map known transport modes without reporting an unknown mode as cleartext."""
    if status.target.transport == "tls-psk":
        return "enabled"
    if status.target.transport == "cleartext":
        return "disabled"
    return "unknown"


def _ota_phase(status: StatusResponse) -> str:
    """Keep a future device phase inside the entity's declared enum."""
    return status.ota.phase if status.ota.phase in OTA_PHASES else "unknown"


@dataclass(frozen=True, kw_only=True)
class StreamLineSensorDescription(SensorEntityDescription):
    """Describe one value read from device status."""

    value_fn: Callable[[StatusResponse], str | int | float]
    attributes_fn: Callable[[StatusResponse], Mapping[str, Any]] | None = None


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
        key="pcm_encryption",
        translation_key="pcm_encryption",
        device_class=SensorDeviceClass.ENUM,
        options=["disabled", "enabled", "unknown"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_pcm_encryption_state,
    ),
    StreamLineSensorDescription(
        key="ota_status",
        translation_key="ota_status",
        device_class=SensorDeviceClass.ENUM,
        options=[*OTA_PHASES, "unknown"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_ota_phase,
        attributes_fn=lambda status: {
            "message": status.ota.message or None,
            "last_attempt": status.diagnostics.last_ota or None,
            "rollback_available": status.ota.rollback_available,
            "rollback_version": status.ota.rollback_version or None,
        },
    ),
    StreamLineSensorDescription(
        key="reset_reason",
        translation_key="reset_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.diagnostics.reset_reason,
        attributes_fn=lambda status: {
            "last_setup_fallback": status.diagnostics.last_fallback or None,
        },
    ),
    StreamLineSensorDescription(
        key="network_errors",
        translation_key="network_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.metrics.network_errors_total,
    ),
    StreamLineSensorDescription(
        key="send_stalls",
        translation_key="send_stalls",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.metrics.send_stalls_total,
    ),
    StreamLineSensorDescription(
        key="longest_send_stall",
        translation_key="longest_send_stall",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.metrics.longest_send_stall_ms,
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
        return self.entity_description.value_fn(self.coordinator.status)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return stable diagnostic details when this sensor defines them."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.status)
