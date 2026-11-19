"""Buttons of the Grünbeck integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GruenbeckConfigEntry, GruenbeckDeviceCoordinator
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 1


async def _salt_refilled(c: GruenbeckDeviceCoordinator) -> None:
    current = c.memory.salt_level_kg or 0.0
    c.set_salt_level(current + c.memory.salt_refill_kg)


async def _refresh(c: GruenbeckDeviceCoordinator) -> None:
    realtime = c.config_entry.runtime_data.realtime
    if realtime is not None:
        await realtime.async_refresh()
    await c.async_request_refresh()


@dataclass(frozen=True, kw_only=True)
class GruenbeckButtonDescription(ButtonEntityDescription):
    """Describes a Grünbeck button."""

    press_fn: Callable[[GruenbeckDeviceCoordinator], Awaitable[None]]
    local: bool = False


BUTTONS: tuple[GruenbeckButtonDescription, ...] = (
    GruenbeckButtonDescription(
        key="regenerate",
        translation_key="regenerate",
        press_fn=lambda c: c.async_regenerate(),
    ),
    GruenbeckButtonDescription(
        key="salt_refilled",
        translation_key="salt_refilled",
        press_fn=_salt_refilled,
        local=True,
    ),
    GruenbeckButtonDescription(
        key="refresh",
        translation_key="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=_refresh,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities(
        GruenbeckButton(coordinator, description)
        for coordinator in coordinators(entry)
        for description in BUTTONS
    )


class GruenbeckButton(GruenbeckEntity, ButtonEntity):
    """Action on a Grünbeck softener."""

    entity_description: GruenbeckButtonDescription

    @property
    def available(self) -> bool:
        """Local buttons work without the cloud."""
        return self.entity_description.local or super().available

    async def async_press(self) -> None:
        """Run the action."""
        await self.entity_description.press_fn(self.coordinator)
