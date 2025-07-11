"""Support for KNX climate entities."""

from __future__ import annotations

from typing import Any

from xknx import XKNX
from xknx.devices import (
    Climate as XknxClimate,
    ClimateMode as XknxClimateMode,
    Device as XknxDevice,
)
from xknx.devices.fan import FanSpeedMode
from xknx.dpt.dpt_20 import HVACControllerMode, HVACOperationMode

from homeassistant import config_entries
from homeassistant.components.climate import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_ON,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_ENTITY_CATEGORY,
    CONF_NAME,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import CONTROLLER_MODES, CURRENT_HVAC_ACTIONS, KNX_MODULE_KEY
from .entity import KnxYamlEntity
from .knx_module import KNXModule
from .schema import ClimateSchema

ATTR_COMMAND_VALUE = "command_value"
CONTROLLER_MODES_INV = {value: key for key, value in CONTROLLER_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up climate(s) for KNX platform."""
    knx_module = hass.data[KNX_MODULE_KEY]
    config: list[ConfigType] = knx_module.config_yaml[Platform.CLIMATE]

    async_add_entities(
        KNXClimate(knx_module, entity_config) for entity_config in config
    )


def _create_climate(xknx: XKNX, config: ConfigType) -> XknxClimate:
    """Return a KNX Climate device to be used within XKNX."""
    climate_mode = XknxClimateMode(
        xknx,
        name=f"{config[CONF_NAME]} Mode",
        group_address_operation_mode=config.get(
            ClimateSchema.CONF_OPERATION_MODE_ADDRESS
        ),
        group_address_operation_mode_state=config.get(
            ClimateSchema.CONF_OPERATION_MODE_STATE_ADDRESS
        ),
        group_address_controller_status=config.get(
            ClimateSchema.CONF_CONTROLLER_STATUS_ADDRESS
        ),
        group_address_controller_status_state=config.get(
            ClimateSchema.CONF_CONTROLLER_STATUS_STATE_ADDRESS
        ),
        group_address_controller_mode=config.get(
            ClimateSchema.CONF_CONTROLLER_MODE_ADDRESS
        ),
        group_address_controller_mode_state=config.get(
            ClimateSchema.CONF_CONTROLLER_MODE_STATE_ADDRESS
        ),
        group_address_operation_mode_protection=config.get(
            ClimateSchema.CONF_OPERATION_MODE_FROST_PROTECTION_ADDRESS
        ),
        group_address_operation_mode_economy=config.get(
            ClimateSchema.CONF_OPERATION_MODE_NIGHT_ADDRESS
        ),
        group_address_operation_mode_comfort=config.get(
            ClimateSchema.CONF_OPERATION_MODE_COMFORT_ADDRESS
        ),
        group_address_operation_mode_standby=config.get(
            ClimateSchema.CONF_OPERATION_MODE_STANDBY_ADDRESS
        ),
        group_address_heat_cool=config.get(ClimateSchema.CONF_HEAT_COOL_ADDRESS),
        group_address_heat_cool_state=config.get(
            ClimateSchema.CONF_HEAT_COOL_STATE_ADDRESS
        ),
        operation_modes=config.get(ClimateSchema.CONF_OPERATION_MODES),
        controller_modes=config.get(ClimateSchema.CONF_CONTROLLER_MODES),
    )

    return XknxClimate(
        xknx,
        name=config[CONF_NAME],
        group_address_temperature=config[ClimateSchema.CONF_TEMPERATURE_ADDRESS],
        group_address_target_temperature=config.get(
            ClimateSchema.CONF_TARGET_TEMPERATURE_ADDRESS
        ),
        group_address_target_temperature_state=config[
            ClimateSchema.CONF_TARGET_TEMPERATURE_STATE_ADDRESS
        ],
        group_address_setpoint_shift=config.get(
            ClimateSchema.CONF_SETPOINT_SHIFT_ADDRESS
        ),
        group_address_setpoint_shift_state=config.get(
            ClimateSchema.CONF_SETPOINT_SHIFT_STATE_ADDRESS
        ),
        setpoint_shift_mode=config.get(ClimateSchema.CONF_SETPOINT_SHIFT_MODE),
        setpoint_shift_max=config[ClimateSchema.CONF_SETPOINT_SHIFT_MAX],
        setpoint_shift_min=config[ClimateSchema.CONF_SETPOINT_SHIFT_MIN],
        temperature_step=config[ClimateSchema.CONF_TEMPERATURE_STEP],
        group_address_on_off=config.get(ClimateSchema.CONF_ON_OFF_ADDRESS),
        group_address_on_off_state=config.get(ClimateSchema.CONF_ON_OFF_STATE_ADDRESS),
        on_off_invert=config[ClimateSchema.CONF_ON_OFF_INVERT],
        group_address_active_state=config.get(ClimateSchema.CONF_ACTIVE_STATE_ADDRESS),
        group_address_command_value_state=config.get(
            ClimateSchema.CONF_COMMAND_VALUE_STATE_ADDRESS
        ),
        min_temp=config.get(ClimateSchema.CONF_MIN_TEMP),
        max_temp=config.get(ClimateSchema.CONF_MAX_TEMP),
        mode=climate_mode,
        group_address_fan_speed=config.get(ClimateSchema.CONF_FAN_SPEED_ADDRESS),
        group_address_fan_speed_state=config.get(
            ClimateSchema.CONF_FAN_SPEED_STATE_ADDRESS
        ),
        fan_speed_mode=config[ClimateSchema.CONF_FAN_SPEED_MODE],
        group_address_swing=config.get(ClimateSchema.CONF_SWING_ADDRESS),
        group_address_swing_state=config.get(ClimateSchema.CONF_SWING_STATE_ADDRESS),
        group_address_horizontal_swing=config.get(
            ClimateSchema.CONF_SWING_HORIZONTAL_ADDRESS
        ),
        group_address_horizontal_swing_state=config.get(
            ClimateSchema.CONF_SWING_HORIZONTAL_STATE_ADDRESS
        ),
        group_address_humidity_state=config.get(
            ClimateSchema.CONF_HUMIDITY_STATE_ADDRESS
        ),
    )


class KNXClimate(KnxYamlEntity, ClimateEntity):
    """Representation of a KNX climate device."""

    _device: XknxClimate
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "knx_climate"

    def __init__(self, knx_module: KNXModule, config: ConfigType) -> None:
        """Initialize of a KNX climate device."""
        super().__init__(
            knx_module=knx_module,
            device=_create_climate(knx_module.xknx, config),
        )
        self._attr_entity_category = config.get(CONF_ENTITY_CATEGORY)
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._device.supports_on_off:
            self._attr_supported_features |= (
                ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
            )
        if (
            self._device.mode is not None
            and len(self._device.mode.controller_modes) >= 2
            and HVACControllerMode.OFF in self._device.mode.controller_modes
        ):
            self._attr_supported_features |= (
                ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
            )

        if (
            self._device.mode is not None
            and self._device.mode.operation_modes  # empty list when not writable
        ):
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = [
                mode.name.lower() for mode in self._device.mode.operation_modes
            ]

        fan_max_step = config[ClimateSchema.CONF_FAN_MAX_STEP]
        self._fan_modes_percentages = [
            int(100 * i / fan_max_step) for i in range(fan_max_step + 1)
        ]
        self.fan_zero_mode: str = config[ClimateSchema.CONF_FAN_ZERO_MODE]

        if self._device.fan_speed is not None and self._device.fan_speed.initialized:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE

            if fan_max_step == 3:
                self._attr_fan_modes = [
                    self.fan_zero_mode,
                    FAN_LOW,
                    FAN_MEDIUM,
                    FAN_HIGH,
                ]
            elif fan_max_step == 2:
                self._attr_fan_modes = [self.fan_zero_mode, FAN_LOW, FAN_HIGH]
            elif fan_max_step == 1:
                self._attr_fan_modes = [self.fan_zero_mode, FAN_ON]
            elif self._device.fan_speed_mode == FanSpeedMode.STEP:
                self._attr_fan_modes = [self.fan_zero_mode] + [
                    str(i) for i in range(1, fan_max_step + 1)
                ]
            else:
                self._attr_fan_modes = [self.fan_zero_mode] + [
                    f"{percentage}%" for percentage in self._fan_modes_percentages[1:]
                ]
        if self._device.swing.initialized:
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
            self._attr_swing_modes = [SWING_ON, SWING_OFF]

        if self._device.horizontal_swing.initialized:
            self._attr_supported_features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
            self._attr_swing_horizontal_modes = [SWING_ON, SWING_OFF]

        self._attr_target_temperature_step = self._device.temperature_step
        self._attr_unique_id = (
            f"{self._device.temperature.group_address_state}_"
            f"{self._device.target_temperature.group_address_state}_"
            f"{self._device.target_temperature.group_address}_"
            f"{self._device._setpoint_shift.group_address}"  # noqa: SLF001
        )
        self.default_hvac_mode: HVACMode = config[
            ClimateSchema.CONF_DEFAULT_CONTROLLER_MODE
        ]
        # non-OFF HVAC mode to be used when turning on the device without on_off address
        self._last_hvac_mode: HVACMode = self.default_hvac_mode

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.temperature.value

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.target_temperature.value

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        temp = self._device.target_temperature_min
        return temp if temp is not None else super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        temp = self._device.target_temperature_max
        return temp if temp is not None else super().max_temp

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if self._device.supports_on_off:
            await self._device.turn_on()
            self.async_write_ha_state()
            return

        if (
            self._device.mode is not None
            and self._device.mode.supports_controller_mode
            and (knx_controller_mode := CONTROLLER_MODES_INV.get(self._last_hvac_mode))
            is not None
        ):
            await self._device.mode.set_controller_mode(knx_controller_mode)
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        if self._device.supports_on_off:
            await self._device.turn_off()
            self.async_write_ha_state()
            return

        if (
            self._device.mode is not None
            and HVACControllerMode.OFF in self._device.mode.controller_modes
        ):
            await self._device.mode.set_controller_mode(HVACControllerMode.OFF)
            self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._device.set_target_temperature(temperature)
            self.async_write_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation ie. heat, cool, idle."""
        if self._device.supports_on_off and not self._device.is_on:
            return HVACMode.OFF
        if self._device.mode is not None and self._device.mode.supports_controller_mode:
            return CONTROLLER_MODES.get(
                self._device.mode.controller_mode, self.default_hvac_mode
            )
        return self.default_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available operation/controller modes."""
        ha_controller_modes: list[HVACMode | None] = []
        if self._device.mode is not None:
            ha_controller_modes.extend(
                CONTROLLER_MODES.get(knx_controller_mode)
                for knx_controller_mode in self._device.mode.controller_modes
            )

        if self._device.supports_on_off:
            if not ha_controller_modes:
                ha_controller_modes.append(self._last_hvac_mode)
            ha_controller_modes.append(HVACMode.OFF)

        hvac_modes = list(set(filter(None, ha_controller_modes)))
        return (
            hvac_modes
            if hvac_modes
            else [self.hvac_mode]  # mode read-only -> fall back to only current mode
        )

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        if self._device.supports_on_off and not self._device.is_on:
            return HVACAction.OFF
        if self._device.is_active is False:
            return HVACAction.IDLE
        if (
            self._device.mode is not None and self._device.mode.supports_controller_mode
        ) or self._device.is_active:
            return CURRENT_HVAC_ACTIONS.get(self.hvac_mode, HVACAction.IDLE)
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set controller mode."""
        if self._device.mode is not None and self._device.mode.supports_controller_mode:
            knx_controller_mode = CONTROLLER_MODES_INV.get(hvac_mode)
            if knx_controller_mode in self._device.mode.controller_modes:
                await self._device.mode.set_controller_mode(knx_controller_mode)

        if self._device.supports_on_off:
            if hvac_mode == HVACMode.OFF:
                await self._device.turn_off()
            elif not self._device.is_on:
                await self._device.turn_on()
        self.async_write_ha_state()

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp.

        Requires ClimateEntityFeature.PRESET_MODE.
        """
        if self._device.mode is not None and self._device.mode.supports_operation_mode:
            return self._device.mode.operation_mode.name.lower()
        return None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if (
            self._device.mode is not None
            and self._device.mode.operation_modes  # empty list when not writable
        ):
            await self._device.mode.set_operation_mode(
                HVACOperationMode[preset_mode.upper()]
            )
            self.async_write_ha_state()

    @property
    def fan_mode(self) -> str:
        """Return the fan setting."""

        fan_speed = self._device.current_fan_speed

        if not fan_speed or self._attr_fan_modes is None:
            return self.fan_zero_mode

        if self._device.fan_speed_mode == FanSpeedMode.STEP:
            return self._attr_fan_modes[fan_speed]

        # Find the closest fan mode percentage
        closest_percentage = min(
            self._fan_modes_percentages[1:],  # fan_speed == 0 is handled above
            key=lambda x: abs(x - fan_speed),
        )
        return self._attr_fan_modes[
            self._fan_modes_percentages.index(closest_percentage)
        ]

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""

        if self._attr_fan_modes is None:
            return

        fan_mode_index = self._attr_fan_modes.index(fan_mode)

        if self._device.fan_speed_mode == FanSpeedMode.STEP:
            await self._device.set_fan_speed(fan_mode_index)
            return

        await self._device.set_fan_speed(self._fan_modes_percentages[fan_mode_index])

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing setting."""
        await self._device.set_swing(swing_mode == SWING_ON)

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set the horizontal swing setting."""
        await self._device.set_horizontal_swing(swing_horizontal_mode == SWING_ON)

    @property
    def swing_mode(self) -> str | None:
        """Return the swing setting."""
        if self._device.swing.value is not None:
            return SWING_ON if self._device.swing.value else SWING_OFF
        return None

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing setting."""
        if self._device.horizontal_swing.value is not None:
            return SWING_ON if self._device.horizontal_swing.value else SWING_OFF
        return None

    @property
    def current_humidity(self) -> float | None:
        """Return the current humidity."""
        return self._device.humidity.value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return device specific state attributes."""
        attr: dict[str, Any] = {}

        if self._device.command_value.initialized:
            attr[ATTR_COMMAND_VALUE] = self._device.command_value.value
        return attr

    async def async_added_to_hass(self) -> None:
        """Store register state change callback and start device object."""
        await super().async_added_to_hass()
        if self._device.mode is not None:
            self._device.mode.register_device_updated_cb(self.after_update_callback)
            self._device.mode.xknx.devices.async_add(self._device.mode)

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect device object when removed."""
        if self._device.mode is not None:
            self._device.mode.unregister_device_updated_cb(self.after_update_callback)
            self._device.mode.xknx.devices.async_remove(self._device.mode)
        await super().async_will_remove_from_hass()

    def after_update_callback(self, device: XknxDevice) -> None:
        """Call after device was updated."""
        if self._device.mode is not None and self._device.mode.supports_controller_mode:
            hvac_mode = CONTROLLER_MODES.get(
                self._device.mode.controller_mode, self.default_hvac_mode
            )
            if hvac_mode is not HVACMode.OFF:
                self._last_hvac_mode = hvac_mode
        super().after_update_callback(device)
