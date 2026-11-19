"""Time entities (regeneration schedule) of the Grünbeck integration."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GruenbeckConfigEntry
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 1

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

TIMES: tuple[TimeEntityDescription, ...] = tuple(
    TimeEntityDescription(
        key=f"regeneration_time_{day}_{slot}",
        translation_key=f"regeneration_time_{day}_{slot}",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    )
    for day in DAYS
    for slot in (1, 2, 3)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up time entities."""
    async_add_entities(
        GruenbeckTime(coordinator, description)
        for coordinator in coordinators(entry)
        for description in TIMES
        if coordinator.device.has_parameter(description.key)
    )


class GruenbeckTime(GruenbeckEntity, TimeEntity):
    """Regeneration time slot; unknown means "not set" (--:--)."""

    @property
    def native_value(self) -> time | None:
        """Return the slot time."""
        return self.coordinator.device.parameter(self.entity_description.key)

    async def async_set_value(self, value: time) -> None:
        """Change the slot time."""
        await self.coordinator.async_set_parameter(self.entity_description.key, value)
