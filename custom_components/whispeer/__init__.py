"""
Custom integration to integrate Whispeer with Home Assistant.

For more details about this integration, please refer to
https://github.com/patlanio/whispeer
"""
import asyncio
import logging
import os
from datetime import timedelta

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core_config import Config
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.components.http import HomeAssistantView

from .api import WhispeerApiClient
from .const import CONF_PASSWORD
from .const import CONF_USERNAME
from .const import DOMAIN
from .const import PLATFORMS
from .const import STARTUP_MESSAGE

SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER: logging.Logger = logging.getLogger(__package__)


class WhispeerPanelView(HomeAssistantView):
    """View to serve the Whispeer panel."""

    url = "/api/whispeer/panel"
    name = "api:whispeer:panel"
    requires_auth = False

    async def get(self, request):
        """Return the panel HTML."""
        panel_path = os.path.join(
            os.path.dirname(__file__), "panel", "index.html"
        )
        
        try:
            with open(panel_path, "r", encoding="utf-8") as file:
                content = file.read()
            return web.Response(text=content, content_type="text/html")
        except FileNotFoundError:
            return web.Response(text="Panel not found", status=404)


class WhispeerApiView(HomeAssistantView):
    """View to handle Whispeer API endpoints."""

    url = "/api/whispeer/devices"
    name = "api:whispeer:devices"
    requires_auth = True

    async def get(self, request):
        """Get devices."""
        try:
            hass = request.app["hass"]
            domain_data = hass.data.get(DOMAIN, {})
            
            # Get the first coordinator entry
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                devices = await coordinator.api.async_get_devices()
                return web.json_response({"devices": devices})
            else:
                return web.json_response({"devices": []})
        except Exception as e:
            _LOGGER.error(f"Error getting devices: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def post(self, request):
        """Add a new device."""
        try:
            hass = request.app["hass"]
            domain_data = hass.data.get(DOMAIN, {})
            
            # Get the first coordinator entry
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                data = await request.json()
                result = await coordinator.api.async_add_device(data)
                return web.json_response(result)
            else:
                return web.json_response({"error": "No coordinator found"}, status=500)
        except Exception as e:
            _LOGGER.error(f"Error adding device: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerDeviceView(HomeAssistantView):
    """View to handle individual device operations."""

    url = "/api/whispeer/device/{device_id}"
    name = "api:whispeer:device"
    requires_auth = True

    async def delete(self, request):
        """Remove a device."""
        try:
            hass = request.app["hass"]
            domain_data = hass.data.get(DOMAIN, {})
            device_id = int(request.match_info['device_id'])
            
            # Get the first coordinator entry
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                result = await coordinator.api.async_remove_device(device_id)
                return web.json_response(result)
            else:
                return web.json_response({"error": "No coordinator found"}, status=500)
        except Exception as e:
            _LOGGER.error(f"Error removing device: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def post(self, request):
        """Test a device."""
        try:
            hass = request.app["hass"]
            domain_data = hass.data.get(DOMAIN, {})
            device_id = int(request.match_info['device_id'])
            
            # Get the first coordinator entry
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                result = await coordinator.api.async_test_device(device_id)
                return web.json_response(result)
            else:
                return web.json_response({"error": "No coordinator found"}, status=500)
        except Exception as e:
            _LOGGER.error(f"Error testing device: {e}")
            return web.json_response({"error": str(e)}, status=500)


async def register_panel(hass):
    """Register the Whispeer panel."""
    try:
        # Register all the views
        hass.http.register_view(WhispeerPanelView())
        hass.http.register_view(WhispeerApiView())
        hass.http.register_view(WhispeerDeviceView())
        
        # Import the frontend component
        from homeassistant.components import frontend
        
        # Register the panel - this is a sync function, not async
        frontend.async_register_built_in_panel(
            hass,
            "iframe",
            "Whispeer",
            "mdi:microphone",
            "whispeer",
            {"url": "/api/whispeer/panel"},
            False,
        )
        
        _LOGGER.info("Whispeer panel registered successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to register Whispeer panel: {e}")
        _LOGGER.exception("Full error details:")


async def async_setup(hass: HomeAssistant, config: Config):
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    session = async_get_clientsession(hass)
    client = WhispeerApiClient(username, password, session)

    coordinator = WhispeerDataUpdateCoordinator(hass, client=client)
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    platforms_to_setup = []
    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            coordinator.platforms.append(platform)
            platforms_to_setup.append(platform)
    
    if platforms_to_setup:
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)

    # Register the panel after the platforms are set up
    await register_panel(hass)

    entry.add_update_listener(async_reload_entry)
    return True


class WhispeerDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: WhispeerApiClient,
    ) -> None:
        """Initialize."""
        self.api = client
        self.platforms = []

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.api.async_get_data()
        except Exception as exception:
            raise UpdateFailed() from exception


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
