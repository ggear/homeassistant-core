"""Support for Hydrawise cloud switches."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydrawise import Controller, HydrawiseBase, Zone

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_WATERING_TIME
from .coordinator import HydrawiseConfigEntry
from .entity import HydrawiseEntity


@dataclass(frozen=True, kw_only=True)
class HydrawiseSwitchEntityDescription(SwitchEntityDescription):
    """Describes Hydrawise binary sensor."""

    turn_on_fn: Callable[[HydrawiseBase, Zone], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[HydrawiseBase, Zone], Coroutine[Any, Any, None]]
    value_fn: Callable[[Zone], bool]


SWITCH_TYPES: tuple[HydrawiseSwitchEntityDescription, ...] = (
    HydrawiseSwitchEntityDescription(
        key="auto_watering",
        translation_key="auto_watering",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=lambda zone: zone.status.suspended_until is None,
        turn_on_fn=lambda api, zone: api.resume_zone(zone),
        turn_off_fn=lambda api, zone: api.suspend_zone(
            zone, dt_util.now() + timedelta(days=365)
        ),
    ),
    HydrawiseSwitchEntityDescription(
        key="manual_watering",
        translation_key="manual_watering",
        device_class=SwitchDeviceClass.SWITCH,
        value_fn=lambda zone: zone.scheduled_runs.current_run is not None,
        turn_on_fn=lambda api, zone: api.start_zone(
            zone,
            custom_run_duration=int(DEFAULT_WATERING_TIME.total_seconds()),
        ),
        turn_off_fn=lambda api, zone: api.stop_zone(zone),
    ),
)

SWITCH_KEYS: list[str] = [desc.key for desc in SWITCH_TYPES]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HydrawiseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Hydrawise switch platform."""
    coordinators = config_entry.runtime_data

    def _add_new_zones(zones: Iterable[tuple[Zone, Controller]]) -> None:
        async_add_entities(
            HydrawiseSwitch(coordinators.main, description, controller, zone_id=zone.id)
            for zone, controller in zones
            for description in SWITCH_TYPES
        )

    _add_new_zones(
        [
            (zone, coordinators.main.data.zone_id_to_controller[zone.id])
            for zone in coordinators.main.data.zones.values()
        ]
    )
    coordinators.main.new_zones_callbacks.append(_add_new_zones)


class HydrawiseSwitch(HydrawiseEntity, SwitchEntity):
    """A switch implementation for Hydrawise device."""

    entity_description: HydrawiseSwitchEntityDescription
    zone: Zone

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await self.entity_description.turn_on_fn(self.coordinator.api, self.zone)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self.entity_description.turn_off_fn(self.coordinator.api, self.zone)
        self._attr_is_on = False
        self.async_write_ha_state()

    def _update_attrs(self) -> None:
        """Update state attributes."""
        self._attr_is_on = self.entity_description.value_fn(self.zone)
