"""Sensor for Shelly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, cast

from aioshelly.block_device import Block
from aioshelly.const import RPC_GENERATIONS

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_PLATFORM,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.typing import StateType

from .const import CONF_SLEEP_PERIOD, ROLE_TO_DEVICE_CLASS_MAP
from .coordinator import ShellyBlockCoordinator, ShellyConfigEntry, ShellyRpcCoordinator
from .entity import (
    BlockEntityDescription,
    RestEntityDescription,
    RpcEntityDescription,
    ShellyBlockAttributeEntity,
    ShellyRestAttributeEntity,
    ShellyRpcAttributeEntity,
    ShellySleepingBlockAttributeEntity,
    ShellySleepingRpcAttributeEntity,
    async_setup_entry_attribute_entities,
    async_setup_entry_rest,
    async_setup_entry_rpc,
    get_entity_rpc_device_info,
)
from .utils import (
    async_remove_orphaned_entities,
    get_blu_trv_device_info,
    get_device_entry_gen,
    get_device_uptime,
    get_shelly_air_lamp_life,
    get_virtual_component_ids,
    is_rpc_wifi_stations_disabled,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BlockSensorDescription(BlockEntityDescription, SensorEntityDescription):
    """Class to describe a BLOCK sensor."""


@dataclass(frozen=True, kw_only=True)
class RpcSensorDescription(RpcEntityDescription, SensorEntityDescription):
    """Class to describe a RPC sensor."""

    device_class_fn: Callable[[dict], SensorDeviceClass | None] | None = None
    emeter_phase: str | None = None


@dataclass(frozen=True, kw_only=True)
class RestSensorDescription(RestEntityDescription, SensorEntityDescription):
    """Class to describe a REST sensor."""


class RpcSensor(ShellyRpcAttributeEntity, SensorEntity):
    """Represent a RPC sensor."""

    entity_description: RpcSensorDescription

    def __init__(
        self,
        coordinator: ShellyRpcCoordinator,
        key: str,
        attribute: str,
        description: RpcSensorDescription,
    ) -> None:
        """Initialize select."""
        super().__init__(coordinator, key, attribute, description)

        if self.option_map:
            self._attr_options = list(self.option_map.values())

        if description.device_class_fn is not None:
            if device_class := description.device_class_fn(
                coordinator.device.config[key]
            ):
                self._attr_device_class = device_class

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        attribute_value = self.attribute_value

        if not self.option_map:
            return attribute_value

        if not isinstance(attribute_value, str):
            return None

        return self.option_map[attribute_value]


class RpcEmeterPhaseSensor(RpcSensor):
    """Represent a RPC energy meter phase sensor."""

    entity_description: RpcSensorDescription

    def __init__(
        self,
        coordinator: ShellyRpcCoordinator,
        key: str,
        attribute: str,
        description: RpcSensorDescription,
    ) -> None:
        """Initialize select."""
        super().__init__(coordinator, key, attribute, description)

        self._attr_device_info = get_entity_rpc_device_info(
            coordinator, key, emeter_phase=description.emeter_phase
        )


class RpcBluTrvSensor(RpcSensor):
    """Represent a RPC BluTrv sensor."""

    def __init__(
        self,
        coordinator: ShellyRpcCoordinator,
        key: str,
        attribute: str,
        description: RpcSensorDescription,
    ) -> None:
        """Initialize."""

        super().__init__(coordinator, key, attribute, description)
        ble_addr: str = coordinator.device.config[key]["addr"]
        self._attr_device_info = get_blu_trv_device_info(
            coordinator.device.config[key], ble_addr, coordinator.mac
        )


SENSORS: dict[tuple[str, str], BlockSensorDescription] = {
    ("device", "battery"): BlockSensorDescription(
        key="device|battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        removal_condition=lambda settings, _: settings.get("external_power") == 1,
        available=lambda block: cast(int, block.battery) != -1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("device", "deviceTemp"): BlockSensorDescription(
        key="device|deviceTemp",
        name="Device temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("emeter", "current"): BlockSensorDescription(
        key="emeter|current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("device", "neutralCurrent"): BlockSensorDescription(
        key="device|neutralCurrent",
        name="Neutral current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ("light", "power"): BlockSensorDescription(
        key="light|power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ("device", "power"): BlockSensorDescription(
        key="device|power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("emeter", "power"): BlockSensorDescription(
        key="emeter|power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("device", "voltage"): BlockSensorDescription(
        key="device|voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    ("emeter", "voltage"): BlockSensorDescription(
        key="emeter|voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("emeter", "powerFactor"): BlockSensorDescription(
        key="emeter|powerFactor",
        name="Power factor",
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("relay", "power"): BlockSensorDescription(
        key="relay|power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("roller", "rollerPower"): BlockSensorDescription(
        key="roller|rollerPower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("device", "energy"): BlockSensorDescription(
        key="device|energy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda value: value / 60,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("emeter", "energy"): BlockSensorDescription(
        key="emeter|energy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        available=lambda block: cast(int, block.energy) != -1,
    ),
    ("emeter", "energyReturned"): BlockSensorDescription(
        key="emeter|energyReturned",
        name="Energy returned",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        available=lambda block: cast(int, block.energyReturned) != -1,
    ),
    ("light", "energy"): BlockSensorDescription(
        key="light|energy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda value: value / 60,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    ("relay", "energy"): BlockSensorDescription(
        key="relay|energy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda value: value / 60,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("roller", "rollerEnergy"): BlockSensorDescription(
        key="roller|rollerEnergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda value: value / 60,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("sensor", "concentration"): BlockSensorDescription(
        key="sensor|concentration",
        name="Gas concentration",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        translation_key="gas_concentration",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("sensor", "temp"): BlockSensorDescription(
        key="sensor|temp",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("sensor", "extTemp"): BlockSensorDescription(
        key="sensor|extTemp",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        available=lambda block: cast(int, block.extTemp) != 999
        and not getattr(block, "sensorError", False),
    ),
    ("sensor", "humidity"): BlockSensorDescription(
        key="sensor|humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        available=lambda block: cast(int, block.humidity) != 999
        and not getattr(block, "sensorError", False),
    ),
    ("sensor", "luminosity"): BlockSensorDescription(
        key="sensor|luminosity",
        name="Luminosity",
        native_unit_of_measurement=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        available=lambda block: cast(int, block.luminosity) != -1,
    ),
    ("sensor", "tilt"): BlockSensorDescription(
        key="sensor|tilt",
        name="Tilt",
        native_unit_of_measurement=DEGREE,
        translation_key="tilt",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("relay", "totalWorkTime"): BlockSensorDescription(
        key="relay|totalWorkTime",
        name="Lamp life",
        native_unit_of_measurement=PERCENTAGE,
        translation_key="lamp_life",
        value=get_shelly_air_lamp_life,
        suggested_display_precision=1,
        # Deprecated, remove in 2025.10
        extra_state_attributes=lambda block: {
            "Operational hours": round(cast(int, block.totalWorkTime) / 3600, 1)
        },
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("adc", "adc"): BlockSensorDescription(
        key="adc|adc",
        name="ADC",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("sensor", "sensorOp"): BlockSensorDescription(
        key="sensor|sensorOp",
        name="Operation",
        device_class=SensorDeviceClass.ENUM,
        options=["warmup", "normal", "fault"],
        translation_key="operation",
        value=lambda value: None if value == "unknown" else value,
        # Deprecated, remove in 2025.10
        extra_state_attributes=lambda block: {"self_test": block.selfTest},
    ),
    ("valve", "valve"): BlockSensorDescription(
        key="valve|valve",
        name="Valve status",
        translation_key="valve_status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "checking",
            "closed",
            "closing",
            "failure",
            "opened",
            "opening",
        ],
        value=lambda value: None if value == "unknown" else value,
        entity_category=EntityCategory.DIAGNOSTIC,
        removal_condition=lambda _, block: block.valve == "not_connected",
    ),
    ("sensor", "gas"): BlockSensorDescription(
        key="sensor|gas",
        name="Gas detected",
        translation_key="gas_detected",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "none",
            "mild",
            "heavy",
            "test",
        ],
        value=lambda value: None if value == "unknown" else value,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("sensor", "selfTest"): BlockSensorDescription(
        key="sensor|selfTest",
        name="Self test",
        translation_key="self_test",
        device_class=SensorDeviceClass.ENUM,
        options=["not_completed", "completed", "running", "pending"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

REST_SENSORS: Final = {
    "rssi": RestSensorDescription(
        key="rssi",
        name="RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value=lambda status, _: status["wifi_sta"]["rssi"],
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "uptime": RestSensorDescription(
        key="uptime",
        name="Uptime",
        value=lambda status, last: get_device_uptime(status["uptime"], last),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


RPC_SENSORS: Final = {
    "power": RpcSensorDescription(
        key="switch",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_em1": RpcSensorDescription(
        key="em1",
        sub_key="act_power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_light": RpcSensorDescription(
        key="light",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_cct": RpcSensorDescription(
        key="cct",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_rgb": RpcSensorDescription(
        key="rgb",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_rgbw": RpcSensorDescription(
        key="rgbw",
        sub_key="apower",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "a_act_power": RpcSensorDescription(
        key="em",
        sub_key="a_act_power",
        name="Active power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_act_power": RpcSensorDescription(
        key="em",
        sub_key="b_act_power",
        name="Active power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_act_power": RpcSensorDescription(
        key="em",
        sub_key="c_act_power",
        name="Active power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "total_act_power": RpcSensorDescription(
        key="em",
        sub_key="total_act_power",
        name="Total active power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "a_aprt_power": RpcSensorDescription(
        key="em",
        sub_key="a_aprt_power",
        name="Apparent power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_aprt_power": RpcSensorDescription(
        key="em",
        sub_key="b_aprt_power",
        name="Apparent power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_aprt_power": RpcSensorDescription(
        key="em",
        sub_key="c_aprt_power",
        name="Apparent power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "aprt_power_em1": RpcSensorDescription(
        key="em1",
        sub_key="aprt_power",
        name="Apparent power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "total_aprt_power": RpcSensorDescription(
        key="em",
        sub_key="total_aprt_power",
        name="Total apparent power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "pf_em1": RpcSensorDescription(
        key="em1",
        sub_key="pf",
        name="Power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "a_pf": RpcSensorDescription(
        key="em",
        sub_key="a_pf",
        name="Power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_pf": RpcSensorDescription(
        key="em",
        sub_key="b_pf",
        name="Power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_pf": RpcSensorDescription(
        key="em",
        sub_key="c_pf",
        name="Power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "voltage": RpcSensorDescription(
        key="switch",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_em1": RpcSensorDescription(
        key="em1",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_light": RpcSensorDescription(
        key="light",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_cct": RpcSensorDescription(
        key="cct",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_rgb": RpcSensorDescription(
        key="rgb",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "voltage_rgbw": RpcSensorDescription(
        key="rgbw",
        sub_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: None if status is None else float(status),
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "a_voltage": RpcSensorDescription(
        key="em",
        sub_key="a_voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_voltage": RpcSensorDescription(
        key="em",
        sub_key="b_voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_voltage": RpcSensorDescription(
        key="em",
        sub_key="c_voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "current": RpcSensorDescription(
        key="switch",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_em1": RpcSensorDescription(
        key="em1",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_light": RpcSensorDescription(
        key="light",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_cct": RpcSensorDescription(
        key="cct",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_rgb": RpcSensorDescription(
        key="rgb",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "current_rgbw": RpcSensorDescription(
        key="rgbw",
        sub_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda status, _: None if status is None else float(status),
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "a_current": RpcSensorDescription(
        key="em",
        sub_key="a_current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_current": RpcSensorDescription(
        key="em",
        sub_key="b_current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_current": RpcSensorDescription(
        key="em",
        sub_key="c_current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "n_current": RpcSensorDescription(
        key="em",
        sub_key="n_current",
        name="Phase N current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        removal_condition=lambda _config, status, key: status[key].get("n_current")
        is None,
        entity_registry_enabled_default=False,
    ),
    "total_current": RpcSensorDescription(
        key="em",
        sub_key="total_current",
        name="Total current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "energy": RpcSensorDescription(
        key="switch",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "ret_energy": RpcSensorDescription(
        key="switch",
        sub_key="ret_aenergy",
        name="Returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        removal_condition=lambda _config, status, key: (
            status[key].get("ret_aenergy") is None
        ),
    ),
    "energy_light": RpcSensorDescription(
        key="light",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "energy_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "ret_energy_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="ret_aenergy",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "energy_cct": RpcSensorDescription(
        key="cct",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "energy_rgb": RpcSensorDescription(
        key="rgb",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "energy_rgbw": RpcSensorDescription(
        key="rgbw",
        sub_key="aenergy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: status["total"],
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "total_act": RpcSensorDescription(
        key="emdata",
        sub_key="total_act",
        name="Total active energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "total_act_energy": RpcSensorDescription(
        key="em1data",
        sub_key="total_act_energy",
        name="Total active energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "a_total_act_energy": RpcSensorDescription(
        key="emdata",
        sub_key="a_total_act_energy",
        name="Total active energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_total_act_energy": RpcSensorDescription(
        key="emdata",
        sub_key="b_total_act_energy",
        name="Total active energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_total_act_energy": RpcSensorDescription(
        key="emdata",
        sub_key="c_total_act_energy",
        name="Total active energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "total_act_ret": RpcSensorDescription(
        key="emdata",
        sub_key="total_act_ret",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "total_act_ret_energy": RpcSensorDescription(
        key="em1data",
        sub_key="total_act_ret_energy",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "a_total_act_ret_energy": RpcSensorDescription(
        key="emdata",
        sub_key="a_total_act_ret_energy",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_total_act_ret_energy": RpcSensorDescription(
        key="emdata",
        sub_key="b_total_act_ret_energy",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_total_act_ret_energy": RpcSensorDescription(
        key="emdata",
        sub_key="c_total_act_ret_energy",
        name="Total active returned energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "freq": RpcSensorDescription(
        key="switch",
        sub_key="freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "freq_em1": RpcSensorDescription(
        key="em1",
        sub_key="freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "freq_pm1": RpcSensorDescription(
        key="pm1",
        sub_key="freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "a_freq": RpcSensorDescription(
        key="em",
        sub_key="a_freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="A",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "b_freq": RpcSensorDescription(
        key="em",
        sub_key="b_freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="B",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "c_freq": RpcSensorDescription(
        key="em",
        sub_key="c_freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        emeter_phase="C",
        entity_class=RpcEmeterPhaseSensor,
    ),
    "illuminance": RpcSensorDescription(
        key="illuminance",
        sub_key="lux",
        name="Illuminance",
        native_unit_of_measurement=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "temperature": RpcSensorDescription(
        key="switch",
        sub_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda status, _: status["tC"],
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "temperature_light": RpcSensorDescription(
        key="light",
        sub_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda status, _: status["tC"],
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "temperature_cct": RpcSensorDescription(
        key="cct",
        sub_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda status, _: status["tC"],
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "temperature_rgb": RpcSensorDescription(
        key="rgb",
        sub_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda status, _: status["tC"],
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "temperature_rgbw": RpcSensorDescription(
        key="rgbw",
        sub_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda status, _: status["tC"],
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "temperature_0": RpcSensorDescription(
        key="temperature",
        sub_key="tC",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "rssi": RpcSensorDescription(
        key="wifi",
        sub_key="rssi",
        name="RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        removal_condition=is_rpc_wifi_stations_disabled,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "uptime": RpcSensorDescription(
        key="sys",
        sub_key="uptime",
        name="Uptime",
        value=get_device_uptime,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        use_polling_coordinator=True,
    ),
    "humidity_0": RpcSensorDescription(
        key="humidity",
        sub_key="rh",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery": RpcSensorDescription(
        key="devicepower",
        sub_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        value=lambda status, _: status["percent"],
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        removal_condition=lambda _config, status, key: (status[key]["battery"] is None),
    ),
    "voltmeter": RpcSensorDescription(
        key="voltmeter",
        sub_key="voltage",
        name="Voltmeter",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value=lambda status, _: float(status),
        suggested_display_precision=2,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        available=lambda status: status is not None,
    ),
    "voltmeter_value": RpcSensorDescription(
        key="voltmeter",
        sub_key="xvoltage",
        name="Voltmeter value",
        removal_condition=lambda _config, status, key: (
            status[key].get("xvoltage") is None
        ),
        unit=lambda config: config["xvoltage"]["unit"] or None,
    ),
    "analoginput": RpcSensorDescription(
        key="input",
        sub_key="percent",
        name="analog",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        removal_condition=lambda config, _, key: (
            config[key]["type"] != "analog" or config[key]["enable"] is False
        ),
    ),
    "analoginput_xpercent": RpcSensorDescription(
        key="input",
        sub_key="xpercent",
        name="analog value",
        removal_condition=lambda config, status, key: (
            config[key]["type"] != "analog"
            or config[key]["enable"] is False
            or status[key].get("xpercent") is None
        ),
        unit=lambda config: config["xpercent"]["unit"] or None,
    ),
    "pulse_counter": RpcSensorDescription(
        key="input",
        sub_key="counts",
        name="pulse counter",
        native_unit_of_measurement="pulse",
        state_class=SensorStateClass.TOTAL,
        value=lambda status, _: status["total"],
        removal_condition=lambda config, _status, key: (
            config[key]["type"] != "count" or config[key]["enable"] is False
        ),
    ),
    "counter_value": RpcSensorDescription(
        key="input",
        sub_key="counts",
        name="counter value",
        value=lambda status, _: status["xtotal"],
        removal_condition=lambda config, status, key: (
            config[key]["type"] != "count"
            or config[key]["enable"] is False
            or status[key]["counts"].get("xtotal") is None
        ),
        unit=lambda config: config["xcounts"]["unit"] or None,
    ),
    "counter_frequency": RpcSensorDescription(
        key="input",
        sub_key="freq",
        name="pulse counter frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        removal_condition=lambda config, _, key: (
            config[key]["type"] != "count" or config[key]["enable"] is False
        ),
    ),
    "counter_frequency_value": RpcSensorDescription(
        key="input",
        sub_key="xfreq",
        name="pulse counter frequency value",
        removal_condition=lambda config, status, key: (
            config[key]["type"] != "count"
            or config[key]["enable"] is False
            or status[key].get("xfreq") is None
        ),
        unit=lambda config: config["xfreq"]["unit"] or None,
    ),
    "text": RpcSensorDescription(
        key="text",
        sub_key="value",
    ),
    "number": RpcSensorDescription(
        key="number",
        sub_key="value",
        unit=lambda config: config["meta"]["ui"]["unit"]
        if config["meta"]["ui"]["unit"]
        else None,
        device_class_fn=lambda config: ROLE_TO_DEVICE_CLASS_MAP.get(config["role"])
        if "role" in config
        else None,
    ),
    "enum": RpcSensorDescription(
        key="enum",
        sub_key="value",
        options_fn=lambda config: config["options"],
        device_class=SensorDeviceClass.ENUM,
    ),
    "valve_position": RpcSensorDescription(
        key="blutrv",
        sub_key="pos",
        name="Valve position",
        translation_key="valve_position",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        removal_condition=lambda config, _status, key: config[key].get("enable", False)
        is False,
        entity_class=RpcBluTrvSensor,
    ),
    "blutrv_battery": RpcSensorDescription(
        key="blutrv",
        sub_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_class=RpcBluTrvSensor,
    ),
    "blutrv_rssi": RpcSensorDescription(
        key="blutrv",
        sub_key="rssi",
        name="Signal strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_class=RpcBluTrvSensor,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ShellyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for device."""
    if get_device_entry_gen(config_entry) in RPC_GENERATIONS:
        if config_entry.data[CONF_SLEEP_PERIOD]:
            async_setup_entry_rpc(
                hass,
                config_entry,
                async_add_entities,
                RPC_SENSORS,
                RpcSleepingSensor,
            )
        else:
            coordinator = config_entry.runtime_data.rpc
            assert coordinator

            async_setup_entry_rpc(
                hass, config_entry, async_add_entities, RPC_SENSORS, RpcSensor
            )

            async_remove_orphaned_entities(
                hass,
                config_entry.entry_id,
                coordinator.mac,
                SENSOR_PLATFORM,
                coordinator.device.status,
            )

            # the user can remove virtual components from the device configuration, so
            # we need to remove orphaned entities
            virtual_component_ids = get_virtual_component_ids(
                coordinator.device.config, SENSOR_PLATFORM
            )
            for component in ("enum", "number", "text"):
                async_remove_orphaned_entities(
                    hass,
                    config_entry.entry_id,
                    coordinator.mac,
                    SENSOR_PLATFORM,
                    virtual_component_ids,
                    component,
                )
        return

    if config_entry.data[CONF_SLEEP_PERIOD]:
        async_setup_entry_attribute_entities(
            hass,
            config_entry,
            async_add_entities,
            SENSORS,
            BlockSleepingSensor,
        )
    else:
        async_setup_entry_attribute_entities(
            hass,
            config_entry,
            async_add_entities,
            SENSORS,
            BlockSensor,
        )
        async_setup_entry_rest(
            hass, config_entry, async_add_entities, REST_SENSORS, RestSensor
        )


class BlockSensor(ShellyBlockAttributeEntity, SensorEntity):
    """Represent a block sensor."""

    entity_description: BlockSensorDescription

    def __init__(
        self,
        coordinator: ShellyBlockCoordinator,
        block: Block,
        attribute: str,
        description: BlockSensorDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, block, attribute, description)

        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        return self.attribute_value


class RestSensor(ShellyRestAttributeEntity, SensorEntity):
    """Represent a REST sensor."""

    entity_description: RestSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        return self.attribute_value


class BlockSleepingSensor(ShellySleepingBlockAttributeEntity, RestoreSensor):
    """Represent a block sleeping sensor."""

    entity_description: BlockSensorDescription

    def __init__(
        self,
        coordinator: ShellyBlockCoordinator,
        block: Block | None,
        attribute: str,
        description: BlockSensorDescription,
        entry: RegistryEntry | None = None,
    ) -> None:
        """Initialize the sleeping sensor."""
        super().__init__(coordinator, block, attribute, description, entry)
        self.restored_data: SensorExtraStoredData | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_sensor_data()

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        if self.block is not None:
            return self.attribute_value

        if self.restored_data is None:
            return None

        return cast(StateType, self.restored_data.native_value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        if self.block is not None:
            return self.entity_description.native_unit_of_measurement

        if self.restored_data is None:
            return None

        return self.restored_data.native_unit_of_measurement


class RpcSleepingSensor(ShellySleepingRpcAttributeEntity, RestoreSensor):
    """Represent a RPC sleeping sensor."""

    entity_description: RpcSensorDescription

    def __init__(
        self,
        coordinator: ShellyRpcCoordinator,
        key: str,
        attribute: str,
        description: RpcEntityDescription,
        entry: RegistryEntry | None = None,
    ) -> None:
        """Initialize the sleeping sensor."""
        super().__init__(coordinator, key, attribute, description, entry)
        self.restored_data: SensorExtraStoredData | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_sensor_data()

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        if self.coordinator.device.initialized:
            return self.attribute_value

        if self.restored_data is None:
            return None

        return cast(StateType, self.restored_data.native_value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        return self.entity_description.native_unit_of_measurement
