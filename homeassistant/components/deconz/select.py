"""Support for deCONZ select entities."""

from __future__ import annotations

from pydeconz.models.event import EventType
from pydeconz.models.sensor.air_purifier import AirPurifier, AirPurifierFanMode
from pydeconz.models.sensor.presence import (
    Presence,
    PresenceConfigDeviceMode,
    PresenceConfigSensitivity,
    PresenceConfigTriggerDistance,
)

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN, SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeconzConfigEntry
from .entity import DeconzDevice

SENSITIVITY_TO_DECONZ = {
    "High": PresenceConfigSensitivity.HIGH.value,
    "Medium": PresenceConfigSensitivity.MEDIUM.value,
    "Low": PresenceConfigSensitivity.LOW.value,
}
DECONZ_TO_SENSITIVITY = {value: key for key, value in SENSITIVITY_TO_DECONZ.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeconzConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the deCONZ button entity."""
    hub = config_entry.runtime_data
    hub.entities[SELECT_DOMAIN] = set()

    @callback
    def async_add_air_purifier_sensor(_: EventType, sensor_id: str) -> None:
        """Add air purifier select entity from deCONZ."""
        sensor = hub.api.sensors.air_purifier[sensor_id]
        async_add_entities([DeconzAirPurifierFanMode(sensor, hub)])

    hub.register_platform_add_device_callback(
        async_add_air_purifier_sensor,
        hub.api.sensors.air_purifier,
    )

    @callback
    def async_add_presence_sensor(_: EventType, sensor_id: str) -> None:
        """Add presence select entity from deCONZ."""
        sensor = hub.api.sensors.presence[sensor_id]
        if sensor.presence_event is not None:
            async_add_entities(
                [
                    DeconzPresenceDeviceModeSelect(sensor, hub),
                    DeconzPresenceSensitivitySelect(sensor, hub),
                    DeconzPresenceTriggerDistanceSelect(sensor, hub),
                ]
            )

    hub.register_platform_add_device_callback(
        async_add_presence_sensor,
        hub.api.sensors.presence,
    )


class DeconzAirPurifierFanMode(DeconzDevice[AirPurifier], SelectEntity):
    """Representation of a deCONZ air purifier fan mode entity."""

    _name_suffix = "Fan Mode"
    unique_id_suffix = "fan_mode"
    _update_key = "mode"

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [
        AirPurifierFanMode.OFF.value,
        AirPurifierFanMode.AUTO.value,
        AirPurifierFanMode.SPEED_1.value,
        AirPurifierFanMode.SPEED_2.value,
        AirPurifierFanMode.SPEED_3.value,
        AirPurifierFanMode.SPEED_4.value,
        AirPurifierFanMode.SPEED_5.value,
    ]

    TYPE = SELECT_DOMAIN

    @property
    def current_option(self) -> str:
        """Return the selected entity option to represent the entity state."""
        return self._device.fan_mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.hub.api.sensors.air_purifier.set_config(
            id=self._device.resource_id,
            fan_mode=AirPurifierFanMode(option),
        )


class DeconzPresenceDeviceModeSelect(DeconzDevice[Presence], SelectEntity):
    """Representation of a deCONZ presence device mode entity."""

    _name_suffix = "Device Mode"
    unique_id_suffix = "device_mode"
    _update_key = "devicemode"

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [
        PresenceConfigDeviceMode.LEFT_AND_RIGHT.value,
        PresenceConfigDeviceMode.UNDIRECTED.value,
    ]

    TYPE = SELECT_DOMAIN

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if self._device.device_mode is not None:
            return self._device.device_mode.value
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.hub.api.sensors.presence.set_config(
            id=self._device.resource_id,
            device_mode=PresenceConfigDeviceMode(option),
        )


class DeconzPresenceSensitivitySelect(DeconzDevice[Presence], SelectEntity):
    """Representation of a deCONZ presence sensitivity entity."""

    _name_suffix = "Sensitivity"
    unique_id_suffix = "sensitivity"
    _update_key = "sensitivity"

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(SENSITIVITY_TO_DECONZ)

    TYPE = SELECT_DOMAIN

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if self._device.sensitivity is not None:
            return DECONZ_TO_SENSITIVITY[self._device.sensitivity]
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.hub.api.sensors.presence.set_config(
            id=self._device.resource_id,
            sensitivity=SENSITIVITY_TO_DECONZ[option],
        )


class DeconzPresenceTriggerDistanceSelect(DeconzDevice[Presence], SelectEntity):
    """Representation of a deCONZ presence trigger distance entity."""

    _name_suffix = "Trigger Distance"
    unique_id_suffix = "trigger_distance"
    _update_key = "triggerdistance"

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [
        PresenceConfigTriggerDistance.FAR.value,
        PresenceConfigTriggerDistance.MEDIUM.value,
        PresenceConfigTriggerDistance.NEAR.value,
    ]

    TYPE = SELECT_DOMAIN

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if self._device.trigger_distance is not None:
            return self._device.trigger_distance.value
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.hub.api.sensors.presence.set_config(
            id=self._device.resource_id,
            trigger_distance=PresenceConfigTriggerDistance(option),
        )
