"""Test the Home Assistant fyta binary sensor module."""

from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from fyta_cli.fyta_exceptions import FytaConnectionError, FytaPlantError
from fyta_cli.fyta_models import Plant
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.fyta.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_platform

from tests.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_load_json_object_fixture,
    snapshot_platform,
)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_fyta_connector: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test all entities."""

    await setup_platform(hass, mock_config_entry, [Platform.BINARY_SENSOR])
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    "exception",
    [
        FytaConnectionError,
        FytaPlantError,
    ],
)
async def test_connection_error(
    hass: HomeAssistant,
    exception: Exception,
    mock_fyta_connector: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test connection error."""
    await setup_platform(hass, mock_config_entry, [Platform.BINARY_SENSOR])

    mock_fyta_connector.update_all_plants.side_effect = exception

    freezer.tick(delta=timedelta(hours=12))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.gummibaum_repotted").state == STATE_UNAVAILABLE
    )


async def test_add_remove_entities(
    hass: HomeAssistant,
    mock_fyta_connector: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test if entities are added and old are removed."""
    await setup_platform(hass, mock_config_entry, [Platform.BINARY_SENSOR])

    assert hass.states.get("binary_sensor.gummibaum_repotted").state == STATE_ON

    plants: dict[int, Plant] = {
        0: Plant.from_dict(
            await async_load_json_object_fixture(hass, "plant_status1.json", DOMAIN)
        ),
        2: Plant.from_dict(
            await async_load_json_object_fixture(hass, "plant_status3.json", DOMAIN)
        ),
    }
    mock_fyta_connector.update_all_plants.return_value = plants
    mock_fyta_connector.plant_list = {
        0: "Kautschukbaum",
        2: "Tomatenpflanze",
    }

    freezer.tick(delta=timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.kakaobaum_repotted") is None
    assert hass.states.get("binary_sensor.tomatenpflanze_repotted").state == STATE_OFF
