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
from homeassistant.helpers import device_registry as dr
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
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: open(panel_path, "r", encoding="utf-8").read()
            )
            
            hass = request.app["hass"]
            access_token = ''
            
            access_token = request.query.get('access_token', '')
            
            if not access_token:
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    access_token = auth_header[7:]
            
            _LOGGER.debug(f"Panel request - Token from query: {bool(request.query.get('access_token'))}, Token from header: {bool(access_token)}")
            
            if not access_token:
                try:
                    _LOGGER.debug("No access token found, frontend will need to handle auth")
                except Exception as e:
                    _LOGGER.debug(f"Could not get system token: {e}")
            
            content = content.replace('href="styles.css"', 'href="/whispeer-assets/styles.css"')
            content = content.replace('src="websocket-manager.js"', 'src="/whispeer-assets/websocket-manager.js"')
            content = content.replace('src="utils.js"', 'src="/whispeer-assets/utils.js"')
            content = content.replace('src="ui-framework.js"', 'src="/whispeer-assets/ui-framework.js"')
            content = content.replace('src="template-engine.js"', 'src="/whispeer-assets/template-engine.js"')
            content = content.replace('src="data-manager.js"', 'src="/whispeer-assets/data-manager.js"')
            content = content.replace('src="device-manager.js"', 'src="/whispeer-assets/device-manager.js"')
            content = content.replace('src="app.js"', 'src="/whispeer-assets/app.js"')
            
            auth_script = f"""
            <script>
                const injectedToken = '{access_token}';

                function getHomeAssistantToken() {{
                    if (injectedToken && injectedToken !== '' && injectedToken !== 'None') {{
                        return injectedToken;
                    }}

                    const urlParams = new URLSearchParams(window.location.search);
                    const urlToken = urlParams.get('access_token');
                    if (urlToken) return urlToken;

                    try {{
                        const conn = window.hassConnection || window.parent?.hassConnection;
                        const t = conn?.options?.auth?.accessToken;
                        if (t) return t;
                    }} catch (_) {{}}

                    try {{
                        const raw = localStorage.getItem('hassTokens');
                        if (raw) {{
                            const parsed = JSON.parse(raw);
                            if (parsed?.access_token) return parsed.access_token;
                        }}
                    }} catch (_) {{}}

                    try {{
                        const parentEl = window.parent?.document?.querySelector('home-assistant');
                        const t = parentEl?.__hass?.auth?.data?.access_token
                               || parentEl?.hass?.auth?.data?.access_token;
                        if (t) return t;
                    }} catch (_) {{}}

                    return null;
                }}

                window.getHomeAssistantToken = getHomeAssistantToken;

                function forEachElementDeep(root, cb) {{
                    if (!root) return;
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                    let node = walker.currentNode;
                    while (node) {{
                        cb(node);
                        if (node.shadowRoot) {{
                            forEachElementDeep(node.shadowRoot, cb);
                        }}
                        node = walker.nextNode();
                    }}
                }}

                function setMainTitleText() {{
                    try {{
                        const parentDoc = window.parent?.document;
                        if (!parentDoc) return;
                        const title = 'Whispeer - Remote Control made simple';
                        const classTargets = new Set(['main-title', 'toolbar-title']);
                        forEachElementDeep(parentDoc, (el) => {{
                            if (!el || !el.classList) return;
                            const hasTargetClass = [...classTargets].some(c => el.classList.contains(c));
                            if (!hasTargetClass) return;
                            const text = (el.textContent || '').trim();
                            if (!text) return;
                            if (text.includes('Whispeer') || text.includes('Remote Control made simple')) {{
                                el.textContent = title;
                            }}
                        }});
                    }} catch (_) {{}}
                }}

                document.title = 'Whispeer - Remote Control made simple';
                setMainTitleText();
                setTimeout(setMainTitleText, 500);
                setTimeout(setMainTitleText, 1500);
                setTimeout(setMainTitleText, 3000);
                window.addEventListener('load', setMainTitleText);

                try {{
                    const parentDoc = window.parent?.document;
                    if (parentDoc) {{
                        const observer = new MutationObserver(() => setMainTitleText());
                        observer.observe(parentDoc.body, {{ childList: true, subtree: true }});
                    }}
                }} catch (_) {{}}
            </script>
            """
            
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
            
            allowed_files = {
                'styles.css': 'text/css',
                'utils.js': 'application/javascript',
                'ui-framework.js': 'application/javascript',
                'template-engine.js': 'application/javascript',
                'websocket-manager.js': 'application/javascript',
                'data-manager.js': 'application/javascript',
                'device-manager.js': 'application/javascript',
                'app.js': 'application/javascript',
                'whispeer.png': 'image/png'
            }
            
            if filename not in allowed_files:
                _LOGGER.error(f"Requested file not allowed: {filename}")
                return web.Response(text="File not found", status=404)
            
            if filename == 'whispeer.png':
                file_path = os.path.join(os.path.dirname(__file__), filename)
            else:
                file_path = os.path.join(
                    os.path.dirname(__file__), "panel", filename
                )
            
            _LOGGER.debug(f"Attempting to serve asset: {file_path}")
            
            loop = asyncio.get_event_loop()
            if filename.endswith('.png'):
                content = await loop.run_in_executor(
                    None,
                    lambda: open(file_path, "rb").read()
                )
            else:
                content = await loop.run_in_executor(
                    None,
                    lambda: open(file_path, "r", encoding="utf-8").read()
                )
            
            content_type = allowed_files[filename]
            _LOGGER.debug(f"Successfully served asset: {filename}")
            if filename.endswith('.png'):
                return web.Response(body=content, content_type=content_type)
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
            sidebar_icon="mdi:remote-tv",
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
    def _is_uid_for_stored_device(uid: str) -> bool:
        if not uid.startswith("whispeer_"):
            return False
        for did in sorted(stored_device_ids, key=len, reverse=True):
            if uid.startswith(f"whispeer_{did}_"):
                return True
        return False

    registry = er.async_get(hass)
    entry_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    for entity_entry in entry_entities:
        uid = entity_entry.unique_id
        if not uid.startswith("whispeer_"):
            continue
        if not _is_uid_for_stored_device(uid):
            _LOGGER.debug(
                "Removing stale entity %s (no matching stored device)",
                entity_entry.entity_id,
            )
            registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    entry_devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    for dev_entry in entry_devices:
        whispeer_identifier = None
        for domain, did in dev_entry.identifiers:
            if domain == DOMAIN:
                whispeer_identifier = str(did)
                break
        if not whispeer_identifier:
            continue
        if whispeer_identifier in stored_device_ids:
            continue
        _LOGGER.debug(
            "Removing stale device registry entry %s (device %s no longer in storage)",
            dev_entry.id,
            whispeer_identifier,
        )
        try:
            device_registry.async_remove_device(dev_entry.id)
        except Exception as exc:
            _LOGGER.debug("Failed removing stale device entry %s: %s", dev_entry.id, exc)


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

    devices = await client.async_get_devices()
    stored_ids: set[str] = {d["id"] for d in devices}
    await async_cleanup_removed_entities(hass, entry, stored_ids)

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

    await register_panel(hass)

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
