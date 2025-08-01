"""Calendar platform for a Remote Calendar."""

from datetime import datetime
import logging

from ical.event import Event
from ical.timeline import Timeline

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import RemoteCalendarConfigEntry
from .const import CONF_CALENDAR_NAME
from .coordinator import RemoteCalendarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemoteCalendarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the remote calendar platform."""
    coordinator = entry.runtime_data
    entity = RemoteCalendarEntity(coordinator, entry)
    async_add_entities([entity], True)


class RemoteCalendarEntity(
    CoordinatorEntity[RemoteCalendarDataUpdateCoordinator], CalendarEntity
):
    """A calendar entity backed by a remote iCalendar url."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RemoteCalendarDataUpdateCoordinator,
        entry: RemoteCalendarConfigEntry,
    ) -> None:
        """Initialize RemoteCalendarEntity."""
        super().__init__(coordinator)
        self._attr_name = entry.data[CONF_CALENDAR_NAME]
        self._attr_unique_id = entry.entry_id
        self._timeline: Timeline | None = None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if self._timeline is None:
            return None
        now = dt_util.now()
        events = self._timeline.active_after(now)
        if event := next(events, None):
            return _get_calendar_event(event)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""

        def events_in_range() -> list[CalendarEvent]:
            """Return all events in the given time range."""
            events = self.coordinator.data.timeline_tz(start_date.tzinfo).overlapping(
                start_date,
                end_date,
            )
            return [_get_calendar_event(event) for event in events]

        return await self.hass.async_add_executor_job(events_in_range)

    async def async_update(self) -> None:
        """Refresh the timeline.

        This is called when the coordinator updates. Creating the timeline may
        require walking through the entire calendar and handling recurring
        events, so it is done as a separate task without blocking the event loop.
        """
        await super().async_update()

        def _get_timeline() -> Timeline | None:
            """Return the next active event."""
            now = dt_util.now()
            return self.coordinator.data.timeline_tz(now.tzinfo)

        self._timeline = await self.hass.async_add_executor_job(_get_timeline)


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Return a CalendarEvent from an API event."""

    return CalendarEvent(
        summary=event.summary or "",
        start=(
            dt_util.as_local(event.start)
            if isinstance(event.start, datetime)
            else event.start
        ),
        end=(
            dt_util.as_local(event.end)
            if isinstance(event.end, datetime)
            else event.end
        ),
        description=event.description,
        uid=event.uid,
        rrule=event.rrule.as_rrule_str() if event.rrule else None,
        recurrence_id=event.recurrence_id,
        location=event.location,
    )
