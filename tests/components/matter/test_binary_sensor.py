"""Test Matter binary sensors."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

from matter_server.client.models.node import MatterNode
from matter_server.common.models import EventType
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.matter.binary_sensor import (
    DISCOVERY_SCHEMAS as BINARY_SENSOR_SCHEMAS,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import (
    set_node_attribute,
    snapshot_matter_entities,
    trigger_subscription_callback,
)


@pytest.fixture(autouse=True)
def binary_sensor_platform() -> Generator[None]:
    """Load only the binary sensor platform."""
    with patch(
        "homeassistant.components.matter.discovery.DISCOVERY_SCHEMAS",
        new={
            Platform.BINARY_SENSOR: BINARY_SENSOR_SCHEMAS,
        },
    ):
        yield


@pytest.mark.usefixtures("matter_devices")
async def test_binary_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test binary sensors."""
    snapshot_matter_entities(hass, entity_registry, snapshot, Platform.BINARY_SENSOR)


@pytest.mark.parametrize("node_fixture", ["occupancy_sensor"])
async def test_occupancy_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test occupancy sensor."""
    state = hass.states.get("binary_sensor.mock_occupancy_sensor_occupancy")
    assert state
    assert state.state == "on"

    set_node_attribute(matter_node, 1, 1030, 0, 0)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/1030/0", 0)
    )

    state = hass.states.get("binary_sensor.mock_occupancy_sensor_occupancy")
    assert state
    assert state.state == "off"


@pytest.mark.parametrize(
    ("node_fixture", "entity_id"),
    [
        ("eve_contact_sensor", "binary_sensor.eve_door_door"),
        ("leak_sensor", "binary_sensor.water_leak_detector_water_leak"),
    ],
)
async def test_boolean_state_sensors(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
    entity_id: str,
) -> None:
    """Test if binary sensors get created from devices with Boolean State cluster."""
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "on"

    # invert the value
    cur_attr_value = matter_node.get_attribute_value(1, 69, 0)
    set_node_attribute(matter_node, 1, 69, 0, not cur_attr_value)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/69/0", not cur_attr_value)
    )

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"


@pytest.mark.parametrize("node_fixture", ["door_lock"])
async def test_battery_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test battery sensor."""
    entity_id = "binary_sensor.mock_door_lock_battery"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"

    set_node_attribute(matter_node, 1, 47, 14, 1)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/47/14", 1)
    )

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "on"


@pytest.mark.parametrize("node_fixture", ["door_lock"])
async def test_optional_sensor_from_featuremap(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test discovery of optional doorsensor in doorlock featuremap."""
    entity_id = "binary_sensor.mock_door_lock_door"
    state = hass.states.get(entity_id)
    assert state is None

    # update the feature map to include the optional door sensor feature
    # and fire a node updated event
    set_node_attribute(matter_node, 1, 257, 65532, 32)
    await trigger_subscription_callback(
        hass, matter_client, event=EventType.NODE_UPDATED, data=matter_node
    )
    # this should result in a new binary sensor entity being discovered
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"
    # now test the reverse, by removing the feature from the feature map
    set_node_attribute(matter_node, 1, 257, 65532, 0)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/257/65532", 0)
    )
    state = hass.states.get(entity_id)
    assert state is None


@pytest.mark.parametrize("node_fixture", ["silabs_evse_charging"])
async def test_evse_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test evse sensors."""
    # Test StateEnum value with binary_sensor.evse_charging_status
    entity_id = "binary_sensor.evse_charging_status"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "on"
    # switch to PluggedInDemand state
    set_node_attribute(matter_node, 1, 153, 0, 2)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/153/0", 2)
    )
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"

    # Test StateEnum value with binary_sensor.evse_plug
    entity_id = "binary_sensor.evse_plug"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "on"
    # switch to NotPluggedIn state
    set_node_attribute(matter_node, 1, 153, 0, 0)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/153/0", 0)
    )
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"

    # Test SupplyStateEnum value with binary_sensor.evse_charger_supply_state
    entity_id = "binary_sensor.evse_charger_supply_state"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "on"
    # switch to Disabled state
    set_node_attribute(matter_node, 1, 153, 1, 0)
    await trigger_subscription_callback(
        hass, matter_client, data=(matter_node.node_id, "1/153/1", 0)
    )
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "off"


@pytest.mark.parametrize("node_fixture", ["silabs_water_heater"])
async def test_water_heater(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test water heater sensor."""
    # BoostState
    state = hass.states.get("binary_sensor.water_heater_boost_state")
    assert state
    assert state.state == "off"

    set_node_attribute(matter_node, 2, 148, 5, 1)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("binary_sensor.water_heater_boost_state")
    assert state
    assert state.state == "on"


@pytest.mark.parametrize("node_fixture", ["pump"])
async def test_pump(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test pump sensors."""
    # PumpStatus
    state = hass.states.get("binary_sensor.mock_pump_running")
    assert state
    assert state.state == "on"

    set_node_attribute(matter_node, 1, 512, 16, 0)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("binary_sensor.mock_pump_running")
    assert state
    assert state.state == "off"

    # PumpStatus --> DeviceFault bit
    state = hass.states.get("binary_sensor.mock_pump_problem")
    assert state
    assert state.state == "unknown"

    set_node_attribute(matter_node, 1, 512, 16, 1)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("binary_sensor.mock_pump_problem")
    assert state
    assert state.state == "on"

    # PumpStatus --> SupplyFault bit
    set_node_attribute(matter_node, 1, 512, 16, 2)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("binary_sensor.mock_pump_problem")
    assert state
    assert state.state == "on"


@pytest.mark.parametrize("node_fixture", ["silabs_dishwasher"])
async def test_dishwasher_alarm(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test dishwasher alarm sensors."""
    state = hass.states.get("binary_sensor.dishwasher_door_alarm")
    assert state

    set_node_attribute(matter_node, 1, 93, 2, 4)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("binary_sensor.dishwasher_door_alarm")
    assert state
    assert state.state == "on"
