"""Selects (enumerated device parameters) of the Grünbeck integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    LANGUAGES,
    LED_MODES,
    OPERATION_MODES,
    REGENERATION_MODES,
    WATER_HARDNESS_UNITS,
)
from .coordinator import GruenbeckConfigEntry
from .entity import GruenbeckEntity, coordinators
from .time import DAYS

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class GruenbeckSelectDescription(SelectEntityDescription):
    """Describes a parameter select with its code table."""

    codes: dict[int, str]


def _describe(
    key: str, codes: dict[int, str], *, config: bool = True, enabled: bool = True
) -> GruenbeckSelectDescription:
    return GruenbeckSelectDescription(
        key=key,
        translation_key=key,
        options=list(codes.values()),
        codes=codes,
        entity_category=EntityCategory.CONFIG if config else None,
        entity_registry_enabled_default=enabled,
    )


SELECTS: tuple[GruenbeckSelectDescription, ...] = (
    _describe("regeneration_mode", REGENERATION_MODES),
    _describe("water_hardness_unit", WATER_HARDNESS_UNITS),
    _describe("mode", OPERATION_MODES, config=False),
    _describe("led_ring_mode", LED_MODES, enabled=False),
    _describe("language", LANGUAGES, enabled=False),
    *(
        _describe(f"mode_individual_{day}", OPERATION_MODES, config=False, enabled=False)
        for day in DAYS
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    async_add_entities(
        GruenbeckSelect(coordinator, description)
        for coordinator in coordinators(entry)
        for description in SELECTS
        if coordinator.device.has_parameter(description.key)
    )


class GruenbeckSelect(GruenbeckEntity, SelectEntity):
    """Enumerated device parameter."""

    entity_description: GruenbeckSelectDescription

    @property
    def current_option(self) -> str | None:
        """Return the option for the current code; unknown codes are None."""
        code = self.coordinator.device.parameter(self.entity_description.key)
        return self.entity_description.codes.get(code)

    async def async_select_option(self, option: str) -> None:
        """Write the code of the chosen option."""
        code = next(code for code, name in self.entity_description.codes.items() if name == option)
        await self.coordinator.async_set_parameter(self.entity_description.key, code)
