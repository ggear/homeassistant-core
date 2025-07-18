"""DataUpdateCoordinator for the Discovergy integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from pydiscovergy import Discovergy
from pydiscovergy.error import DiscovergyClientError, HTTPError, InvalidLogin
from pydiscovergy.models import Meter, Reading

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type DiscovergyConfigEntry = ConfigEntry[list[DiscovergyUpdateCoordinator]]


class DiscovergyUpdateCoordinator(DataUpdateCoordinator[Reading]):
    """The Discovergy update coordinator."""

    config_entry: DiscovergyConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DiscovergyConfigEntry,
        meter: Meter,
        discovergy_client: Discovergy,
    ) -> None:
        """Initialize the Discovergy coordinator."""
        self.meter = meter
        self.discovergy_client = discovergy_client

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"Discovergy meter {meter.meter_id}",
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> Reading:
        """Get last reading for meter."""
        try:
            return await self.discovergy_client.meter_last_reading(
                meter_id=self.meter.meter_id
            )
        except InvalidLogin as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except (HTTPError, DiscovergyClientError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="reading_update_failed",
                translation_placeholders={"meter_id": self.meter.meter_id},
            ) from err
