"""Tests for Shelly climate platform."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock, PropertyMock

from aioshelly.const import (
    BLU_TRV_IDENTIFIER,
    MODEL_BLU_GATEWAY_G3,
    MODEL_VALVE,
    MODEL_WALL_DISPLAY,
)
from aioshelly.exceptions import DeviceConnectionError, InvalidAuthError, RpcCallError
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_NONE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.shelly.const import DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from . import MOCK_MAC, init_integration, register_device, register_entity
from .conftest import MOCK_STATUS_COAP

from tests.common import mock_restore_cache, mock_restore_cache_with_extra_data

SENSOR_BLOCK_ID = 3
DEVICE_BLOCK_ID = 4
EMETER_BLOCK_ID = 5
GAS_VALVE_BLOCK_ID = 6
ENTITY_ID = f"{CLIMATE_DOMAIN}.test_name"


async def test_climate_hvac_mode(
    hass: HomeAssistant,
    mock_block_device: Mock,
    monkeypatch: pytest.MonkeyPatch,
    entity_registry: EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test climate hvac mode service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(
        mock_block_device.blocks[SENSOR_BLOCK_ID],
        "sensor_ids",
        {"battery": 98, "valvePos": 50, "targetTemp": 21.0},
    )
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.delattr(mock_block_device.blocks[EMETER_BLOCK_ID], "targetTemp")
    monkeypatch.delattr(mock_block_device.blocks[GAS_VALVE_BLOCK_ID], "targetTemp")
    await init_integration(hass, 1, sleep_period=1000, model=MODEL_VALVE)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    # Test initial hvac mode - off
    assert hass.states.get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-state")

    assert entity_registry.async_get(ENTITY_ID) == snapshot(name=f"{ENTITY_ID}-entry")

    # Test set hvac mode heat
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": 20.0}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 20.0)
    mock_block_device.mock_update()

    assert (state := hass.states.get(ENTITY_ID))
    assert state.state == HVACMode.HEAT

    # Test set hvac mode off
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": "4"}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 4.0)
    mock_block_device.mock_update()
    assert (state := hass.states.get(ENTITY_ID))
    assert state.state == HVACMode.OFF

    # Test unavailable on error
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 1)
    mock_block_device.mock_update()
    assert (state := hass.states.get(ENTITY_ID))
    assert state.state == STATE_UNAVAILABLE


async def test_climate_set_temperature(
    hass: HomeAssistant, mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test climate set temperature service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.delattr(mock_block_device.blocks[GAS_VALVE_BLOCK_ID], "targetTemp")
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (state := hass.states.get(ENTITY_ID))
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 4

    # Test set temperature
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 23},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": "23.0"}
    )
    mock_block_device.http_request.reset_mock()

    # Test conversion from C to F
    monkeypatch.setattr(
        mock_block_device,
        "settings",
        {
            "thermostats": [
                {"target_t": {"units": "F"}},
            ]
        },
    )

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 20},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": "68.0"}
    )


async def test_climate_set_preset_mode(
    hass: HomeAssistant, mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test climate set preset mode service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.delattr(mock_block_device.blocks[GAS_VALVE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", None)
    await init_integration(hass, 1, sleep_period=1000, model=MODEL_VALVE)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (state := hass.states.get(ENTITY_ID))
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_NONE

    # Test set Profile2
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "Profile2"},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"schedule": 1, "schedule_profile": "2"}
    )

    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", 2)
    mock_block_device.mock_update()

    assert (state := hass.states.get(ENTITY_ID))
    assert state.attributes[ATTR_PRESET_MODE] == "Profile2"

    # Set preset to none
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: PRESET_NONE},
        blocking=True,
    )

    assert len(mock_block_device.http_request.mock_calls) == 2
    mock_block_device.http_request.assert_called_with(
        "get", "thermostat/0", {"schedule": 0}
    )

    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", 0)
    mock_block_device.mock_update()

    assert (state := hass.states.get(ENTITY_ID))
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_NONE


async def test_block_restored_climate(
    hass: HomeAssistant,
    mock_block_device: Mock,
    device_registry: DeviceRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test block restored climate."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.delattr(mock_block_device.blocks[GAS_VALVE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.delattr(mock_block_device.blocks[EMETER_BLOCK_ID], "targetTemp")
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    device = register_device(device_registry, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
        device_id=device.id,
    )
    attrs = {"current_temperature": 20.5, "temperature": 4.0}
    extra_data = {"last_target_temp": 22.0}
    mock_restore_cache_with_extra_data(
        hass, ((State(entity_id, HVACMode.OFF, attributes=attrs), extra_data),)
    )

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 4.0

    # Partial update, should not change state
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 4.0

    # Make device online
    monkeypatch.setattr(mock_block_device, "initialized", True)
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 4.0

    # Test set hvac mode heat, target temp should be set to last target temp (22)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": 22.0}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 22.0)
    mock_block_device.mock_update()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.HEAT
    assert state.attributes.get(ATTR_TEMPERATURE) == 22.0


async def test_block_restored_climate_us_customary(
    hass: HomeAssistant,
    mock_block_device: Mock,
    device_registry: DeviceRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test block restored climate with US CUSTOMARY unit system."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.delattr(mock_block_device.blocks[GAS_VALVE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.delattr(mock_block_device.blocks[EMETER_BLOCK_ID], "targetTemp")
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    device = register_device(device_registry, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
        device_id=device.id,
    )
    attrs = {"current_temperature": 67, "temperature": 39}
    extra_data = {"last_target_temp": 10.0}
    mock_restore_cache_with_extra_data(
        hass, ((State(entity_id, HVACMode.OFF, attributes=attrs), extra_data),)
    )

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 39
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == 67

    # Partial update, should not change state
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 39
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == 67

    # Make device online
    monkeypatch.setattr(mock_block_device, "initialized", True)
    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 4.0)
    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "temp", 18.2)
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF
    assert state.attributes.get(ATTR_TEMPERATURE) == 39
    assert state.attributes.get(ATTR_CURRENT_TEMPERATURE) == 65

    # Test set hvac mode heat, target temp should be set to last target temp (10.0/50)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": 10.0}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 10.0)
    mock_block_device.mock_update()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.HEAT
    assert state.attributes.get(ATTR_TEMPERATURE) == 50


async def test_block_restored_climate_unavailable(
    hass: HomeAssistant,
    mock_block_device: Mock,
    device_registry: DeviceRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test block restored climate unavailable state."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    device = register_device(device_registry, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
        device_id=device.id,
    )
    mock_restore_cache(hass, [State(entity_id, STATE_UNAVAILABLE)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF


async def test_block_restored_climate_set_preset_before_online(
    hass: HomeAssistant,
    mock_block_device: Mock,
    device_registry: DeviceRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test block restored climate set preset before device is online."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    device = register_device(device_registry, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
        device_id=device.id,
    )
    mock_restore_cache(hass, [State(entity_id, HVACMode.HEAT)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.HEAT

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "Profile1"},
            blocking=True,
        )

    mock_block_device.http_request.assert_not_called()


async def test_block_set_mode_connection_error(
    hass: HomeAssistant, mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test block device set mode connection error."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(
        mock_block_device,
        "http_request",
        AsyncMock(side_effect=DeviceConnectionError),
    )
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    with pytest.raises(
        HomeAssistantError,
        match="Device communication error occurred while calling action for climate.test_name of Test name",
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
            blocking=True,
        )


async def test_block_set_mode_auth_error(
    hass: HomeAssistant, mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test block device set mode authentication error."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(
        mock_block_device,
        "http_request",
        AsyncMock(side_effect=InvalidAuthError),
    )
    entry = await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is ConfigEntryState.LOADED

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )

    assert entry.state is ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id


async def test_block_restored_climate_auth_error(
    hass: HomeAssistant,
    mock_block_device: Mock,
    device_registry: DeviceRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test block restored climate with authentication error during init."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    device = register_device(device_registry, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
        device_id=device.id,
    )
    mock_restore_cache(hass, [State(entity_id, HVACMode.HEAT)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Make device online with auth error
    monkeypatch.setattr(mock_block_device, "initialized", True)
    type(mock_block_device).settings = PropertyMock(
        return_value={}, side_effect=InvalidAuthError
    )
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id


async def test_device_not_calibrated(
    hass: HomeAssistant,
    mock_block_device: Mock,
    monkeypatch: pytest.MonkeyPatch,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test to create an issue when the device is not calibrated."""
    await init_integration(hass, 1, sleep_period=1000, model=MODEL_VALVE)

    # Make device online
    mock_block_device.mock_online()
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_status = MOCK_STATUS_COAP.copy()
    mock_status["calibrated"] = False
    monkeypatch.setattr(
        mock_block_device,
        "status",
        mock_status,
    )
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(
        domain=DOMAIN, issue_id=f"not_calibrated_{MOCK_MAC}"
    )

    # The device has been calibrated
    monkeypatch.setattr(
        mock_block_device,
        "status",
        MOCK_STATUS_COAP,
    )
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert not issue_registry.async_get_issue(
        domain=DOMAIN, issue_id=f"not_calibrated_{MOCK_MAC}"
    )


async def test_rpc_climate_hvac_mode(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
    mock_rpc_device: Mock,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: SnapshotAssertion,
) -> None:
    """Test climate hvac mode service."""
    entity_id = "climate.test_name"

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    assert (state := hass.states.get(entity_id)) == snapshot(name=f"{entity_id}-state")

    assert entity_registry.async_get(entity_id) == snapshot(name=f"{entity_id}-entry")

    monkeypatch.setitem(mock_rpc_device.status["thermostat:0"], "output", False)
    mock_rpc_device.mock_update()

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
    assert state.attributes[ATTR_CURRENT_HUMIDITY] == 44.4

    monkeypatch.setitem(mock_rpc_device.status["thermostat:0"], "enable", False)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    mock_rpc_device.mock_update()

    mock_rpc_device.call_rpc.assert_called_once_with(
        "Thermostat.SetConfig", {"config": {"id": 0, "enable": False}}
    )
    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.OFF


async def test_rpc_climate_without_humidity(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
    mock_rpc_device: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test climate entity without the humidity value."""
    entity_id = "climate.test_name"
    new_status = deepcopy(mock_rpc_device.status)
    new_status.pop("humidity:0")
    monkeypatch.setattr(mock_rpc_device, "status", new_status)

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 23
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 12.3
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert ATTR_CURRENT_HUMIDITY not in state.attributes

    assert (entry := entity_registry.async_get(entity_id))
    assert entry.unique_id == "123456789ABC-thermostat:0"


async def test_rpc_climate_set_temperature(
    hass: HomeAssistant, mock_rpc_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test climate set target temperature."""
    entity_id = "climate.test_name"

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_TEMPERATURE] == 23

    monkeypatch.setitem(mock_rpc_device.status["thermostat:0"], "target_C", 28)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 28},
        blocking=True,
    )
    mock_rpc_device.mock_update()

    mock_rpc_device.call_rpc.assert_called_once_with(
        "Thermostat.SetConfig", {"config": {"id": 0, "target_C": 28}}
    )
    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_TEMPERATURE] == 28


async def test_rpc_climate_hvac_mode_cool(
    hass: HomeAssistant, mock_rpc_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test climate with hvac mode cooling."""
    entity_id = "climate.test_name"
    new_config = deepcopy(mock_rpc_device.config)
    new_config["thermostat:0"]["type"] = "cooling"
    monkeypatch.setattr(mock_rpc_device, "config", new_config)

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    assert (state := hass.states.get(entity_id))
    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.COOLING


async def test_wall_display_thermostat_mode(
    hass: HomeAssistant,
    mock_rpc_device: Mock,
    entity_registry: EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: SnapshotAssertion,
) -> None:
    """Test Wall Display in thermostat mode."""
    climate_entity_id = "climate.test_name"
    switch_entity_id = "switch.test_name_test_switch_0"

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    # the switch entity should be removed
    assert hass.states.get(switch_entity_id) is None
    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 0

    # the climate entity should be created
    state = hass.states.get(climate_entity_id)
    assert state == snapshot(name=f"{climate_entity_id}-state")
    assert len(hass.states.async_entity_ids(CLIMATE_DOMAIN)) == 1

    entry = entity_registry.async_get(climate_entity_id)
    assert entry == snapshot(name=f"{climate_entity_id}-entry")


async def test_wall_display_thermostat_mode_external_actuator(
    hass: HomeAssistant,
    mock_rpc_device: Mock,
    entity_registry: EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Wall Display in thermostat mode with an external actuator."""
    climate_entity_id = "climate.test_name"
    switch_entity_id = "switch.test_name_test_switch_0"

    new_status = deepcopy(mock_rpc_device.status)
    new_status["sys"]["relay_in_thermostat"] = False
    new_status.pop("cover:0")
    monkeypatch.setattr(mock_rpc_device, "status", new_status)

    await init_integration(hass, 2, model=MODEL_WALL_DISPLAY)

    # the switch entity should be created
    assert (state := hass.states.get(switch_entity_id))
    assert state.state == STATE_ON
    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 1

    # the climate entity should be created
    assert (state := hass.states.get(climate_entity_id))
    assert state.state == HVACMode.HEAT
    assert len(hass.states.async_entity_ids(CLIMATE_DOMAIN)) == 1

    assert (entry := entity_registry.async_get(climate_entity_id))
    assert entry.unique_id == "123456789ABC-thermostat:0"


async def test_blu_trv_climate_set_temperature(
    hass: HomeAssistant,
    mock_blu_trv: Mock,
    entity_registry: EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: SnapshotAssertion,
) -> None:
    """Test BLU TRV set target temperature."""

    entity_id = "climate.trv_name"
    monkeypatch.delitem(mock_blu_trv.status, "thermostat:0")

    await init_integration(hass, 3, model=MODEL_BLU_GATEWAY_G3)

    assert (state := hass.states.get(entity_id)) == snapshot(name=f"{entity_id}-state")

    assert entity_registry.async_get(entity_id) == snapshot(name=f"{entity_id}-entry")

    monkeypatch.setitem(
        mock_blu_trv.status[f"{BLU_TRV_IDENTIFIER}:200"], "target_C", 28
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 28},
        blocking=True,
    )
    mock_blu_trv.mock_update()

    mock_blu_trv.blu_trv_set_target_temperature.assert_called_once_with(200, 28.0)

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_TEMPERATURE] == 28


async def test_blu_trv_climate_disabled(
    hass: HomeAssistant,
    mock_blu_trv: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test BLU TRV disabled."""

    entity_id = "climate.trv_name"
    monkeypatch.delitem(mock_blu_trv.status, "thermostat:0")

    await init_integration(hass, 3, model=MODEL_BLU_GATEWAY_G3)

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_TEMPERATURE] == 17.1

    monkeypatch.setitem(
        mock_blu_trv.config[f"{BLU_TRV_IDENTIFIER}:200"], "enable", False
    )
    mock_blu_trv.mock_update()

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_TEMPERATURE] is None


async def test_blu_trv_climate_hvac_action(
    hass: HomeAssistant,
    mock_blu_trv: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test BLU TRV is heating."""

    entity_id = "climate.trv_name"
    monkeypatch.delitem(mock_blu_trv.status, "thermostat:0")

    await init_integration(hass, 3, model=MODEL_BLU_GATEWAY_G3)

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    monkeypatch.setitem(mock_blu_trv.status[f"{BLU_TRV_IDENTIFIER}:200"], "pos", 10)
    mock_blu_trv.mock_update()

    assert (state := hass.states.get(entity_id))
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (
            DeviceConnectionError,
            "Device communication error occurred while calling action for climate.trv_name of Test name",
        ),
        (
            RpcCallError(999),
            "RPC call error occurred while calling action for climate.trv_name of Test name",
        ),
    ],
)
async def test_blu_trv_set_target_temp_exc(
    hass: HomeAssistant,
    mock_blu_trv: Mock,
    exception: Exception,
    error: str,
) -> None:
    """BLU TRV target temperature setting test with excepton."""
    await init_integration(hass, 3, model=MODEL_BLU_GATEWAY_G3)

    mock_blu_trv.blu_trv_set_target_temperature.side_effect = exception

    with pytest.raises(HomeAssistantError, match=error):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: "climate.trv_name", ATTR_TEMPERATURE: 28},
            blocking=True,
        )


async def test_blu_trv_set_target_temp_auth_error(
    hass: HomeAssistant,
    mock_blu_trv: Mock,
) -> None:
    """BLU TRV target temperature setting test with authentication error."""
    entry = await init_integration(hass, 3, model=MODEL_BLU_GATEWAY_G3)

    mock_blu_trv.blu_trv_set_target_temperature.side_effect = InvalidAuthError

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.trv_name", ATTR_TEMPERATURE: 28},
        blocking=True,
    )

    assert entry.state is ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id
