"""Provide frame helper for finding the current frame context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import enum
import functools
import inspect
import linecache
import logging
import sys
import threading
from types import FrameType
from typing import Any, cast

from propcache.api import cached_property

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import (
    Integration,
    async_get_issue_integration,
    async_suggest_report_issue,
)
from homeassistant.util.async_ import run_callback_threadsafe

_LOGGER = logging.getLogger(__name__)

# Keep track of integrations already reported to prevent flooding
_REPORTED_INTEGRATIONS: set[str] = set()


class _Hass:
    """Container which makes a HomeAssistant instance available to frame helper."""

    hass: HomeAssistant | None = None


_hass = _Hass()


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Set up the frame helper."""
    _hass.hass = hass


@dataclass(kw_only=True)
class IntegrationFrame:
    """Integration frame container."""

    custom_integration: bool
    integration: str
    module: str | None
    relative_filename: str
    frame: FrameType

    @cached_property
    def line_number(self) -> int:
        """Return the line number of the frame."""
        return self.frame.f_lineno

    @cached_property
    def filename(self) -> str:
        """Return the filename of the frame."""
        return self.frame.f_code.co_filename

    @cached_property
    def line(self) -> str:
        """Return the line of the frame."""
        return (linecache.getline(self.filename, self.line_number) or "?").strip()


def get_integration_logger(fallback_name: str) -> logging.Logger:
    """Return a logger by checking the current integration frame.

    If Python is unable to access the sources files, the call stack frame
    will be missing information, so let's guard by requiring a fallback name.
    https://github.com/home-assistant/core/issues/24982
    """
    try:
        integration_frame = get_integration_frame()
    except MissingIntegrationFrame:
        return logging.getLogger(fallback_name)

    if integration_frame.custom_integration:
        logger_name = f"custom_components.{integration_frame.integration}"
    else:
        logger_name = f"homeassistant.components.{integration_frame.integration}"

    return logging.getLogger(logger_name)


def get_current_frame(depth: int = 0) -> FrameType:
    """Return the current frame."""
    # Add one to depth since get_current_frame is included
    return sys._getframe(depth + 1)  # noqa: SLF001


def get_integration_frame(exclude_integrations: set | None = None) -> IntegrationFrame:
    """Return the frame, integration and integration path of the current stack frame."""
    found_frame = None
    if not exclude_integrations:
        exclude_integrations = set()

    frame: FrameType | None = get_current_frame()
    while frame is not None:
        filename = frame.f_code.co_filename

        for path in ("custom_components/", "homeassistant/components/"):
            try:
                index = filename.index(path)
                start = index + len(path)
                end = filename.index("/", start)
                integration = filename[start:end]
                if integration not in exclude_integrations:
                    found_frame = frame

                break
            except ValueError:
                continue

        if found_frame is not None:
            break

        frame = frame.f_back

    if found_frame is None:
        raise MissingIntegrationFrame

    found_module: str | None = None
    for module, module_obj in dict(sys.modules).items():
        if not hasattr(module_obj, "__file__"):
            continue
        if module_obj.__file__ == found_frame.f_code.co_filename:
            found_module = module
            break

    return IntegrationFrame(
        custom_integration=path == "custom_components/",
        integration=integration,
        module=found_module,
        relative_filename=found_frame.f_code.co_filename[index:],
        frame=found_frame,
    )


class MissingIntegrationFrame(HomeAssistantError):
    """Raised when no integration is found in the frame."""


class ReportBehavior(enum.Enum):
    """Enum for behavior on code usage."""

    IGNORE = enum.auto()
    """Ignore the code usage."""
    LOG = enum.auto()
    """Log the code usage."""
    ERROR = enum.auto()
    """Raise an error on code usage."""


def report_usage(
    what: str,
    *,
    breaks_in_ha_version: str | None = None,
    core_behavior: ReportBehavior = ReportBehavior.ERROR,
    core_integration_behavior: ReportBehavior = ReportBehavior.LOG,
    custom_integration_behavior: ReportBehavior = ReportBehavior.LOG,
    exclude_integrations: set[str] | None = None,
    integration_domain: str | None = None,
    level: int = logging.WARNING,
) -> None:
    """Report incorrect code usage.

    :param what: will be wrapped with "Detected that integration 'integration' {what}.
    Please create a bug report at https://..."
    :param breaks_in_ha_version: if set, the report will be adjusted to specify the
    breaking version
    :param exclude_integrations: skip specified integration when reviewing the stack.
    If no integration is found, the core behavior will be applied
    :param integration_domain: domain of the integration causing the issue. If None, the
    stack frame will be searched to identify the integration causing the issue.
    """
    if (hass := _hass.hass) is None:
        raise RuntimeError("Frame helper not set up")
    integration_frame: IntegrationFrame | None = None
    integration_frame_err: MissingIntegrationFrame | None = None
    if not integration_domain:
        try:
            integration_frame = get_integration_frame(
                exclude_integrations=exclude_integrations
            )
        except MissingIntegrationFrame as err:
            # We need to be careful with assigning the error here as it affects the
            # cleanup of objects referenced from the stack trace as seen in
            # https://github.com/home-assistant/core/pull/148021#discussion_r2182379834
            # When core_behavior is ReportBehavior.ERROR, we will re-raise the error,
            # so we can safely assign it to integration_frame_err.
            if core_behavior is ReportBehavior.ERROR:
                integration_frame_err = err
    _report_usage_partial = functools.partial(
        _report_usage,
        hass,
        what,
        breaks_in_ha_version=breaks_in_ha_version,
        core_behavior=core_behavior,
        core_integration_behavior=core_integration_behavior,
        custom_integration_behavior=custom_integration_behavior,
        integration_domain=integration_domain,
        integration_frame=integration_frame,
        integration_frame_err=integration_frame_err,
        level=level,
    )
    if hass.loop_thread_id != threading.get_ident():
        future = run_callback_threadsafe(hass.loop, _report_usage_partial)
        future.result()
        return
    _report_usage_partial()


def _report_usage(
    hass: HomeAssistant,
    what: str,
    *,
    breaks_in_ha_version: str | None,
    core_behavior: ReportBehavior,
    core_integration_behavior: ReportBehavior,
    custom_integration_behavior: ReportBehavior,
    integration_domain: str | None,
    integration_frame: IntegrationFrame | None,
    integration_frame_err: MissingIntegrationFrame | None,
    level: int,
) -> None:
    """Report incorrect code usage.

    Must be called from the event loop.
    """
    if integration_domain:
        if integration := async_get_issue_integration(hass, integration_domain):
            _report_usage_integration_domain(
                hass,
                what,
                breaks_in_ha_version,
                integration,
                core_integration_behavior,
                custom_integration_behavior,
                level,
            )
            return
        _report_usage_no_integration(what, core_behavior, breaks_in_ha_version, None)
        return

    if not integration_frame:
        _report_usage_no_integration(
            what, core_behavior, breaks_in_ha_version, integration_frame_err
        )
        return

    integration_behavior = core_integration_behavior
    if integration_frame.custom_integration:
        integration_behavior = custom_integration_behavior

    if integration_behavior is not ReportBehavior.IGNORE:
        _report_usage_integration_frame(
            hass,
            what,
            breaks_in_ha_version,
            integration_frame,
            level,
            integration_behavior is ReportBehavior.ERROR,
        )


def _report_usage_integration_domain(
    hass: HomeAssistant | None,
    what: str,
    breaks_in_ha_version: str | None,
    integration: Integration,
    core_integration_behavior: ReportBehavior,
    custom_integration_behavior: ReportBehavior,
    level: int,
) -> None:
    """Report incorrect usage in an integration (identified via domain).

    Async friendly.
    """
    integration_behavior = core_integration_behavior
    if not integration.is_built_in:
        integration_behavior = custom_integration_behavior

    if integration_behavior is ReportBehavior.IGNORE:
        return

    # Keep track of integrations already reported to prevent flooding
    key = f"{integration.domain}:{what}"
    if (
        integration_behavior is not ReportBehavior.ERROR
        and key in _REPORTED_INTEGRATIONS
    ):
        return
    _REPORTED_INTEGRATIONS.add(key)

    report_issue = async_suggest_report_issue(hass, integration=integration)
    integration_type = "" if integration.is_built_in else "custom "
    _LOGGER.log(
        level,
        "Detected that %sintegration '%s' %s. %s %s",
        integration_type,
        integration.domain,
        what,
        f"This will stop working in Home Assistant {breaks_in_ha_version}, please"
        if breaks_in_ha_version
        else "Please",
        report_issue,
    )

    if integration_behavior is ReportBehavior.ERROR:
        raise RuntimeError(
            f"Detected that {integration_type}integration "
            f"'{integration.domain}' {what}. Please {report_issue}"
        )


def _report_usage_integration_frame(
    hass: HomeAssistant,
    what: str,
    breaks_in_ha_version: str | None,
    integration_frame: IntegrationFrame,
    level: int = logging.WARNING,
    error: bool = False,
) -> None:
    """Report incorrect usage in an integration (identified via frame).

    Async friendly.
    """
    # Keep track of integrations already reported to prevent flooding
    key = f"{integration_frame.filename}:{integration_frame.line_number}"
    if not error and key in _REPORTED_INTEGRATIONS:
        return
    _REPORTED_INTEGRATIONS.add(key)

    report_issue = async_suggest_report_issue(
        hass,
        integration_domain=integration_frame.integration,
        module=integration_frame.module,
    )
    integration_type = "custom " if integration_frame.custom_integration else ""
    _LOGGER.log(
        level,
        "Detected that %sintegration '%s' %s at %s, line %s: %s. %s %s",
        integration_type,
        integration_frame.integration,
        what,
        integration_frame.relative_filename,
        integration_frame.line_number,
        integration_frame.line,
        f"This will stop working in Home Assistant {breaks_in_ha_version}, please"
        if breaks_in_ha_version
        else "Please",
        report_issue,
    )
    if not error:
        return
    raise RuntimeError(
        f"Detected that {integration_type}integration "
        f"'{integration_frame.integration}' {what} at "
        f"{integration_frame.relative_filename}, line "
        f"{integration_frame.line_number}: {integration_frame.line}. "
        f"Please {report_issue}"
    )


def _report_usage_no_integration(
    what: str,
    core_behavior: ReportBehavior,
    breaks_in_ha_version: str | None,
    err: MissingIntegrationFrame | None,
) -> None:
    """Report incorrect usage without an integration.

    This could happen because the offending call happened outside of an integration,
    or because the integration could not be identified.
    """
    msg = f"Detected code that {what}. Please report this issue"
    if core_behavior is ReportBehavior.ERROR:
        raise RuntimeError(msg) from err
    if core_behavior is ReportBehavior.LOG:
        if breaks_in_ha_version:
            msg = (
                f"Detected code that {what}. This will stop working in Home "
                f"Assistant {breaks_in_ha_version}, please report this issue"
            )
        _LOGGER.warning(msg, stack_info=True)


def warn_use[_CallableT: Callable](func: _CallableT, what: str) -> _CallableT:
    """Mock a function to warn when it was about to be used."""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def report_use(*args: Any, **kwargs: Any) -> None:
            report_usage(what)

    else:

        @functools.wraps(func)
        def report_use(*args: Any, **kwargs: Any) -> None:
            report_usage(what)

    return cast(_CallableT, report_use)


def report_non_thread_safe_operation(what: str) -> None:
    """Report a non-thread safe operation."""
    report_usage(
        f"calls {what} from a thread other than the event loop, "
        "which may cause Home Assistant to crash or data to corrupt. "
        "For more information, see "
        "https://developers.home-assistant.io/docs/asyncio_thread_safety/"
        f"#{what.replace('.', '')}",
        core_behavior=ReportBehavior.ERROR,
        core_integration_behavior=ReportBehavior.ERROR,
        custom_integration_behavior=ReportBehavior.ERROR,
    )
