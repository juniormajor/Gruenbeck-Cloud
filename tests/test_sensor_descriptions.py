"""Sensor descriptions: state classes that give long-term statistics."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.gruenbeck.sensor import SENSORS

# Sensors that are fixed texts, dates, enums or remaining times keep no state class.
WITHOUT_STATE_CLASS = {
    "next_regeneration",
    "startup",
    "last_service",
    "salt_range",
    "regeneration_step",
    "water_last_day",
    "salt_last_day",
    "last_cloud_update",
    "last_realtime_update",
    "next_service",
    "regeneration_remaining_time",
    "last_regeneration_exchanger",
    "last_regeneration_exchanger_2",
    "step_indication_regeneration_valve",
    "step_indication_regeneration_valve_2",
}

TOTAL_ONLY = {SensorDeviceClass.VOLUME, SensorDeviceClass.WATER}


def test_numeric_sensors_have_state_class() -> None:
    """Every sensor with a unit outside the exception list gets statistics."""
    missing = [
        d.key
        for d in SENSORS
        if d.state_class is None and d.key not in WITHOUT_STATE_CLASS
    ]
    assert missing == []


def test_measurement_not_on_total_device_classes() -> None:
    """Volume and water must be totals; stored volumes use volume_storage."""
    wrong = [
        d.key
        for d in SENSORS
        if d.state_class is SensorStateClass.MEASUREMENT and d.device_class in TOTAL_ONLY
    ]
    assert wrong == []
