"""Text entities (installer contact) of the Grünbeck integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GruenbeckConfigEntry
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 1

TEXTS: tuple[TextEntityDescription, ...] = tuple(
    TextEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        native_max=100,
    )
    for key in ("installer_name", "installer_phone", "installer_email")
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up text entities."""
    async_add_entities(
        GruenbeckText(coordinator, description)
        for coordinator in coordinators(entry)
        for description in TEXTS
        if coordinator.device.has_parameter(description.key)
    )


class GruenbeckText(GruenbeckEntity, TextEntity):
    """Installer contact parameter."""

    @property
    def native_value(self) -> str | None:
        """Return the parameter value."""
        return self.coordinator.device.parameter(self.entity_description.key)

    async def async_set_value(self, value: str) -> None:
        """Change the parameter."""
        await self.coordinator.async_set_parameter(self.entity_description.key, value)
