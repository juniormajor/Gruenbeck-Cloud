"""Takeover of an existing ``gruenbeck_cloud`` (hagruenbeck_cloud) setup.

Home Assistant keeps long-term statistics under the entity id. The takeover
therefore records every legacy entity, removes the legacy config entry and
registers the new entities directly under the old entity ids, before any of
them reports a state. Names, icons, areas, labels, aliases, disabled/hidden
flags and entity options (for example a display unit of m³) are carried over,
as are the user-given device name and area.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_MIGRATE_LEGACY, DOMAIN, LEGACY_DOMAIN, MANUFACTURER
from .coordinator import GruenbeckAccount, GruenbeckConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class _EntityPlan:
    serial: str
    key: str
    domain: str
    entity_id: str
    name: str | None
    icon: str | None
    area_id: str | None
    aliases: set[str]
    labels: set[str]
    disabled_by: er.RegistryEntryDisabler | None
    hidden_by: er.RegistryEntryHider | None
    options: dict[str, dict[str, Any]]


@dataclass
class _DevicePlan:
    name_by_user: str | None
    area_id: str | None
    labels: set[str]


def legacy_entries_for(hass: HomeAssistant, serials: set[str]) -> list[Any]:
    """Return legacy config entries that cover one of the given serials."""
    ent_reg = er.async_get(hass)
    result = []
    for legacy in hass.config_entries.async_entries(LEGACY_DOMAIN):
        for reg in er.async_entries_for_config_entry(ent_reg, legacy.entry_id):
            if reg.unique_id.partition("_")[0] in serials:
                result.append(legacy)
                break
    return result


async def async_migrate_legacy(
    hass: HomeAssistant, entry: GruenbeckConfigEntry, account: GruenbeckAccount
) -> dict[str, str]:
    """Take over legacy entities; return a map of entity_id to new unique_id."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    serials = set(account.coordinators)
    entity_plans: list[_EntityPlan] = []
    device_plans: dict[str, _DevicePlan] = {}

    for legacy in legacy_entries_for(hass, serials):
        for reg in er.async_entries_for_config_entry(ent_reg, legacy.entry_id):
            serial, _, key = reg.unique_id.partition("_")
            if serial not in serials or not key:
                continue
            entity_plans.append(
                _EntityPlan(
                    serial=serial,
                    key=key,
                    domain=reg.domain,
                    entity_id=reg.entity_id,
                    name=reg.name,
                    icon=reg.icon,
                    area_id=reg.area_id,
                    aliases=set(reg.aliases),
                    labels=set(reg.labels),
                    disabled_by=reg.disabled_by,
                    hidden_by=reg.hidden_by,
                    options={dom: dict(opts) for dom, opts in reg.options.items()},
                )
            )
            if reg.device_id and serial not in device_plans:
                device = dev_reg.async_get(reg.device_id)
                if device is not None:
                    device_plans[serial] = _DevicePlan(
                        device.name_by_user, device.area_id, set(device.labels)
                    )
        _LOGGER.info(
            "Taking over %s entities from legacy entry %s",
            len(entity_plans),
            legacy.title,
        )
        await hass.config_entries.async_remove(legacy.entry_id)

    # Restored "unavailable" states of the removed entities would block their
    # ids; nothing provides them any more, so drop them.
    for item in entity_plans:
        if ent_reg.async_get(item.entity_id) is None:
            hass.states.async_remove(item.entity_id)

    result: dict[str, str] = {}
    for serial, coordinator in account.coordinators.items():
        device = coordinator.device
        new_device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            name=device.name,
            model=device.series,
            serial_number=serial,
        )
        if plan := device_plans.get(serial):
            dev_reg.async_update_device(
                new_device.id,
                name_by_user=plan.name_by_user,
                area_id=plan.area_id,
                labels=plan.labels,
            )
        for item in (p for p in entity_plans if p.serial == serial):
            unique_id = f"{serial}_{item.key}"
            object_id = item.entity_id.split(".", 1)[1]
            new = ent_reg.async_get_or_create(
                item.domain,
                DOMAIN,
                unique_id,
                config_entry=entry,
                device_id=new_device.id,
                suggested_object_id=object_id,
                disabled_by=item.disabled_by,
                hidden_by=item.hidden_by,
            )
            if new.entity_id != item.entity_id:
                _LOGGER.warning(
                    "Could not keep entity id %s (got %s); its history stays under the old id",
                    item.entity_id,
                    new.entity_id,
                )
            ent_reg.async_update_entity(
                new.entity_id,
                name=item.name,
                icon=item.icon,
                area_id=item.area_id,
                aliases=item.aliases,
                labels=item.labels,
            )
            for domain, options in item.options.items():
                ent_reg.async_update_entity_options(new.entity_id, domain, options)
            result[new.entity_id] = unique_id

    data = {k: v for k, v in entry.data.items() if k != CONF_MIGRATE_LEGACY}
    hass.config_entries.async_update_entry(entry, data=data)
    _LOGGER.info("Legacy takeover finished: %s entities", len(result))
    return result
