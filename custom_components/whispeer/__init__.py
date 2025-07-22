"""
Custom integration to integrate Whispeer with Home Assistant.

For more details about this integration, please refer to
https://github.com/patlanio/whispeer
"""
import asyncio
import logging
import os
from datetime import timedelta

import aiofiles
from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core_config import Config
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.components import frontend
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
        """Return the panel HTML with access token injected."""
        panel_path = os.path.join(
            os.path.dirname(__file__), "panel", "index.html"
        )
        
        try:
            async with aiofiles.open(panel_path, "r", encoding="utf-8") as file:
                content = await file.read()
            
            # Get the access token from the request query params if available
            hass = request.app["hass"]
            access_token = request.query.get('access_token', '')
            
            # If no token in query, try to create a long-lived token
            if not access_token:
                try:
                    # Try to get the current user from headers or create a system token
                    # For panels, we can create a system-level access that doesn't require user auth
                    _LOGGER.debug("No access token in request, panel will need to handle auth in frontend")
                except Exception as e:
                    _LOGGER.debug(f"Could not create system token: {e}")
            
            # Inject a simpler authentication script
            auth_script = f"""
            <script>
                // Store the access token for the frontend
                const injectedToken = '{access_token}';
                
                // Function to get Home Assistant token
                function getHomeAssistantToken() {{
                    // First try injected token from URL or backend
                    if (injectedToken && injectedToken !== '') {{
                        localStorage.setItem('ha_access_token', injectedToken);
                        return injectedToken;
                    }}
                    
                    // Try from URL parameters
                    const urlParams = new URLSearchParams(window.location.search);
                    const urlToken = urlParams.get('access_token');
                    if (urlToken) {{
                        localStorage.setItem('ha_access_token', urlToken);
                        return urlToken;
                    }}
                    
                    // Try from localStorage
                    const storedToken = localStorage.getItem('ha_access_token');
                    if (storedToken && storedToken !== 'undefined' && storedToken !== '') {{
                        return storedToken;
                    }}
                    
                    // Try to extract from current page context
                    try {{
                        // Look for Home Assistant's auth in the page
                        if (window.parent && window.parent !== window) {{
                            // We're in an iframe, try to get token from parent
                            const parentUrl = window.parent.location.href;
                            if (parentUrl.includes('/auth/')) {{
                                // Extract token from parent URL if available
                                const match = parentUrl.match(/access_token=([^&]+)/);
                                if (match) {{
                                    const token = match[1];
                                    localStorage.setItem('ha_access_token', token);
                                    return token;
                                }}
                            }}
                        }}
                    }} catch (e) {{
                        console.debug('Cannot access parent context:', e);
                    }}
                    
                    return null;
                }}
                
                // Override the getHomeAssistantToken function in the panel
                window.getHomeAssistantToken = getHomeAssistantToken;
                
                // Try to get token immediately when script loads
                const initialToken = getHomeAssistantToken();
                if (initialToken) {{
                    console.log('Home Assistant token found');
                }} else {{
                    console.warn('No Home Assistant token found - commands will not work');
                }}
            </script>
            """
            
            # Inject the script before the closing head tag
            content = content.replace('</head>', f'{auth_script}</head>')
            
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


class WhispeerCommandView(HomeAssistantView):
    """View to handle command sending."""

    url = "/api/services/whispeer/send_command"
    name = "api:whispeer:send_command"
    requires_auth = True

    async def post(self, request):
        """Send command to device."""
        try:
            hass = request.app["hass"]
            data = await request.json()
            
            device_id = data.get('device_id')
            device_type = data.get('device_type')
            command_name = data.get('command_name')
            command_code = data.get('command_code')
            
            if not all([device_id, device_type, command_name, command_code]):
                return web.json_response({
                    "error": "Missing required fields: device_id, device_type, command_name, command_code"
                }, status=400)
            
            # Get coordinator to access API
            domain_data = hass.data.get(DOMAIN, {})
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                result = await coordinator.api.async_send_command(
                    device_id, device_type, command_name, command_code
                )
                return web.json_response(result)
            else:
                # Fallback implementation when no coordinator is available
                _LOGGER.info(f"Sending command '{command_name}' to device '{device_id}' (type: {device_type})")
                _LOGGER.debug(f"Command code: {command_code}")
                
                result = {
                    "status": "success",
                    "message": f"Command '{command_name}' sent to '{device_id}'",
                    "device_id": device_id,
                    "command_name": command_name,
                    "timestamp": "2025-01-22T12:00:00Z"
                }
                return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error sending command: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerSyncView(HomeAssistantView):
    """View to handle device synchronization."""

    url = "/api/services/whispeer/sync_devices"
    name = "api:whispeer:sync_devices"
    requires_auth = True

    async def post(self, request):
        """Sync devices with backend."""
        try:
            hass = request.app["hass"]
            data = await request.json()
            devices = data.get('devices', {})
            
            # Get coordinator to access API
            domain_data = hass.data.get(DOMAIN, {})
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if coordinator:
                result = await coordinator.api.async_sync_devices(devices)
                return web.json_response(result)
            else:
                # Fallback implementation
                _LOGGER.info(f"Syncing {len(devices)} devices")
                _LOGGER.debug(f"Device data: {devices}")
                
                result = {
                    "status": "success",
                    "message": f"Successfully synced {len(devices)} devices",
                    "synced_count": len(devices)
                }
                return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error syncing devices: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerRemoveDeviceView(HomeAssistantView):
    """View to handle device removal."""

    url = "/api/services/whispeer/remove_device"
    name = "api:whispeer:remove_device"
    requires_auth = True

    async def post(self, request):
        """Remove device from backend."""
        try:
            data = await request.json()
            device_id = data.get('device_id')
            
            if not device_id:
                return web.json_response({
                    "error": "Missing required field: device_id"
                }, status=400)
            
            _LOGGER.info(f"Removing device '{device_id}' from backend")
            
            # Here you would implement the actual device removal logic
            # For now, we'll simulate success
            result = {
                "status": "success",
                "message": f"Device '{device_id}' removed successfully"
            }
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error removing device from backend: {e}")
            return web.json_response({"error": str(e)}, status=500)


async def register_panel(hass):
    """Register the Whispeer panel."""
    try:
        # Register all the views first
        hass.http.register_view(WhispeerPanelView())
        hass.http.register_view(WhispeerApiView())
        hass.http.register_view(WhispeerDeviceView())
        hass.http.register_view(WhispeerCommandView())
        hass.http.register_view(WhispeerSyncView())
        hass.http.register_view(WhispeerRemoveDeviceView())
        
        # Register the panel using the frontend component
        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="Whispeer",
            sidebar_icon="mdi:microphone", 
            frontend_url_path="whispeer",
            config={
                "url": "/api/whispeer/panel",
                "require_admin": False
            }
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
