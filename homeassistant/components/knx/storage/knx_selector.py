"""Selectors for KNX."""

from collections.abc import Hashable, Iterable
from enum import Enum
from typing import Any

import voluptuous as vol

from ..validation import ga_validator, maybe_ga_validator
from .const import CONF_DPT, CONF_GA_PASSIVE, CONF_GA_STATE, CONF_GA_WRITE


class GroupSelect(vol.Any):
    """Use the first validated value.

    This is a version of vol.Any with custom error handling to
    show proper invalid markers for sub-schema items in the UI.
    """

    def _exec(self, funcs: Iterable, v: Any, path: list[Hashable] | None = None) -> Any:
        """Execute the validation functions."""
        errors: list[vol.Invalid] = []
        for func in funcs:
            try:
                if path is None:
                    return func(v)
                return func(path, v)
            except vol.Invalid as e:
                errors.append(e)
        if errors:
            raise next(
                (err for err in errors if "extra keys not allowed" not in err.msg),
                errors[0],
            )
        raise vol.AnyInvalid(self.msg or "no valid value found", path=path)


class GASelector:
    """Selector for a KNX group address structure."""

    schema: vol.Schema

    def __init__(
        self,
        write: bool = True,
        state: bool = True,
        passive: bool = True,
        write_required: bool = False,
        state_required: bool = False,
        dpt: type[Enum] | None = None,
    ) -> None:
        """Initialize the group address selector."""
        self.write = write
        self.state = state
        self.passive = passive
        self.write_required = write_required
        self.state_required = state_required
        self.dpt = dpt

        self.schema = self.build_schema()

    def __call__(self, data: Any) -> Any:
        """Validate the passed data."""
        return self.schema(data)

    def build_schema(self) -> vol.Schema:
        """Create the schema based on configuration."""
        schema: dict[vol.Marker, Any] = {}  # will be modified in-place
        self._add_group_addresses(schema)
        self._add_passive(schema)
        self._add_dpt(schema)
        return vol.Schema(
            vol.All(
                schema,
                vol.Schema(  # one group address shall be included
                    vol.Any(
                        {vol.Required(CONF_GA_WRITE): vol.IsTrue()},
                        {vol.Required(CONF_GA_STATE): vol.IsTrue()},
                        {vol.Required(CONF_GA_PASSIVE): vol.IsTrue()},
                        msg="At least one group address must be set",
                    ),
                    extra=vol.ALLOW_EXTRA,
                ),
            )
        )

    def _add_group_addresses(self, schema: dict[vol.Marker, Any]) -> None:
        """Add basic group address items to the schema."""

        def add_ga_item(key: str, allowed: bool, required: bool) -> None:
            """Add a group address item validator to the schema."""
            if not allowed:
                schema[vol.Remove(key)] = object
                return
            if required:
                schema[vol.Required(key)] = ga_validator
            else:
                schema[vol.Optional(key, default=None)] = maybe_ga_validator

        add_ga_item(CONF_GA_WRITE, self.write, self.write_required)
        add_ga_item(CONF_GA_STATE, self.state, self.state_required)

    def _add_passive(self, schema: dict[vol.Marker, Any]) -> None:
        """Add passive group addresses validator to the schema."""
        if self.passive:
            schema[vol.Optional(CONF_GA_PASSIVE, default=list)] = vol.Any(
                [ga_validator],
                vol.All(  # Coerce `None` to an empty list if passive is allowed
                    vol.IsFalse(), vol.SetTo(list)
                ),
            )
        else:
            schema[vol.Remove(CONF_GA_PASSIVE)] = object

    def _add_dpt(self, schema: dict[vol.Marker, Any]) -> None:
        """Add DPT validator to the schema."""
        if self.dpt is not None:
            schema[vol.Required(CONF_DPT)] = vol.In({item.value for item in self.dpt})
        else:
            schema[vol.Remove(CONF_DPT)] = object
