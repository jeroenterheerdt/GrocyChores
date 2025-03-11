import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_NAME,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import CoreState, HomeAssistant, asyncio, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_state_change,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .apis.grocy_chores import GrocyChoresAPI
from .const import DOMAIN, STATE_INIT
from .coordinator import GrocyChoresCoordinator
from .schema import configuration_schema
from .services import async_setup_services, async_unload_services
from .utils import update_domain_data

LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = configuration_schema
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

mqtt_lock = asyncio.Lock()


async def async_setup(hass: HomeAssistant, config: dict):
    update_domain_data(hass, "configuration", CONFIG_SCHEMA(config).get(DOMAIN, {}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    LOGGER.info("🔄 Initializing Grocy Chores")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("instances", {})
    hass.data[DOMAIN].setdefault("entities", {})

    config = entry.options or entry.data
    verify_ssl = config.get("verify_ssl", True)

    api = GrocyChoresAPI(
        async_get_clientsession(hass, verify_ssl=verify_ssl), hass, config
    )
    session = async_get_clientsession(hass)
    coordinator = GrocyChoresCoordinator(hass, session, entry, api)

    hass.data[DOMAIN]["instances"]["coordinator"] = coordinator
    hass.data[DOMAIN]["instances"]["session"] = session
    hass.data[DOMAIN]["instances"]["api"] = api
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Grocy Chores integration."""
    LOGGER.info("🔄 Unloading Grocy Chores...")

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )

    if unload_ok:
        if DOMAIN in hass.data:
            hass.data.pop(DOMAIN)

        if not hass.data.get(DOMAIN, {}):
            async_unload_services(hass)

    return unload_ok
