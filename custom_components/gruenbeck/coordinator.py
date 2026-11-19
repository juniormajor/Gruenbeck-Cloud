"""Coordinators of the Grünbeck integration.

One ``GruenbeckAccount`` per config entry owns the HTTP client, the realtime
channel and one ``GruenbeckDeviceCoordinator`` per softener of the account.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GruenbeckAuthError,
    GruenbeckClient,
    GruenbeckDevice,
    GruenbeckError,
    GruenbeckParameterError,
    GruenbeckRateLimitError,
    GruenbeckRealtime,
    GruenbeckServerError,
)
from .api.models import encode_parameter, parse_daily_usage
from .const import (
    DEFAULT_SALT_REFILL_KG,
    DOMAIN,
    FAILURE_GRACE,
    MAX_BACKOFF,
    MEASUREMENT_INTERVAL,
    OUTAGE_ISSUE_AFTER,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass
class DeviceMemory:
    """Values the integration keeps across restarts for one device."""

    salt_level_kg: float | None = None
    salt_refill_kg: float = DEFAULT_SALT_REFILL_KG
    salt_counter_kg: float | None = None
    soft_water_total: int | None = None
    known_errors: list[str] | None = None


@dataclass
class GruenbeckAccount:
    """Runtime data of one config entry."""

    client: GruenbeckClient
    realtime: GruenbeckRealtime | None
    coordinators: dict[str, GruenbeckDeviceCoordinator]
    store: Store[dict[str, Any]]
    memory: dict[str, DeviceMemory]

    def as_storage(self) -> dict[str, Any]:
        """Return the device memory in storage form."""
        return {serial: dict(vars(mem)) for serial, mem in self.memory.items()}

    @callback
    def request_save(self) -> None:
        """Schedule a debounced save of the device memory."""
        self.store.async_delay_save(self.as_storage, 30)


type GruenbeckConfigEntry = ConfigEntry[GruenbeckAccount]


class GruenbeckDeviceCoordinator(DataUpdateCoordinator[GruenbeckDevice]):
    """Polls one softener and merges realtime pushes."""

    config_entry: GruenbeckConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GruenbeckConfigEntry,
        client: GruenbeckClient,
        device: GruenbeckDevice,
        memory: DeviceMemory,
        scan_interval: timedelta,
        *,
        poll_realtime: bool = False,
    ) -> None:
        """Set up the coordinator for one device.

        ``poll_realtime`` requests realtime values over HTTP on every poll; it
        is used when the SignalR channel is switched off.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.serial_number}",
            update_interval=scan_interval,
            always_update=False,
        )
        self.client = client
        self.device = device
        self.memory = memory
        self.base_interval = scan_interval
        self.poll_realtime = poll_realtime
        self.failures = 0
        self.first_failure: datetime | None = None
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self._last_measurements: datetime | None = None
        self._measurement_listeners: list[Any] = []
        self.request_save: Callable[[], None] = lambda: None

    @property
    def serial(self) -> str:
        """Serial number of the device."""
        return self.device.serial_number

    @property
    def cloud_ok(self) -> bool:
        """True while the last poll succeeded."""
        return self.failures == 0 and self.last_success is not None

    # ---------------------------------------------------------------- polling

    async def _async_update_data(self) -> GruenbeckDevice:
        device = self.device
        try:
            info = await self.client.async_get_info(device.id)
        except GruenbeckAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GruenbeckError as err:
            return self._handle_failure(err)

        device.update_info(info)
        try:
            device.update_parameters(await self.client.async_get_parameters(device.id))
        except GruenbeckAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GruenbeckError as err:
            # Keep the previous parameter set; the info part is fresh.
            _LOGGER.debug("Parameters of %s not refreshed: %s", self.serial, err)

        now = dt_util.utcnow()
        if self.poll_realtime:
            try:
                await self.client.async_realtime(device.id, "enter")
                values = await self.client.async_realtime(device.id, "refresh")
            except GruenbeckAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except GruenbeckError as err:
                _LOGGER.debug("Realtime poll of %s failed: %s", self.serial, err)
            else:
                if values:
                    device.update_realtime(values, now)
        if self._last_measurements is None or now - self._last_measurements >= MEASUREMENT_INTERVAL:
            await self._async_fetch_measurements()
            self._last_measurements = now

        self._handle_success(now)
        self._update_derived()
        return device

    async def _async_fetch_measurements(self) -> None:
        for kind in ("water", "salt"):
            try:
                payload = await self.client.async_get_measurements(self.device.id, kind)
            except GruenbeckError as err:
                _LOGGER.debug("%s measurements of %s failed: %s", kind, self.serial, err)
                continue
            values = parse_daily_usage(payload, self.device.report, kind)
            if values:
                setattr(self.device, kind, values)
        for listener in list(self._measurement_listeners):
            await listener(self)

    def add_measurement_listener(self, listener: Any) -> None:
        """Register an async callable run after new daily measurements."""
        self._measurement_listeners.append(listener)

    def _handle_failure(self, err: GruenbeckError) -> GruenbeckDevice:
        now = dt_util.utcnow()
        self.failures += 1
        self.first_failure = self.first_failure or now
        self.last_error = str(err)
        if isinstance(err, (GruenbeckRateLimitError, GruenbeckServerError)):
            interval = self.update_interval or self.base_interval
            self.update_interval = min(interval * 2, MAX_BACKOFF)
            if isinstance(err, GruenbeckRateLimitError) and err.retry_after:
                self.update_interval = max(self.update_interval, timedelta(seconds=err.retry_after))
        if now - self.first_failure >= OUTAGE_ISSUE_AFTER:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"cloud_unreachable_{self.config_entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="cloud_unreachable",
                translation_placeholders={
                    "since": dt_util.as_local(self.first_failure).strftime("%Y-%m-%d %H:%M"),
                    "error": self.last_error or "",
                },
            )
        if self.failures < FAILURE_GRACE and self.data is not None:
            _LOGGER.debug(
                "Poll %s of %s failed (%s), keeping last values",
                self.failures,
                self.serial,
                err,
            )
            self.async_update_listeners()
            return self.device
        raise UpdateFailed(f"Grünbeck cloud not reachable: {err}") from err

    def _handle_success(self, now: datetime) -> None:
        self.failures = 0
        self.first_failure = None
        self.last_error = None
        self.last_success = now
        self.device.cloud_updated = now
        self.update_interval = self.base_interval
        ir.async_delete_issue(self.hass, DOMAIN, f"cloud_unreachable_{self.config_entry.entry_id}")
        issue_id = f"unparsable_fields_{self.serial}"
        if self.device.report.failures:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="unparsable_fields",
                translation_placeholders={
                    "fields": ", ".join(sorted(self.device.report.failures)),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # --------------------------------------------------------------- realtime

    @callback
    def async_handle_realtime(self, payload: dict[str, Any]) -> None:
        """Merge a realtime push without resetting the poll timer."""
        if self.device.update_realtime(payload, dt_util.utcnow()):
            self._update_derived()
            self.async_update_listeners()

    # ---------------------------------------------------------------- derived

    def _update_derived(self) -> None:
        """Maintain the monotonic water meter and the computed salt level."""
        mem = self.memory
        water = self.device.realtime("soft_water_quantity")
        if isinstance(water, int) and water > 0:
            last = mem.soft_water_total
            if last is None or water >= last:
                mem.soft_water_total = water
            elif water < last * 0.1:
                _LOGGER.info(
                    "Soft water meter of %s restarted at %s (was %s)", self.serial, water, last
                )
                mem.soft_water_total = water
            else:
                _LOGGER.debug("Ignoring decreasing soft water value %s < %s", water, last)
        counter = self.device.realtime("salt_consumption")
        if isinstance(counter, (int, float)):
            previous = mem.salt_counter_kg
            if previous is not None and mem.salt_level_kg is not None:
                delta = counter - previous
                if 0 < delta < 10:
                    mem.salt_level_kg = max(0.0, mem.salt_level_kg - delta)
            mem.salt_counter_kg = counter
        self.request_save()

    def set_salt_level(self, level_kg: float) -> None:
        """Set the computed salt level, e.g. after refilling."""
        self.memory.salt_level_kg = max(0.0, float(level_kg))
        counter = self.device.realtime("salt_consumption")
        if isinstance(counter, (int, float)):
            self.memory.salt_counter_kg = counter
        self.request_save()
        self.async_update_listeners()

    # ---------------------------------------------------------------- actions

    async def async_set_parameter(self, key: str, value: Any) -> None:
        """Change one parameter and apply the cloud's answer."""
        await self.async_set_parameters({key: value})

    async def async_set_parameters(self, values: dict[str, Any]) -> None:
        """Change several parameters at once."""
        changes = dict(encode_parameter(key, value) for key, value in values.items())
        try:
            payload = await self.client.async_set_parameters(self.device.id, changes)
        except GruenbeckParameterError as err:
            raise HomeAssistantError(str(err)) from err
        except GruenbeckAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(str(err)) from err
        except GruenbeckError as err:
            raise HomeAssistantError(f"Grünbeck cloud not reachable: {err}") from err
        self.device.update_parameters(payload)
        self.async_update_listeners()

    async def async_regenerate(self) -> None:
        """Start a manual regeneration."""
        try:
            await self.client.async_regenerate(self.device.id)
        except GruenbeckError as err:
            raise HomeAssistantError(f"Regeneration not started: {err}") from err

    async def async_refresh_measurements(self) -> None:
        """Fetch daily measurements now (service call)."""
        await self._async_fetch_measurements()
        self._last_measurements = dt_util.utcnow()
        self.async_update_listeners()


def load_memory(raw: dict[str, Any] | None) -> dict[str, DeviceMemory]:
    """Rebuild device memory from storage, ignoring unknown keys."""
    result: dict[str, DeviceMemory] = {}
    for serial, values in (raw or {}).items():
        if not isinstance(values, dict):
            continue
        known = {k: v for k, v in values.items() if k in DeviceMemory.__dataclass_fields__}
        result[serial] = DeviceMemory(**known)
    return result


def now_utc() -> datetime:
    """Return the current UTC time (patchable in tests)."""
    return datetime.now(UTC)
