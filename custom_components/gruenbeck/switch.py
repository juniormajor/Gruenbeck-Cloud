"""Switches (device parameters) of the Grünbeck integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GruenbeckConfigEntry
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 1

_ENABLED = ("dlst", "buzzer", "push_notification", "email_notification")
_DISABLED = (
    "led_ring_flash_on_signal",
    "ntp_sync",
    "fault_signal_contact",
    "knx",
    "nominal_flow_monitoring",
    "disinfection_monitoring",
)

SWITCHES: tuple[SwitchEntityDescription, ...] = tuple(
    SwitchEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=key in _ENABLED,
    )
    for key in (*_ENABLED, *_DISABLED)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up parameter switches present in the device's parameter set."""
    async_add_entities(
        GruenbeckSwitch(coordinator, description)
        for coordinator in coordinators(entry)
        for description in SWITCHES
        if coordinator.device.has_parameter(description.key)
    )


class GruenbeckSwitch(GruenbeckEntity, SwitchEntity):
    """Boolean device parameter."""

    @property
    def is_on(self) -> bool | None:
        """Return the parameter value."""
        return self.coordinator.device.parameter(self.entity_description.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the parameter."""
        await self.coordinator.async_set_parameter(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the parameter."""
        await self.coordinator.async_set_parameter(self.entity_description.key, False)
