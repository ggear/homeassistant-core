"""Test the Reolink number platform."""

from unittest.mock import MagicMock, patch

import pytest
from reolink_aio.api import Chime
from reolink_aio.exceptions import InvalidParameterError, ReolinkError

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import TEST_NVR_NAME

from tests.common import MockConfigEntry


async def test_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_host: MagicMock,
) -> None:
    """Test number entity with volume."""
    reolink_host.volume.return_value = 80

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.NUMBER]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    entity_id = f"{Platform.NUMBER}.{TEST_NVR_NAME}_volume"

    assert hass.states.get(entity_id).state == "80"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 50},
        blocking=True,
    )
    reolink_host.set_volume.assert_called_with(0, volume=50)

    reolink_host.set_volume.side_effect = ReolinkError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 50},
            blocking=True,
        )

    reolink_host.set_volume.side_effect = InvalidParameterError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 50},
            blocking=True,
        )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_smart_ai_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_host: MagicMock,
) -> None:
    """Test number entity with smart ai sensitivity."""
    reolink_host.baichuan.smart_ai_sensitivity.return_value = 80

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.NUMBER]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    entity_id = f"{Platform.NUMBER}.{TEST_NVR_NAME}_AI_crossline_zone1_sensitivity"

    assert hass.states.get(entity_id).state == "80"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 50},
        blocking=True,
    )
    reolink_host.baichuan.set_smart_ai.assert_called_with(
        0, "crossline", 0, sensitivity=50
    )

    reolink_host.baichuan.set_smart_ai.side_effect = InvalidParameterError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 50},
            blocking=True,
        )


async def test_host_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_host: MagicMock,
) -> None:
    """Test number entity with volume."""
    reolink_host.alarm_volume = 85

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.NUMBER]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    entity_id = f"{Platform.NUMBER}.{TEST_NVR_NAME}_alarm_volume"

    assert hass.states.get(entity_id).state == "85"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 45},
        blocking=True,
    )
    reolink_host.set_hub_audio.assert_called_with(alarm_volume=45)

    reolink_host.set_hub_audio.side_effect = ReolinkError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 45},
            blocking=True,
        )

    reolink_host.set_hub_audio.side_effect = InvalidParameterError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 45},
            blocking=True,
        )


async def test_chime_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_host: MagicMock,
    reolink_chime: Chime,
) -> None:
    """Test number entity of a chime with chime volume."""
    reolink_chime.volume = 3

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.NUMBER]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    entity_id = f"{Platform.NUMBER}.test_chime_volume"

    assert hass.states.get(entity_id).state == "3"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 2},
        blocking=True,
    )
    reolink_chime.set_option.assert_called_with(volume=2)

    reolink_chime.set_option.side_effect = ReolinkError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 1},
            blocking=True,
        )

    reolink_chime.set_option.side_effect = InvalidParameterError("Test error")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 1},
            blocking=True,
        )
