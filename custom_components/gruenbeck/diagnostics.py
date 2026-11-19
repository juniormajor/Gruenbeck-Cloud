"""Diagnostics of the Grünbeck integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import GruenbeckConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "id",
    "serialNumber",
    "serial_number",
    "pname",
    "ptelnr",
    "pmailadress",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GruenbeckConfigEntry
) -> dict[str, Any]:
    """Return redacted raw payloads, parse failures and connection state."""
    account = entry.runtime_data
    realtime = account.realtime
    devices = []
    for coordinator in account.coordinators.values():
        device = coordinator.device
        devices.append(
            {
                "series": device.series,
                "name": device.name,
                "info": async_redact_data(device.info, TO_REDACT),
                "parameters": async_redact_data(device.parameters_raw, TO_REDACT),
                "realtime": async_redact_data(device.realtime_raw, TO_REDACT),
                "unparsable_fields": dict(device.report.failures),
                "cloud_ok": coordinator.cloud_ok,
                "failures": coordinator.failures,
                "last_error": coordinator.last_error,
                "poll_interval_s": (
                    coordinator.update_interval.total_seconds()
                    if coordinator.update_interval
                    else None
                ),
                "memory": vars(coordinator.memory),
                "water_days": len(device.water),
                "salt_days": len(device.salt),
            }
        )
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "realtime": None
        if realtime is None
        else {
            "connected": realtime.connected,
            "last_message": realtime.last_message.isoformat() if realtime.last_message else None,
            "last_error": realtime.last_error,
            "reconnects": realtime.reconnects,
        },
        "devices": devices,
    }
