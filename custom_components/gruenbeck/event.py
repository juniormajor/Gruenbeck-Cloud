"""Event entities: regeneration start/end and device errors."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    EVENT_ERROR_RAISED,
    EVENT_ERROR_RESOLVED,
    EVENT_REGENERATION_FINISHED,
    EVENT_REGENERATION_STARTED,
)
from .coordinator import GruenbeckConfigEntry, GruenbeckDeviceCoordinator
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 0

REGENERATION = EventEntityDescription(
    key="regeneration",
    translation_key="regeneration",
    event_types=[EVENT_REGENERATION_STARTED, EVENT_REGENERATION_FINISHED],
)
DEVICE_ERROR = EventEntityDescription(
    key="device_error",
    translation_key="device_error",
    event_types=[EVENT_ERROR_RAISED, EVENT_ERROR_RESOLVED],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up event entities."""
    entities: list[EventEntity] = []
    for coordinator in coordinators(entry):
        entities.append(GruenbeckRegenerationEvent(coordinator, REGENERATION))
        entities.append(GruenbeckErrorEvent(coordinator, DEVICE_ERROR))
    async_add_entities(entities)


class GruenbeckRegenerationEvent(GruenbeckEntity, EventEntity):
    """Fires when a regeneration starts or ends (from the regeneration step)."""

    def __init__(self, coordinator: GruenbeckDeviceCoordinator, description) -> None:
        """Remember the last regeneration step."""
        super().__init__(coordinator, description)
        self._last_step: int | None = coordinator.device.realtime("regeneration_step")

    @callback
    def _handle_coordinator_update(self) -> None:
        step = self.coordinator.device.realtime("regeneration_step")
        last = self._last_step
        if step is not None and last is not None and (step == 0) != (last == 0):
            if step != 0:
                self._trigger_event(EVENT_REGENERATION_STARTED, {"step": step})
            else:
                self._trigger_event(
                    EVENT_REGENERATION_FINISHED,
                    {
                        "regeneration_counter": self.coordinator.device.realtime(
                            "regeneration_counter"
                        )
                    },
                )
        if step is not None:
            self._last_step = step
        super()._handle_coordinator_update()


class GruenbeckErrorEvent(GruenbeckEntity, EventEntity):
    """Fires for new and newly resolved entries of the device error log."""

    @callback
    def _handle_coordinator_update(self) -> None:
        memory = self.coordinator.memory
        errors = self.coordinator.device.errors
        open_now = {err.key for err in errors if not err.is_resolved}
        if memory.known_errors is None:
            # First run: remember the current log without firing events.
            memory.known_errors = sorted(open_now)
            self.coordinator.request_save()
        else:
            known = set(memory.known_errors)
            for err in errors:
                if err.key in open_now and err.key not in known:
                    self._trigger_event(EVENT_ERROR_RAISED, err.as_dict())
                elif err.key in known and err.key not in open_now:
                    self._trigger_event(EVENT_ERROR_RESOLVED, err.as_dict())
            if open_now != known:
                memory.known_errors = sorted(open_now)
                self.coordinator.request_save()
        super()._handle_coordinator_update()
