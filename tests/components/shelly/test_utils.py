"""Tests for Shelly utils."""

from typing import Any
from unittest.mock import Mock

from aioshelly.const import (
    MODEL_1,
    MODEL_1L,
    MODEL_BUTTON1,
    MODEL_BUTTON1_V2,
    MODEL_DIMMER_2,
    MODEL_EM3,
    MODEL_I3,
    MODEL_MOTION,
    MODEL_PLUS_2PM_V2,
    MODEL_WALL_DISPLAY,
)
import pytest

from homeassistant.components.shelly.const import (
    GEN1_RELEASE_URL,
    GEN2_BETA_RELEASE_URL,
    GEN2_RELEASE_URL,
    UPTIME_DEVIATION,
)
from homeassistant.components.shelly.utils import (
    get_block_channel_name,
    get_block_device_sleep_period,
    get_block_input_triggers,
    get_device_uptime,
    get_host,
    get_number_of_channels,
    get_release_url,
    get_rpc_channel_name,
    get_rpc_input_triggers,
    is_block_momentary_input,
)
from homeassistant.util import dt as dt_util

DEVICE_BLOCK_ID = 4


async def test_block_get_number_of_channels(
    mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test block get number of channels."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "type", "emeter")
    monkeypatch.setitem(mock_block_device.shelly, "num_emeters", 3)

    assert (
        get_number_of_channels(
            mock_block_device,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        == 3
    )

    monkeypatch.setitem(mock_block_device.shelly, "num_inputs", 4)
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "type", "input")
    assert (
        get_number_of_channels(
            mock_block_device,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        == 4
    )

    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_DIMMER_2)
    assert (
        get_number_of_channels(
            mock_block_device,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        == 2
    )


async def test_block_get_block_channel_name(
    mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test block get block channel name."""
    result = get_block_channel_name(
        mock_block_device,
        mock_block_device.blocks[DEVICE_BLOCK_ID],
    )
    # when has_entity_name is True the result should be None
    assert result is None

    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "type", "relay")
    result = get_block_channel_name(
        mock_block_device,
        mock_block_device.blocks[DEVICE_BLOCK_ID],
    )
    # when has_entity_name is True the result should be None
    assert result is None

    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_EM3)
    result = get_block_channel_name(
        mock_block_device,
        mock_block_device.blocks[DEVICE_BLOCK_ID],
    )
    # when has_entity_name is True the result should be None
    assert result is None

    monkeypatch.setitem(
        mock_block_device.settings, "relays", [{"name": "test-channel"}]
    )
    result = get_block_channel_name(
        mock_block_device,
        mock_block_device.blocks[DEVICE_BLOCK_ID],
    )
    # when has_entity_name is True the result should be None
    assert result is None


async def test_is_block_momentary_input(
    mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test is block momentary input."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "type", "relay")

    monkeypatch.setitem(mock_block_device.settings, "mode", "roller")
    monkeypatch.setitem(
        mock_block_device.settings, "rollers", [{"button_type": "detached"}]
    )
    assert (
        is_block_momentary_input(
            mock_block_device.settings,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        is False
    )
    assert (
        is_block_momentary_input(
            mock_block_device.settings, mock_block_device.blocks[DEVICE_BLOCK_ID], True
        )
        is True
    )

    monkeypatch.setitem(mock_block_device.settings, "mode", "relay")
    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_1L)
    assert (
        is_block_momentary_input(
            mock_block_device.settings, mock_block_device.blocks[DEVICE_BLOCK_ID], True
        )
        is False
    )

    monkeypatch.delitem(mock_block_device.settings, "relays")
    monkeypatch.delitem(mock_block_device.settings, "rollers")
    assert (
        is_block_momentary_input(
            mock_block_device.settings,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        is False
    )

    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_BUTTON1_V2)

    assert (
        is_block_momentary_input(
            mock_block_device.settings,
            mock_block_device.blocks[DEVICE_BLOCK_ID],
        )
        is True
    )


@pytest.mark.parametrize(
    ("settings", "sleep_period"),
    [
        ({}, 0),
        ({"sleep_mode": {"period": 1000, "unit": "m"}}, 1000 * 60),
        ({"sleep_mode": {"period": 5, "unit": "h"}}, 5 * 3600),
    ],
)
async def test_get_block_device_sleep_period(
    settings: dict[str, Any], sleep_period: int
) -> None:
    """Test get block device sleep period."""
    assert get_block_device_sleep_period(settings) == sleep_period


@pytest.mark.freeze_time("2019-01-10 18:43:00+00:00")
async def test_get_device_uptime() -> None:
    """Test block test get device uptime."""
    assert get_device_uptime(
        55, dt_util.as_utc(dt_util.parse_datetime("2019-01-10 18:42:00+00:00"))
    ) == dt_util.as_utc(dt_util.parse_datetime("2019-01-10 18:42:00+00:00"))

    assert get_device_uptime(
        55 - UPTIME_DEVIATION,
        dt_util.as_utc(dt_util.parse_datetime("2019-01-10 18:42:00+00:00")),
    ) == dt_util.as_utc(dt_util.parse_datetime("2019-01-10 18:43:05+00:00"))


async def test_get_block_input_triggers(
    mock_block_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test get block input triggers."""
    monkeypatch.setattr(
        mock_block_device.blocks[DEVICE_BLOCK_ID],
        "sensor_ids",
        {"inputEvent": "S", "inputEventCnt": 0},
    )
    monkeypatch.setitem(
        mock_block_device.settings, "rollers", [{"button_type": "detached"}]
    )
    assert set(
        get_block_input_triggers(
            mock_block_device, mock_block_device.blocks[DEVICE_BLOCK_ID]
        )
    ) == {("long", "button"), ("single", "button")}

    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_BUTTON1)
    assert set(
        get_block_input_triggers(
            mock_block_device, mock_block_device.blocks[DEVICE_BLOCK_ID]
        )
    ) == {
        ("long", "button"),
        ("double", "button"),
        ("single", "button"),
        ("triple", "button"),
    }

    monkeypatch.setitem(mock_block_device.settings["device"], "type", MODEL_I3)
    assert set(
        get_block_input_triggers(
            mock_block_device, mock_block_device.blocks[DEVICE_BLOCK_ID]
        )
    ) == {
        ("long_single", "button"),
        ("single_long", "button"),
        ("triple", "button"),
        ("long", "button"),
        ("single", "button"),
        ("double", "button"),
    }


async def test_get_rpc_channel_name(mock_rpc_device: Mock) -> None:
    """Test get RPC channel name."""
    assert get_rpc_channel_name(mock_rpc_device, "input:0") == "Test input 0"
    assert get_rpc_channel_name(mock_rpc_device, "input:3") == "Input 3"


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("cover", None),
        ("light", None),
        ("rgb", None),
        ("rgbw", None),
        ("switch", None),
        ("thermostat", None),
    ],
)
async def test_get_rpc_channel_name_multiple_components(
    mock_rpc_device: Mock,
    monkeypatch: pytest.MonkeyPatch,
    component: str,
    expected: str,
) -> None:
    """Test get RPC channel name when there is more components of the same type."""
    config = {
        f"{component}:0": {"name": None},
        f"{component}:1": {"name": None},
    }
    monkeypatch.setattr(mock_rpc_device, "config", config)

    # we use sub-devices, so the entity name is not set
    assert get_rpc_channel_name(mock_rpc_device, f"{component}:0") == expected
    assert get_rpc_channel_name(mock_rpc_device, f"{component}:1") == expected


async def test_get_rpc_input_triggers(
    mock_rpc_device: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test get RPC input triggers."""
    monkeypatch.setattr(mock_rpc_device, "config", {"input:0": {"type": "button"}})
    assert set(get_rpc_input_triggers(mock_rpc_device)) == {
        ("btn_down", "button1"),
        ("btn_up", "button1"),
        ("single_push", "button1"),
        ("double_push", "button1"),
        ("triple_push", "button1"),
        ("long_push", "button1"),
    }

    monkeypatch.setattr(mock_rpc_device, "config", {"input:0": {"type": "switch"}})
    assert not get_rpc_input_triggers(mock_rpc_device)


@pytest.mark.parametrize(
    ("gen", "model", "beta", "expected"),
    [
        (1, MODEL_MOTION, False, None),
        (1, MODEL_1, False, GEN1_RELEASE_URL),
        (1, MODEL_1, True, None),
        (2, MODEL_WALL_DISPLAY, False, None),
        (2, MODEL_PLUS_2PM_V2, False, GEN2_RELEASE_URL),
        (2, MODEL_PLUS_2PM_V2, True, GEN2_BETA_RELEASE_URL),
    ],
)
def test_get_release_url(
    gen: int, model: str, beta: bool, expected: str | None
) -> None:
    """Test get_release_url() with a device without a release note URL."""
    result = get_release_url(gen, model, beta)

    assert result is expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("shelly_device.local", "shelly_device.local"),
        ("192.168.178.12", "192.168.178.12"),
        (
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "[2001:0db8:85a3:0000:0000:8a2e:0370:7334]",
        ),
    ],
)
def test_get_host(host: str, expected: str) -> None:
    """Test get_host function."""
    assert get_host(host) == expected
