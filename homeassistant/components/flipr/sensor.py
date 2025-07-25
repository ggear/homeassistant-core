"""Sensor platform for the Flipr's pool_sensor."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FliprConfigEntry
from .entity import FliprEntity

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="chlorine",
        translation_key="chlorine",
        native_unit_of_measurement="mg/L",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="date_time",
        translation_key="last_measured",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="red_ox",
        translation_key="red_ox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FliprConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Defer sensor setup to the shared sensor module."""
    coordinators = config_entry.runtime_data.flipr_coordinators

    async_add_entities(
        FliprSensor(coordinator, description)
        for description in SENSOR_TYPES
        for coordinator in coordinators
    )


class FliprSensor(FliprEntity, SensorEntity):
    """Sensor representing FliprSensor data."""

    @property
    def native_value(self) -> str:
        """State of the sensor."""
        return self.coordinator.data[self.entity_description.key]
