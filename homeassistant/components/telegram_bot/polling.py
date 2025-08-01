"""Support for Telegram bot using polling."""

import logging

from telegram import Bot, Update
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ApplicationBuilder, CallbackContext, TypeHandler

from homeassistant.core import HomeAssistant

from .bot import BaseTelegramBot, TelegramBotConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant, bot: Bot, config: TelegramBotConfigEntry
) -> BaseTelegramBot | None:
    """Set up the Telegram polling platform."""
    pollbot = PollBot(hass, bot, config)

    await pollbot.start_polling()

    return pollbot


async def process_error(update: object, context: CallbackContext) -> None:
    """Telegram bot error handler."""
    if context.error:
        error_callback(context.error, update)


def error_callback(error: Exception, update: object | None = None) -> None:
    """Log the error."""
    try:
        raise error
    except (TimedOut, NetworkError, RetryAfter):
        # Long polling timeout or connection problem. Nothing serious.
        pass
    except TelegramError:
        if update is not None:
            _LOGGER.error('Update "%s" caused error: "%s"', update, error)
        else:
            _LOGGER.error("%s: %s", error.__class__.__name__, error)


class PollBot(BaseTelegramBot):
    """Controls the Application object that holds the bot and an updater.

    The application is set up to pass telegram updates to `self.handle_update`
    """

    def __init__(
        self, hass: HomeAssistant, bot: Bot, config: TelegramBotConfigEntry
    ) -> None:
        """Create Application to poll for updates."""
        super().__init__(hass, config)
        self.bot = bot
        self.application = ApplicationBuilder().bot(self.bot).build()
        self.application.add_handler(TypeHandler(Update, self.handle_update))
        self.application.add_error_handler(process_error)

    async def shutdown(self) -> None:
        """Shutdown the app."""
        await self.stop_polling()

    async def start_polling(self) -> None:
        """Start the polling task."""
        _LOGGER.debug("Starting polling")
        await self.application.initialize()
        if self.application.updater:
            await self.application.updater.start_polling(error_callback=error_callback)
        await self.application.start()

    async def stop_polling(self) -> None:
        """Stop the polling task."""
        _LOGGER.debug("Stopping polling")
        if self.application.updater:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
