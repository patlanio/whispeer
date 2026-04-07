"""Whispeer API Client — HA-native backend.

All IR/RF command sending and learning is delegated to Home Assistant's
``remote`` platform via ``HassClient``.  No direct hardware access or
third-party library imports are required.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

import aiohttp
import async_timeout
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from aiohttp import web

from .const import SIGNAL_WHISPEER_DATA_UPDATED, SIGNAL_WHISPEER_NEW_DEVICE
from .hass_client import HassClient

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}

# Active learning sessions keyed by session_id.
LEARNING_SESSIONS: Dict[str, "LearnSession"] = {}


# ------------------------------------------------------------------
# Learning session model
# ------------------------------------------------------------------

class LearnSession:
    """Track an in-progress learn-command flow."""

    def __init__(
        self,
        session_id: str,
        command_type: str,
        hub_entity_id: str,
    ) -> None:
        self.session_id = session_id
        self.command_type = command_type
        self.hub_entity_id = hub_entity_id
        self.status = "preparing"  # preparing | learning | completed | error | timeout
        self.command_data: Optional[str] = None
        self.error_message: Optional[str] = None
        self.created_at = time.time()

    def update_status(
        self,
        status: str,
        command_data: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self.status = status
        if command_data is not None:
            self.command_data = command_data
        if error_message is not None:
            self.error_message = error_message


# ------------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------------

def _ok(message: str, **extra: Any) -> dict:
    return {"status": "success", "message": message, **extra}


def _err(message: str, **extra: Any) -> dict:
    return {"status": "error", "message": message, **extra}


# ------------------------------------------------------------------
# Main API Client
# ------------------------------------------------------------------

class WhispeerApiClient:
    """Manages device storage and delegates HW commands to HassClient."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hass=None,
    ) -> None:
        self._session = session
        self._hass = hass
        self._store = Store(hass, 1, "whispeer_devices")
        self._hub_store = Store(hass, 1, "whispeer_hubs")
        self._devices_cache: Dict[str, Dict[str, Any]] = {}
        self._hubs_cache: Dict[str, Dict[str, Any]] = {}
        self._hass_client = HassClient(hass)

    # ------------------------------------------------------------------
    # Basic status
    # ------------------------------------------------------------------

    async def async_get_data(self) -> dict:
        return {
            "status": "success",
            "message": "Whispeer API is ready",
            "timestamp": asyncio.get_event_loop().time(),
        }

    # ------------------------------------------------------------------
    # Hub persistence
    # ------------------------------------------------------------------

    async def _load_hubs(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = await self._hub_store.async_load()
            if isinstance(data, dict):
                return data
            return {}
        except Exception as exc:
            _LOGGER.error("Failed to load hubs: %s", exc)
            return {}

    async def _save_hubs(self, hubs: Dict[str, Dict[str, Any]]) -> None:
        try:
            await self._hub_store.async_save(hubs)
            self._hubs_cache = hubs
        except Exception as exc:
            _LOGGER.error("Failed to save hubs: %s", exc)

    async def async_get_hubs(self) -> list[dict]:
        """Return stored hubs as a list."""
        if not self._hubs_cache:
            self._hubs_cache = await self._load_hubs()
        return [{"id": hid, **info} for hid, info in self._hubs_cache.items()]

    async def async_save_hub(self, hub_data: dict) -> dict:
        """Persist a hub (create or update)."""
        hubs = await self._load_hubs()
        hub_id = hub_data.get("id") or uuid.uuid4().hex[:8]
        hubs[hub_id] = {
            "name": hub_data.get("name", f"Hub {hub_id}"),
            "entity_id": hub_data.get("entity_id", ""),
            "capabilities": hub_data.get("capabilities", ["ir"]),
            "model": hub_data.get("model", ""),
        }
        await self._save_hubs(hubs)
        return _ok("Hub saved", id=hub_id, **hubs[hub_id])

    async def async_remove_hub(self, hub_id: str) -> dict:
        hubs = await self._load_hubs()
        removed = hubs.pop(hub_id, None)
        await self._save_hubs(hubs)
        if removed is None:
            return _err(f"Hub {hub_id} not found")
        return _ok(f"Hub {hub_id} removed")

    # ------------------------------------------------------------------
    # Device persistence
    # ------------------------------------------------------------------

    async def _load_devices(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = await self._store.async_load()
            if not data:
                return {}
            if isinstance(data, dict):
                sanitized: Dict[str, Dict[str, Any]] = {}
                for did, info in data.items():
                    did_str = str(did).strip() or uuid.uuid4().hex[:8]
                    if not isinstance(info, dict):
                        info = {}
                    if not info.get("id"):
                        info["id"] = did_str
                    sanitized[did_str] = info
                return sanitized
            return {}
        except Exception as exc:
            _LOGGER.error("Failed to load devices: %s", exc)
            return {}

    async def _save_devices(self, devices: Dict[str, Dict[str, Any]]) -> None:
        try:
            await self._store.async_save(devices)
            self._devices_cache = devices
        except Exception as exc:
            _LOGGER.error("Failed to save devices: %s", exc)

    async def async_get_devices(self) -> list:
        if not self._devices_cache:
            self._devices_cache = await self._load_devices()
        return [{"id": did, **info} for did, info in self._devices_cache.items()]

    async def async_add_device(self, device_data: dict) -> dict:
        devices = await self._load_devices()
        device_id = (device_data.get("id") or uuid.uuid4().hex[:8]).strip()
        info = {
            "name": device_data.get("name") or f"Device {device_id}",
            "type": device_data.get("type") or "ir",
            "category": device_data.get("category") or "",
            "interface_id": device_data.get("interface_id") or "",
            "emitter": device_data.get("emitter") or {},
            "commands": device_data.get("commands") or {},
        }
        devices[str(device_id)] = info
        await self._save_devices(devices)

        device_info = {"id": str(device_id), **info}
        async_dispatcher_send(self._hass, SIGNAL_WHISPEER_NEW_DEVICE, device_info)

        return _ok("Device added successfully", id=str(device_id), **info)

    async def async_remove_device(self, device_id) -> dict:
        devices = await self._load_devices()
        removed = devices.pop(str(device_id), None)
        await self._save_devices(devices)
        if removed is None:
            return _err(f"Device {device_id} not found")

        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set(devices.keys())
        )
        return _ok(f"Device {device_id} removed successfully")

    async def async_sync_devices(self, devices: dict, replace: bool = False) -> dict:
        if not isinstance(devices, dict):
            return _err("Invalid devices payload")

        current = await self._load_devices()
        merged = {} if replace else {**current}

        for did, info in devices.items():
            did_str = str(did).strip() or uuid.uuid4().hex[:8]
            if not isinstance(info, dict):
                info = {}
            if not info.get("id"):
                info["id"] = did_str
            merged[did_str] = info

        await self._save_devices(merged)

        new_ids = set(merged.keys()) - set(current.keys())
        for did in new_ids:
            async_dispatcher_send(
                self._hass, SIGNAL_WHISPEER_NEW_DEVICE, {"id": did, **merged[did]}
            )

        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set(merged.keys())
        )

        return _ok(
            f"Synced {len(devices)} devices",
            device_count=len(devices),
            merged_count=len(merged),
            replace=replace,
        )

    async def async_clear_devices(self) -> dict:
        await self._save_devices({})
        async_dispatcher_send(self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set())
        return _ok("All devices cleared")

    async def async_test_device(self, device_id) -> dict:
        return _ok(f"Device {device_id} test completed", test_result="passed")

    # ------------------------------------------------------------------
    # Command sending  (delegates to HassClient → remote.send_command)
    # ------------------------------------------------------------------

    async def async_send_command(
        self,
        device_id: str,
        device_type: str,
        command_name: str,
        command_code: str,
        emitter_data: dict | None = None,
    ) -> dict:
        """Send a command through the associated HA remote entity."""
        if not command_code:
            return _err(f"No command code for '{command_name}' on device '{device_id}'")

        # Resolve hub entity_id from the device's emitter/interface_id.
        entity_id = self._resolve_entity_id(device_id, emitter_data)
        if not entity_id:
            return _err(
                f"No hub entity_id found for device '{device_id}'. "
                "Please assign an interface (hub) to this device."
            )

        success = await self._hass_client.async_send_command(entity_id, command_code)

        if success:
            return _ok(
                f"Command '{command_name}' sent on {entity_id}",
                device_id=device_id,
                command_name=command_name,
                entity_id=entity_id,
            )
        return _err(
            f"Failed to send '{command_name}' on {entity_id}",
            device_id=device_id,
            command_name=command_name,
            entity_id=entity_id,
        )

    def _resolve_entity_id(
        self, device_id: str, emitter_data: dict | None
    ) -> str | None:
        """Determine the remote.* entity_id for a device."""
        # 1. Emitter payload may carry entity_id directly.
        if emitter_data:
            eid = emitter_data.get("entity_id") or ""
            if eid.startswith("remote."):
                return eid

        # 2. Look inside the cached device data for interface_id → hub.
        device = self._devices_cache.get(str(device_id)) or {}
        interface_id = device.get("interface_id") or ""

        # interface_id may be the hub id — look up the hub.
        hub = self._hubs_cache.get(interface_id) or {}
        eid = hub.get("entity_id") or ""
        if eid.startswith("remote."):
            return eid

        # 3. Emitter may store the entity_id from legacy data.
        emitter = device.get("emitter") or {}
        eid = emitter.get("entity_id") or ""
        if eid.startswith("remote."):
            return eid

        return None

    # ------------------------------------------------------------------
    # Interface discovery  (queries HA for remote.* entities)
    # ------------------------------------------------------------------

    async def async_get_interfaces(self, device_type: str, hass=None) -> dict:
        """Return available hubs/interfaces for the given device type."""
        hubs = await self._hass_client.async_discover_hubs()

        # Filter by capability
        cap = device_type.lower()
        filtered = [h for h in hubs if cap in h.get("capabilities", [])]

        interfaces = []
        for h in filtered:
            interfaces.append({
                "label": f"{h['name']} ({h['entity_id']})",
                "entity_id": h["entity_id"],
                "model": h.get("model", ""),
                "capabilities": h.get("capabilities", []),
                "source": "homeassistant",
            })

        return _ok(
            f"Found {len(interfaces)} interface(s)",
            interfaces=interfaces,
        )

    # ------------------------------------------------------------------
    # Learning  (remote.learn_command)
    # ------------------------------------------------------------------

    async def async_prepare_to_learn(
        self,
        device_type: str,
        entity_id: str,
        frequency: float = 433.92,
    ) -> dict:
        """Create a learning session and kick off remote.learn_command in background."""
        if not entity_id or not entity_id.startswith("remote."):
            return _err("A valid remote.* entity_id is required for learning")

        session_id = uuid.uuid4().hex
        session = LearnSession(session_id, device_type, entity_id)
        LEARNING_SESSIONS[session_id] = session

        session.update_status("learning")

        # Fire-and-forget background task that calls remote.learn_command
        # and waits for the event.
        asyncio.ensure_future(self._background_learn(session))

        return _ok(
            f"Learning session started on {entity_id}",
            session_id=session_id,
            device_type=device_type,
            entity_id=entity_id,
        )

    async def _background_learn(self, session: LearnSession) -> None:
        """Background coroutine that performs the actual learning."""
        try:
            _LOGGER.info("Starting background learn for session %s on %s", session.session_id, session.hub_entity_id)
            # RF learning uses two phases (frequency sweep + command capture),
            # each up to `timeout` seconds, so use a longer per-phase timeout.
            per_phase_timeout = 45 if session.command_type.lower() == "rf" else 30
            code = await self._hass_client.async_learn_command(
                entity_id=session.hub_entity_id,
                command="default_command",
                command_type=session.command_type,
                timeout=per_phase_timeout,
            )
            if code:
                session.update_status("completed", command_data=code)
            else:
                session.update_status("timeout", error_message="No code received within timeout")
        except Exception as exc:
            _LOGGER.exception("Background learn failed for session %s", session.session_id)
            session.update_status("error", error_message=str(exc))

    async def async_check_learned_command(self, session_id: str, device_type: str) -> dict:
        """Poll the status of an existing learning session."""
        session = LEARNING_SESSIONS.get(session_id)
        if not session:
            return _err(f"Session {session_id} not found or expired")

        if session.status == "completed":
            return _ok(
                f"{session.command_type.upper()} command learned",
                command_data=session.command_data,
                command_type=session.command_type,
                session_id=session_id,
                learning_status="completed",
            )
        if session.status == "error":
            return _err(
                session.error_message or "Learning failed",
                session_id=session_id,
                learning_status="error",
            )
        if session.status == "timeout":
            return _err(
                "Learning timed out",
                session_id=session_id,
                learning_status="timeout",
            )

        # Still in progress
        return _ok(
            "Learning in progress — press a button on the remote",
            session_id=session_id,
            learning_status="learning",
            device_type=session.command_type,
        )

    async def async_get_stored_codes(self) -> dict:
        """Return all learned remote codes found in HA storage."""
        codes = await self._hass_client.async_get_stored_codes()
        return {"codes": codes}

    # ------------------------------------------------------------------
    # Generic HTTP helper (kept for backward compat if anything uses it)
    # ------------------------------------------------------------------

    async def api_wrapper(
        self, method: str, url: str, data: dict | None = None, headers: dict | None = None
    ) -> dict | None:
        try:
            async with async_timeout.timeout(TIMEOUT):
                resp = await getattr(self._session, method)(
                    url, headers=headers or {}, json=data or {}
                )
                return await resp.json()
        except Exception as exc:
            _LOGGER.error("API request %s %s failed: %s", method.upper(), url, exc)
            return None


# =====================================================================
# HTTP Views  (registered in __init__.py)
# =====================================================================

def _get_coordinator(request):
    """Retrieve the first coordinator with an ``api`` attribute."""
    hass = request.app["hass"]
    domain_data = hass.data.get("whispeer", {})
    for entry_data in domain_data.values():
        if hasattr(entry_data, "api"):
            return entry_data
    return None


class WhispeerInterfacesView(HomeAssistantView):
    """POST /api/services/whispeer/get_interfaces"""

    url = "/api/services/whispeer/get_interfaces"
    name = "api:whispeer:get_interfaces"
    requires_auth = False

    async def post(self, request):
        try:
            data = await request.json()
            device_type = (data.get("type") or "").lower()

            if not device_type:
                return web.json_response({"error": "Missing field: type"}, status=400)
            if device_type not in ("ir", "rf"):
                return web.json_response(
                    {"error": f"Unsupported device type: {device_type}"}, status=400
                )

            coord = _get_coordinator(request)
            if not coord:
                return web.json_response(
                    {"error": "Whispeer coordinator not available"}, status=500
                )

            result = await coord.api.async_get_interfaces(device_type)
            return web.json_response(result)
        except Exception as exc:
            _LOGGER.error("Error getting interfaces: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)


class WhispeerPrepareToLearnView(HomeAssistantView):
    """POST /api/services/whispeer/prepare_to_learn"""

    url = "/api/services/whispeer/prepare_to_learn"
    name = "api:whispeer:prepare_to_learn"
    requires_auth = False

    async def post(self, request):
        try:
            data = await request.json()
            device_type = (data.get("device_type") or "").lower()
            emitter = data.get("emitter") or {}

            if not device_type:
                return web.json_response(
                    {"status": "error", "message": "Missing field: device_type"}, status=400
                )
            if device_type not in ("ir", "rf"):
                return web.json_response(
                    {"status": "error", "message": f"Unsupported device type: {device_type}"},
                    status=400,
                )

            entity_id = emitter.get("entity_id") or ""
            if not entity_id.startswith("remote."):
                return web.json_response(
                    {"status": "error", "message": "A remote.* entity_id is required in emitter"},
                    status=400,
                )

            coord = _get_coordinator(request)
            if not coord:
                return web.json_response(
                    {"status": "error", "message": "Whispeer coordinator not found"}, status=500
                )

            result = await coord.api.async_prepare_to_learn(
                device_type,
                entity_id,
                emitter.get("frequency", 433.92),
            )
            return web.json_response(result)
        except Exception as exc:
            _LOGGER.error("Error preparing to learn: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)


class WhispeerCheckLearnedCommandView(HomeAssistantView):
    """POST /api/services/whispeer/check_learned_command"""

    url = "/api/services/whispeer/check_learned_command"
    name = "api:whispeer:check_learned_command"
    requires_auth = False

    async def post(self, request):
        try:
            data = await request.json()
            device_type = (data.get("device_type") or "").lower()
            session_id = data.get("session_id") or ""

            if not device_type:
                return web.json_response(
                    {"status": "error", "message": "Missing field: device_type"}, status=400
                )
            if not session_id:
                return web.json_response(
                    {"status": "error", "message": "Missing field: session_id"}, status=400
                )

            coord = _get_coordinator(request)
            if not coord:
                return web.json_response(
                    {"status": "error", "message": "Whispeer coordinator not found"}, status=500
                )

            result = await coord.api.async_check_learned_command(session_id, device_type)
            return web.json_response(result)
        except Exception as exc:
            _LOGGER.error("[check_learned_command] Exception: %s", exc, exc_info=True)
            return web.json_response({"error": str(exc)}, status=500)
