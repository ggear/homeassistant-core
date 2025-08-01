"""Support for LaMetric time."""

from homeassistant.components import notify as hass_notify
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import LaMetricConfigEntry, LaMetricDataUpdateCoordinator
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the LaMetric integration."""
    async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: LaMetricConfigEntry) -> bool:
    """Set up LaMetric from a config entry."""
    coordinator = LaMetricDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up notify platform, no entry support for notify component yet,
    # have to use discovery to load platform.
    hass.async_create_task(
        discovery.async_load_platform(
            hass,
            Platform.NOTIFY,
            DOMAIN,
            {CONF_NAME: coordinator.data.name, "entry_id": entry.entry_id},
            {},
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LaMetricConfigEntry) -> bool:
    """Unload LaMetric config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass_notify.async_reload(hass, DOMAIN)
    return unload_ok
