# HACK-GRAHAM-Start: Inject devices defined in static config into discovery workflow

import logging
import asyncio
from os.path import dirname, join
from homeassistant.components.tplink import get_manually_configured_devices

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    assert len(asyncio.run(get_manually_configured_devices())) == 0
    assert len(asyncio.run(get_manually_configured_devices(
        join(dirname(__file__), "fixtures", "network_devices_empty.json")))) == 0
    assert len(asyncio.run(get_manually_configured_devices(
        join(dirname(__file__), "fixtures", "network_devices_invalid.json")))) == 0
    assert len(asyncio.run(get_manually_configured_devices(
        join(dirname(__file__), "fixtures", "network_devices_valid.json")))) > 0

# HACK-GRAHAM-Finish
