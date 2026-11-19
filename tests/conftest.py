"""Shared fixtures.

Response fixtures under ``fixtures/`` come from pygruenbeck_cloud's test suite
(MIT, Copyright (c) 2024 Marco Neumann); they contain no real account data.
"""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gruenbeck.api.models import GruenbeckDevice
from custom_components.gruenbeck.const import CONF_REALTIME, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
SERIAL = "6ZF9Z5KAA2"
DEVICE_ID = "softliQ.D/6ZF9Z5KAA2"


def load(name: str) -> Any:
    """Load a JSON fixture (``.txt`` files are JSON unless HTML)."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text)


def load_text(name: str) -> str:
    """Load a raw fixture."""
    return (FIXTURES / name).read_text(encoding="utf-8")


REALTIME = {
    "id": SERIAL,
    "mcountwater1": 123456,
    "mcountreg": 512,
    "mflow1": 0.4,
    "mrescapa1": 1.73,
    "mresidcap1": 81,
    "msaltrange": 999,
    "msaltusage": 102.5,
    "mregstatus": 0,
    "mendreg1": "03:12",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the custom integration."""


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Patch the cloud client used by the integration."""
    with (
        patch("custom_components.gruenbeck.GruenbeckClient", autospec=True) as cls,
        patch("custom_components.gruenbeck.config_flow.async_validate") as validate,
    ):
        client = cls.return_value
        devices = [GruenbeckDevice.from_list_entry(entry) for entry in load("get_devices.txt")]
        softeners = [d for d in devices if d.series == "softliQ.D"]
        client.async_get_devices.return_value = softeners
        validate.return_value = softeners
        client.async_get_info.return_value = load("get_device_infos.txt")
        client.async_get_parameters.return_value = load("get_device_infos_parameters.txt")
        client.async_get_measurements.side_effect = lambda _id, kind: load("get_device_infos.txt")[
            kind
        ]
        client.async_realtime.return_value = dict(REALTIME)
        client.async_set_parameters.side_effect = lambda _id, changes: {
            **load("get_device_infos_parameters.txt"),
            **changes,
        }
        client.session = AsyncMock()
        client.validate = validate
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Config entry with the realtime channel disabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "secret"},
        options={CONF_REALTIME: False},
    )
