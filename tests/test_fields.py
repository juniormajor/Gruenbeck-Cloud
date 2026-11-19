"""Tolerant parsing (R4)."""

from __future__ import annotations

from datetime import UTC, date, time, timedelta, timezone

import pytest

from custom_components.gruenbeck.api.fields import (
    Field,
    FieldReport,
    encode_value,
    parse_datetime,
    parse_field,
    parse_time,
)

TZ = timezone(timedelta(hours=1))


@pytest.mark.parametrize(
    "raw",
    [
        "2026-11-18T04:26:12",  # issue p0l0/hagruenbeck_cloud#91: no fraction
        "2026-11-18T04:26:12.655",
        "2026-11-18T04:26:12.6550000",  # seven digits
        "2026-11-18T03:26:12Z",
        "2026-11-18T04:26:12+01:00",
    ],
)
def test_datetime_variants(raw: str) -> None:
    """All timestamp variants parse to the same minute."""
    value = parse_datetime(raw, TZ)
    assert value.astimezone(UTC).replace(second=0, microsecond=0).isoformat() == (
        "2026-11-18T03:26:00+00:00"
    )


def test_time_not_set() -> None:
    """``--:--`` means an empty slot."""
    assert parse_time("--:--") is None
    assert parse_time("07:00") == time(7, 0)
    assert encode_value("time", None) is None
    assert encode_value("time", time(2, 5)) == "02:05"


def test_unparsable_value_is_reported_not_raised() -> None:
    """A broken value becomes None and lands in the report."""
    report = FieldReport()
    assert parse_field(Field("x", "int"), {"x": "abc"}, report, name="x") is None
    assert "x" in report.failures
    assert parse_field(Field("x", "int"), {"x": "12"}, report, name="x") == 12
    assert "x" not in report.failures


def test_missing_and_null() -> None:
    """Missing keys and nulls are None without a report."""
    report = FieldReport()
    assert parse_field(Field("x", "date"), {}, report) is None
    assert parse_field(Field("x", "date"), {"x": None}, report) is None
    assert parse_field(Field("x", "date"), {"x": "2022.05.20"}, report) == date(2022, 5, 20)
    assert not report.failures


def test_bool_and_float_forms() -> None:
    """Numeric strings and 0/1 are accepted."""
    assert parse_field(Field("x", "bool"), {"x": 1}) is True
    assert parse_field(Field("x", "float"), {"x": "0,5"}) == 0.5
    assert parse_field(Field("x", "int"), {"x": 3.0}) == 3
    assert parse_field(Field("x", "int"), {"x": True}) is None
