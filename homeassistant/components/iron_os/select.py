"""Select platform for IronOS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, StrEnum

from pynecil import (
    AnimationSpeed,
    AutostartMode,
    BatteryType,
    CharSetting,
    LockingMode,
    LogoDuration,
    ScreenOrientationMode,
    ScrollSpeed,
    SettingsDataResponse,
    TempUnit,
    TipType,
    USBPDMode,
)

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import IronOSConfigEntry
from .coordinator import IronOSCoordinators
from .entity import IronOSBaseEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class IronOSSelectEntityDescription(SelectEntityDescription):
    """Describes IronOS select entity."""

    value_fn: Callable[[SettingsDataResponse], str | None]
    characteristic: CharSetting
    raw_value_fn: Callable[[str], Enum]


class PinecilSelect(StrEnum):
    """Select controls for Pinecil device."""

    MIN_DC_VOLTAGE_CELLS = "min_dc_voltage_cells"
    ORIENTATION_MODE = "orientation_mode"
    ANIMATION_SPEED = "animation_speed"
    AUTOSTART_MODE = "autostart_mode"
    TEMP_UNIT = "temp_unit"
    DESC_SCROLL_SPEED = "desc_scroll_speed"
    LOCKING_MODE = "locking_mode"
    LOGO_DURATION = "logo_duration"
    USB_PD_MODE = "usb_pd_mode"
    TIP_TYPE = "tip_type"


def enum_to_str(enum: Enum | None) -> str | None:
    """Convert enum name to lower-case string."""
    return enum.name.lower() if isinstance(enum, Enum) else None


PINECIL_SELECT_DESCRIPTIONS: tuple[IronOSSelectEntityDescription, ...] = (
    IronOSSelectEntityDescription(
        key=PinecilSelect.MIN_DC_VOLTAGE_CELLS,
        translation_key=PinecilSelect.MIN_DC_VOLTAGE_CELLS,
        characteristic=CharSetting.MIN_DC_VOLTAGE_CELLS,
        value_fn=lambda x: enum_to_str(x.get("min_dc_voltage_cells")),
        raw_value_fn=lambda value: BatteryType[value.upper()],
        options=[x.name.lower() for x in BatteryType],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.ORIENTATION_MODE,
        translation_key=PinecilSelect.ORIENTATION_MODE,
        characteristic=CharSetting.ORIENTATION_MODE,
        value_fn=lambda x: enum_to_str(x.get("orientation_mode")),
        raw_value_fn=lambda value: ScreenOrientationMode[value.upper()],
        options=[x.name.lower() for x in ScreenOrientationMode],
        entity_category=EntityCategory.CONFIG,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.ANIMATION_SPEED,
        translation_key=PinecilSelect.ANIMATION_SPEED,
        characteristic=CharSetting.ANIMATION_SPEED,
        value_fn=lambda x: enum_to_str(x.get("animation_speed")),
        raw_value_fn=lambda value: AnimationSpeed[value.upper()],
        options=[x.name.lower() for x in AnimationSpeed],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.AUTOSTART_MODE,
        translation_key=PinecilSelect.AUTOSTART_MODE,
        characteristic=CharSetting.AUTOSTART_MODE,
        value_fn=lambda x: enum_to_str(x.get("autostart_mode")),
        raw_value_fn=lambda value: AutostartMode[value.upper()],
        options=[x.name.lower() for x in AutostartMode],
        entity_category=EntityCategory.CONFIG,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.TEMP_UNIT,
        translation_key=PinecilSelect.TEMP_UNIT,
        characteristic=CharSetting.TEMP_UNIT,
        value_fn=lambda x: enum_to_str(x.get("temp_unit")),
        raw_value_fn=lambda value: TempUnit[value.upper()],
        options=[x.name.lower() for x in TempUnit],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.DESC_SCROLL_SPEED,
        translation_key=PinecilSelect.DESC_SCROLL_SPEED,
        characteristic=CharSetting.DESC_SCROLL_SPEED,
        value_fn=lambda x: enum_to_str(x.get("desc_scroll_speed")),
        raw_value_fn=lambda value: ScrollSpeed[value.upper()],
        options=[x.name.lower() for x in ScrollSpeed],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.LOCKING_MODE,
        translation_key=PinecilSelect.LOCKING_MODE,
        characteristic=CharSetting.LOCKING_MODE,
        value_fn=lambda x: enum_to_str(x.get("locking_mode")),
        raw_value_fn=lambda value: LockingMode[value.upper()],
        options=[x.name.lower() for x in LockingMode],
        entity_category=EntityCategory.CONFIG,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.LOGO_DURATION,
        translation_key=PinecilSelect.LOGO_DURATION,
        characteristic=CharSetting.LOGO_DURATION,
        value_fn=lambda x: enum_to_str(x.get("logo_duration")),
        raw_value_fn=lambda value: LogoDuration[value.upper()],
        options=[x.name.lower() for x in LogoDuration],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)
PINECIL_SELECT_DESCRIPTIONS_V222: tuple[IronOSSelectEntityDescription, ...] = (
    IronOSSelectEntityDescription(
        key=PinecilSelect.USB_PD_MODE,
        translation_key=PinecilSelect.USB_PD_MODE,
        characteristic=CharSetting.USB_PD_MODE,
        value_fn=lambda x: enum_to_str(x.get("usb_pd_mode")),
        raw_value_fn=lambda value: USBPDMode[value.upper()],
        options=["off", "on"],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)
PINECIL_SELECT_DESCRIPTIONS_V223: tuple[IronOSSelectEntityDescription, ...] = (
    IronOSSelectEntityDescription(
        key=PinecilSelect.USB_PD_MODE,
        translation_key=PinecilSelect.USB_PD_MODE,
        characteristic=CharSetting.USB_PD_MODE,
        value_fn=lambda x: enum_to_str(x.get("usb_pd_mode")),
        raw_value_fn=lambda value: USBPDMode[value.upper()],
        options=[x.name.lower() for x in USBPDMode],
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    IronOSSelectEntityDescription(
        key=PinecilSelect.TIP_TYPE,
        translation_key=PinecilSelect.TIP_TYPE,
        characteristic=CharSetting.TIP_TYPE,
        value_fn=lambda x: enum_to_str(x.get("tip_type")),
        raw_value_fn=lambda value: TipType[value.upper()],
        options=[x.name.lower() for x in TipType],
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IronOSConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    coordinators = entry.runtime_data
    descriptions = PINECIL_SELECT_DESCRIPTIONS

    descriptions += (
        PINECIL_SELECT_DESCRIPTIONS_V223
        if coordinators.live_data.v223_features
        else PINECIL_SELECT_DESCRIPTIONS_V222
    )

    async_add_entities(
        IronOSSelectEntity(coordinators, description) for description in descriptions
    )


class IronOSSelectEntity(IronOSBaseEntity, SelectEntity):
    """Implementation of a IronOS select entity."""

    entity_description: IronOSSelectEntityDescription

    def __init__(
        self,
        coordinators: IronOSCoordinators,
        entity_description: IronOSSelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinators.live_data, entity_description)

        self.settings = coordinators.settings

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""

        return self.entity_description.value_fn(self.settings.data)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""

        await self.settings.write(
            self.entity_description.characteristic,
            self.entity_description.raw_value_fn(option),
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()
        self.async_on_remove(
            self.settings.async_add_listener(
                self._handle_coordinator_update, self.entity_description.characteristic
            )
        )
        await self.settings.async_request_refresh()
