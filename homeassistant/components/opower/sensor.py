"""Support for Opower sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from opower import Forecast, MeterType, UnitOfMeasure

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpowerConfigEntry, OpowerCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OpowerEntityDescription(SensorEntityDescription):
    """Class describing Opower sensors entities."""

    value_fn: Callable[[Forecast], str | float | date]


# suggested_display_precision=0 for all sensors since
# Opower provides 0 decimal points for all these.
# (for the statistics in the energy dashboard Opower does provide decimal points)
ELEC_SENSORS: tuple[OpowerEntityDescription, ...] = (
    OpowerEntityDescription(
        key="elec_usage_to_date",
        translation_key="elec_usage_to_date",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        # Not TOTAL_INCREASING because it can decrease for accounts with solar
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.usage_to_date,
    ),
    OpowerEntityDescription(
        key="elec_forecasted_usage",
        translation_key="elec_forecasted_usage",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.forecasted_usage,
    ),
    OpowerEntityDescription(
        key="elec_typical_usage",
        translation_key="elec_typical_usage",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.typical_usage,
    ),
    OpowerEntityDescription(
        key="elec_cost_to_date",
        translation_key="elec_cost_to_date",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.cost_to_date,
    ),
    OpowerEntityDescription(
        key="elec_forecasted_cost",
        translation_key="elec_forecasted_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.forecasted_cost,
    ),
    OpowerEntityDescription(
        key="elec_typical_cost",
        translation_key="elec_typical_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.typical_cost,
    ),
    OpowerEntityDescription(
        key="elec_start_date",
        translation_key="elec_start_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.start_date,
    ),
    OpowerEntityDescription(
        key="elec_end_date",
        translation_key="elec_end_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.end_date,
    ),
)
GAS_SENSORS: tuple[OpowerEntityDescription, ...] = (
    OpowerEntityDescription(
        key="gas_usage_to_date",
        translation_key="gas_usage_to_date",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CENTUM_CUBIC_FEET,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.usage_to_date,
    ),
    OpowerEntityDescription(
        key="gas_forecasted_usage",
        translation_key="gas_forecasted_usage",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CENTUM_CUBIC_FEET,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.forecasted_usage,
    ),
    OpowerEntityDescription(
        key="gas_typical_usage",
        translation_key="gas_typical_usage",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CENTUM_CUBIC_FEET,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.typical_usage,
    ),
    OpowerEntityDescription(
        key="gas_cost_to_date",
        translation_key="gas_cost_to_date",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.cost_to_date,
    ),
    OpowerEntityDescription(
        key="gas_forecasted_cost",
        translation_key="gas_forecasted_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.forecasted_cost,
    ),
    OpowerEntityDescription(
        key="gas_typical_cost",
        translation_key="gas_typical_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.typical_cost,
    ),
    OpowerEntityDescription(
        key="gas_start_date",
        translation_key="gas_start_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.start_date,
    ),
    OpowerEntityDescription(
        key="gas_end_date",
        translation_key="gas_end_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.end_date,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Opower sensor."""

    coordinator = entry.runtime_data
    entities: list[OpowerSensor] = []
    forecasts = coordinator.data.values()
    for forecast in forecasts:
        device_id = f"{coordinator.api.utility.subdomain()}_{forecast.account.utility_account_id}"
        device = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"{forecast.account.meter_type.name} account {forecast.account.utility_account_id}",
            manufacturer="Opower",
            model=coordinator.api.utility.name(),
            entry_type=DeviceEntryType.SERVICE,
        )
        sensors: tuple[OpowerEntityDescription, ...] = ()
        if (
            forecast.account.meter_type == MeterType.ELEC
            and forecast.unit_of_measure == UnitOfMeasure.KWH
        ):
            sensors = ELEC_SENSORS
        elif (
            forecast.account.meter_type == MeterType.GAS
            and forecast.unit_of_measure in [UnitOfMeasure.THERM, UnitOfMeasure.CCF]
        ):
            sensors = GAS_SENSORS
        entities.extend(
            OpowerSensor(
                coordinator,
                sensor,
                forecast.account.utility_account_id,
                device,
                device_id,
            )
            for sensor in sensors
        )

    async_add_entities(entities)


class OpowerSensor(CoordinatorEntity[OpowerCoordinator], SensorEntity):
    """Representation of an Opower sensor."""

    _attr_has_entity_name = True
    entity_description: OpowerEntityDescription

    def __init__(
        self,
        coordinator: OpowerCoordinator,
        description: OpowerEntityDescription,
        utility_account_id: str,
        device: DeviceInfo,
        device_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = device
        self.utility_account_id = utility_account_id

    @property
    def native_value(self) -> StateType | date:
        """Return the state."""
        return self.entity_description.value_fn(
            self.coordinator.data[self.utility_account_id]
        )
