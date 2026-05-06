"""
Custom integration to integrate Whispeer with Home Assistant.

For more details about this integration, please refer to
https://github.com/patlanio/whispeer
"""
import asyncio
import logging
import os

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core_config import Config
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .api import WhispeerApiClient
from .const import DOMAIN
from .websocket import async_setup_websocket
from .const import PLATFORMS
from .const import STARTUP_MESSAGE
from .const import SIGNAL_WHISPEER_DATA_UPDATED

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
            # Use asyncio to run file I/O in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: open(panel_path, "r", encoding="utf-8").read()
            )
            
            # Get the access token from the request 
            hass = request.app["hass"]
            access_token = ''
            
            # Try to get token from query parameters first
            access_token = request.query.get('access_token', '')
            
            # If no token in query, try to get from headers
            if not access_token:
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    access_token = auth_header[7:]  # Remove 'Bearer ' prefix
            
            # Log for debugging
            _LOGGER.debug(f"Panel request - Token from query: {bool(request.query.get('access_token'))}, Token from header: {bool(access_token)}")
            
            # If still no token, try to create a temporary one or use alternative auth
            if not access_token:
                try:
                    # For iframe panels, we often need to handle auth differently
                    # Let's try to use the websocket auth token if available
                    _LOGGER.debug("No access token found, frontend will need to handle auth")
                except Exception as e:
                    _LOGGER.debug(f"Could not get system token: {e}")
            
            # Update asset paths to use the API endpoints
            content = content.replace('href="styles.css"', 'href="/whispeer-assets/styles.css"')
            content = content.replace('src="websocket-manager.js"', 'src="/whispeer-assets/websocket-manager.js"')
            content = content.replace('src="utils.js"', 'src="/whispeer-assets/utils.js"')
            content = content.replace('src="ui-framework.js"', 'src="/whispeer-assets/ui-framework.js"')
            content = content.replace('src="template-engine.js"', 'src="/whispeer-assets/template-engine.js"')
            content = content.replace('src="data-manager.js"', 'src="/whispeer-assets/data-manager.js"')
            content = content.replace('src="device-manager.js"', 'src="/whispeer-assets/device-manager.js"')
            content = content.replace('src="app.js"', 'src="/whispeer-assets/app.js"')
            
            # Inject enhanced authentication script
            auth_script = f"""
            <script>
                // Store the access token for the frontend
                const injectedToken = '{access_token}';

                function getHomeAssistantToken() {{
                    // 1. Token injected by the backend (only present when HA passes auth header)
                    if (injectedToken && injectedToken !== '' && injectedToken !== 'None') {{
                        return injectedToken;
                    }}

                    // 2. URL query param (?access_token=...)
                    const urlParams = new URLSearchParams(window.location.search);
                    const urlToken = urlParams.get('access_token');
                    if (urlToken) return urlToken;

                    // 3. HA hassConnection (modern HA, home-assistant-js-websocket)
                    try {{
                        const conn = window.hassConnection || window.parent?.hassConnection;
                        const t = conn?.options?.auth?.accessToken;
                        if (t) return t;
                    }} catch (_) {{}}

                    // 4. HA hassTokens in localStorage (set by HA frontend)
                    try {{
                        const raw = localStorage.getItem('hassTokens');
                        if (raw) {{
                            const parsed = JSON.parse(raw);
                            if (parsed?.access_token) return parsed.access_token;
                        }}
                    }} catch (_) {{}}

                    // 5. hass object on home-assistant element in parent
                    try {{
                        const parentEl = window.parent?.document?.querySelector('home-assistant');
                        const t = parentEl?.__hass?.auth?.data?.access_token
                               || parentEl?.hass?.auth?.data?.access_token;
                        if (t) return t;
                    }} catch (_) {{}}

                    return null;
                }}

                window.getHomeAssistantToken = getHomeAssistantToken;
            </script>
            """
            
            # Inject the script before the closing head tag
            content = content.replace('</head>', f'{auth_script}</head>')
            
            return web.Response(text=content, content_type="text/html")
        except FileNotFoundError:
            return web.Response(text="Panel not found", status=404)


class WhispeerAssetsView(HomeAssistantView):
    """View to serve static assets for the Whispeer panel."""

    url = r"/whispeer-assets/{filename}"
    name = "whispeer:assets"
    requires_auth = False

    async def get(self, request, filename):
        """Serve static assets."""
        try:
            _LOGGER.debug(f"Asset request received: {request.path}")
            _LOGGER.debug(f"Requested filename: {filename}")
            
            # Security: only allow specific files
            allowed_files = {
                'styles.css': 'text/css',
                'utils.js': 'application/javascript',
                'ui-framework.js': 'application/javascript',
                'template-engine.js': 'application/javascript',
                'websocket-manager.js': 'application/javascript',
                'data-manager.js': 'application/javascript',
                'device-manager.js': 'application/javascript',
                'app.js': 'application/javascript'
            }
            
            if filename not in allowed_files:
                _LOGGER.error(f"Requested file not allowed: {filename}")
                return web.Response(text="File not found", status=404)
            
            file_path = os.path.join(
                os.path.dirname(__file__), "panel", filename
            )
            
            _LOGGER.debug(f"Attempting to serve asset: {file_path}")
            
            # Use asyncio to run file I/O in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: open(file_path, "r", encoding="utf-8").read()
            )
            
            content_type = allowed_files[filename]
            _LOGGER.debug(f"Successfully served asset: {filename}")
            return web.Response(text=content, content_type=content_type)
            
        except FileNotFoundError as e:
            _LOGGER.error(f"Asset file not found: {filename} - {e}")
            return web.Response(text="File not found", status=404)
        except Exception as e:
            _LOGGER.error(f"Error serving asset {filename}: {e}")
            return web.Response(text="Internal server error", status=500)


async def register_panel(hass):
    """Register the Whispeer panel (HTML + static assets only)."""
    try:
        hass.http.register_view(WhispeerPanelView())
        hass.http.register_view(WhispeerAssetsView())
        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="Whispeer",
            sidebar_icon="mdi:microphone",
            frontend_url_path="whispeer",
            config={
                "url": "/api/whispeer/panel",
                "require_admin": False,
            },
        )
        _LOGGER.info("Whispeer panel registered successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to register Whispeer panel: {e}")
        _LOGGER.exception("Full error details:")


async def async_setup(hass: HomeAssistant, config: Config):
    """Set up this integration using YAML is not supported."""
    return True


async def async_cleanup_removed_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    stored_device_ids: set[str],
) -> None:
    """Remove entities from the HA entity registry whose device has been deleted.

    When a device is removed in the Whispeer frontend the corresponding
    entities would otherwise remain in the registry showing the
    "This entity is no longer provided" warning.  This helper proactively
    removes them so the user never sees stale entities.

    Args:
        hass: The HomeAssistant instance.
        entry: The config entry that owns the entities.
        stored_device_ids: The set of device IDs **currently** present in
            Whispeer storage after the mutation (add / remove / sync).
    """
    registry = er.async_get(hass)
    # Collect every entity belonging to this config entry.
    entry_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    for entity_entry in entry_entities:
        uid = entity_entry.unique_id  # e.g. "whispeer_9330c71e_luz"
        if not uid.startswith("whispeer_"):
            continue
        # Extract the device_id component: "whispeer_{device_id}_{cmd}"
        parts = uid.split("_", 2)  # ["whispeer", device_id, cmd_name]
        if len(parts) < 3:
            continue
        device_id = parts[1]
        if device_id not in stored_device_ids:
            _LOGGER.debug(
                "Removing stale entity %s (device %s no longer in storage)",
                entity_entry.entity_id,
                device_id,
            )
            registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    session = async_get_clientsession(hass)
    client = WhispeerApiClient(session, hass)

    coordinator = WhispeerDataUpdateCoordinator(hass, client=client)

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

    # On startup, clean up entities whose devices were removed while HA was
    # offline (e.g. user deleted a device through the frontend and HA was
    # restarted afterwards).
    devices = await client.async_get_devices()
    stored_ids: set[str] = {d["id"] for d in devices}
    await async_cleanup_removed_entities(hass, entry, stored_ids)

    # Listen for runtime data changes so stale entities are removed immediately
    # when the user deletes a device from the frontend (no restart needed).
    @callback
    def _on_data_updated(current_device_ids: set[str]) -> None:
        hass.async_create_task(
            async_cleanup_removed_entities(hass, entry, current_device_ids)
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_DATA_UPDATED, _on_data_updated
        )
    )

    # Register the panel after the platforms are set up.
    await register_panel(hass)

    # Register WebSocket commands (idempotent — safe to call on every reload).
    async_setup_websocket(hass)

    entry.add_update_listener(async_reload_entry)
    return True


class WhispeerDataUpdateCoordinator:
    """Lightweight holder for the API client shared across entity platforms."""

    def __init__(self, hass: HomeAssistant, client: WhispeerApiClient) -> None:
        self.api = client
        self.platforms: list[str] = []
        self.last_update_success = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    # Remove the sidebar panel so re-registration on reload doesn't raise.
    try:
        frontend.async_remove_panel(hass, "whispeer")
    except Exception:
        pass

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
