"""Support for the Abode Security System."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from jaraco.abode.client import Client as Abode
import jaraco.abode.config
from jaraco.abode.exceptions import (
    AuthenticationException as AbodeAuthenticationException,
    Exception as AbodeException,
)
from jaraco.abode.helpers.timeline import Groups as GROUPS
from requests.exceptions import ConnectTimeout, HTTPError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DATE,
    ATTR_DEVICE_ID,
    ATTR_TIME,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_POLLING, DOMAIN, LOGGER
from .services import async_setup_services

ATTR_DEVICE_NAME = "device_name"
ATTR_DEVICE_TYPE = "device_type"
ATTR_EVENT_CODE = "event_code"
ATTR_EVENT_NAME = "event_name"
ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_UTC = "event_utc"
ATTR_USER_NAME = "user_name"
ATTR_APP_TYPE = "app_type"
ATTR_EVENT_BY = "event_by"

CONFIG_SCHEMA = cv.removed(DOMAIN, raise_if_present=False)

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.COVER,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class AbodeSystem:
    """Abode System class."""

    abode: Abode
    polling: bool
    entity_ids: set[str | None] = field(default_factory=set)
    logout_listener: CALLBACK_TYPE | None = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Abode component."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Abode integration from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    polling = entry.data[CONF_POLLING]

    # Configure abode library to use config directory for storing data
    jaraco.abode.config.paths.override(user_data=Path(hass.config.path("Abode")))

    # For previous config entries where unique_id is None
    if entry.unique_id is None:
        hass.config_entries.async_update_entry(
            entry, unique_id=entry.data[CONF_USERNAME]
        )

    try:
        abode = await hass.async_add_executor_job(
            Abode, username, password, True, True, True
        )

    except AbodeAuthenticationException as ex:
        raise ConfigEntryAuthFailed(f"Invalid credentials: {ex}") from ex

    except (AbodeException, ConnectTimeout, HTTPError) as ex:
        raise ConfigEntryNotReady(f"Unable to connect to Abode: {ex}") from ex

    hass.data[DOMAIN] = AbodeSystem(abode, polling)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await setup_hass_events(hass)
    await hass.async_add_executor_job(setup_abode_events, hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    await hass.async_add_executor_job(hass.data[DOMAIN].abode.events.stop)
    await hass.async_add_executor_job(hass.data[DOMAIN].abode.logout)

    hass.data[DOMAIN].logout_listener()
    hass.data.pop(DOMAIN)

    return unload_ok


async def setup_hass_events(hass: HomeAssistant) -> None:
    """Home Assistant start and stop callbacks."""

    def logout(event: Event) -> None:
        """Logout of Abode."""
        if not hass.data[DOMAIN].polling:
            hass.data[DOMAIN].abode.events.stop()

        hass.data[DOMAIN].abode.logout()
        LOGGER.info("Logged out of Abode")

    if not hass.data[DOMAIN].polling:
        await hass.async_add_executor_job(hass.data[DOMAIN].abode.events.start)

    hass.data[DOMAIN].logout_listener = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, logout
    )


def setup_abode_events(hass: HomeAssistant) -> None:
    """Event callbacks."""

    def event_callback(event: str, event_json: dict[str, str]) -> None:
        """Handle an event callback from Abode."""
        data = {
            ATTR_DEVICE_ID: event_json.get(ATTR_DEVICE_ID, ""),
            ATTR_DEVICE_NAME: event_json.get(ATTR_DEVICE_NAME, ""),
            ATTR_DEVICE_TYPE: event_json.get(ATTR_DEVICE_TYPE, ""),
            ATTR_EVENT_CODE: event_json.get(ATTR_EVENT_CODE, ""),
            ATTR_EVENT_NAME: event_json.get(ATTR_EVENT_NAME, ""),
            ATTR_EVENT_TYPE: event_json.get(ATTR_EVENT_TYPE, ""),
            ATTR_EVENT_UTC: event_json.get(ATTR_EVENT_UTC, ""),
            ATTR_USER_NAME: event_json.get(ATTR_USER_NAME, ""),
            ATTR_APP_TYPE: event_json.get(ATTR_APP_TYPE, ""),
            ATTR_EVENT_BY: event_json.get(ATTR_EVENT_BY, ""),
            ATTR_DATE: event_json.get(ATTR_DATE, ""),
            ATTR_TIME: event_json.get(ATTR_TIME, ""),
        }

        hass.bus.fire(event, data)

    events = [
        GROUPS.ALARM,
        GROUPS.ALARM_END,
        GROUPS.PANEL_FAULT,
        GROUPS.PANEL_RESTORE,
        GROUPS.AUTOMATION,
        GROUPS.DISARM,
        GROUPS.ARM,
        GROUPS.ARM_FAULT,
        GROUPS.TEST,
        GROUPS.CAPTURE,
        GROUPS.DEVICE,
    ]

    for event in events:
        hass.data[DOMAIN].abode.events.add_event_callback(
            event, partial(event_callback, event)
        )
