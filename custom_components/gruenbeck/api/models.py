"""Data model of a Grünbeck device as delivered by the cloud.

The model keeps the raw JSON of every source (device info, parameters,
realtime values) and parses values on access through the field tables below.
Unknown keys are preserved, so a new firmware field never breaks anything and
shows up in diagnostics.

Field names follow ``pygruenbeck_cloud`` (MIT, Copyright (c) 2024 Marco
Neumann) so that entity keys stay compatible with ``hagruenbeck_cloud``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timezone
from typing import Any, Final

from .fields import Field, FieldReport, Kind, encode_value, parse_field

# Device information from GET /api/devices/{id}
INFO_FIELDS: Final[dict[str, Field]] = {
    "has_error": Field("hasError", "bool"),
    "next_regeneration": Field("nextRegeneration", "datetime"),
    "startup": Field("startup", "date"),
    "last_service": Field("lastService", "date"),
    "hardware_version": Field("hardwareVersion", "str"),
    "software_version": Field("softwareVersion", "str"),
    "mode": Field("mode", "int"),
    "nominal_flow": Field("nominalFlow", "float"),
    "raw_water": Field("rawWater", "float"),
    "soft_water": Field("softWater", "float"),
    "unit": Field("unit", "int"),
    "time_zone": Field("timeZone", "tz"),
}

# Parameters from GET/PATCH /api/devices/{id}/parameters
PARAMETER_FIELDS: Final[dict[str, Field]] = {
    "dlst": Field("pdlstauto", "bool"),
    "buzzer": Field("pbuzzer", "bool"),
    "buzzer_from": Field("pbuzzfrom", "time"),
    "buzzer_to": Field("pbuzzto", "time"),
    "push_notification": Field("pallowpushnotification", "bool"),
    "email_notification": Field("pallowemail", "bool"),
    "water_hardness_unit": Field("phunit", "int"),
    "raw_water_hardness": Field("prawhard", "int"),
    "soft_water_hardness": Field("psetsoft", "int"),
    "mode": Field("pmode", "int"),
    "mode_individual_monday": Field("pmodemo", "int"),
    "mode_individual_tuesday": Field("pmodetu", "int"),
    "mode_individual_wednesday": Field("pmodewe", "int"),
    "mode_individual_thursday": Field("pmodeth", "int"),
    "mode_individual_friday": Field("pmodefr", "int"),
    "mode_individual_saturday": Field("pmodesa", "int"),
    "mode_individual_sunday": Field("pmodesu", "int"),
    "regeneration_mode": Field("pregmode", "int"),
    "maintenance_interval": Field("pmaintint", "int"),
    "installer_name": Field("pname", "str"),
    "installer_phone": Field("ptelnr", "str"),
    "installer_email": Field("pmailadress", "str"),
    "ntp_sync": Field("pntpsync", "bool"),
    "fault_signal_contact": Field("pcfcontact", "bool"),
    "knx": Field("pknx", "bool"),
    "nominal_flow_monitoring": Field("pmonflow", "bool"),
    "disinfection_monitoring": Field("pmondisinf", "bool"),
    "led_ring_mode": Field("pled", "int"),
    "led_ring_flash_on_signal": Field("pledatsaltpre", "bool"),
    "led_ring_brightness": Field("pledbright", "int"),
    "residual_capacity_limit": Field("prescaplimit", "int"),
    "current_setpoint": Field("pcurrent", "int"),
    "charge": Field("pload", "int"),
    "interval_forced_regeneration": Field("pforcedregdist", "int"),
    "end_frequency_regeneration_valve": Field("pfreqregvalve", "int"),
    "end_frequency_regeneration_valve_2": Field("pfreqregvalve2", "int"),
    "end_frequency_blending_valve": Field("pfreqblendvalve", "int"),
    "treatment_volume": Field("pvolume", "int"),
    "soft_water_meter_pulse_rate": Field("ppratesoftwater", "float"),
    "blending_water_meter_pulse_rate": Field("pprateblending", "float"),
    "regeneration_water_meter_pulse_rate": Field("pprateregwater", "float"),
    "capacity_figure_monday": Field("psetcapmo", "int"),
    "capacity_figure_tuesday": Field("psetcaptu", "int"),
    "capacity_figure_wednesday": Field("psetcapwe", "int"),
    "capacity_figure_thursday": Field("psetcapth", "int"),
    "capacity_figure_friday": Field("psetcapfr", "int"),
    "capacity_figure_saturday": Field("psetcapsa", "int"),
    "capacity_figure_sunday": Field("psetcapsu", "int"),
    "nominal_flow_rate": Field("pnomflow", "float"),
    "regeneration_monitoring_time": Field("pmonregmeter", "int"),
    "salting_monitoring_time": Field("pmonsalting", "int"),
    "slow_rinse": Field("prinsing", "float"),
    "backwash": Field("pbackwash", "int"),
    "washing_out": Field("pwashingout", "int"),
    "minimum_filling_volume_smallest_cap": Field("pminvolmincap", "float"),
    "maximum_filling_volume_smallest_cap": Field("pmaxvolmincap", "float"),
    "minimum_filling_volume_largest_cap": Field("pminvolmaxcap", "float"),
    "maximum_filling_volume_largest_cap": Field("pmaxvolmaxcap", "float"),
    "longest_switch_on_time_chlorine_cell": Field("pmaxdurdisinfect", "int"),
    "maximum_remaining_time_regeneration": Field("pmaxresdurreg", "int"),
    "language": Field("planguage", "int"),
}
for _day, _short in (
    ("monday", "mo"),
    ("tuesday", "tu"),
    ("wednesday", "we"),
    ("thursday", "th"),
    ("friday", "fr"),
    ("saturday", "sa"),
    ("sunday", "su"),
):
    for _slot in (1, 2, 3):
        PARAMETER_FIELDS[f"regeneration_time_{_day}_{_slot}"] = Field(
            f"preg{_short}{_slot}", "time"
        )

# Realtime values from the SignalR hub and POST realtime/refresh
REALTIME_FIELDS: Final[dict[str, Field]] = {
    "soft_water_quantity": Field("mcountwater1", "int"),
    "soft_water_quantity_2": Field("mcountwater2", "int"),
    "regeneration_counter": Field("mcountreg", "int"),
    "current_flow_rate": Field("mflow1", "float"),
    "current_flow_rate_2": Field("mflow2", "float"),
    "remaining_capacity_volume": Field("mrescapa1", "float"),
    "remaining_capacity_volume_2": Field("mrescapa2", "float"),
    "remaining_capacity_percentage": Field("mresidcap1", "int"),
    "remaining_capacity_percentage_2": Field("mresidcap2", "int"),
    "salt_range": Field("msaltrange", "int"),
    "salt_consumption": Field("msaltusage", "float"),
    "next_service": Field("mmaint", "int"),
    "regeneration_remaining_time": Field("mremregstep", "float"),
    "regeneration_step": Field("mregstatus", "int"),
    "make_up_water_volume": Field("mcountwatertank", "int"),
    "exhausted_percentage": Field("mlifeadsorb", "int"),
    "actual_value_soft_water_hardness": Field("mhardsoftw", "int"),
    "capacity_figure": Field("mcapacity", "float"),
    "flow_rate_peak_value": Field("mflowmax", "float"),
    "exchanger_peak_value": Field("mflowmax1reg2", "float"),
    "exchanger_peak_value_2": Field("mflowmax2reg1", "float"),
    "last_regeneration_exchanger": Field("mendreg1", "time"),
    "last_regeneration_exchanger_2": Field("mendreg2", "time"),
    "regeneration_flow_rate_exchanger": Field("mflowreg1", "int"),
    "regeneration_flow_rate_exchanger_2": Field("mflowreg2", "int"),
    "blending_flow_rate": Field("mflowblend", "float"),
    "step_indication_regeneration_valve": Field("mstep1", "int"),
    "step_indication_regeneration_valve_2": Field("mstep2", "int"),
    "current_chlorine": Field("mcurrent", "int"),
    "remaining_amount_of_water": Field("mreswatadmod", "float"),
}

_ERROR_FIELDS: Final[dict[str, Field]] = {
    "date": Field("date", "datetime"),
    "is_resolved": Field("isResolved", "bool"),
    "message": Field("message", "str"),
    "description": Field("description", "str"),
    "type": Field("type", "str"),
    "error_code": Field("errorCode", "int"),
}


@dataclass(frozen=True, slots=True)
class DeviceError:
    """One entry of the device error log."""

    date: datetime | None
    is_resolved: bool | None
    message: str | None
    description: str | None
    type: str | None
    error_code: int | None

    @property
    def key(self) -> str:
        """Stable identity of an error entry."""
        stamp = self.date.isoformat() if self.date else "?"
        return f"{self.error_code}@{stamp}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly representation."""
        return {
            "date": self.date.isoformat() if self.date else None,
            "is_resolved": self.is_resolved,
            "message": self.message,
            "description": self.description,
            "type": self.type,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class DailyUsage:
    """One day of water (litres) or salt (grams) usage."""

    day: date
    value: float


def parse_daily_usage(
    payload: Any, report: FieldReport | None = None, name: str = "usage"
) -> list[DailyUsage]:
    """Parse a list of ``{"date": ..., "value": ...}`` entries."""
    if not isinstance(payload, list):
        return []
    result: list[DailyUsage] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        day = parse_field(Field("date", "date"), entry, report, name=f"{name}.date")
        value = parse_field(Field("value", "float"), entry, report, name=f"{name}.value")
        if day is not None and value is not None:
            result.append(DailyUsage(day, value))
    result.sort(key=lambda item: item.day)
    return result


@dataclass
class GruenbeckDevice:
    """State of one water softener."""

    id: str
    serial_number: str
    series: str
    name: str
    type: int | None = None
    info: dict[str, Any] = field(default_factory=dict)
    parameters_raw: dict[str, Any] = field(default_factory=dict)
    realtime_raw: dict[str, Any] = field(default_factory=dict)
    water: list[DailyUsage] = field(default_factory=list)
    salt: list[DailyUsage] = field(default_factory=list)
    realtime_updated: datetime | None = None
    cloud_updated: datetime | None = None
    report: FieldReport = field(default_factory=FieldReport)

    @classmethod
    def from_list_entry(cls, entry: dict[str, Any]) -> GruenbeckDevice:
        """Create a device from one entry of GET /api/devices."""
        return cls(
            id=str(entry.get("id", "")),
            serial_number=str(entry.get("serialNumber", "")),
            series=str(entry.get("series", "")),
            name=str(entry.get("name") or entry.get("series") or "Grünbeck"),
            type=entry.get("type") if isinstance(entry.get("type"), int) else None,
            info=dict(entry),
        )

    @property
    def is_softener(self) -> bool:
        """Return True for softliQ devices."""
        return "soft" in self.series.lower()

    @property
    def is_se(self) -> bool:
        """Return True for the softliQ SE series (different payload)."""
        return "softliq.se" in self.series.lower()

    @property
    def time_zone(self) -> timezone:
        """Offset reported by the device, UTC if unknown."""
        return self._parse(INFO_FIELDS["time_zone"], self.info, "time_zone") or UTC

    def _parse(self, spec: Field, payload: dict[str, Any], name: str) -> Any:
        return parse_field(spec, payload, self.report, name=name, default_tz=self.time_zone_raw)

    @property
    def time_zone_raw(self) -> timezone | None:
        """Offset without fallback, used as default for naive timestamps."""
        return parse_field(INFO_FIELDS["time_zone"], self.info, None)

    def info_value(self, key: str) -> Any:
        """Return a parsed device information value."""
        return self._parse(INFO_FIELDS[key], self.info, f"info.{key}")

    def parameter(self, key: str) -> Any:
        """Return a parsed parameter value."""
        return self._parse(PARAMETER_FIELDS[key], self.parameters_raw, f"parameter.{key}")

    def realtime(self, key: str) -> Any:
        """Return a parsed realtime value."""
        return self._parse(REALTIME_FIELDS[key], self.realtime_raw, f"realtime.{key}")

    def has_parameter(self, key: str) -> bool:
        """Return True if the parameter is part of the payload."""
        return PARAMETER_FIELDS[key].source in self.parameters_raw

    def has_realtime(self, key: str) -> bool:
        """Return True if the realtime value has been reported at least once."""
        return REALTIME_FIELDS[key].source in self.realtime_raw

    @property
    def errors(self) -> list[DeviceError]:
        """Parsed error log, newest first."""
        raw = self.info.get("errors")
        if not isinstance(raw, list):
            return []
        result = [
            DeviceError(
                **{
                    key: parse_field(spec, entry, self.report, name=f"errors.{key}")
                    for key, spec in _ERROR_FIELDS.items()
                }
            )
            for entry in raw
            if isinstance(entry, dict)
        ]
        result.sort(key=lambda err: err.date or datetime.min.replace(tzinfo=UTC), reverse=True)
        return result

    def update_info(self, payload: dict[str, Any]) -> None:
        """Merge the device information payload."""
        self.info.update(payload)
        if "water" in payload:
            self.water = parse_daily_usage(payload["water"], self.report, "water")
        if "salt" in payload:
            self.salt = parse_daily_usage(payload["salt"], self.report, "salt")

    def update_parameters(self, payload: dict[str, Any]) -> None:
        """Replace the parameter payload, ignoring bookkeeping keys."""
        self.parameters_raw = {
            key: value for key, value in payload.items() if not key.startswith("$")
        }

    def update_realtime(self, payload: dict[str, Any], now: datetime) -> bool:
        """Merge realtime values; return True if anything changed."""
        changed = False
        for key, value in payload.items():
            if key in ("id", "type"):
                continue
            if self.realtime_raw.get(key) != value:
                self.realtime_raw[key] = value
                changed = True
        self.realtime_updated = now
        return changed


def encode_parameter(key: str, value: Any) -> tuple[str, Any]:
    """Return JSON key and encoded value for a parameter change."""
    spec = PARAMETER_FIELDS[key]
    kind: Kind = spec.kind
    return spec.source, encode_value(kind, value)
