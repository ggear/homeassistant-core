"""Support for esphome datetimes."""

from __future__ import annotations

from datetime import datetime
from functools import partial

from aioesphomeapi import DateTimeInfo, DateTimeState

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.util import dt as dt_util

from .entity import EsphomeEntity, esphome_state_property, platform_async_setup_entry

PARALLEL_UPDATES = 0


class EsphomeDateTime(EsphomeEntity[DateTimeInfo, DateTimeState], DateTimeEntity):
    """A datetime implementation for esphome."""

    @property
    @esphome_state_property
    def native_value(self) -> datetime | None:
        """Return the state of the entity."""
        state = self._state
        if state.missing_state:
            return None
        return dt_util.utc_from_timestamp(state.epoch_seconds)

    async def async_set_value(self, value: datetime) -> None:
        """Update the current datetime."""
        self._client.datetime_command(
            self._key, int(value.timestamp()), device_id=self._static_info.device_id
        )


async_setup_entry = partial(
    platform_async_setup_entry,
    info_type=DateTimeInfo,
    entity_type=EsphomeDateTime,
    state_type=DateTimeState,
)
