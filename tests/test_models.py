"""Device model built from fixture payloads."""

from __future__ import annotations

from datetime import time

from custom_components.gruenbeck.api.models import (
    GruenbeckDevice,
    encode_parameter,
)
from custom_components.gruenbeck.api.realtime import device_updates, split_messages

from .conftest import REALTIME, load


def _device() -> GruenbeckDevice:
    device = GruenbeckDevice.from_list_entry(load("get_devices.txt")[0])
    device.update_info(load("get_device_infos.txt"))
    device.update_parameters(load("get_device_infos_parameters.txt"))
    return device


def test_info_and_parameters() -> None:
    """Values from the fixtures parse."""
    device = _device()
    assert device.serial_number == "6ZF9Z5KAA2"
    assert device.info_value("next_regeneration").isoformat() == "2024-01-10T03:38:00+01:00"
    assert device.parameter("mode") == 2
    assert device.parameter("regeneration_time_monday_1") == time(7, 0)
    assert device.parameter("regeneration_time_saturday_1") is None
    assert device.parameter("soft_water_meter_pulse_rate") == 0.0043
    assert [e.value for e in device.water] == [125, 226, 123]
    assert len(device.errors) == 3
    assert device.errors[0].is_resolved is False
    assert not device.report.failures


def test_changed_payload_does_not_break() -> None:
    """New, missing and malformed fields only affect themselves."""
    device = _device()
    device.update_info({"nextRegeneration": "tomorrow", "limeRetained": 12})
    device.update_parameters({**load("get_device_infos_parameters.txt"), "pmode": "x"})
    assert device.info_value("next_regeneration") is None
    assert device.parameter("mode") is None
    assert device.parameter("raw_water_hardness") == 25
    assert set(device.report.failures) == {"info.next_regeneration", "parameter.mode"}


def test_encode_parameter() -> None:
    """Parameters are encoded to the cloud's JSON keys and types."""
    assert encode_parameter("mode", 3.0) == ("pmode", 3)
    assert encode_parameter("regeneration_time_friday_2", time(1, 30)) == ("pregfr2", "01:30")
    assert encode_parameter("buzzer", 1) == ("pbuzzer", True)


def test_signalr_frames() -> None:
    """Records are split at the record separator and filtered by target."""
    frame = (
        '{"type":6}\x1e'
        '{"type":1,"target":"SendMessageToDevice","arguments":['
        + __import__("json").dumps(REALTIME)
        + "]}\x1e{broken\x1e"
    )
    records = split_messages(frame)
    assert len(records) == 2
    updates = [u for r in records for u in device_updates(r)]
    assert updates[0]["mcountwater1"] == 123456
