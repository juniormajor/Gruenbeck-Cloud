"""Base entity of the Grünbeck integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GruenbeckConfigEntry, GruenbeckDeviceCoordinator


class GruenbeckEntity(CoordinatorEntity[GruenbeckDeviceCoordinator]):
    """Entity bound to one softener."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: GruenbeckDeviceCoordinator, description: EntityDescription
    ) -> None:
        """Initialise from a description; unique id is ``<serial>_<key>``."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}_{description.key}"
        device = coordinator.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer=MANUFACTURER,
            name=device.name,
            model=device.series,
            serial_number=coordinator.serial,
            hw_version=device.info_value("hardware_version"),
            sw_version=device.info_value("software_version"),
        )


def coordinators(entry: GruenbeckConfigEntry) -> list[GruenbeckDeviceCoordinator]:
    """Return all device coordinators of an entry."""
    return list(entry.runtime_data.coordinators.values())
