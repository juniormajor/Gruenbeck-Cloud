"""The Grünbeck integration: softliQ water softeners via the Grünbeck cloud."""

from __future__ import annotations

import contextlib
from datetime import timedelta
import logging

import aiohttp
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import GruenbeckAuthError, GruenbeckClient, GruenbeckError, GruenbeckRealtime
from .const import (
    CONF_MIGRATE_LEGACY,
    CONF_REALTIME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import (
    STORAGE_VERSION,
    DeviceMemory,
    GruenbeckAccount,
    GruenbeckConfigEntry,
    GruenbeckDeviceCoordinator,
    load_memory,
)
from .migration import async_migrate_legacy
from .services import async_setup_services
from .statistics import async_import_daily_statistics

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GruenbeckConfigEntry) -> bool:
    """Set up one Grünbeck cloud account."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    client = GruenbeckClient(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    try:
        devices = await client.async_get_devices()
    except GruenbeckAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except GruenbeckError as err:
        raise ConfigEntryNotReady(f"Grünbeck cloud not reachable: {err}") from err

    store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    memory = load_memory(await store.async_load())
    seconds = max(
        MIN_SCAN_INTERVAL, int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    )

    realtime: GruenbeckRealtime | None = None
    if entry.options.get(CONF_REALTIME, True):
        realtime = GruenbeckRealtime(
            client, session, {device.serial_number: device.id for device in devices}
        )

    account = GruenbeckAccount(client, realtime, {}, store, memory)
    for device in devices:
        mem = memory.setdefault(device.serial_number, DeviceMemory())
        coordinator = GruenbeckDeviceCoordinator(
            hass,
            entry,
            client,
            device,
            mem,
            timedelta(seconds=seconds),
            poll_realtime=realtime is None,
        )
        coordinator.request_save = account.request_save
        coordinator.add_measurement_listener(async_import_daily_statistics)
        account.coordinators[device.serial_number] = coordinator

    for coordinator in account.coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = account

    if entry.data.get(CONF_MIGRATE_LEGACY):
        await async_migrate_legacy(hass, entry, account)

    if realtime is not None:
        for serial, coordinator in account.coordinators.items():
            entry.async_on_unload(realtime.register(serial, coordinator.async_handle_realtime))
        realtime.start(lambda coro, name: entry.async_create_background_task(hass, coro, name))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GruenbeckConfigEntry) -> None:
    """Reload after options changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GruenbeckConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        account = entry.runtime_data
        if account.realtime is not None:
            await account.realtime.stop()
            for coordinator in account.coordinators.values():
                with contextlib.suppress(GruenbeckError):
                    await account.client.async_realtime(coordinator.device.id, "leave")
        await account.store.async_save(account.as_storage())
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: GruenbeckConfigEntry) -> None:
    """Delete the stored device memory with the entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
