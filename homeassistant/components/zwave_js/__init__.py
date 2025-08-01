"""The Z-Wave JS integration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import contextlib
import logging
from typing import Any

from awesomeversion import AwesomeVersion
import voluptuous as vol
from zwave_js_server.client import Client as ZwaveClient
from zwave_js_server.const import CommandClass, RemoveNodeReason
from zwave_js_server.exceptions import (
    BaseZwaveJSServerError,
    InvalidServerVersion,
    NotConnected,
)
from zwave_js_server.model.driver import Driver
from zwave_js_server.model.node import Node as ZwaveNode
from zwave_js_server.model.notification import (
    EntryControlNotification,
    MultilevelSwitchNotification,
    NotificationNotification,
    PowerLevelNotification,
)
from zwave_js_server.model.value import Value, ValueNotification

from homeassistant.components.hassio import AddonError, AddonManager, AddonState
from homeassistant.components.persistent_notification import async_create
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_ID,
    ATTR_DOMAIN,
    ATTR_ENTITY_ID,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP,
    EVENT_LOGGING_CHANGED,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.typing import UNDEFINED, ConfigType

from .addon import get_addon_manager
from .api import async_register_api
from .const import (
    ATTR_ACKNOWLEDGED_FRAMES,
    ATTR_COMMAND_CLASS,
    ATTR_COMMAND_CLASS_NAME,
    ATTR_DATA_TYPE,
    ATTR_DATA_TYPE_LABEL,
    ATTR_DIRECTION,
    ATTR_ENDPOINT,
    ATTR_EVENT,
    ATTR_EVENT_DATA,
    ATTR_EVENT_LABEL,
    ATTR_EVENT_TYPE,
    ATTR_EVENT_TYPE_LABEL,
    ATTR_HOME_ID,
    ATTR_LABEL,
    ATTR_NODE_ID,
    ATTR_PARAMETERS,
    ATTR_PROPERTY,
    ATTR_PROPERTY_KEY,
    ATTR_PROPERTY_KEY_NAME,
    ATTR_PROPERTY_NAME,
    ATTR_STATUS,
    ATTR_TEST_NODE_ID,
    ATTR_TYPE,
    ATTR_VALUE,
    ATTR_VALUE_RAW,
    CONF_ADDON_DEVICE,
    CONF_ADDON_LR_S2_ACCESS_CONTROL_KEY,
    CONF_ADDON_LR_S2_AUTHENTICATED_KEY,
    CONF_ADDON_NETWORK_KEY,
    CONF_ADDON_S0_LEGACY_KEY,
    CONF_ADDON_S2_ACCESS_CONTROL_KEY,
    CONF_ADDON_S2_AUTHENTICATED_KEY,
    CONF_ADDON_S2_UNAUTHENTICATED_KEY,
    CONF_DATA_COLLECTION_OPTED_IN,
    CONF_INSTALLER_MODE,
    CONF_INTEGRATION_CREATED_ADDON,
    CONF_KEEP_OLD_DEVICES,
    CONF_LR_S2_ACCESS_CONTROL_KEY,
    CONF_LR_S2_AUTHENTICATED_KEY,
    CONF_NETWORK_KEY,
    CONF_S0_LEGACY_KEY,
    CONF_S2_ACCESS_CONTROL_KEY,
    CONF_S2_AUTHENTICATED_KEY,
    CONF_S2_UNAUTHENTICATED_KEY,
    CONF_USB_PATH,
    CONF_USE_ADDON,
    DOMAIN,
    DRIVER_READY_TIMEOUT,
    EVENT_DEVICE_ADDED_TO_REGISTRY,
    EVENT_VALUE_UPDATED,
    LIB_LOGGER,
    LOGGER,
    LR_ADDON_VERSION,
    USER_AGENT,
    ZWAVE_JS_NOTIFICATION_EVENT,
    ZWAVE_JS_VALUE_NOTIFICATION_EVENT,
    ZWAVE_JS_VALUE_UPDATED_EVENT,
)
from .discovery import (
    ZwaveDiscoveryInfo,
    async_discover_node_values,
    async_discover_single_value,
)
from .helpers import (
    async_disable_server_logging_if_needed,
    async_enable_server_logging_if_needed,
    async_enable_statistics,
    get_device_id,
    get_device_id_ext,
    get_network_identifier_for_notification,
    get_unique_id,
    get_valueless_base_unique_id,
)
from .migrate import async_migrate_discovered_value
from .models import ZwaveJSConfigEntry, ZwaveJSData
from .services import async_setup_services

CONNECT_TIMEOUT = 10

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_INSTALLER_MODE, default=False): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
MIN_CONTROLLER_FIRMWARE_SDK_VERSION = AwesomeVersion("6.50.0")

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SIREN,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Z-Wave JS component."""
    hass.data[DOMAIN] = config.get(DOMAIN, {})
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not isinstance(entry.unique_id, str):
            hass.config_entries.async_update_entry(
                entry, unique_id=str(entry.unique_id)
            )

    async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZwaveJSConfigEntry) -> bool:
    """Set up Z-Wave JS from a config entry."""
    if use_addon := entry.data.get(CONF_USE_ADDON):
        await async_ensure_addon_running(hass, entry)

    client = ZwaveClient(
        entry.data[CONF_URL],
        async_get_clientsession(hass),
        additional_user_agent_components=USER_AGENT,
    )

    # connect and throw error if connection failed
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await client.connect()
    except InvalidServerVersion as err:
        if use_addon:
            addon_manager = _get_addon_manager(hass)
            addon_manager.async_schedule_update_addon(catch_error=True)
        else:
            async_create_issue(
                hass,
                DOMAIN,
                "invalid_server_version",
                is_fixable=False,
                severity=IssueSeverity.ERROR,
                translation_key="invalid_server_version",
            )
        raise ConfigEntryNotReady(f"Invalid server version: {err}") from err
    except (TimeoutError, BaseZwaveJSServerError) as err:
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    async_delete_issue(hass, DOMAIN, "invalid_server_version")
    LOGGER.debug("Connected to Zwave JS Server")

    # Set up websocket API
    async_register_api(hass)

    driver_ready = asyncio.Event()
    listen_task = entry.async_create_background_task(
        hass,
        client_listen(hass, entry, client, driver_ready),
        f"{DOMAIN}_{entry.title}_client_listen",
    )

    entry.async_on_unload(client.disconnect)

    async def handle_ha_shutdown(event: Event) -> None:
        """Handle HA shutdown."""
        await client.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, handle_ha_shutdown)
    )

    driver_ready_task = entry.async_create_task(
        hass,
        driver_ready.wait(),
        f"{DOMAIN}_{entry.title}_driver_ready",
    )
    done, pending = await asyncio.wait(
        (driver_ready_task, listen_task),
        return_when=asyncio.FIRST_COMPLETED,
        timeout=DRIVER_READY_TIMEOUT,
    )

    if driver_ready_task in pending or listen_task in done:
        error_message = "Driver ready timed out"
        listen_error: BaseException | None = None
        if listen_task.done():
            listen_error, error_message = _get_listen_task_error(listen_task)
        else:
            listen_task.cancel()
        driver_ready_task.cancel()
        raise ConfigEntryNotReady(error_message) from listen_error

    LOGGER.debug("Connection to Zwave JS Server initialized")

    driver_events = DriverEvents(hass, entry)
    entry_runtime_data = ZwaveJSData(
        client=client,
        driver_events=driver_events,
    )
    entry.runtime_data = entry_runtime_data

    driver = client.driver
    # When the driver is ready we know it's set on the client.
    assert driver is not None

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    with contextlib.suppress(NotConnected):
        # If the client isn't connected the listen task may have an exception
        # and we'll handle the clean up below.
        await driver_events.setup(driver)

    # If the listen task is already failed, we need to raise ConfigEntryNotReady
    if listen_task.done():
        listen_error, error_message = _get_listen_task_error(listen_task)
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        raise ConfigEntryNotReady(error_message) from listen_error

    # Re-attach trigger listeners.
    # Schedule this call to make sure the config entry is loaded first.

    @callback
    def on_config_entry_loaded() -> None:
        """Signal that server connection and driver are ready."""
        if entry.state is ConfigEntryState.LOADED:
            async_dispatcher_send(
                hass,
                f"{DOMAIN}_{driver.controller.home_id}_connected_to_server",
            )

    entry.async_on_unload(entry.async_on_state_change(on_config_entry_loaded))

    return True


def _get_listen_task_error(
    listen_task: asyncio.Task,
) -> tuple[BaseException | None, str]:
    """Check the listen task for errors."""
    if listen_error := listen_task.exception():
        error_message = f"Client listen failed: {listen_error}"
    else:
        error_message = "Client connection was closed"
    return listen_error, error_message


class DriverEvents:
    """Represent driver events."""

    driver: Driver

    def __init__(self, hass: HomeAssistant, entry: ZwaveJSConfigEntry) -> None:
        """Set up the driver events instance."""
        self.config_entry = entry
        self.dev_reg = dr.async_get(hass)
        self.hass = hass
        # Make sure to not pass self to ControllerEvents until all attributes are set.
        self.controller_events = ControllerEvents(hass, self)

    async def setup(self, driver: Driver) -> None:
        """Set up devices using the ready driver."""
        self.driver = driver
        controller = driver.controller

        # If opt in preference hasn't been specified yet, we do nothing, otherwise
        # we apply the preference
        if opted_in := self.config_entry.data.get(CONF_DATA_COLLECTION_OPTED_IN):
            await async_enable_statistics(driver)
        elif opted_in is False:
            await driver.async_disable_statistics()

        async def handle_logging_changed(_: Event | None = None) -> None:
            """Handle logging changed event."""
            if LIB_LOGGER.isEnabledFor(logging.DEBUG):
                await async_enable_server_logging_if_needed(
                    self.hass, self.config_entry, driver
                )
            else:
                await async_disable_server_logging_if_needed(
                    self.hass, self.config_entry, driver
                )

        # Set up server logging on setup if needed
        await handle_logging_changed()

        self.config_entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_LOGGING_CHANGED, handle_logging_changed)
        )

        # run discovery on controller node
        if controller.own_node:
            await self.controller_events.async_on_node_added(controller.own_node)

        # run discovery on all other ready nodes
        await asyncio.gather(
            *(
                self.controller_events.async_on_node_added(node)
                for node in controller.nodes.values()
                if node != controller.own_node
            )
        )

        # listen for new nodes being added to the mesh
        self.config_entry.async_on_unload(
            controller.on(
                "node added",
                lambda event: self.hass.async_create_task(
                    self.controller_events.async_on_node_added(event["node"]),
                    eager_start=False,
                ),
            )
        )
        # listen for nodes being removed from the mesh
        # NOTE: This will not remove nodes that were removed when HA was not running
        self.config_entry.async_on_unload(
            controller.on("node removed", self.controller_events.async_on_node_removed)
        )

        # listen for identify events for the controller
        self.config_entry.async_on_unload(
            controller.on("identify", self.controller_events.async_on_identify)
        )

        if (
            old_unique_id := self.config_entry.unique_id
        ) is not None and old_unique_id != (
            new_unique_id := str(driver.controller.home_id)
        ):
            device_registry = dr.async_get(self.hass)
            controller_model = "Unknown model"
            if (
                (own_node := driver.controller.own_node)
                and (
                    controller_device_entry := device_registry.async_get_device(
                        identifiers={get_device_id(driver, own_node)}
                    )
                )
                and (model := controller_device_entry.model)
            ):
                controller_model = model

            # Do not clean up old stale devices if an unknown controller is connected.
            data = {**self.config_entry.data, CONF_KEEP_OLD_DEVICES: True}
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            async_create_issue(
                self.hass,
                DOMAIN,
                f"migrate_unique_id.{self.config_entry.entry_id}",
                data={
                    "config_entry_id": self.config_entry.entry_id,
                    "config_entry_title": self.config_entry.title,
                    "controller_model": controller_model,
                    "new_unique_id": new_unique_id,
                    "old_unique_id": old_unique_id,
                },
                is_fixable=True,
                severity=IssueSeverity.ERROR,
                translation_key="migrate_unique_id",
            )
        else:
            data = self.config_entry.data.copy()
            data.pop(CONF_KEEP_OLD_DEVICES, None)
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            async_delete_issue(
                self.hass, DOMAIN, f"migrate_unique_id.{self.config_entry.entry_id}"
            )

        # Check for nodes that no longer exist and remove them
        stored_devices = dr.async_entries_for_config_entry(
            self.dev_reg, self.config_entry.entry_id
        )
        known_devices = [
            self.dev_reg.async_get_device(identifiers={get_device_id(driver, node)})
            for node in controller.nodes.values()
        ]
        provisioned_devices = [
            self.dev_reg.async_get(entry.additional_properties["device_id"])
            for entry in await controller.async_get_provisioning_entries()
            if entry.additional_properties
            and "device_id" in entry.additional_properties
        ]

        # Devices that are in the device registry that are not known by the controller
        # can be removed
        if not self.config_entry.data.get(CONF_KEEP_OLD_DEVICES):
            for device in stored_devices:
                if device not in known_devices and device not in provisioned_devices:
                    self.dev_reg.async_remove_device(device.id)


class ControllerEvents:
    """Represent controller events.

    Handle the following events:
    - node added
    - node removed
    """

    def __init__(self, hass: HomeAssistant, driver_events: DriverEvents) -> None:
        """Set up the controller events instance."""
        self.hass = hass
        self.config_entry = driver_events.config_entry
        self.discovered_value_ids: dict[str, set[str]] = defaultdict(set)
        self.driver_events = driver_events
        self.dev_reg = driver_events.dev_reg
        self.registered_unique_ids: dict[str, dict[Platform, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.node_events = NodeEvents(hass, self)

    @callback
    def remove_device(self, device: dr.DeviceEntry) -> None:
        """Remove device from registry."""
        # note: removal of entity registry entry is handled by core
        self.dev_reg.async_remove_device(device.id)
        self.registered_unique_ids.pop(device.id, None)
        self.discovered_value_ids.pop(device.id, None)

    async def async_on_node_added(self, node: ZwaveNode) -> None:
        """Handle node added event."""
        # Remove stale entities that may exist from a previous interview when an
        # interview is started.
        base_unique_id = get_valueless_base_unique_id(self.driver_events.driver, node)
        self.config_entry.async_on_unload(
            node.on(
                "interview started",
                lambda _: async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_{base_unique_id}_remove_entity_on_interview_started",
                ),
            )
        )

        await self.async_check_preprovisioned_device(node)

        if node.is_controller_node:
            # Create a controller status sensor for each device
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.config_entry.entry_id}_add_controller_status_sensor",
            )
        else:
            # Create a node status sensor for each device
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.config_entry.entry_id}_add_node_status_sensor",
                node,
            )

            # Create a ping button for each device
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.config_entry.entry_id}_add_ping_button_entity",
                node,
            )

        # Create statistics sensors for each device
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_{self.config_entry.entry_id}_add_statistics_sensors",
            node,
        )

        LOGGER.debug("Node added: %s", node.node_id)

        # Listen for ready node events, both new and re-interview.
        self.config_entry.async_on_unload(
            node.on(
                "ready",
                lambda event: self.hass.async_create_task(
                    self.node_events.async_on_node_ready(event["node"]),
                    eager_start=False,
                ),
            )
        )

        # we only want to run discovery when the node has reached ready state,
        # otherwise we'll have all kinds of missing info issues.
        if node.ready:
            await self.node_events.async_on_node_ready(node)
            return

        # we do submit the node to device registry so user has
        # some visual feedback that something is (in the process of) being added
        await self.async_register_node_in_dev_reg(node)

    @callback
    def async_on_node_removed(self, event: dict) -> None:
        """Handle node removed event."""
        node: ZwaveNode = event["node"]
        reason: RemoveNodeReason = event["reason"]
        # grab device in device registry attached to this node
        dev_id = get_device_id(self.driver_events.driver, node)
        device = self.dev_reg.async_get_device(identifiers={dev_id})
        # We assert because we know the device exists
        assert device
        if reason in (RemoveNodeReason.REPLACED, RemoveNodeReason.PROXY_REPLACED):
            self.discovered_value_ids.pop(device.id, None)

            async_dispatcher_send(
                self.hass,
                (
                    f"{DOMAIN}_"
                    f"{get_valueless_base_unique_id(self.driver_events.driver, node)}_"
                    "remove_entity"
                ),
            )
            # We don't want to remove the device so we can keep the user customizations
            return

        if reason == RemoveNodeReason.RESET:
            device_name = device.name_by_user or device.name or f"Node {node.node_id}"
            identifier = get_network_identifier_for_notification(
                self.hass, self.config_entry, self.driver_events.driver.controller
            )
            notification_msg = (
                f"`{device_name}` has been factory reset "
                "and removed from the Z-Wave network"
            )
            if identifier:
                # Remove trailing comma if it's there
                if identifier[-1] == ",":
                    identifier = identifier[:-1]
                notification_msg = f"{notification_msg} {identifier}."
            else:
                notification_msg = f"{notification_msg}."
            async_create(
                self.hass,
                notification_msg,
                "Device Was Factory Reset!",
                f"{DOMAIN}.node_reset_and_removed.{dev_id[1]}",
            )

        self.remove_device(device)

    @callback
    def async_on_identify(self, event: dict) -> None:
        """Handle identify event."""
        # Get node device
        node: ZwaveNode = event["node"]
        dev_id = get_device_id(self.driver_events.driver, node)
        device = self.dev_reg.async_get_device(identifiers={dev_id})
        assert device
        device_name = device.name_by_user or device.name or f"Node {node.node_id}"
        # In case the user has multiple networks, we should give them more information
        # about the network for the controller being identified.
        identifier = get_network_identifier_for_notification(
            self.hass, self.config_entry, self.driver_events.driver.controller
        )
        async_create(
            self.hass,
            (
                f"`{device_name}` has just requested the controller for your Z-Wave "
                f"network {identifier} to identify itself. No action is needed from "
                "you other than to note the source of the request, and you can safely "
                "dismiss this notification when ready."
            ),
            "New Z-Wave Identify Controller Request",
            f"{DOMAIN}.identify_controller.{dev_id[1]}",
        )

    async def async_check_preprovisioned_device(self, node: ZwaveNode) -> None:
        """Check if the node was preprovisioned and update the device registry."""
        provisioning_entry = (
            await self.driver_events.driver.controller.async_get_provisioning_entry(
                node.node_id
            )
        )
        if (
            provisioning_entry
            and provisioning_entry.additional_properties
            and "device_id" in provisioning_entry.additional_properties
        ):
            preprovisioned_device = self.dev_reg.async_get(
                provisioning_entry.additional_properties["device_id"]
            )

            if preprovisioned_device:
                dsk = provisioning_entry.dsk
                dsk_identifier = (DOMAIN, f"provision_{dsk}")

                # If the pre-provisioned device has the DSK identifier, remove it
                if dsk_identifier in preprovisioned_device.identifiers:
                    driver = self.driver_events.driver
                    device_id = get_device_id(driver, node)
                    device_id_ext = get_device_id_ext(driver, node)
                    new_identifiers = preprovisioned_device.identifiers.copy()
                    new_identifiers.remove(dsk_identifier)
                    new_identifiers.add(device_id)
                    if device_id_ext:
                        new_identifiers.add(device_id_ext)
                    self.dev_reg.async_update_device(
                        preprovisioned_device.id,
                        new_identifiers=new_identifiers,
                    )

    async def async_register_node_in_dev_reg(self, node: ZwaveNode) -> dr.DeviceEntry:
        """Register node in dev reg."""
        driver = self.driver_events.driver
        device_id = get_device_id(driver, node)
        device_id_ext = get_device_id_ext(driver, node)
        node_id_device = self.dev_reg.async_get_device(identifiers={device_id})
        via_identifier = None
        controller = driver.controller
        # Get the controller node device ID if this node is not the controller
        if controller.own_node and controller.own_node != node:
            via_identifier = get_device_id(driver, controller.own_node)

        if device_id_ext:
            # If there is a device with this node ID but with a different hardware
            # signature, remove the node ID based identifier from it. The hardware
            # signature can be different for one of two reasons: 1) in the ideal
            # scenario, the node was replaced with a different node that's a different
            # device entirely, or 2) the device erroneously advertised the wrong
            # hardware identifiers (this is known to happen due to poor RF conditions).
            # While we would like to remove the old device automatically for case 1, we
            # have no way to distinguish between these reasons so we leave it up to the
            # user to remove the old device manually.
            if (
                node_id_device
                and len(node_id_device.identifiers) == 2
                and device_id_ext not in node_id_device.identifiers
            ):
                new_identifiers = node_id_device.identifiers.copy()
                new_identifiers.remove(device_id)
                self.dev_reg.async_update_device(
                    node_id_device.id, new_identifiers=new_identifiers
                )
            # If there is an orphaned device that already exists with this hardware
            # based identifier, add the node ID based identifier to the orphaned
            # device.
            if (
                hardware_device := self.dev_reg.async_get_device(
                    identifiers={device_id_ext}
                )
            ) and len(hardware_device.identifiers) == 1:
                new_identifiers = hardware_device.identifiers.copy()
                new_identifiers.add(device_id)
                self.dev_reg.async_update_device(
                    hardware_device.id, new_identifiers=new_identifiers
                )
            ids = {device_id, device_id_ext}
        else:
            ids = {device_id}

        device = self.dev_reg.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers=ids,
            sw_version=node.firmware_version,
            name=node.name or node.device_config.description or f"Node {node.node_id}",
            model=node.device_config.label,
            manufacturer=node.device_config.manufacturer,
            suggested_area=node.location if node.location else UNDEFINED,
            via_device=via_identifier,
        )

        async_dispatcher_send(self.hass, EVENT_DEVICE_ADDED_TO_REGISTRY, device)

        return device


class NodeEvents:
    """Represent node events.

    Handle the following events:
    - ready
    - value added
    - value updated
    - metadata updated
    - value notification
    - notification
    """

    def __init__(
        self, hass: HomeAssistant, controller_events: ControllerEvents
    ) -> None:
        """Set up the node events instance."""
        self.config_entry = controller_events.config_entry
        self.controller_events = controller_events
        self.dev_reg = controller_events.dev_reg
        self.ent_reg = er.async_get(hass)
        self.hass = hass

    async def async_on_node_ready(self, node: ZwaveNode) -> None:
        """Handle node ready event."""
        LOGGER.debug("Processing node %s", node)
        # register (or update) node in device registry
        device = await self.controller_events.async_register_node_in_dev_reg(node)

        # Remove any old value ids if this is a reinterview.
        self.controller_events.discovered_value_ids.pop(device.id, None)

        value_updates_disc_info: dict[str, ZwaveDiscoveryInfo] = {}

        # run discovery on all node values and create/update entities
        await asyncio.gather(
            *(
                self.async_handle_discovery_info(
                    device, disc_info, value_updates_disc_info
                )
                for disc_info in async_discover_node_values(
                    node, device, self.controller_events.discovered_value_ids
                )
            )
        )

        # add listeners to handle new values that get added later
        for event in ("value added", EVENT_VALUE_UPDATED, "metadata updated"):
            self.config_entry.async_on_unload(
                node.on(
                    event,
                    lambda event: self.hass.async_create_task(
                        self.async_on_value_added(
                            value_updates_disc_info, event["value"]
                        )
                    ),
                )
            )

        # add listener for stateless node value notification events
        self.config_entry.async_on_unload(
            node.on(
                "value notification",
                lambda event: self.async_on_value_notification(
                    event["value_notification"]
                ),
            )
        )

        # add listener for stateless node notification events
        self.config_entry.async_on_unload(
            node.on("notification", self.async_on_notification)
        )

        # Create a firmware update entity for each device that
        # supports firmware updates
        controller = self.controller_events.driver_events.driver.controller
        if (
            not (is_controller_node := node.is_controller_node)
            and any(
                cc.id == CommandClass.FIRMWARE_UPDATE_MD.value
                for cc in node.command_classes
            )
        ) or (
            is_controller_node
            and (sdk_version := controller.sdk_version) is not None
            and sdk_version >= MIN_CONTROLLER_FIRMWARE_SDK_VERSION
        ):
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.config_entry.entry_id}_add_firmware_update_entity",
                node,
            )

        # After ensuring the node is set up in HA, we should check if the node's
        # device config has changed, and if so, issue a repair registry entry for a
        # possible reinterview
        if not node.is_controller_node and await node.async_has_device_config_changed():
            device_name = device.name_by_user or device.name or "Unnamed device"
            async_create_issue(
                self.hass,
                DOMAIN,
                f"device_config_file_changed.{device.id}",
                data={"device_id": device.id, "device_name": device_name},
                is_fixable=True,
                is_persistent=False,
                translation_key="device_config_file_changed",
                translation_placeholders={"device_name": device_name},
                severity=IssueSeverity.WARNING,
            )

    async def async_handle_discovery_info(
        self,
        device: dr.DeviceEntry,
        disc_info: ZwaveDiscoveryInfo,
        value_updates_disc_info: dict[str, ZwaveDiscoveryInfo],
    ) -> None:
        """Handle discovery info and all dependent tasks."""
        platform = disc_info.platform
        # This migration logic was added in 2021.3 to handle a breaking change to
        # the value_id format. Some time in the future, this call (as well as the
        # helper functions) can be removed.
        async_migrate_discovered_value(
            self.hass,
            self.ent_reg,
            self.controller_events.registered_unique_ids[device.id][platform],
            device,
            self.controller_events.driver_events.driver,
            disc_info,
        )

        LOGGER.debug("Discovered entity: %s", disc_info)
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_{self.config_entry.entry_id}_add_{platform}",
            disc_info,
        )

        # If we don't need to watch for updates return early
        if not disc_info.assumed_state:
            return
        value_updates_disc_info[disc_info.primary_value.value_id] = disc_info
        # If this is not the first time we found a value we want to watch for updates,
        # return early because we only need one listener for all values.
        if len(value_updates_disc_info) != 1:
            return
        # add listener for value updated events
        self.config_entry.async_on_unload(
            disc_info.node.on(
                EVENT_VALUE_UPDATED,
                lambda event: self.async_on_value_updated_fire_event(
                    value_updates_disc_info, event["value"]
                ),
            )
        )

    async def async_on_value_added(
        self, value_updates_disc_info: dict[str, ZwaveDiscoveryInfo], value: Value
    ) -> None:
        """Fire value updated event."""
        # If node isn't ready or a device for this node doesn't already exist, we can
        # let the node ready event handler perform discovery. If a value has already
        # been processed, we don't need to do it again
        device_id = get_device_id(
            self.controller_events.driver_events.driver, value.node
        )
        if (
            not value.node.ready
            or not (device := self.dev_reg.async_get_device(identifiers={device_id}))
            or value.value_id in self.controller_events.discovered_value_ids[device.id]
        ):
            return

        LOGGER.debug("Processing node %s added value %s", value.node, value)
        await asyncio.gather(
            *(
                self.async_handle_discovery_info(
                    device, disc_info, value_updates_disc_info
                )
                for disc_info in async_discover_single_value(
                    value, device, self.controller_events.discovered_value_ids
                )
            )
        )

    @callback
    def async_on_value_notification(self, notification: ValueNotification) -> None:
        """Relay stateless value notification events from Z-Wave nodes to hass."""
        driver = self.controller_events.driver_events.driver
        device = self.dev_reg.async_get_device(
            identifiers={get_device_id(driver, notification.node)}
        )
        # We assert because we know the device exists
        assert device
        raw_value = value = notification.value
        if notification.metadata.states:
            value = notification.metadata.states.get(str(value), value)
        self.hass.bus.async_fire(
            ZWAVE_JS_VALUE_NOTIFICATION_EVENT,
            {
                ATTR_DOMAIN: DOMAIN,
                ATTR_NODE_ID: notification.node.node_id,
                ATTR_HOME_ID: driver.controller.home_id,
                ATTR_ENDPOINT: notification.endpoint,
                ATTR_DEVICE_ID: device.id,
                ATTR_COMMAND_CLASS: notification.command_class,
                ATTR_COMMAND_CLASS_NAME: notification.command_class_name,
                ATTR_LABEL: notification.metadata.label,
                ATTR_PROPERTY: notification.property_,
                ATTR_PROPERTY_NAME: notification.property_name,
                ATTR_PROPERTY_KEY: notification.property_key,
                ATTR_PROPERTY_KEY_NAME: notification.property_key_name,
                ATTR_VALUE: value,
                ATTR_VALUE_RAW: raw_value,
            },
        )

    @callback
    def async_on_notification(self, event: dict[str, Any]) -> None:
        """Relay stateless notification events from Z-Wave nodes to hass."""
        if "notification" not in event:
            LOGGER.info("Unknown notification: %s", event)
            return

        driver = self.controller_events.driver_events.driver
        notification: (
            EntryControlNotification
            | NotificationNotification
            | PowerLevelNotification
            | MultilevelSwitchNotification
        ) = event["notification"]
        device = self.dev_reg.async_get_device(
            identifiers={get_device_id(driver, notification.node)}
        )
        # We assert because we know the device exists
        assert device
        event_data = {
            ATTR_DOMAIN: DOMAIN,
            ATTR_NODE_ID: notification.node.node_id,
            ATTR_HOME_ID: driver.controller.home_id,
            ATTR_ENDPOINT: notification.endpoint_idx,
            ATTR_DEVICE_ID: device.id,
            ATTR_COMMAND_CLASS: notification.command_class,
        }

        if isinstance(notification, EntryControlNotification):
            event_data.update(
                {
                    ATTR_COMMAND_CLASS_NAME: "Entry Control",
                    ATTR_EVENT_TYPE: notification.event_type,
                    ATTR_EVENT_TYPE_LABEL: notification.event_type_label,
                    ATTR_DATA_TYPE: notification.data_type,
                    ATTR_DATA_TYPE_LABEL: notification.data_type_label,
                    ATTR_EVENT_DATA: notification.event_data,
                }
            )
        elif isinstance(notification, NotificationNotification):
            event_data.update(
                {
                    ATTR_COMMAND_CLASS_NAME: "Notification",
                    ATTR_LABEL: notification.label,
                    ATTR_TYPE: notification.type_,
                    ATTR_EVENT: notification.event,
                    ATTR_EVENT_LABEL: notification.event_label,
                    ATTR_PARAMETERS: notification.parameters,
                }
            )
        elif isinstance(notification, PowerLevelNotification):
            event_data.update(
                {
                    ATTR_COMMAND_CLASS_NAME: "Powerlevel",
                    ATTR_TEST_NODE_ID: notification.test_node_id,
                    ATTR_STATUS: notification.status,
                    ATTR_ACKNOWLEDGED_FRAMES: notification.acknowledged_frames,
                }
            )
        elif isinstance(notification, MultilevelSwitchNotification):
            event_data.update(
                {
                    ATTR_COMMAND_CLASS_NAME: "Multilevel Switch",
                    ATTR_EVENT_TYPE: notification.event_type,
                    ATTR_EVENT_TYPE_LABEL: notification.event_type_label,
                    ATTR_DIRECTION: notification.direction,
                }
            )
        else:
            raise TypeError(f"Unhandled notification type: {notification}")

        self.hass.bus.async_fire(ZWAVE_JS_NOTIFICATION_EVENT, event_data)

    @callback
    def async_on_value_updated_fire_event(
        self, value_updates_disc_info: dict[str, ZwaveDiscoveryInfo], value: Value
    ) -> None:
        """Fire value updated event."""
        # Get the discovery info for the value that was updated. If there is
        # no discovery info for this value, we don't need to fire an event
        if value.value_id not in value_updates_disc_info:
            return

        driver = self.controller_events.driver_events.driver
        disc_info = value_updates_disc_info[value.value_id]

        device = self.dev_reg.async_get_device(
            identifiers={get_device_id(driver, value.node)}
        )
        # We assert because we know the device exists
        assert device

        unique_id = get_unique_id(driver, disc_info.primary_value.value_id)
        entity_id = self.ent_reg.async_get_entity_id(
            disc_info.platform, DOMAIN, unique_id
        )

        raw_value = value_ = value.value
        if value.metadata.states:
            value_ = value.metadata.states.get(str(value_), value_)

        self.hass.bus.async_fire(
            ZWAVE_JS_VALUE_UPDATED_EVENT,
            {
                ATTR_NODE_ID: value.node.node_id,
                ATTR_HOME_ID: driver.controller.home_id,
                ATTR_DEVICE_ID: device.id,
                ATTR_ENTITY_ID: entity_id,
                ATTR_COMMAND_CLASS: value.command_class,
                ATTR_COMMAND_CLASS_NAME: value.command_class_name,
                ATTR_ENDPOINT: value.endpoint,
                ATTR_PROPERTY: value.property_,
                ATTR_PROPERTY_NAME: value.property_name,
                ATTR_PROPERTY_KEY: value.property_key,
                ATTR_PROPERTY_KEY_NAME: value.property_key_name,
                ATTR_VALUE: value_,
                ATTR_VALUE_RAW: raw_value,
            },
        )


async def client_listen(
    hass: HomeAssistant,
    entry: ZwaveJSConfigEntry,
    client: ZwaveClient,
    driver_ready: asyncio.Event,
) -> None:
    """Listen with the client."""
    try:
        await client.listen(driver_ready)
    except BaseZwaveJSServerError as err:
        if entry.state is not ConfigEntryState.LOADED:
            raise
        LOGGER.error("Client listen failed: %s", err)
    except Exception as err:
        # We need to guard against unknown exceptions to not crash this task.
        LOGGER.exception("Unexpected exception: %s", err)
        if entry.state is not ConfigEntryState.LOADED:
            raise

    # The entry needs to be reloaded since a new driver state
    # will be acquired on reconnect.
    # All model instances will be replaced when the new state is acquired.
    if not hass.is_stopping:
        if entry.state is not ConfigEntryState.LOADED:
            raise HomeAssistantError("Listen task ended unexpectedly")
        LOGGER.debug("Disconnected from server. Reloading integration")
        hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZwaveJSConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    entry_runtime_data = entry.runtime_data
    client = entry_runtime_data.client

    if client.connected and (driver := client.driver):
        await async_disable_server_logging_if_needed(hass, entry, driver)

    if entry.data.get(CONF_USE_ADDON) and entry.disabled_by:
        addon_manager: AddonManager = get_addon_manager(hass)
        LOGGER.debug("Stopping Z-Wave JS add-on")
        try:
            await addon_manager.async_stop_addon()
        except AddonError as err:
            LOGGER.error("Failed to stop the Z-Wave JS add-on: %s", err)
            return False

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ZwaveJSConfigEntry) -> None:
    """Remove a config entry."""
    if not entry.data.get(CONF_INTEGRATION_CREATED_ADDON):
        return

    addon_manager: AddonManager = get_addon_manager(hass)
    try:
        await addon_manager.async_stop_addon()
    except AddonError as err:
        LOGGER.error(err)
        return
    try:
        await addon_manager.async_create_backup()
    except AddonError as err:
        LOGGER.error(err)
        return
    try:
        await addon_manager.async_uninstall_addon()
    except AddonError as err:
        LOGGER.error(err)


async def async_ensure_addon_running(
    hass: HomeAssistant, entry: ZwaveJSConfigEntry
) -> None:
    """Ensure that Z-Wave JS add-on is installed and running."""
    addon_manager = _get_addon_manager(hass)
    try:
        addon_info = await addon_manager.async_get_addon_info()
    except AddonError as err:
        raise ConfigEntryNotReady(err) from err

    usb_path: str = entry.data[CONF_USB_PATH]
    # s0_legacy_key was saved as network_key before s2 was added.
    s0_legacy_key: str = entry.data.get(CONF_S0_LEGACY_KEY, "")
    if not s0_legacy_key:
        s0_legacy_key = entry.data.get(CONF_NETWORK_KEY, "")
    s2_access_control_key: str = entry.data.get(CONF_S2_ACCESS_CONTROL_KEY, "")
    s2_authenticated_key: str = entry.data.get(CONF_S2_AUTHENTICATED_KEY, "")
    s2_unauthenticated_key: str = entry.data.get(CONF_S2_UNAUTHENTICATED_KEY, "")
    lr_s2_access_control_key: str = entry.data.get(CONF_LR_S2_ACCESS_CONTROL_KEY, "")
    lr_s2_authenticated_key: str = entry.data.get(CONF_LR_S2_AUTHENTICATED_KEY, "")
    addon_state = addon_info.state
    addon_config = {
        CONF_ADDON_DEVICE: usb_path,
        CONF_ADDON_S0_LEGACY_KEY: s0_legacy_key,
        CONF_ADDON_S2_ACCESS_CONTROL_KEY: s2_access_control_key,
        CONF_ADDON_S2_AUTHENTICATED_KEY: s2_authenticated_key,
        CONF_ADDON_S2_UNAUTHENTICATED_KEY: s2_unauthenticated_key,
    }
    if addon_info.version and AwesomeVersion(addon_info.version) >= LR_ADDON_VERSION:
        addon_config[CONF_ADDON_LR_S2_ACCESS_CONTROL_KEY] = lr_s2_access_control_key
        addon_config[CONF_ADDON_LR_S2_AUTHENTICATED_KEY] = lr_s2_authenticated_key

    if addon_state == AddonState.NOT_INSTALLED:
        addon_manager.async_schedule_install_setup_addon(
            addon_config,
            catch_error=True,
        )
        raise ConfigEntryNotReady

    if addon_state == AddonState.NOT_RUNNING:
        addon_manager.async_schedule_setup_addon(
            addon_config,
            catch_error=True,
        )
        raise ConfigEntryNotReady

    addon_options = addon_info.options
    addon_device = addon_options[CONF_ADDON_DEVICE]
    # s0_legacy_key was saved as network_key before s2 was added.
    addon_s0_legacy_key = addon_options.get(CONF_ADDON_S0_LEGACY_KEY, "")
    if not addon_s0_legacy_key:
        addon_s0_legacy_key = addon_options.get(CONF_ADDON_NETWORK_KEY, "")
    addon_s2_access_control_key = addon_options.get(
        CONF_ADDON_S2_ACCESS_CONTROL_KEY, ""
    )
    addon_s2_authenticated_key = addon_options.get(CONF_ADDON_S2_AUTHENTICATED_KEY, "")
    addon_s2_unauthenticated_key = addon_options.get(
        CONF_ADDON_S2_UNAUTHENTICATED_KEY, ""
    )
    updates = {}
    if usb_path != addon_device:
        updates[CONF_USB_PATH] = addon_device
    if s0_legacy_key != addon_s0_legacy_key:
        updates[CONF_S0_LEGACY_KEY] = addon_s0_legacy_key
    if s2_access_control_key != addon_s2_access_control_key:
        updates[CONF_S2_ACCESS_CONTROL_KEY] = addon_s2_access_control_key
    if s2_authenticated_key != addon_s2_authenticated_key:
        updates[CONF_S2_AUTHENTICATED_KEY] = addon_s2_authenticated_key
    if s2_unauthenticated_key != addon_s2_unauthenticated_key:
        updates[CONF_S2_UNAUTHENTICATED_KEY] = addon_s2_unauthenticated_key

    if addon_info.version and AwesomeVersion(addon_info.version) >= AwesomeVersion(
        LR_ADDON_VERSION
    ):
        addon_lr_s2_access_control_key = addon_options.get(
            CONF_ADDON_LR_S2_ACCESS_CONTROL_KEY, ""
        )
        addon_lr_s2_authenticated_key = addon_options.get(
            CONF_ADDON_LR_S2_AUTHENTICATED_KEY, ""
        )
        if lr_s2_access_control_key != addon_lr_s2_access_control_key:
            updates[CONF_LR_S2_ACCESS_CONTROL_KEY] = addon_lr_s2_access_control_key
        if lr_s2_authenticated_key != addon_lr_s2_authenticated_key:
            updates[CONF_LR_S2_AUTHENTICATED_KEY] = addon_lr_s2_authenticated_key

    if updates:
        hass.config_entries.async_update_entry(entry, data={**entry.data, **updates})


@callback
def _get_addon_manager(hass: HomeAssistant) -> AddonManager:
    """Ensure that Z-Wave JS add-on is updated and running."""
    addon_manager: AddonManager = get_addon_manager(hass)
    if addon_manager.task_in_progress():
        raise ConfigEntryNotReady
    return addon_manager
