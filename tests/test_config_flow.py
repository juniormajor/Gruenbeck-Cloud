"""Config, reauth, reconfigure and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gruenbeck.api import GruenbeckAuthError, GruenbeckConnectionError
from custom_components.gruenbeck.const import CONF_MIGRATE_LEGACY, DOMAIN, LEGACY_DOMAIN

CREDS = {"username": "User@Example.com", "password": "secret"}


async def test_user_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Credentials create an entry keyed by the account."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "credentials"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "user@example.com"


async def test_user_flow_errors(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Errors are shown and the flow recovers."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    for exc, code in (
        (GruenbeckAuthError("x"), "invalid_auth"),
        (GruenbeckConnectionError("x"), "cannot_connect"),
    ):
        mock_client.validate.side_effect = exc
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
        assert result["errors"] == {"base": code}
    mock_client.validate.side_effect = None
    mock_client.validate.return_value = []
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["errors"] == {"base": "no_devices"}


async def test_legacy_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """An existing gruenbeck_cloud entry can be taken over without typing."""
    MockConfigEntry(domain=LEGACY_DOMAIN, data={**CREDS, "device_id": "x"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "legacy"}
    )
    assert result["step_id"] == "legacy"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MIGRATE_LEGACY] is True


async def test_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Reauth stores the new password."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["password"] == "new"


async def test_reconfigure_wrong_account(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Reconfigure refuses another account."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "other@example.com", "password": "x"}
    )
    assert result["reason"] == "wrong_account"


async def test_options(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Options are stored."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 600, "realtime": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["scan_interval"] == 600
