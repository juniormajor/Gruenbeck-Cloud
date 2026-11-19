"""Diagnostics redact account data."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gruenbeck.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """No credentials, serials or installer contacts leak."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(result)
    assert "secret" not in text
    assert "6ZF9Z5KAA2" not in text
    assert "service@gruenbeck.de" not in text
    assert result["devices"][0]["parameters"]["pmode"] == 2
