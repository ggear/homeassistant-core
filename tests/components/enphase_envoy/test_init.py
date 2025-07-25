"""Test Enphase Envoy runtime."""

from datetime import timedelta
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from jwt import encode
from pyenphase import EnvoyAuthenticationError, EnvoyError, EnvoyTokenAuth
from pyenphase.auth import EnvoyLegacyAuth
import pytest
import respx

from homeassistant.components.enphase_envoy import DOMAIN
from homeassistant.components.enphase_envoy.const import (
    OPTION_DIAGNOSTICS_INCLUDE_FIXTURES,
    OPTION_DISABLE_KEEP_ALIVE,
    Platform,
)
from homeassistant.components.enphase_envoy.coordinator import (
    FIRMWARE_REFRESH_INTERVAL,
    MAC_VERIFICATION_DELAY,
    SCAN_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from . import setup_integration

from tests.common import MockConfigEntry, async_fire_time_changed
from tests.typing import WebSocketGenerator


async def test_with_pre_v7_firmware(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test enphase_envoy coordinator with pre V7 firmware."""
    mock_envoy.firmware = "5.1.1"
    mock_envoy.auth = EnvoyLegacyAuth(
        "127.0.0.1", username="test-username", password="test-password"
    )
    await setup_integration(hass, config_entry)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == "116"


@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_token_in_config_file(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with token provided from config."""
    token = encode(
        payload={"name": "envoy", "exp": 1907837780},
        key="secret",
        algorithm="HS256",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: token,
        },
    )
    mock_envoy.auth = EnvoyTokenAuth("127.0.0.1", token=token, envoy_serial="1234")
    await setup_integration(hass, entry)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == "116"


@respx.mock
@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_expired_token_in_config(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with expired token provided from config."""
    current_token = encode(
        # some time in 2021
        payload={"name": "envoy", "exp": 1627314600},
        key="secret",
        algorithm="HS256",
    )

    # mock envoy with expired token in config
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: current_token,
        },
    )
    # Make sure to mock pyenphase.auth.EnvoyTokenAuth._obtain_token
    # when specifying username and password in EnvoyTokenauth
    mock_envoy.auth = EnvoyTokenAuth(
        "127.0.0.1",
        token=current_token,
        envoy_serial="1234",
        cloud_username="test_username",
        cloud_password="test_password",
    )
    await setup_integration(hass, entry)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == "116"


async def test_coordinator_update_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator update error handling."""
    await setup_integration(hass, config_entry)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    original_state = entity_state

    # force HA to detect changed data by changing raw
    mock_envoy.data.raw = {"I": "am changed 1"}
    mock_envoy.update.side_effect = EnvoyError

    # Move time to next update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == STATE_UNAVAILABLE

    mock_envoy.reset_mock(return_value=True, side_effect=True)

    mock_envoy.data.raw = {"I": "am changed 2"}

    # Move time to next update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == original_state.state


async def test_coordinator_update_authentication_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test enphase_envoy coordinator update authentication error handling."""
    with patch("homeassistant.components.enphase_envoy.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, config_entry)

    # force HA to detect changed data by changing raw
    mock_envoy.data.raw = {"I": "am changed 1"}
    mock_envoy.update.side_effect = EnvoyAuthenticationError("This must fail")

    # Move time to next update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == STATE_UNAVAILABLE


@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_coordinator_token_refresh_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with expired token and failure to refresh."""
    token = encode(
        # some time in 2021
        payload={"name": "envoy", "exp": 1627314600},
        key="secret",
        algorithm="HS256",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: token,
        },
    )
    # override fresh token in conftest mock_envoy.auth
    mock_envoy.auth = EnvoyTokenAuth("127.0.0.1", token=token, envoy_serial="1234")
    # force token refresh to fail.
    with patch(
        "pyenphase.auth.EnvoyTokenAuth._obtain_token",
        side_effect=EnvoyError,
    ):
        await setup_integration(hass, entry)

    assert (entity_state := hass.states.get("sensor.inverter_1"))
    assert entity_state.state == "116"


@respx.mock
@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_coordinator_first_update_auth_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator update error handling."""
    current_token = encode(
        # some time in future
        payload={"name": "envoy", "exp": 1927314600},
        key="secret",
        algorithm="HS256",
    )

    # mock envoy with expired token in config
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: current_token,
        },
    )
    mock_envoy.auth = EnvoyTokenAuth(
        "127.0.0.1",
        token=current_token,
        envoy_serial="1234",
        cloud_username="test_username",
        cloud_password="test_password",
    )
    mock_envoy.authenticate.side_effect = EnvoyAuthenticationError("Failing test")
    await setup_integration(hass, entry, ConfigEntryState.SETUP_ERROR)


async def test_config_no_unique_id(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test enphase_envoy init if config entry has no unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id=None,
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    await setup_integration(hass, entry)
    assert entry.unique_id == mock_envoy.serial_number


async def test_config_different_unique_id(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test enphase_envoy init if config entry has different unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="4321",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    await setup_integration(hass, entry, expected_state=ConfigEntryState.SETUP_RETRY)


@pytest.mark.parametrize(
    ("mock_envoy"),
    [
        "envoy_metered_batt_relay",
    ],
    indirect=["mock_envoy"],
)
async def test_remove_config_entry_device(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test removing enphase_envoy config entry device."""
    assert await async_setup_component(hass, "config", {})
    await setup_integration(hass, config_entry)

    # use client to send remove_device command
    hass_client = await hass_ws_client(hass)

    # add device that will pass remove test
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "delete_this_device")},
    )
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert response["success"]

    # inverters are not allowed to be removed
    entity = entity_registry.entities["sensor.inverter_1"]
    device_entry = device_registry.async_get(entity.device_id)
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert not response["success"]

    # envoy itself is not allowed to be removed
    entity = entity_registry.entities["sensor.envoy_1234_current_power_production"]
    device_entry = device_registry.async_get(entity.device_id)
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert not response["success"]

    # encharge can not be removed
    entity = entity_registry.entities["sensor.encharge_123456_power"]
    device_entry = device_registry.async_get(entity.device_id)
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert not response["success"]

    # enpower can not be removed
    entity = entity_registry.entities["sensor.enpower_654321_temperature"]
    device_entry = device_registry.async_get(entity.device_id)
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert not response["success"]

    # relays can be removed
    entity = entity_registry.entities["switch.nc1_fixture"]
    device_entry = device_registry.async_get(entity.device_id)
    response = await hass_client.remove_device(device_entry.id, config_entry.entry_id)
    assert response["success"]


async def test_option_change_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
) -> None:
    """Test options change will reload entity."""
    await setup_integration(hass, config_entry)
    # By default neither option is available
    assert config_entry.options == {}

    # option change will also take care of COV of init::async_reload_entry
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            OPTION_DIAGNOSTICS_INCLUDE_FIXTURES: False,
            OPTION_DISABLE_KEEP_ALIVE: True,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.options == {
        OPTION_DIAGNOSTICS_INCLUDE_FIXTURES: False,
        OPTION_DISABLE_KEEP_ALIVE: True,
    }
    # flip em
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            OPTION_DIAGNOSTICS_INCLUDE_FIXTURES: True,
            OPTION_DISABLE_KEEP_ALIVE: False,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.options == {
        OPTION_DIAGNOSTICS_INCLUDE_FIXTURES: True,
        OPTION_DISABLE_KEEP_ALIVE: False,
    }


def mock_envoy_setup(mock_envoy: AsyncMock):
    """Mock envoy.setup."""
    mock_envoy.firmware = "9.9.9999"


@patch(
    "homeassistant.components.enphase_envoy.coordinator.SCAN_INTERVAL",
    timedelta(days=1),
)
@respx.mock
async def test_coordinator_firmware_refresh(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator scheduled firmware check."""
    await setup_integration(hass, config_entry)

    # Move time to next firmware check moment
    # SCAN_INTERVAL is patched to 1 day to disable it's firmware detection
    mock_envoy.setup.reset_mock()
    freezer.tick(FIRMWARE_REFRESH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_envoy.setup.assert_called_once_with()
    mock_envoy.setup.reset_mock()

    envoy = config_entry.runtime_data.envoy
    assert envoy.firmware == "7.6.175"

    caplog.set_level(logging.WARNING)

    with patch(
        "homeassistant.components.enphase_envoy.Envoy.setup",
        MagicMock(return_value=mock_envoy_setup(mock_envoy)),
    ):
        freezer.tick(FIRMWARE_REFRESH_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)

        assert (
            "Envoy firmware changed from: 7.6.175 to: 9.9.9999, reloading config entry Envoy 1234"
            in caplog.text
        )
        envoy = config_entry.runtime_data.envoy
        assert envoy.firmware == "9.9.9999"


@respx.mock
async def test_coordinator_firmware_refresh_with_envoy_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator scheduled firmware check."""
    await setup_integration(hass, config_entry)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("homeassistant.components.enphase_envoy.coordinator").setLevel(
        logging.DEBUG
    )

    mock_envoy.setup.side_effect = EnvoyError
    freezer.tick(FIRMWARE_REFRESH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert "Error reading firmware:" in caplog.text


@respx.mock
async def test_coordinator_interface_information(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator interface mac verification."""
    await setup_integration(hass, config_entry)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("homeassistant.components.enphase_envoy.coordinator").setLevel(
        logging.DEBUG
    )

    # move time forward so interface information is fetched
    freezer.tick(MAC_VERIFICATION_DELAY)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    # verify first time add of mac to connections is in log
    assert "added connection" in caplog.text

    # update options and reload
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            OPTION_DIAGNOSTICS_INCLUDE_FIXTURES: False,
            OPTION_DISABLE_KEEP_ALIVE: True,
        },
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.LOADED

    caplog.clear()
    # envoy reloaded and device registry still has connection info
    # force mac verification again to test existing connection is verified
    freezer.tick(MAC_VERIFICATION_DELAY)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    # verify existing connection is verified in log
    assert "connection verified as existing" in caplog.text


@respx.mock
async def test_coordinator_interface_information_no_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test coordinator interface mac verification full code cov."""
    await setup_integration(hass, config_entry)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("homeassistant.components.enphase_envoy.coordinator").setLevel(
        logging.DEBUG
    )

    # update device to force no device found in mac verification
    envoy_device = device_registry.async_get_device(
        identifiers={
            (
                DOMAIN,
                mock_envoy.serial_number,
            )
        }
    )
    device_registry.async_update_device(
        device_id=envoy_device.id,
        new_identifiers={(DOMAIN, "9999")},
    )

    # move time forward so interface information is fetched
    freezer.tick(MAC_VERIFICATION_DELAY)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    # verify no device found message in log
    assert "No envoy device found in device registry" in caplog.text


@respx.mock
async def test_coordinator_interface_information_mac_also_in_other_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test coordinator interface mac verification with MAC also in other existing device."""
    await setup_integration(hass, config_entry)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("homeassistant.components.enphase_envoy.coordinator").setLevel(
        logging.DEBUG
    )

    # add existing device with MAC and sparsely populated i.e. unifi that found envoy
    other_config_entry = MockConfigEntry(domain="test", data={})
    other_config_entry.add_to_hass(hass)
    device_registry.async_get_or_create(
        config_entry_id=other_config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "00:11:22:33:44:55")},
        manufacturer="Enphase Energy",
    )

    envoy_device = device_registry.async_get_device(
        identifiers={
            (
                DOMAIN,
                mock_envoy.serial_number,
            )
        }
    )
    assert envoy_device

    # move time forward so interface information is fetched
    freezer.tick(MAC_VERIFICATION_DELAY)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    # verify mac was added
    assert "added connection: ('mac', '00:11:22:33:44:55') to Envoy 1234" in caplog.text

    # verify connection is now in envoy device
    envoy_device_refetched = device_registry.async_get(envoy_device.id)
    assert envoy_device_refetched
    assert envoy_device_refetched.name == "Envoy 1234"
    assert envoy_device_refetched.serial_number == "1234"
    assert envoy_device_refetched.connections == {
        (
            dr.CONNECTION_NETWORK_MAC,
            "00:11:22:33:44:55",
        )
    }
