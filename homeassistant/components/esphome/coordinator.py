"""Coordinator to interact with an ESPHome dashboard."""

from __future__ import annotations

from datetime import timedelta
import logging

from awesomeversion import AwesomeVersion
from esphome_dashboard_api import ConfiguredDevice, ESPHomeDashboardAPI

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

MIN_VERSION_SUPPORTS_UPDATE = AwesomeVersion("2023.1.0")
REFRESH_INTERVAL = timedelta(minutes=5)


class ESPHomeDashboardCoordinator(DataUpdateCoordinator[dict[str, ConfiguredDevice]]):
    """Class to interact with the ESPHome dashboard."""

    def __init__(self, hass: HomeAssistant, addon_slug: str, url: str) -> None:
        """Initialize the dashboard coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=None,
            name="ESPHome Dashboard",
            update_interval=REFRESH_INTERVAL,
            always_update=False,
        )
        self.addon_slug = addon_slug
        self.url = url
        self.api = ESPHomeDashboardAPI(url, async_get_clientsession(hass))
        self.supports_update: bool | None = None

    async def _async_update_data(self) -> dict[str, ConfiguredDevice]:
        """Fetch device data."""
        devices = await self.api.get_devices()
        configured_devices = devices["configured"]

        if (
            self.supports_update is None
            and configured_devices
            and (current_version := configured_devices[0].get("current_version"))
        ):
            self.supports_update = (
                AwesomeVersion(current_version) > MIN_VERSION_SUPPORTS_UPDATE
            )

        return {dev["name"]: dev for dev in configured_devices}
