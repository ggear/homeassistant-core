"""Tests for the Reolink media_source platform."""

from datetime import datetime, timedelta
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from reolink_aio.exceptions import ReolinkError
from reolink_aio.typings import VOD_trigger

from homeassistant.components.media_source import (
    DOMAIN as MEDIA_SOURCE_DOMAIN,
    URI_SCHEME,
    Unresolvable,
    async_browse_media,
    async_resolve_media,
)
from homeassistant.components.reolink.config_flow import DEFAULT_PROTOCOL
from homeassistant.components.reolink.const import CONF_BC_PORT, CONF_USE_HTTPS, DOMAIN
from homeassistant.components.reolink.media_source import VOD_SPLIT_TIME
from homeassistant.components.stream import DOMAIN as MEDIA_STREAM_DOMAIN
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import format_mac
from homeassistant.setup import async_setup_component

from .conftest import (
    TEST_BC_PORT,
    TEST_HOST2,
    TEST_HOST_MODEL,
    TEST_MAC2,
    TEST_NVR_NAME,
    TEST_NVR_NAME2,
    TEST_PASSWORD2,
    TEST_PORT,
    TEST_USE_HTTPS,
    TEST_USERNAME2,
)

from tests.common import MockConfigEntry

TEST_YEAR = 2023
TEST_MONTH = 11
TEST_DAY = 14
TEST_DAY2 = 15
TEST_HOUR = 13
TEST_MINUTE = 12
TEST_START = f"{TEST_YEAR}{TEST_MONTH}{TEST_DAY}{TEST_HOUR}{TEST_MINUTE}"
TEST_END = f"{TEST_YEAR}{TEST_MONTH}{TEST_DAY}{TEST_HOUR}{TEST_MINUTE + 5}"
TEST_START_TIME = datetime(TEST_YEAR, TEST_MONTH, TEST_DAY, 0, 0)
TEST_END_TIME = datetime(TEST_YEAR, TEST_MONTH, TEST_DAY, 23, 59, 59)
TEST_FILE_NAME = f"{TEST_START}00"
TEST_FILE_NAME_MP4 = f"{TEST_START}00.mp4"
TEST_STREAM = "main"
TEST_CHANNEL = "0"
TEST_CAM_NAME = "Cam new name"

TEST_MIME_TYPE = "application/x-mpegURL"
TEST_MIME_TYPE_MP4 = "video/mp4"
TEST_URL = "http:test_url&user=admin&password=test"
TEST_URL2 = "http:test_url&token=test"


@pytest.fixture(autouse=True)
async def setup_component(hass: HomeAssistant) -> None:
    """Set up component."""
    assert await async_setup_component(hass, MEDIA_SOURCE_DOMAIN, {})
    assert await async_setup_component(hass, MEDIA_STREAM_DOMAIN, {})


async def test_platform_loads_before_config_entry(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that the platform can be loaded before the config entry."""
    # Fake that the config entry is not loaded before the media_source platform
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert mock_setup_entry.call_count == 0


async def test_resolve(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test resolving Reolink media items."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    caplog.set_level(logging.DEBUG)

    file_id = f"FILE|{config_entry.entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_FILE_NAME}|{TEST_START}|{TEST_END}"
    reolink_host.get_vod_source.return_value = (TEST_MIME_TYPE_MP4, TEST_URL)

    play_media = await async_resolve_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{file_id}", None
    )
    assert play_media.mime_type == TEST_MIME_TYPE_MP4

    file_id = f"FILE|{config_entry.entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_FILE_NAME_MP4}|{TEST_START}|{TEST_END}"
    reolink_host.get_vod_source.return_value = (TEST_MIME_TYPE_MP4, TEST_URL2)

    play_media = await async_resolve_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{file_id}", None
    )
    assert play_media.mime_type == TEST_MIME_TYPE_MP4

    reolink_host.is_nvr = False

    play_media = await async_resolve_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{file_id}", None
    )
    assert play_media.mime_type == TEST_MIME_TYPE_MP4

    file_id = f"FILE|{config_entry.entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_FILE_NAME}|{TEST_START}|{TEST_END}"
    reolink_host.get_vod_source.return_value = (TEST_MIME_TYPE, TEST_URL)

    play_media = await async_resolve_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{file_id}", None
    )
    assert play_media.mime_type == TEST_MIME_TYPE


async def test_browsing(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test browsing the Reolink three."""
    entry_id = config_entry.entry_id
    reolink_host.supported.return_value = 1
    reolink_host.model = "Reolink TrackMix PoE"
    reolink_host.is_nvr = False

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.CAMERA]):
        assert await hass.config_entries.async_setup(entry_id) is True
    await hass.async_block_till_done()

    entries = dr.async_entries_for_config_entry(device_registry, entry_id)
    assert len(entries) > 0
    device_registry.async_update_device(entries[0].id, name_by_user=TEST_CAM_NAME)

    caplog.set_level(logging.DEBUG)

    # browse root
    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}")

    browse_root_id = f"CAM|{entry_id}|{TEST_CHANNEL}"
    assert browse.domain == DOMAIN
    assert browse.title == "Reolink"
    assert browse.identifier is None
    assert browse.children[0].identifier == browse_root_id
    assert browse.children[0].title == f"{TEST_CAM_NAME} lens 0"

    # browse resolution select
    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_root_id}")

    browse_resolution_id = f"RESs|{entry_id}|{TEST_CHANNEL}"
    browse_res_sub_id = f"RES|{entry_id}|{TEST_CHANNEL}|sub"
    browse_res_main_id = f"RES|{entry_id}|{TEST_CHANNEL}|main"
    browse_res_AT_sub_id = f"RES|{entry_id}|{TEST_CHANNEL}|autotrack_sub"
    browse_res_AT_main_id = f"RES|{entry_id}|{TEST_CHANNEL}|autotrack_main"
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} lens 0"
    assert browse.identifier == browse_resolution_id
    assert browse.children[0].identifier == browse_res_sub_id
    assert browse.children[1].identifier == browse_res_main_id
    assert browse.children[2].identifier == browse_res_AT_sub_id
    assert browse.children[3].identifier == browse_res_AT_main_id

    # browse camera recording days
    mock_status = MagicMock()
    mock_status.year = TEST_YEAR
    mock_status.month = TEST_MONTH
    mock_status.days = (TEST_DAY, TEST_DAY2)
    reolink_host.request_vod_files.return_value = ([mock_status], [])

    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_res_sub_id}")
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} lens 0 Low res."

    browse = await async_browse_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{browse_res_AT_sub_id}"
    )
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} lens 0 Telephoto low res."

    browse = await async_browse_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{browse_res_AT_main_id}"
    )
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} lens 0 Telephoto high res."

    browse = await async_browse_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{browse_res_main_id}"
    )

    browse_days_id = f"DAYS|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}"
    browse_day_0_id = f"DAY|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_YEAR}|{TEST_MONTH}|{TEST_DAY}"
    browse_day_1_id = f"DAY|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_YEAR}|{TEST_MONTH}|{TEST_DAY2}"
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} lens 0 High res."
    assert browse.identifier == browse_days_id
    assert browse.children[0].identifier == browse_day_0_id
    assert browse.children[1].identifier == browse_day_1_id

    # browse camera recording files on day
    mock_vod_file = MagicMock()
    mock_vod_file.start_time = TEST_START_TIME
    mock_vod_file.start_time_id = TEST_START
    mock_vod_file.end_time_id = TEST_END
    mock_vod_file.duration = timedelta(minutes=5)
    mock_vod_file.file_name = TEST_FILE_NAME
    mock_vod_file.triggers = VOD_trigger.PERSON
    reolink_host.request_vod_files.return_value = ([mock_status], [mock_vod_file])

    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_day_0_id}")

    browse_files_id = f"FILES|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}"
    browse_file_id = f"FILE|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_FILE_NAME}|{TEST_START}|{TEST_END}"
    assert browse.domain == DOMAIN
    assert (
        browse.title
        == f"{TEST_NVR_NAME} lens 0 High res. {TEST_YEAR}/{TEST_MONTH}/{TEST_DAY}"
    )
    assert browse.identifier == browse_files_id
    assert browse.children[0].identifier == browse_file_id
    reolink_host.request_vod_files.assert_called_with(
        int(TEST_CHANNEL),
        TEST_START_TIME,
        TEST_END_TIME,
        stream=TEST_STREAM,
        split_time=VOD_SPLIT_TIME,
        trigger=None,
    )

    reolink_host.model = TEST_HOST_MODEL

    # browse event trigger person on a NVR
    reolink_host.is_nvr = True
    browse_event_person_id = f"EVE|{entry_id}|{TEST_CHANNEL}|{TEST_STREAM}|{TEST_YEAR}|{TEST_MONTH}|{TEST_DAY}|{VOD_trigger.PERSON.name}"

    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_day_0_id}")
    assert browse.children[0].identifier == browse_event_person_id

    browse = await async_browse_media(
        hass, f"{URI_SCHEME}{DOMAIN}/{browse_event_person_id}"
    )

    assert browse.domain == DOMAIN
    assert (
        browse.title
        == f"{TEST_NVR_NAME} High res. {TEST_YEAR}/{TEST_MONTH}/{TEST_DAY} Person"
    )
    assert browse.identifier == browse_files_id
    assert browse.children[0].identifier == browse_file_id
    reolink_host.request_vod_files.assert_called_with(
        int(TEST_CHANNEL),
        TEST_START_TIME,
        TEST_END_TIME,
        stream=TEST_STREAM,
        split_time=VOD_SPLIT_TIME,
        trigger=VOD_trigger.PERSON,
    )


async def test_browsing_h265_encoding(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test browsing a Reolink camera with h265 stream encoding."""
    entry_id = config_entry.entry_id
    reolink_host.is_nvr = True

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.CAMERA]):
        assert await hass.config_entries.async_setup(entry_id) is True
    await hass.async_block_till_done()

    browse_root_id = f"CAM|{entry_id}|{TEST_CHANNEL}"

    mock_status = MagicMock()
    mock_status.year = TEST_YEAR
    mock_status.month = TEST_MONTH
    mock_status.days = (TEST_DAY, TEST_DAY2)
    reolink_host.request_vod_files.return_value = ([mock_status], [])
    reolink_host.time.return_value = None
    reolink_host.get_encoding.return_value = "h265"
    reolink_host.supported.return_value = False

    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_root_id}")

    browse_resolution_id = f"RESs|{entry_id}|{TEST_CHANNEL}"
    browse_res_sub_id = f"RES|{entry_id}|{TEST_CHANNEL}|sub"
    browse_res_main_id = f"RES|{entry_id}|{TEST_CHANNEL}|main"

    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME}"
    assert browse.identifier == browse_resolution_id
    assert browse.children[0].identifier == browse_res_sub_id
    assert browse.children[1].identifier == browse_res_main_id

    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/{browse_res_sub_id}")

    browse_days_id = f"DAYS|{entry_id}|{TEST_CHANNEL}|sub"
    browse_day_0_id = (
        f"DAY|{entry_id}|{TEST_CHANNEL}|sub|{TEST_YEAR}|{TEST_MONTH}|{TEST_DAY}"
    )
    browse_day_1_id = (
        f"DAY|{entry_id}|{TEST_CHANNEL}|sub|{TEST_YEAR}|{TEST_MONTH}|{TEST_DAY2}"
    )
    assert browse.domain == DOMAIN
    assert browse.title == f"{TEST_NVR_NAME} Low res."
    assert browse.identifier == browse_days_id
    assert browse.children[0].identifier == browse_day_0_id
    assert browse.children[1].identifier == browse_day_1_id


async def test_browsing_rec_playback_unsupported(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test browsing a Reolink camera which does not support playback of recordings."""

    def test_supported(ch, key):
        """Test supported function."""
        if key == "replay":
            return False
        return True

    reolink_host.supported = test_supported

    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.CAMERA]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # browse root
    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}")

    assert browse.domain == DOMAIN
    assert browse.title == "Reolink"
    assert browse.identifier is None
    assert browse.children == []


async def test_browsing_errors(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test browsing a Reolink camera errors."""
    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.CAMERA]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # browse root
    with pytest.raises(Unresolvable):
        await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}/UNKNOWN")
    with pytest.raises(Unresolvable):
        await async_resolve_media(hass, f"{URI_SCHEME}{DOMAIN}/UNKNOWN", None)


async def test_browsing_not_loaded(
    hass: HomeAssistant,
    reolink_host: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test browsing a Reolink camera integration which is not loaded."""
    with patch("homeassistant.components.reolink.PLATFORMS", [Platform.CAMERA]):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    reolink_host.get_host_data.side_effect = ReolinkError("Test error")
    config_entry2 = MockConfigEntry(
        domain=DOMAIN,
        unique_id=format_mac(TEST_MAC2),
        data={
            CONF_HOST: TEST_HOST2,
            CONF_USERNAME: TEST_USERNAME2,
            CONF_PASSWORD: TEST_PASSWORD2,
            CONF_PORT: TEST_PORT,
            CONF_USE_HTTPS: TEST_USE_HTTPS,
            CONF_BC_PORT: TEST_BC_PORT,
        },
        options={
            CONF_PROTOCOL: DEFAULT_PROTOCOL,
        },
        title=TEST_NVR_NAME2,
    )
    config_entry2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry2.entry_id) is False
    await hass.async_block_till_done()

    # browse root
    browse = await async_browse_media(hass, f"{URI_SCHEME}{DOMAIN}")

    assert browse.domain == DOMAIN
    assert browse.title == "Reolink"
    assert browse.identifier is None
    assert len(browse.children) == 1
