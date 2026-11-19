"""Binary sensors of the Grünbeck integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GruenbeckConfigEntry, GruenbeckDeviceCoordinator
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GruenbeckBinaryDescription(BinarySensorEntityDescription):
    """Describes a Grünbeck binary sensor."""

    value_fn: Callable[[GruenbeckDeviceCoordinator], bool | None]
    attr_fn: Callable[[GruenbeckDeviceCoordinator], Mapping[str, Any] | None] = lambda _: None
    always_available: bool = False


def _regenerating(c: GruenbeckDeviceCoordinator) -> bool | None:
    step = c.device.realtime("regeneration_step")
    return None if step is None else step != 0


def _realtime_connected(c: GruenbeckDeviceCoordinator) -> bool | None:
    realtime = c.config_entry.runtime_data.realtime
    return None if realtime is None else realtime.connected


BINARY_SENSORS: tuple[GruenbeckBinaryDescription, ...] = (
    GruenbeckBinaryDescription(
        key="has_error",
        translation_key="has_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.device.info_value("has_error"),
        attr_fn=lambda c: {"errors": [err.as_dict() for err in c.device.errors[:20]]},
    ),
    GruenbeckBinaryDescription(
        key="regeneration_active",
        translation_key="regeneration_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_regenerating,
    ),
    GruenbeckBinaryDescription(
        key="cloud_connection",
        translation_key="cloud_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.cloud_ok,
        attr_fn=lambda c: {
            "last_error": c.last_error,
            "failures": c.failures,
            "poll_interval_s": (c.update_interval.total_seconds() if c.update_interval else None),
        },
        always_available=True,
    ),
    GruenbeckBinaryDescription(
        key="realtime_connection",
        translation_key="realtime_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_realtime_connected,
        always_available=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    entities: list[GruenbeckBinarySensor] = []
    for coordinator in coordinators(entry):
        for description in BINARY_SENSORS:
            if description.key == "realtime_connection" and entry.runtime_data.realtime is None:
                continue
            entities.append(GruenbeckBinarySensor(coordinator, description))
    async_add_entities(entities)


class GruenbeckBinarySensor(GruenbeckEntity, BinarySensorEntity):
    """Binary sensor of a Grünbeck softener."""

    entity_description: GruenbeckBinaryDescription

    async def async_added_to_hass(self) -> None:
        """Also follow realtime connection changes."""
        await super().async_added_to_hass()
        realtime = self.coordinator.config_entry.runtime_data.realtime
        if self.entity_description.key == "realtime_connection" and realtime:
            self.async_on_remove(realtime.register_state(lambda _: self.async_write_ha_state()))

    @property
    def available(self) -> bool:
        """Connection sensors stay available to show the outage."""
        return self.entity_description.always_available or super().available

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra attributes."""
        return self.entity_description.attr_fn(self.coordinator)
