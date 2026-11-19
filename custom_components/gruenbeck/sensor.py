"""Sensors of the Grünbeck integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfMass,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import REGENERATION_STEPS, UNIT_DH, UNIT_L_H, UNIT_M3_X_DH
from .coordinator import GruenbeckConfigEntry, GruenbeckDeviceCoordinator
from .entity import GruenbeckEntity, coordinators

PARALLEL_UPDATES = 0

Value = StateType | date | datetime


@dataclass(frozen=True, kw_only=True)
class GruenbeckSensorDescription(SensorEntityDescription):
    """Describes a Grünbeck sensor."""

    value_fn: Callable[[GruenbeckDeviceCoordinator], Value]
    attr_fn: Callable[[GruenbeckDeviceCoordinator], Mapping[str, Any] | None] = lambda _: None


def _rt(key: str) -> Callable[[GruenbeckDeviceCoordinator], Value]:
    return lambda c: c.device.realtime(key)


def _time_str(key: str) -> Callable[[GruenbeckDeviceCoordinator], Value]:
    def _value(c: GruenbeckDeviceCoordinator) -> Value:
        value = c.device.realtime(key)
        return value.strftime("%H:%M") if isinstance(value, time) else None

    return _value


def _hardness(param: str, info: str) -> Callable[[GruenbeckDeviceCoordinator], Value]:
    def _value(c: GruenbeckDeviceCoordinator) -> Value:
        value = c.device.parameter(param)
        return value if value is not None else c.device.info_value(info)

    return _value


def _salt_range(c: GruenbeckDeviceCoordinator) -> Value:
    value = c.device.realtime("salt_range")
    # The SD18 reports 999 when it does not calculate the range.
    return value if isinstance(value, int) and value < 999 else None


def _regeneration_step(c: GruenbeckDeviceCoordinator) -> Value:
    return REGENERATION_STEPS.get(c.device.realtime("regeneration_step"))


def _daily(kind: str) -> Callable[[GruenbeckDeviceCoordinator], Value]:
    def _value(c: GruenbeckDeviceCoordinator) -> Value:
        today = c.device.cloud_updated
        entries = getattr(c.device, kind)
        if not entries:
            return None
        if today is not None:
            finished = [e for e in entries if e.day < today.astimezone(c.device.time_zone).date()]
            if finished:
                return finished[-1].value
        return None

    return _value


def _daily_attr(kind: str) -> Callable[[GruenbeckDeviceCoordinator], Mapping[str, Any]]:
    def _attrs(c: GruenbeckDeviceCoordinator) -> Mapping[str, Any]:
        return {
            "daily_usage": [
                {"date": e.day.isoformat(), "value": e.value} for e in getattr(c.device, kind)[-14:]
            ]
        }

    return _attrs


SENSORS: tuple[GruenbeckSensorDescription, ...] = (
    GruenbeckSensorDescription(
        key="next_regeneration",
        translation_key="next_regeneration",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.device.info_value("next_regeneration"),
    ),
    GruenbeckSensorDescription(
        key="startup",
        translation_key="startup",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.device.info_value("startup"),
    ),
    GruenbeckSensorDescription(
        key="last_service",
        translation_key="last_service",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.device.info_value("last_service"),
    ),
    GruenbeckSensorDescription(
        key="raw_water",
        translation_key="raw_water",
        native_unit_of_measurement=UNIT_DH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_hardness("raw_water_hardness", "raw_water"),
    ),
    GruenbeckSensorDescription(
        key="soft_water",
        translation_key="soft_water",
        native_unit_of_measurement=UNIT_DH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_hardness("soft_water_hardness", "soft_water"),
    ),
    GruenbeckSensorDescription(
        key="soft_water_quantity",
        translation_key="soft_water_quantity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.memory.soft_water_total,
        attr_fn=_daily_attr("water"),
    ),
    GruenbeckSensorDescription(
        key="regeneration_counter",
        translation_key="regeneration_counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_rt("regeneration_counter"),
    ),
    GruenbeckSensorDescription(
        key="current_flow_rate",
        translation_key="current_flow_rate",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_rt("current_flow_rate"),
    ),
    GruenbeckSensorDescription(
        key="remaining_capacity_volume",
        translation_key="remaining_capacity_volume",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.VOLUME,
        value_fn=_rt("remaining_capacity_volume"),
    ),
    GruenbeckSensorDescription(
        key="remaining_capacity_percentage",
        translation_key="remaining_capacity_percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_rt("remaining_capacity_percentage"),
    ),
    GruenbeckSensorDescription(
        key="salt_range",
        translation_key="salt_range",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=_salt_range,
    ),
    GruenbeckSensorDescription(
        key="salt_consumption",
        translation_key="salt_consumption",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_rt("salt_consumption"),
        attr_fn=_daily_attr("salt"),
    ),
    GruenbeckSensorDescription(
        key="regeneration_step",
        translation_key="regeneration_step",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(REGENERATION_STEPS.values())),
        value_fn=_regeneration_step,
    ),
    # Additions (R3)
    GruenbeckSensorDescription(
        key="salt_level",
        translation_key="salt_level",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: c.memory.salt_level_kg,
    ),
    GruenbeckSensorDescription(
        key="water_last_day",
        translation_key="water_last_day",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=_daily("water"),
    ),
    GruenbeckSensorDescription(
        key="salt_last_day",
        translation_key="salt_last_day",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        value_fn=_daily("salt"),
    ),
    GruenbeckSensorDescription(
        key="last_cloud_update",
        translation_key="last_cloud_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.device.cloud_updated,
    ),
    GruenbeckSensorDescription(
        key="last_realtime_update",
        translation_key="last_realtime_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.device.realtime_updated,
    ),
    # Disabled by default, as in hagruenbeck_cloud
    GruenbeckSensorDescription(
        key="next_service",
        translation_key="next_service",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTime.DAYS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_rt("next_service"),
    ),
    GruenbeckSensorDescription(
        key="regeneration_remaining_time",
        translation_key="regeneration_remaining_time",
        entity_registry_enabled_default=False,
        value_fn=_rt("regeneration_remaining_time"),
    ),
    GruenbeckSensorDescription(
        key="soft_water_quantity_2",
        translation_key="soft_water_quantity_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_rt("soft_water_quantity_2"),
    ),
    GruenbeckSensorDescription(
        key="current_flow_rate_2",
        translation_key="current_flow_rate_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        value_fn=_rt("current_flow_rate_2"),
    ),
    GruenbeckSensorDescription(
        key="remaining_capacity_volume_2",
        translation_key="remaining_capacity_volume_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.VOLUME,
        value_fn=_rt("remaining_capacity_volume_2"),
    ),
    GruenbeckSensorDescription(
        key="remaining_capacity_percentage_2",
        translation_key="remaining_capacity_percentage_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_rt("remaining_capacity_percentage_2"),
    ),
    GruenbeckSensorDescription(
        key="make_up_water_volume",
        translation_key="make_up_water_volume",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        value_fn=_rt("make_up_water_volume"),
    ),
    GruenbeckSensorDescription(
        key="exhausted_percentage",
        translation_key="exhausted_percentage",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_rt("exhausted_percentage"),
    ),
    GruenbeckSensorDescription(
        key="actual_value_soft_water_hardness",
        translation_key="actual_value_soft_water_hardness",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UNIT_DH,
        value_fn=_rt("actual_value_soft_water_hardness"),
    ),
    GruenbeckSensorDescription(
        key="capacity_figure",
        translation_key="capacity_figure",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UNIT_M3_X_DH,
        value_fn=_rt("capacity_figure"),
    ),
    GruenbeckSensorDescription(
        key="flow_rate_peak_value",
        translation_key="flow_rate_peak_value",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        value_fn=_rt("flow_rate_peak_value"),
    ),
    GruenbeckSensorDescription(
        key="exchanger_peak_value",
        translation_key="exchanger_peak_value",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        value_fn=_rt("exchanger_peak_value"),
    ),
    GruenbeckSensorDescription(
        key="exchanger_peak_value_2",
        translation_key="exchanger_peak_value_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        value_fn=_rt("exchanger_peak_value_2"),
    ),
    GruenbeckSensorDescription(
        key="last_regeneration_exchanger",
        translation_key="last_regeneration_exchanger",
        entity_registry_enabled_default=False,
        value_fn=_time_str("last_regeneration_exchanger"),
    ),
    GruenbeckSensorDescription(
        key="last_regeneration_exchanger_2",
        translation_key="last_regeneration_exchanger_2",
        entity_registry_enabled_default=False,
        value_fn=_time_str("last_regeneration_exchanger_2"),
    ),
    GruenbeckSensorDescription(
        key="regeneration_flow_rate_exchanger",
        translation_key="regeneration_flow_rate_exchanger",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UNIT_L_H,
        value_fn=_rt("regeneration_flow_rate_exchanger"),
    ),
    GruenbeckSensorDescription(
        key="regeneration_flow_rate_exchanger_2",
        translation_key="regeneration_flow_rate_exchanger_2",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UNIT_L_H,
        value_fn=_rt("regeneration_flow_rate_exchanger_2"),
    ),
    GruenbeckSensorDescription(
        key="blending_flow_rate",
        translation_key="blending_flow_rate",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        value_fn=_rt("blending_flow_rate"),
    ),
    GruenbeckSensorDescription(
        key="step_indication_regeneration_valve",
        translation_key="step_indication_regeneration_valve",
        entity_registry_enabled_default=False,
        value_fn=_rt("step_indication_regeneration_valve"),
    ),
    GruenbeckSensorDescription(
        key="step_indication_regeneration_valve_2",
        translation_key="step_indication_regeneration_valve_2",
        entity_registry_enabled_default=False,
        value_fn=_rt("step_indication_regeneration_valve_2"),
    ),
    GruenbeckSensorDescription(
        key="current_chlorine",
        translation_key="current_chlorine",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        device_class=SensorDeviceClass.CURRENT,
        value_fn=_rt("current_chlorine"),
    ),
    GruenbeckSensorDescription(
        key="remaining_amount_of_water",
        translation_key="remaining_amount_of_water",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.VOLUME,
        value_fn=_rt("remaining_amount_of_water"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GruenbeckConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for all devices of the account."""
    async_add_entities(
        GruenbeckSensor(coordinator, description)
        for coordinator in coordinators(entry)
        for description in SENSORS
    )


class GruenbeckSensor(GruenbeckEntity, SensorEntity):
    """Sensor of a Grünbeck softener."""

    entity_description: GruenbeckSensorDescription

    @property
    def native_value(self) -> Value:
        """Return the parsed value or None."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra attributes."""
        return self.entity_description.attr_fn(self.coordinator)
