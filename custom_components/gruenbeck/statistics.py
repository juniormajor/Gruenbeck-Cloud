"""Daily water and salt usage as external long-term statistics.

The cloud reports finished days only as daily totals. They are imported as
external statistics (``gruenbeck:<serial>_water_daily`` in litres and
``gruenbeck:<serial>_salt_daily`` in kilograms) with one value per day at
local midnight, so they can be shown in statistics graphs and used in the
energy dashboard's water section. Days already imported are skipped; the
running sum continues from the last stored value.
"""

from __future__ import annotations

from datetime import datetime, time
import logging
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfMass, UnitOfVolume
from homeassistant.util import dt as dt_util

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import GruenbeckDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

_KINDS = {
    # kind: (unit, unit_class, factor from cloud value)
    "water": (UnitOfVolume.LITERS, "volume", 1.0),
    "salt": (UnitOfMass.KILOGRAMS, "mass", 0.001),
}


def statistic_id(serial: str, kind: str) -> str:
    """Return the external statistic id for a device and kind."""
    clean = "".join(ch if ch.isalnum() else "_" for ch in serial.lower())
    return f"{DOMAIN}:{clean}_{kind}_daily"


async def async_import_daily_statistics(coordinator: GruenbeckDeviceCoordinator) -> None:
    """Import finished days not yet present in the recorder."""
    hass = coordinator.hass
    if "recorder" not in hass.config.components:
        return
    device = coordinator.device
    today = dt_util.now().date()
    tz = dt_util.get_default_time_zone()
    for kind, (unit, unit_class, factor) in _KINDS.items():
        entries = [e for e in getattr(device, kind) if e.day < today]
        if not entries:
            continue
        stat_id = statistic_id(device.serial_number, kind)
        last = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, stat_id, True, {"sum", "state"}
        )
        last_sum = 0.0
        last_start: datetime | None = None
        if rows := last.get(stat_id):
            last_sum = float(rows[0].get("sum") or 0.0)
            start = rows[0]["start"]
            last_start = (
                dt_util.utc_from_timestamp(start) if isinstance(start, (int, float)) else start
            )
        statistics: list[StatisticData] = []
        for entry in entries:
            start = datetime.combine(entry.day, time.min, tzinfo=tz)
            if last_start is not None and start <= last_start:
                continue
            value = entry.value * factor
            last_sum += value
            statistics.append(StatisticData(start=start, state=value, sum=last_sum))
        if not statistics:
            continue
        metadata = StatisticMetaData(
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=f"{device.name} {kind} per day",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class=unit_class,
            unit_of_measurement=unit,
        )
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.debug("Imported %s %s days for %s", len(statistics), kind, stat_id)
