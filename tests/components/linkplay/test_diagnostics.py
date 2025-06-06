"""Tests for the LinkPlay diagnostics."""

from unittest.mock import patch

from linkplay.bridge import LinkPlayMultiroom
from linkplay.consts import API_ENDPOINT
from linkplay.endpoint import LinkPlayApiEndpoint
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.linkplay.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import setup_integration
from .conftest import HOST, mock_lp_aiohttp_client

from tests.common import MockConfigEntry, async_load_fixture
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test diagnostics."""

    with (
        mock_lp_aiohttp_client() as mock_session,
        patch.object(LinkPlayMultiroom, "update_status", return_value=None),
    ):
        endpoints = [
            LinkPlayApiEndpoint(
                protocol="https", port=443, endpoint=HOST, session=None
            ),
            LinkPlayApiEndpoint(protocol="http", port=80, endpoint=HOST, session=None),
        ]
        for endpoint in endpoints:
            mock_session.get(
                API_ENDPOINT.format(str(endpoint), "getPlayerStatusEx"),
                text=await async_load_fixture(hass, "getPlayerEx.json", DOMAIN),
            )

            mock_session.get(
                API_ENDPOINT.format(str(endpoint), "getStatusEx"),
                text=await async_load_fixture(hass, "getStatusEx.json", DOMAIN),
            )

        await setup_integration(hass, mock_config_entry)

        assert (
            await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
            == snapshot
        )
