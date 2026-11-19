"""Config flow of the Grünbeck integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import GruenbeckAuthError, GruenbeckClient, GruenbeckDevice, GruenbeckError
from .const import (
    CONF_MIGRATE_LEGACY,
    CONF_REALTIME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LEGACY_DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def async_validate(
    hass: HomeAssistant, username: str, password: str
) -> list[GruenbeckDevice]:
    """Log in and return the softeners of the account."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    # Home Assistant closes sessions it created on shutdown; closing them
    # ourselves is reported as a bug by the frame helper.
    return await GruenbeckClient(session, username, password).async_get_devices()


def _legacy_credentials(hass: HomeAssistant) -> dict[str, str] | None:
    for legacy in hass.config_entries.async_entries(LEGACY_DOMAIN):
        if legacy.data.get(CONF_USERNAME) and legacy.data.get(CONF_PASSWORD):
            return {
                CONF_USERNAME: legacy.data[CONF_USERNAME],
                CONF_PASSWORD: legacy.data[CONF_PASSWORD],
            }
    return None


class GruenbeckConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Grünbeck cloud account."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._data: dict[str, Any] = {}
        self._devices: list[GruenbeckDevice] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GruenbeckOptionsFlow:
        """Return the options flow."""
        return GruenbeckOptionsFlow()

    async def _async_try(self, data: Mapping[str, Any], errors: dict[str, str]) -> bool:
        try:
            self._devices = await async_validate(
                self.hass, data[CONF_USERNAME], data[CONF_PASSWORD]
            )
        except GruenbeckAuthError:
            errors["base"] = "invalid_auth"
        except GruenbeckError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during login")
            errors["base"] = "unknown"
        else:
            if not self._devices:
                errors["base"] = "no_devices"
        return not errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for credentials, or offer to take over an existing setup."""
        if user_input is None and _legacy_credentials(self.hass):
            return self.async_show_menu(step_id="user", menu_options=["legacy", "credentials"])
        return await self.async_step_credentials(user_input)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter credentials manually."""
        errors: dict[str, str] = {}
        if user_input is not None and await self._async_try(user_input, errors):
            self._data = dict(user_input)
            return await self._async_finish()
        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(CREDENTIALS_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_legacy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Take over a gruenbeck_cloud setup with its stored credentials."""
        credentials = _legacy_credentials(self.hass)
        errors: dict[str, str] = {}
        if credentials is None:
            return self.async_abort(reason="no_legacy")
        if user_input is not None and await self._async_try(credentials, errors):
            self._data = {**credentials, CONF_MIGRATE_LEGACY: True}
            return await self._async_finish()
        return self.async_show_form(
            step_id="legacy",
            description_placeholders={"username": credentials[CONF_USERNAME]},
            errors=errors,
        )

    async def _async_finish(self) -> ConfigFlowResult:
        await self.async_set_unique_id(self._data[CONF_USERNAME].strip().lower())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=self._data[CONF_USERNAME], data=self._data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            if await self._async_try(data, errors):
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the credentials of the same account."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None and await self._async_try(user_input, errors):
            await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input or {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            errors=errors,
        )


class GruenbeckOptionsFlow(OptionsFlow):
    """Polling interval and realtime channel."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=3600,
                            step=30,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_REALTIME, default=options.get(CONF_REALTIME, True)): bool,
                }
            ),
        )
