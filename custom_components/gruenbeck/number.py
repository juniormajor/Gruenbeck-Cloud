"""Numbers (device parameters and local settings) of the Grünbeck integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfMass,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UNIT_DH, UNIT_L_IMP, UNIT_M3_X_DH, UNIT_MA_MIN
from .coordinator import GruenbeckConfigEntry
from .entity import GruenbeckEntity, coordinators
from .time import DAYS

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class GruenbeckNumberDescription(NumberEntityDescription):
    """Describes a numeric device parameter."""


def _n(
    key: str,
    unit: str | None,
    lo: float,
    hi: float,
    step: float = 1,
    *,
    device_class: NumberDeviceClass | None = None,
    enabled: bool = False,
    mode: NumberMode = NumberMode.BOX,
) -> GruenbeckNumberDescription:
    return GruenbeckNumberDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        native_min_value=lo,
        native_max_value=hi,
        native_step=step,
        device_class=device_class,
        mode=mode,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=enabled,
    )


NUMBERS: tuple[GruenbeckNumberDescription, ...] = (
    _n("raw_water_hardness", UNIT_DH, 0, 100, enabled=True),
    _n("soft_water_hardness", UNIT_DH, 0, 100, enabled=True),
    _n("maintenance_interval", UnitOfTime.DAYS, 1, 365, mode=NumberMode.SLIDER),
    _n("led_ring_brightness", PERCENTAGE, 1, 100, mode=NumberMode.SLIDER),
    _n("residual_capacity_limit", PERCENTAGE, 1, 100, mode=NumberMode.SLIDER),
    _n(
        "current_setpoint",
        UnitOfElectricCurrent.MILLIAMPERE,
        0,
        5000,
        device_class=NumberDeviceClass.CURRENT,
    ),
    _n("charge", UNIT_MA_MIN, 0, 10000),
    _n("interval_forced_regeneration", UnitOfTime.DAYS, 1, 365, mode=NumberMode.SLIDER),
    *(
        _n(key, UnitOfFrequency.HERTZ, 0, 1000, device_class=NumberDeviceClass.FREQUENCY)
        for key in (
            "end_frequency_regeneration_valve",
            "end_frequency_regeneration_valve_2",
            "end_frequency_blending_valve",
        )
    ),
    _n(
        "treatment_volume",
        UnitOfVolume.CUBIC_METERS,
        0,
        10000,
        device_class=NumberDeviceClass.WATER,
    ),
    *(
        _n(key, UNIT_L_IMP, 0, 10, 0.0001)
        for key in (
            "soft_water_meter_pulse_rate",
            "blending_water_meter_pulse_rate",
            "regeneration_water_meter_pulse_rate",
        )
    ),
    *(_n(f"capacity_figure_{day}", UNIT_M3_X_DH, 0, 100) for day in DAYS),
    _n(
        "nominal_flow_rate",
        UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        0,
        20,
        0.1,
        device_class=NumberDeviceClass.VOLUME_FLOW_RATE,
    ),
    _n("regeneration_monitoring_time", UnitOfTime.MINUTES, 0, 999),
    _n("salting_monitoring_time", UnitOfTime.MINUTES, 0, 999),
    _n("slow_rinse", UnitOfTime.MINUTES, 0, 999, 0.1),
    _n("backwash", UnitOfVolume.LITERS, 0, 999, device_class=NumberDeviceClass.VOLUME),
    _n("washing_out", UnitOfVolume.LITERS, 0, 999, device_class=NumberDeviceClass.VOLUME),
    *(
        _n(key, UnitOfVolume.LITERS, 0, 100, 0.01, device_class=NumberDeviceClass.VOLUME)
        for key in (
            "minimum_filling_volume_smallest_cap",
            "maximum_filling_volume_smallest_cap",
            "minimum_filling_volume_largest_cap",
            "maximum_filling_volume_largest_cap",
        )
    ),
    _n("longest_switch_on_time_chlorine_cell", UnitOfTime.MINUTES, 0, 999),
    _n("maximum_remaining_time_regeneration", UnitOfTime.MINUTES, 0, 999),
)

SALT_REFILL = NumberEntityDescription(
    key="salt_refill_amount",
    translation_key="salt_refill_amount",
    native_unit_of_measurement=UnitOfMass.KILOGRAMS,
    device_class=NumberDeviceClass.WEIGHT,
    native_min_value=0,
    native_max_value=200,
    native_step=0.5,
    mode=NumberMode.BOX,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers."""
    entities: list[NumberEntity] = []
    for coordinator in coordinators(entry):
        entities.extend(
            GruenbeckParameterNumber(coordinator, description)
            for description in NUMBERS
            if coordinator.device.has_parameter(description.key)
        )
        entities.append(GruenbeckSaltRefillNumber(coordinator, SALT_REFILL))
    async_add_entities(entities)


class GruenbeckParameterNumber(GruenbeckEntity, NumberEntity):
    """Numeric device parameter."""

    @property
    def native_value(self) -> float | None:
        """Return the parameter value."""
        return self.coordinator.device.parameter(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Write the parameter."""
        await self.coordinator.async_set_parameter(self.entity_description.key, value)


class GruenbeckSaltRefillNumber(GruenbeckEntity, NumberEntity):
    """Amount of salt added per refill; local setting, not sent to the cloud."""

    @property
    def available(self) -> bool:
        """Local setting is always available."""
        return True

    @property
    def native_value(self) -> float:
        """Return the configured refill amount."""
        return self.coordinator.memory.salt_refill_kg

    async def async_set_native_value(self, value: float) -> None:
        """Store the refill amount."""
        self.coordinator.memory.salt_refill_kg = float(value)
        self.coordinator.request_save()
        self.async_write_ha_state()
