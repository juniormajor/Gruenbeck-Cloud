"""Tolerant field parsing for Grünbeck cloud payloads.

Every value is parsed on its own. A value that is missing or does not match
the expected type becomes ``None`` and is reported once through
``FieldReport``; it never aborts the parsing of the remaining payload. This is
the main difference to earlier implementations, where one changed date format
(for example a timestamp without fractional seconds) took the whole
integration down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
import logging
import re
from typing import Any, Final, Literal

_LOGGER = logging.getLogger(__name__)

Kind = Literal["int", "float", "bool", "str", "time", "date", "datetime", "tz"]

_TIME_RE: Final = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_TZ_RE: Final = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
_DATE_FORMATS: Final = ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y")


class ParseError(ValueError):
    """Raised internally when a raw value cannot be converted."""


def parse_int(raw: Any) -> int:
    """Parse an integer, accepting integral floats and numeric strings."""
    if isinstance(raw, bool):
        raise ParseError(f"boolean {raw!r} is not an integer")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str):
        try:
            number = float(raw.strip().replace(",", "."))
        except ValueError as err:
            raise ParseError(f"{raw!r} is not numeric") from err
        if number.is_integer():
            return int(number)
    raise ParseError(f"{raw!r} is not an integer")


def parse_float(raw: Any) -> float:
    """Parse a float, accepting numeric strings with comma or point."""
    if isinstance(raw, bool):
        raise ParseError(f"boolean {raw!r} is not a number")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip().replace(",", "."))
        except ValueError as err:
            raise ParseError(f"{raw!r} is not numeric") from err
    raise ParseError(f"{raw!r} is not a number")


def parse_bool(raw: Any) -> bool:
    """Parse a boolean from bool, 0/1 or common string forms."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str) and raw.strip().lower() in ("true", "false", "1", "0"):
        return raw.strip().lower() in ("true", "1")
    raise ParseError(f"{raw!r} is not a boolean")


def parse_time(raw: Any) -> time | None:
    """Parse ``HH:MM`` or ``HH:MM:SS``; ``--:--`` means "not set"."""
    if not isinstance(raw, str):
        raise ParseError(f"{raw!r} is not a time string")
    value = raw.strip()
    if not value or value.startswith("--"):
        return None
    match = _TIME_RE.match(value)
    if not match:
        raise ParseError(f"{raw!r} is not a time")
    hour, minute, second = int(match[1]), int(match[2]), int(match[3] or 0)
    if hour == 24 and minute == 0:
        hour = 0
    try:
        return time(hour, minute, second)
    except ValueError as err:
        raise ParseError(f"{raw!r} is not a valid time") from err


def parse_date(raw: Any) -> date:
    """Parse a date in ISO, dotted ISO or German notation."""
    if not isinstance(raw, str):
        raise ParseError(f"{raw!r} is not a date string")
    value = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as err:
        raise ParseError(f"{raw!r} is not a date") from err


def parse_datetime(raw: Any, default_tz: timezone | None = None) -> datetime:
    """Parse an ISO 8601 timestamp with or without fractional seconds.

    Accepts any number of fractional digits (the cloud sends 0, 3 and 7),
    a trailing ``Z`` and explicit offsets. Naive values get ``default_tz``.
    """
    if not isinstance(raw, str):
        raise ParseError(f"{raw!r} is not a timestamp string")
    value = raw.strip().replace(" ", "T", 1)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    # Python accepts at most 6 fractional digits before 3.11 semantics; trim.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise ParseError(f"{raw!r} is not a timestamp") from err
    if parsed.tzinfo is None and default_tz is not None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed


def parse_tz(raw: Any) -> timezone:
    """Parse an UTC offset such as ``+01:00``."""
    if not isinstance(raw, str):
        raise ParseError(f"{raw!r} is not an offset string")
    match = _TZ_RE.match(raw.strip())
    if not match:
        raise ParseError(f"{raw!r} is not an offset")
    sign = -1 if match[1] == "-" else 1
    return timezone(sign * timedelta(hours=int(match[2]), minutes=int(match[3])))


def encode_value(kind: Kind, value: Any) -> Any:
    """Encode a Python value into the JSON form the cloud expects."""
    if value is None:
        return None
    if kind == "int":
        return round(float(value))
    if kind == "float":
        return float(value)
    if kind == "bool":
        return bool(value)
    if kind == "time":
        if isinstance(value, time):
            return value.strftime("%H:%M")
        parsed = parse_time(str(value))
        return parsed.strftime("%H:%M") if parsed else "--:--"
    return str(value)


@dataclass(frozen=True, slots=True)
class Field:
    """Describes one value of a cloud payload."""

    source: str
    kind: Kind


@dataclass
class FieldReport:
    """Collects fields that could not be parsed, for logs and repairs."""

    failures: dict[str, str] = field(default_factory=dict)
    _logged: set[str] = field(default_factory=set)

    def failed(self, name: str, raw: Any, err: Exception) -> None:
        """Record a failure and log it once per field and session."""
        self.failures[name] = f"{raw!r}: {err}"
        if name not in self._logged:
            self._logged.add(name)
            _LOGGER.warning(
                "Ignoring unparsable value for %s (%r): %s; the entity stays "
                "unknown until the cloud sends a readable value",
                name,
                raw,
                err,
            )

    def ok(self, name: str) -> None:
        """Clear a previous failure once the field parses again."""
        self.failures.pop(name, None)


def parse_field(
    spec: Field,
    payload: dict[str, Any] | None,
    report: FieldReport | None = None,
    *,
    name: str | None = None,
    default_tz: timezone | None = None,
) -> Any:
    """Parse one field from a payload; return ``None`` on any problem."""
    if not payload or spec.source not in payload:
        return None
    raw = payload[spec.source]
    if raw is None:
        return None
    label = name or spec.source
    try:
        if spec.kind == "int":
            value: Any = parse_int(raw)
        elif spec.kind == "float":
            value = parse_float(raw)
        elif spec.kind == "bool":
            value = parse_bool(raw)
        elif spec.kind == "time":
            value = parse_time(raw)
        elif spec.kind == "date":
            value = parse_date(raw)
        elif spec.kind == "datetime":
            value = parse_datetime(raw, default_tz or UTC)
        elif spec.kind == "tz":
            value = parse_tz(raw)
        else:
            value = raw if isinstance(raw, str) else str(raw)
    except ParseError as err:
        if report is not None:
            report.failed(label, raw, err)
        return None
    if report is not None:
        report.ok(label)
    return value
