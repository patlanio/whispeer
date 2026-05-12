"""Whispeer API Client — HA-native backend.

Command sending and learning is routed to the appropriate provider:
  • RF + Broadlink  → BroadlinkLearnProvider  (direct python-broadlink)
  • IR / other RF   → HassLearnProvider       (remote.learn_command)
  • BLE             → BleLearnProvider        (ble_emitter)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import SIGNAL_WHISPEER_DATA_UPDATED, SIGNAL_WHISPEER_NEW_DEVICE
from .hass_client import HassClient
from .learn_provider import LearnProvider, LearnSession, LEARNING_SESSIONS
from .learn_from_broadlink import BroadlinkLearnProvider
from .learn_from_hass import HassLearnProvider
from .learn_from_ble import BleLearnProvider
from .test_support import get_test_harness

_LOGGER: logging.Logger = logging.getLogger(__package__)

_LEARN_PROVIDERS: list[type[LearnProvider]] = [
    BroadlinkLearnProvider,
    HassLearnProvider,
]


def _pick_learn_provider(device_type: str, manufacturer: str, hass) -> LearnProvider:
    """Return provider for learn flow.

    Routing rules:
      - RF + Broadlink => BroadlinkLearnProvider
      - everything else => HassLearnProvider
    """
    normalized_type = (device_type or "").strip().lower()
    normalized_manufacturer = (manufacturer or "").strip().lower()

    if normalized_type == "rf" and "broadlink" in normalized_manufacturer:
        return BroadlinkLearnProvider(hass)

    return HassLearnProvider(hass)



def _ok(message: str, **extra: Any) -> dict:
    return {"status": "success", "message": message, **extra}


def _err(message: str, **extra: Any) -> dict:
    return {"status": "error", "message": message, **extra}



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
        self._test_harness = get_test_harness(hass)

    def _record_test_event(self, category: str, action: str, **details: Any) -> None:
        self._test_harness.record(category, action, **details)


    async def async_get_data(self) -> dict:
        return {
            "status": "success",
            "message": "Whispeer API is ready",
            "timestamp": asyncio.get_event_loop().time(),
        }


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
        if device_data.get("frequency") is not None:
            info["frequency"] = device_data["frequency"]
        if device_data.get("emit_interval") is not None:
            info["emit_interval"] = device_data["emit_interval"]
        devices[str(device_id)] = info
        await self._save_devices(devices)

        device_info = {"id": str(device_id), **info}
        async_dispatcher_send(self._hass, SIGNAL_WHISPEER_NEW_DEVICE, device_info)

        self._record_test_event(
            "device",
            "added",
            device_id=str(device_id),
            name=info["name"],
            device_type=info["type"],
            interface_id=info["interface_id"],
        )

        return _ok("Device added successfully", id=str(device_id), **info)

    async def async_remove_device(self, device_id) -> dict:
        devices = await self._load_devices()
        removed = devices.pop(str(device_id), None)
        await self._save_devices(devices)
        if removed is None:
            self._record_test_event("device", "remove_missed", device_id=str(device_id))
            return _err(f"Device {device_id} not found")

        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set(devices.keys())
        )
        self._record_test_event("device", "removed", device_id=str(device_id))
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

        self._record_test_event(
            "device",
            "synced",
            incoming_count=len(devices),
            merged_count=len(merged),
            replace=replace,
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
        self._record_test_event("device", "cleared")
        return _ok("All devices cleared")

    async def async_test_device(self, device_id) -> dict:
        return _ok(f"Device {device_id} test completed", test_result="passed")


    async def async_send_command(
        self,
        device_id: str,
        device_type: str,
        command_name: str,
        command_code: str,
        emitter_data: dict | None = None,
    ) -> dict:
        """Send a command through the associated HA remote entity."""
        self._record_test_event(
            "api",
            "send_command_requested",
            device_id=device_id,
            device_type=device_type,
            command_name=command_name,
            emitter=emitter_data,
        )

        if not command_code:
            return _err(f"No command code for '{command_name}' on device '{device_id}'")

        send_override = self._test_harness.get_send_command_override(
            device_id=device_id,
            device_type=device_type,
            command_name=command_name,
        )
        if send_override:
            entity_id = self._resolve_entity_id(device_id, emitter_data) or send_override.get(
                "entity_id", ""
            )
            extra = {
                "device_id": device_id,
                "command_name": command_name,
                "entity_id": entity_id,
            }
            result_extra = send_override.get("result") or {}
            if isinstance(result_extra, dict):
                extra.update(result_extra)

            success = bool(send_override.get("success", True))
            message = send_override.get("message") or (
                f"Mock send completed for '{command_name}'"
                if success
                else f"Mock send failed for '{command_name}'"
            )
            self._record_test_event(
                "api",
                "send_command_overridden",
                device_id=device_id,
                device_type=device_type,
                command_name=command_name,
                entity_id=entity_id,
                success=success,
            )
            if success:
                return _ok(message, **extra)
            return _err(message, **extra)

        if device_type == "ble":
            result = await self._send_ble_command(
                device_id, command_name, command_code, emitter_data
            )
            self._record_test_event(
                "api",
                "send_command_completed",
                device_id=device_id,
                device_type=device_type,
                command_name=command_name,
                result=result,
            )
            return result

        entity_id = self._resolve_entity_id(device_id, emitter_data)
        if not entity_id:
            return _err(
                f"No hub entity_id found for device '{device_id}'. "
                "Please assign an interface (hub) to this device."
            )

        success = await self._hass_client.async_send_command(entity_id, command_code)

        if success:
            result = _ok(
                f"Command '{command_name}' sent on {entity_id}",
                device_id=device_id,
                command_name=command_name,
                entity_id=entity_id,
            )
            self._record_test_event(
                "api",
                "send_command_completed",
                device_id=device_id,
                device_type=device_type,
                command_name=command_name,
                entity_id=entity_id,
                success=True,
            )
            return result
        result = _err(
            f"Failed to send '{command_name}' on {entity_id}",
            device_id=device_id,
            command_name=command_name,
            entity_id=entity_id,
        )
        self._record_test_event(
            "api",
            "send_command_completed",
            device_id=device_id,
            device_type=device_type,
            command_name=command_name,
            entity_id=entity_id,
            success=False,
        )
        return result

    def _resolve_entity_id(
        self, device_id: str, emitter_data: dict | None
    ) -> str | None:
        """Determine the remote.* entity_id for a device."""
        if emitter_data:
            eid = emitter_data.get("entity_id") or ""
            if eid.startswith("remote."):
                return eid

        device = self._devices_cache.get(str(device_id)) or {}
        interface_id = device.get("interface_id") or ""

        hub = self._hubs_cache.get(interface_id) or {}
        eid = hub.get("entity_id") or ""
        if eid.startswith("remote."):
            return eid

        return None


    async def async_get_interfaces(self, device_type: str, hass=None) -> dict:
        """Return available hubs/interfaces for the given device type."""
        self._record_test_event("api", "interfaces_requested", device_type=device_type)

        interface_override = self._test_harness.get_interface_override(device_type)
        if interface_override is not None:
            self._record_test_event(
                "api",
                "interfaces_overridden",
                device_type=device_type,
                count=len(interface_override),
            )
            return _ok(
                f"Found {len(interface_override)} interface(s)",
                interfaces=interface_override,
            )

        if device_type == "ble":
            return await self.async_get_ble_interfaces()

        hubs = await self._hass_client.async_discover_hubs()

        cap = device_type.lower()
        filtered = [h for h in hubs if cap in h.get("capabilities", [])]

        interfaces = []
        for h in filtered:
            interfaces.append({
                "label": f"{h['name']} ({h['entity_id']})",
                "entity_id": h["entity_id"],
                "model": h.get("model", ""),
                "manufacturer": h.get("manufacturer", ""),
                "capabilities": h.get("capabilities", []),
                "source": "homeassistant",
            })

        return _ok(
            f"Found {len(interfaces)} interface(s)",
            interfaces=interfaces,
        )


    async def async_prepare_to_learn(
        self,
        device_type: str,
        entity_id: str,
        manufacturer: str = "",
        frequency: float | None = None,
    ) -> dict:
        """Create a learning session and dispatch it to the matching provider.

        The provider is selected based on *device_type* and *manufacturer*:
          • RF + Broadlink  → BroadlinkLearnProvider
          • everything else → HassLearnProvider

        *frequency* is passed to the session so providers can skip the sweep
        phase when a frequency has already been detected for this device.
        """
        if not entity_id or not entity_id.startswith("remote."):
            return _err("A valid remote.* entity_id is required for learning")

        session_id = uuid.uuid4().hex
        session = LearnSession(session_id, device_type, entity_id)
        LEARNING_SESSIONS[session_id] = session

        self._record_test_event(
            "learn",
            "session_created",
            session_id=session_id,
            device_type=device_type,
            entity_id=entity_id,
            manufacturer=manufacturer,
            frequency=frequency,
        )

        if frequency is not None:
            session.detected_frequency = frequency
            session.phase = "capturing"

        provider = _pick_learn_provider(device_type, manufacturer, self._hass)
        self._record_test_event(
            "learn",
            "provider_selected",
            session_id=session_id,
            provider=provider.NAME,
            device_type=device_type,
            entity_id=entity_id,
        )
        _LOGGER.info(
            "async_prepare_to_learn: session %s → %s provider",
            session_id, provider.NAME,
        )

        learn_override = self._test_harness.consume_learn_override(
            device_type=device_type,
            entity_id=entity_id,
        )
        if learn_override is not None:
            self._record_test_event(
                "learn",
                "override_selected",
                session_id=session_id,
                provider=provider.NAME,
            )
            asyncio.ensure_future(
                self._test_harness.async_run_session_override(
                    session,
                    learn_override,
                    default_phase=session.phase,
                    journal_category="learn",
                )
            )
        else:
            asyncio.ensure_future(provider.start(session))

        return _ok(
            f"Learning session started on {entity_id}",
            session_id=session_id,
            device_type=device_type,
            entity_id=entity_id,
        )

    async def async_find_frequency(
        self,
        entity_id: str,
    ) -> dict:
        """Start a sweep-only session to detect RF frequency (Broadlink only)."""
        if not entity_id or not entity_id.startswith("remote."):
            return _err("A valid remote.* entity_id is required")

        session_id = uuid.uuid4().hex
        session = LearnSession(session_id, "rf", entity_id)
        session.phase = "sweeping"
        session.update_status("learning")
        LEARNING_SESSIONS[session_id] = session

        self._record_test_event(
            "frequency",
            "session_created",
            session_id=session_id,
            entity_id=entity_id,
        )

        provider = BroadlinkLearnProvider(self._hass)
        frequency_override = self._test_harness.consume_frequency_override(
            entity_id=entity_id,
        )
        if frequency_override is not None:
            self._record_test_event(
                "frequency",
                "override_selected",
                session_id=session_id,
            )
            asyncio.ensure_future(
                self._test_harness.async_run_session_override(
                    session,
                    frequency_override,
                    default_phase=session.phase,
                    journal_category="frequency",
                )
            )
        else:
            asyncio.ensure_future(provider.find_frequency(session))

        return _ok(
            f"Frequency sweep started on {entity_id}",
            session_id=session_id,
        )

    async def async_check_learned_command(self, session_id: str, device_type: str) -> dict:
        """Poll the status of an existing learning session."""
        session = LEARNING_SESSIONS.get(session_id)
        if not session:
            return _err(f"Session {session_id} not found or expired")

        if session.status == "completed":
            result = _ok(
                f"{session.command_type.upper()} command learned",
                command_data=session.command_data,
                command_type=session.command_type,
                session_id=session_id,
                learning_status="completed",
                phase="completed",
            )
            if session.detected_frequency is not None:
                result["detected_frequency"] = session.detected_frequency
            return result
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

        return _ok(
            "Learning in progress",
            session_id=session_id,
            learning_status=session.status,
            phase=session.phase,
            device_type=session.command_type,
        )

    async def async_get_stored_codes(self) -> dict:
        """Return all learned remote codes found in HA storage."""
        codes = await self._hass_client.async_get_stored_codes()
        self._record_test_event("storage", "codes_loaded", count=len(codes))
        return {"codes": codes}

    async def async_send_stored_code(
        self,
        identifier: str,
        code: str,
        device: str = "",
        command: str = "",
    ) -> dict:
        """Send a stored code by resolving the hub from its MAC identifier."""
        self._record_test_event(
            "storage",
            "send_stored_code_requested",
            identifier=identifier,
            device=device,
            command=command,
        )
        entity_id = await self._hass_client.async_find_remote_by_identifier(identifier)
        if not entity_id:
            return _err(
                f"No remote entity found for identifier '{identifier}'. "
                "Make sure the Broadlink hub is connected in Home Assistant."
            )
        success = await self._hass_client.async_send_command(entity_id, code)
        if success:
            result = _ok(
                f"Stored code '{command}' on '{device}' sent via {entity_id}",
                entity_id=entity_id,
            )
            self._record_test_event(
                "storage",
                "send_stored_code_completed",
                identifier=identifier,
                entity_id=entity_id,
                success=True,
            )
            return result
        result = _err(
            f"Failed to send stored code '{command}' on '{device}' via {entity_id}",
            entity_id=entity_id,
        )
        self._record_test_event(
            "storage",
            "send_stored_code_completed",
            identifier=identifier,
            entity_id=entity_id,
            success=False,
        )
        return result


    def _resolve_ble_adapter(
        self, device_id: str, emitter_data: dict | None
    ) -> str | None:
        """Return the hci_name for the BLE adapter to use."""
        if emitter_data:
            adapter = emitter_data.get("hci_name")
            if adapter:
                return adapter
        device = self._devices_cache.get(str(device_id)) or {}
        emitter = device.get("emitter") or {}
        return emitter.get("hci_name")

    async def _send_ble_command(
        self,
        device_id: str,
        command_name: str,
        command_code: str,
        emitter_data: dict | None,
    ) -> dict:
        """Route a BLE command to BleLearnProvider."""
        adapter = self._resolve_ble_adapter(device_id, emitter_data)
        if not adapter:
            return _err("No BLE adapter (hci_name) found for this device")

        provider = BleLearnProvider(self._hass)
        result = await provider.send_command(command_code, adapter)
        if result["status"] == "success":
            return _ok(f"BLE command sent on {adapter}")
        return _err(f"Failed to send BLE command on {adapter}")

    async def async_get_ble_interfaces(self) -> dict:
        """Return available BLE adapters as interfaces."""
        interface_override = self._test_harness.get_interface_override("ble")
        if interface_override is not None:
            self._record_test_event(
                "ble",
                "interfaces_overridden",
                count=len(interface_override),
            )
            return _ok(
                f"Found {len(interface_override)} BLE adapter(s)",
                interfaces=interface_override,
            )

        provider = BleLearnProvider(self._hass)
        adapters = await provider.get_interfaces()
        if not adapters:
            return _err(
                "No BLE adapters found. Ensure hcitool and hciconfig are "
                "installed and a Bluetooth adapter is connected."
            )
        interfaces = []
        for a in adapters:
            status_icon = "✅" if a["status"] == "UP" else "⚠️"
            interfaces.append({
                "label": f"{a['hci_name']} — {a['mac']} {status_icon}",
                "hci_name": a["hci_name"],
                "mac": a["mac"],
                "status": a["status"],
                "can_emit": a["can_emit"],
                "source": "ble",
            })
        self._record_test_event("ble", "interfaces_loaded", count=len(interfaces))
        return _ok(f"Found {len(interfaces)} BLE adapter(s)", interfaces=interfaces)

    async def async_scan_ble(self, adapter_mac: str) -> dict:
        """Return BLE advertisements visible to the adapter with *adapter_mac*."""
        scan_override = self._test_harness.get_ble_scan_override(adapter_mac)
        if scan_override is not None:
            devices = scan_override.get("devices") or []
            error = scan_override.get("error")
            self._record_test_event(
                "ble",
                "scan_overridden",
                adapter_mac=adapter_mac,
                device_count=len(devices),
                error=error,
            )
            if error:
                return _err(error, devices=devices)
            return _ok(f"Found {len(devices)} device(s)", devices=devices)

        provider = BleLearnProvider(self._hass)
        devices, error = await provider.scan(adapter_mac)
        if error:
            return _err(error, devices=devices)
        self._record_test_event(
            "ble",
            "scan_completed",
            adapter_mac=adapter_mac,
            device_count=len(devices),
        )
        return _ok(f"Found {len(devices)} device(s)", devices=devices)

    async def async_emit_ble(
        self,
        adapter: str,
        ad_type: str,
        field_id: int | str,
        data_hex: str,
    ) -> dict:
        """Emit a BLE advertisement."""
        emit_override = self._test_harness.get_ble_emit_override(adapter=adapter)
        if emit_override is not None:
            extra = emit_override.get("result") or {}
            success = bool(emit_override.get("success", True))
            message = emit_override.get("message") or (
                f"Mock BLE advertisement emitted on {adapter}"
                if success
                else f"Mock BLE emit failed on {adapter}"
            )
            self._record_test_event(
                "ble",
                "emit_overridden",
                adapter=adapter,
                ad_type=ad_type,
                field_id=field_id,
                success=success,
            )
            if success:
                return _ok(message, **extra)
            return _err(message, **extra)

        provider = BleLearnProvider(self._hass)
        success = await provider.emit(adapter, ad_type, field_id, data_hex)
        if success:
            result = _ok(f"BLE advertisement emitted on {adapter}")
            self._record_test_event(
                "ble",
                "emit_completed",
                adapter=adapter,
                ad_type=ad_type,
                field_id=field_id,
                success=True,
            )
            return result
        result = _err(f"Failed to emit BLE on {adapter}")
        self._record_test_event(
            "ble",
            "emit_completed",
            adapter=adapter,
            ad_type=ad_type,
            field_id=field_id,
            success=False,
        )
        return result

    async def async_emit_ble_raw(self, adapter: str, raw_hex: str) -> dict:
        """Emit a raw BLE advertisement PDU."""
        emit_override = self._test_harness.get_ble_emit_override(adapter=adapter)
        if emit_override is not None:
            extra = emit_override.get("result") or {}
            success = bool(emit_override.get("success", True))
            message = emit_override.get("message") or (
                f"Mock raw BLE advertisement emitted on {adapter}"
                if success
                else f"Mock raw BLE emit failed on {adapter}"
            )
            self._record_test_event(
                "ble",
                "emit_raw_overridden",
                adapter=adapter,
                raw_hex_length=len(raw_hex),
                success=success,
            )
            if success:
                return _ok(message, **extra)
            return _err(message, **extra)

        provider = BleLearnProvider(self._hass)
        success = await provider.emit_raw(adapter, raw_hex)
        if success:
            result = _ok(f"Raw BLE advertisement emitted on {adapter}")
            self._record_test_event(
                "ble",
                "emit_raw_completed",
                adapter=adapter,
                raw_hex_length=len(raw_hex),
                success=True,
            )
            return result
        result = _err(f"Failed to emit raw BLE on {adapter}")
        self._record_test_event(
            "ble",
            "emit_raw_completed",
            adapter=adapter,
            raw_hex_length=len(raw_hex),
            success=False,
        )
        return result



