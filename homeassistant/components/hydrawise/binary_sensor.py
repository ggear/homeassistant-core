"""Support for Hydrawise sprinkler binary sensors."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from pydrawise import Controller, Zone
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import VolDictType

from .const import SERVICE_RESUME, SERVICE_START_WATERING, SERVICE_SUSPEND
from .coordinator import HydrawiseConfigEntry
from .entity import HydrawiseEntity


@dataclass(frozen=True, kw_only=True)
class HydrawiseBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Hydrawise binary sensor."""

    value_fn: Callable[[HydrawiseBinarySensor], bool | None]
    always_available: bool = False


CONTROLLER_BINARY_SENSORS: tuple[HydrawiseBinarySensorEntityDescription, ...] = (
    HydrawiseBinarySensorEntityDescription(
        key="status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=(
            lambda status_sensor: status_sensor.coordinator.last_update_success
            and status_sensor.controller.online
        ),
        # Connectivtiy sensor is always available
        always_available=True,
    ),
)

RAIN_SENSOR_BINARY_SENSOR: tuple[HydrawiseBinarySensorEntityDescription, ...] = (
    HydrawiseBinarySensorEntityDescription(
        key="rain_sensor",
        translation_key="rain_sensor",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda rain_sensor: rain_sensor.sensor.status.active,
    ),
)

ZONE_BINARY_SENSORS: tuple[HydrawiseBinarySensorEntityDescription, ...] = (
    HydrawiseBinarySensorEntityDescription(
        key="is_watering",
        translation_key="watering",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=(
            lambda watering_sensor: watering_sensor.zone.scheduled_runs.current_run
            is not None
        ),
    ),
)

SCHEMA_START_WATERING: VolDictType = {
    vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
}
SCHEMA_SUSPEND: VolDictType = {
    vol.Required("until"): cv.datetime,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HydrawiseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Hydrawise binary_sensor platform."""
    coordinators = config_entry.runtime_data

    def _add_new_controllers(controllers: Iterable[Controller]) -> None:
        entities: list[HydrawiseBinarySensor] = []
        for controller in controllers:
            entities.extend(
                HydrawiseBinarySensor(coordinators.main, description, controller)
                for description in CONTROLLER_BINARY_SENSORS
            )
            entities.extend(
                HydrawiseBinarySensor(
                    coordinators.main,
                    description,
                    controller,
                    sensor_id=sensor.id,
                )
                for sensor in controller.sensors
                for description in RAIN_SENSOR_BINARY_SENSOR
                if "rain sensor" in sensor.model.name.lower()
            )
        async_add_entities(entities)

    def _add_new_zones(zones: Iterable[tuple[Zone, Controller]]) -> None:
        async_add_entities(
            HydrawiseZoneBinarySensor(
                coordinators.main, description, controller, zone_id=zone.id
            )
            for zone, controller in zones
            for description in ZONE_BINARY_SENSORS
        )

    _add_new_controllers(coordinators.main.data.controllers.values())
    _add_new_zones(
        [
            (zone, coordinators.main.data.zone_id_to_controller[zone.id])
            for zone in coordinators.main.data.zones.values()
        ]
    )
    coordinators.main.new_controllers_callbacks.append(_add_new_controllers)
    coordinators.main.new_zones_callbacks.append(_add_new_zones)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(SERVICE_RESUME, None, "resume")
    platform.async_register_entity_service(
        SERVICE_START_WATERING, SCHEMA_START_WATERING, "start_watering"
    )
    platform.async_register_entity_service(SERVICE_SUSPEND, SCHEMA_SUSPEND, "suspend")


class HydrawiseBinarySensor(HydrawiseEntity, BinarySensorEntity):
    """A sensor implementation for Hydrawise device."""

    entity_description: HydrawiseBinarySensorEntityDescription

    def _update_attrs(self) -> None:
        """Update state attributes."""
        self._attr_is_on = self.entity_description.value_fn(self)

    @property
    def available(self) -> bool:
        """Set the entity availability."""
        if self.entity_description.always_available:
            return True
        return super().available


class HydrawiseZoneBinarySensor(HydrawiseBinarySensor):
    """A binary sensor for a Hydrawise irrigation zone.

    This is only used for irrigation zones, as they have special methods for
    service actions that don't apply to other binary sensors.
    """

    zone: Zone

    async def start_watering(self, duration: int | None = None) -> None:
        """Start watering in the irrigation zone."""
        await self.coordinator.api.start_zone(
            self.zone, custom_run_duration=int((duration or 0) * 60)
        )

    async def suspend(self, until: datetime) -> None:
        """Suspend automatic watering in the irrigation zone."""
        await self.coordinator.api.suspend_zone(self.zone, until=until)

    async def resume(self) -> None:
        """Resume automatic watering in the irrigation zone."""
        await self.coordinator.api.resume_zone(self.zone)
