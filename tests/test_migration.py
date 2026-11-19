"""Takeover of a gruenbeck_cloud setup (C08 E4)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gruenbeck.const import CONF_MIGRATE_LEGACY, DOMAIN, LEGACY_DOMAIN

from .conftest import SERIAL


async def test_takeover_keeps_entity_ids(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Legacy entity ids, options and device customisations survive."""
    legacy = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        title="softliQ.D/6ZF9Z5KAA2",
        unique_id=SERIAL,
        data={"username": "user@example.com", "password": "secret", "device_id": "x"},
    )
    legacy.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old_device = dev_reg.async_get_or_create(
        config_entry_id=legacy.entry_id,
        identifiers={(LEGACY_DOMAIN, "softliQ.D/6ZF9Z5KAA2")},
        name="softliQ.D/6ZF9Z5KAA2",
    )
    dev_reg.async_update_device(old_device.id, name_by_user="Gruenbeck SD18")
    water = ent_reg.async_get_or_create(
        "sensor",
        LEGACY_DOMAIN,
        f"{SERIAL}_soft_water_quantity",
        suggested_object_id="gruenbeck_sd18_soft_water_quantity",
        config_entry=legacy,
        device_id=old_device.id,
    )
    ent_reg.async_update_entity_options(water.entity_id, "sensor", {"unit_of_measurement": "m³"})
    ent_reg.async_get_or_create(
        "sensor",
        LEGACY_DOMAIN,
        f"{SERIAL}_remaining_capacity_volume",
        suggested_object_id="gruenbeck_sd18_remaining_capacity_m3",
        config_entry=legacy,
        device_id=old_device.id,
    )
    hass.states.async_set(
        "sensor.gruenbeck_sd18_soft_water_quantity", "unavailable", {"restored": True}
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "secret", CONF_MIGRATE_LEGACY: True},
        options={"realtime": False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(LEGACY_DOMAIN) == []
    assert CONF_MIGRATE_LEGACY not in entry.data
    moved = ent_reg.async_get("sensor.gruenbeck_sd18_soft_water_quantity")
    assert moved is not None
    assert moved.platform == DOMAIN
    assert moved.options["sensor"]["unit_of_measurement"] == "m³"
    assert ent_reg.async_get("sensor.gruenbeck_sd18_remaining_capacity_m3").platform == DOMAIN
    state = hass.states.get("sensor.gruenbeck_sd18_soft_water_quantity")
    assert state.state == "123.456"
    device = dev_reg.async_get(moved.device_id)
    assert device.name_by_user == "Gruenbeck SD18"
