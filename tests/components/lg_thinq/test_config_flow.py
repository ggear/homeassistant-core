"""Test the lgthinq config flow."""

from unittest.mock import AsyncMock

from homeassistant.components.lg_thinq.const import CONF_CONNECT_CLIENT_ID, DOMAIN
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_COUNTRY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import MOCK_CONNECT_CLIENT_ID, MOCK_COUNTRY, MOCK_PAT

from tests.common import MockConfigEntry

DHCP_DISCOVERY = DhcpServiceInfo(
    ip="1.1.1.1",
    hostname="LG_Smart_Dryer2_open",
    macaddress=dr.format_mac("34:E6:E6:11:22:33").replace(":", ""),
)


async def test_config_flow(
    hass: HomeAssistant,
    mock_config_thinq_api: AsyncMock,
    mock_uuid: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that an thinq entry is normally created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: MOCK_PAT, CONF_COUNTRY: MOCK_COUNTRY},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ACCESS_TOKEN: MOCK_PAT,
        CONF_COUNTRY: MOCK_COUNTRY,
        CONF_CONNECT_CLIENT_ID: MOCK_CONNECT_CLIENT_ID,
    }

    mock_config_thinq_api.async_get_device_list.assert_called_once()


async def test_config_flow_invalid_pat(
    hass: HomeAssistant,
    mock_invalid_thinq_api: AsyncMock,
) -> None:
    """Test that an thinq flow should be aborted with an invalid PAT."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_ACCESS_TOKEN: MOCK_PAT, CONF_COUNTRY: MOCK_COUNTRY},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]
    mock_invalid_thinq_api.async_get_device_list.assert_called_once()


async def test_config_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_config_thinq_api: AsyncMock,
) -> None:
    """Test that thinq flow should be aborted when already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_ACCESS_TOKEN: MOCK_PAT, CONF_COUNTRY: MOCK_COUNTRY},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_config_flow(
    hass: HomeAssistant,
    mock_config_thinq_api: AsyncMock,
    mock_uuid: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that a thinq entry is normally created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP_DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: MOCK_PAT, CONF_COUNTRY: MOCK_COUNTRY},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ACCESS_TOKEN: MOCK_PAT,
        CONF_COUNTRY: MOCK_COUNTRY,
        CONF_CONNECT_CLIENT_ID: MOCK_CONNECT_CLIENT_ID,
    }

    mock_config_thinq_api.async_get_device_list.assert_called_once()


async def test_dhcp_config_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_config_thinq_api: AsyncMock,
) -> None:
    """Test that thinq flow should be aborted when already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP_DISCOVERY
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
