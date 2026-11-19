"""Setup, entities, failure handling and derived values."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.gruenbeck.api import GruenbeckAuthError, GruenbeckServerError
from custom_components.gruenbeck.const import DOMAIN

from .conftest import SERIAL

PREFIX = "softiq_sd18"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_entities(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Entities exist and show fixture values."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"sensor.{PREFIX}_raw_water").state == "25"
    assert hass.states.get(f"select.{PREFIX}_operation_mode").state == "comfort"
    assert hass.states.get(f"switch.{PREFIX}_push_notifications").state == "on"
    assert hass.states.get(f"binary_sensor.{PREFIX}_has_error").state == "on"
    assert hass.states.get(f"binary_sensor.{PREFIX}_cloud_connection").state == "on"
    # realtime via HTTP polling because the channel is off in the fixture entry
    assert hass.states.get(f"sensor.{PREFIX}_soft_water_quantity").state == "123456"
    assert hass.states.get(f"sensor.{PREFIX}_salt_range").state == STATE_UNKNOWN
    assert hass.states.get(f"sensor.{PREFIX}_regeneration_step").state == "inactive"
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(f"sensor.{PREFIX}_soft_water_quantity")
    assert entry.unique_id == f"{SERIAL}_soft_water_quantity"


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Rejected credentials lead to a reauth flow."""
    mock_client.async_get_devices.side_effect = GruenbeckAuthError("no")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows[0]["context"]["source"] == "reauth"


async def test_cloud_outage_grace_and_backoff(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Short outages keep values; longer ones mark entities unavailable."""
    await _setup(hass, config_entry)
    entity = f"sensor.{PREFIX}_raw_water"
    mock_client.async_get_info.side_effect = GruenbeckServerError("boom", 500)
    coordinator = config_entry.runtime_data.coordinators[SERIAL]

    await coordinator.async_refresh()
    assert hass.states.get(entity).state == "25"
    assert hass.states.get(f"binary_sensor.{PREFIX}_cloud_connection").state == "off"
    assert coordinator.update_interval == timedelta(seconds=720)

    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == STATE_UNAVAILABLE
    # connection sensor stays available to show the outage
    assert hass.states.get(f"binary_sensor.{PREFIX}_cloud_connection").state == "off"

    freezer.tick(timedelta(hours=3))
    await coordinator.async_refresh()
    issues = ir.async_get(hass).issues
    assert (DOMAIN, f"cloud_unreachable_{config_entry.entry_id}") in issues

    mock_client.async_get_info.side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "25"
    assert coordinator.update_interval == timedelta(seconds=360)
    assert (DOMAIN, f"cloud_unreachable_{config_entry.entry_id}") not in ir.async_get(hass).issues


async def test_water_meter_is_monotonic(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Drops of the soft water counter are ignored (issues #240, #275)."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinators[SERIAL]
    entity = f"sensor.{PREFIX}_soft_water_quantity"
    coordinator.async_handle_realtime({"id": SERIAL, "mcountwater1": 120000})
    assert hass.states.get(entity).state == "123456"
    coordinator.async_handle_realtime({"id": SERIAL, "mcountwater1": 0})
    assert hass.states.get(entity).state == "123456"
    coordinator.async_handle_realtime({"id": SERIAL, "mcountwater1": 123500})
    assert hass.states.get(entity).state == "123500"


async def test_salt_level_and_refill(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Refill sets the level, consumption lowers it."""
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{PREFIX}_salt_refilled"}, blocking=True
    )
    assert hass.states.get(f"sensor.{PREFIX}_salt_level").state == "25.0"
    coordinator = config_entry.runtime_data.coordinators[SERIAL]
    coordinator.async_handle_realtime({"id": SERIAL, "msaltusage": 103.0})
    assert float(hass.states.get(f"sensor.{PREFIX}_salt_level").state) == 24.5


async def test_regeneration_events(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Start and end of a regeneration fire events."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinators[SERIAL]
    entity = f"event.{PREFIX}_regeneration"
    coordinator.async_handle_realtime({"id": SERIAL, "mregstatus": 20})
    assert hass.states.get(entity).attributes["event_type"] == "regeneration_started"
    assert hass.states.get(f"binary_sensor.{PREFIX}_regeneration_active").state == "on"
    coordinator.async_handle_realtime({"id": SERIAL, "mregstatus": 0})
    assert hass.states.get(entity).attributes["event_type"] == "regeneration_finished"


async def test_write_parameter(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Selects and times write encoded values."""
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{PREFIX}_operation_mode", "option": "power"},
        blocking=True,
    )
    mock_client.async_set_parameters.assert_awaited_with("softliQ.D/6ZF9Z5KAA2", {"pmode": 3})
    assert hass.states.get(f"select.{PREFIX}_operation_mode").state == "power"


async def test_actions(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Domain actions resolve the device."""
    await _setup(hass, config_entry)
    device_id = er.async_get(hass).async_get(f"sensor.{PREFIX}_raw_water").device_id
    await hass.services.async_call(DOMAIN, "regenerate", {"device_id": device_id}, blocking=True)
    mock_client.async_regenerate.assert_awaited_once()
    result = await hass.services.async_call(
        DOMAIN,
        "get_measurements",
        {"device_id": device_id, "kind": "water"},
        blocking=True,
        return_response=True,
    )
    assert result["entries"][-1] == {"date": "2024-01-08", "value": 123}
    await hass.services.async_call(
        DOMAIN,
        "set_parameters",
        {"device_id": device_id, "parameters": {"buzzer": True}},
        blocking=True,
    )
    mock_client.async_set_parameters.assert_awaited_with("softliQ.D/6ZF9Z5KAA2", {"pbuzzer": True})


async def test_unload(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_poll_timer(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Polling runs every 360 s."""
    await _setup(hass, config_entry)
    calls = mock_client.async_get_info.await_count
    freezer.tick(timedelta(seconds=361))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.async_get_info.await_count == calls + 1
