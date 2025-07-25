"""Config flow for RSS/Atom feeds."""

from __future__ import annotations

import html
import logging
from typing import Any
import urllib.error

import feedparser
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_MAX_ENTRIES, DEFAULT_MAX_ENTRIES, DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_fetch_feed(hass: HomeAssistant, url: str) -> feedparser.FeedParserDict:
    """Fetch the feed."""
    return await hass.async_add_executor_job(feedparser.parse, url)


class FeedReaderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> FeedReaderOptionsFlowHandler:
        """Get the options flow for this handler."""
        return FeedReaderOptionsFlowHandler()

    def show_user_form(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
        description_placeholders: dict[str, str] | None = None,
        step_id: str = "user",
    ) -> ConfigFlowResult:
        """Show the user form."""
        if user_input is None:
            user_input = {}
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_URL, default=user_input.get(CONF_URL, "")
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
                }
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if not user_input:
            return self.show_user_form()

        self._async_abort_entries_match({CONF_URL: user_input[CONF_URL]})

        feed = await async_fetch_feed(self.hass, user_input[CONF_URL])

        if feed.bozo:
            LOGGER.debug("feed bozo_exception: %s", feed.bozo_exception)
            if isinstance(feed.bozo_exception, urllib.error.URLError):
                return self.show_user_form(user_input, {"base": "url_error"})

        feed_title = html.unescape(feed["feed"]["title"])

        return self.async_create_entry(
            title=feed_title,
            data=user_input,
            options={CONF_MAX_ENTRIES: DEFAULT_MAX_ENTRIES},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        reconfigure_entry = self._get_reconfigure_entry()
        if not user_input:
            return self.show_user_form(
                user_input={**reconfigure_entry.data},
                description_placeholders={"name": reconfigure_entry.title},
                step_id="reconfigure",
            )

        feed = await async_fetch_feed(self.hass, user_input[CONF_URL])

        if feed.bozo:
            LOGGER.debug("feed bozo_exception: %s", feed.bozo_exception)
            if isinstance(feed.bozo_exception, urllib.error.URLError):
                return self.show_user_form(
                    user_input=user_input,
                    description_placeholders={"name": reconfigure_entry.title},
                    step_id="reconfigure",
                    errors={"base": "url_error"},
                )

        return self.async_update_reload_and_abort(reconfigure_entry, data=user_input)


class FeedReaderOptionsFlowHandler(OptionsFlowWithReload):
    """Handle an options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MAX_ENTRIES,
                    default=self.config_entry.options.get(
                        CONF_MAX_ENTRIES, DEFAULT_MAX_ENTRIES
                    ),
                ): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
