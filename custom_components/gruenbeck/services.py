"""Actions of the Grünbeck integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
import voluptuous as vol

from .api.models import PARAMETER_FIELDS
from .const import DOMAIN
from .coordinator import GruenbeckDeviceCoordinator

SERVICE_REGENERATE = "regenerate"
SERVICE_SET_PARAMETERS = "set_parameters"
SERVICE_GET_MEASUREMENTS = "get_measurements"
SERVICE_SET_SALT_LEVEL = "set_salt_level"

ATTR_PARAMETERS = "parameters"
ATTR_KIND = "kind"
ATTR_LEVEL = "level"

_DEVICE = {vol.Required(ATTR_DEVICE_ID): cv.string}


def _coordinator(hass: HomeAssistant, device_id: str) -> GruenbeckDeviceCoordinator:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_device")
    serial = next((ident for dom, ident in device.identifiers if dom == DOMAIN), None)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and serial in entry.runtime_data.coordinators:
            return entry.runtime_data.coordinators[serial]
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_device")


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions once per Home Assistant instance."""

    async def regenerate(call: ServiceCall) -> None:
        await _coordinator(hass, call.data[ATTR_DEVICE_ID]).async_regenerate()

    async def set_parameters(call: ServiceCall) -> None:
        values: dict[str, Any] = call.data[ATTR_PARAMETERS]
        unknown = sorted(set(values) - set(PARAMETER_FIELDS))
        if unknown:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_parameters",
                translation_placeholders={"keys": ", ".join(unknown)},
            )
        await _coordinator(hass, call.data[ATTR_DEVICE_ID]).async_set_parameters(values)

    async def get_measurements(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call.data[ATTR_DEVICE_ID])
        await coordinator.async_refresh_measurements()
        kind = call.data[ATTR_KIND]
        return {
            "entries": [
                {"date": e.day.isoformat(), "value": e.value}
                for e in getattr(coordinator.device, kind)
            ]
        }

    async def set_salt_level(call: ServiceCall) -> None:
        _coordinator(hass, call.data[ATTR_DEVICE_ID]).set_salt_level(call.data[ATTR_LEVEL])

    hass.services.async_register(DOMAIN, SERVICE_REGENERATE, regenerate, vol.Schema(_DEVICE))
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PARAMETERS,
        set_parameters,
        vol.Schema({**_DEVICE, vol.Required(ATTR_PARAMETERS): dict}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MEASUREMENTS,
        get_measurements,
        vol.Schema({**_DEVICE, vol.Required(ATTR_KIND): vol.In(["water", "salt"])}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SALT_LEVEL,
        set_salt_level,
        vol.Schema({**_DEVICE, vol.Required(ATTR_LEVEL): vol.Coerce(float)}),
    )
