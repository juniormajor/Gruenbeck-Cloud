"""Daily measurements become external statistics."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.gruenbeck.statistics import statistic_id

from .conftest import SERIAL


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock: Any, enable_custom_integrations: None) -> None:
    """Start the recorder before hass is created."""


async def test_daily_import(
    recorder_mock: Any,
    hass: HomeAssistant,
    mock_client: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Finished days are imported once, with a running sum."""
    freezer.move_to("2024-01-08T12:00:00+00:00")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    water = statistic_id(SERIAL, "water")
    rows = await hass.async_add_executor_job(
        get_last_statistics, hass, 1, water, True, {"sum", "state"}
    )
    # 2024-01-06 (125 l) and 2024-01-07 (226 l); 2024-01-08 is not finished
    assert rows[water][0]["state"] == 226
    assert rows[water][0]["sum"] == 351

    coordinator = config_entry.runtime_data.coordinators[SERIAL]
    await coordinator.async_refresh_measurements()
    await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(get_last_statistics, hass, 1, water, True, {"sum"})
    assert rows[water][0]["sum"] == 351
    salt = statistic_id(SERIAL, "salt")
    rows = await hass.async_add_executor_job(get_last_statistics, hass, 1, salt, True, {"sum"})
    assert round(rows[salt][0]["sum"], 3) == 0.311
