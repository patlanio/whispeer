"""Home Assistant API client for Whispeer.

Centralises all communication with HA services (remote.send_command,
remote.learn_command) and state queries
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr

_LOGGER = logging.getLogger(__name__)

class HassClient:
    """Thin wrapper around HA service calls for remote-entity interaction."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._ble_buffer: dict[str, dict] = {}
        self._ble_cancel_cb = None


    async def async_discover_hubs(self) -> list[dict[str, Any]]:
        """
        Returns every remote.* entity, cross-referenced with the Device Registry
        to get the actual hardware model and capabilities.
        """
        hubs: list[dict[str, Any]] = []

        states = self._hass.states.async_all("remote")

        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)

        for state in states:
            entity_id = state.entity_id

            entry = entity_registry.async_get(entity_id)
            model = ""
            manufacturer = ""

            if entry and entry.device_id:
                device = device_registry.async_get(entry.device_id)
                if device:
                    model = device.model or ""
                    manufacturer = device.manufacturer or ""

            caps = _get_capabilities(state, device)

            hubs.append({
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name", entity_id),
                "model": model,
                "manufacturer": manufacturer,
                "capabilities": caps,
            })

        return hubs


    async def async_send_command(
        self,
        entity_id: str,
        command_data: str,
    ) -> bool:
        """Send an IR/RF code via ``remote.send_command``.

        ``command_data`` is the hex (or base64) string stored in the
        device command slot.
        """
        b64 = _ensure_base64(command_data)

        _LOGGER.info(
            "Sending command via remote.send_command on %s (code length=%d)",
            entity_id,
            len(b64),
        )

        try:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": entity_id,
                    "command": [f"b64:{b64}"],
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Failed to send command on %s", entity_id)
            return False


    async def async_learn_command(
        self,
        entity_id: str,
        command: str,
        command_type: str = "ir",
        timeout: int = 30,
        device: str = "default_device",
    ) -> str | None:
        """Put the hub into learning mode via ``remote.learn_command``.

        Calls ``remote.learn_command`` with ``blocking=True`` so the
        coroutine waits until the remote physically captures the button
        press (or until the device-side timeout expires).  The learned
        code is then read from HA storage and returned as a hex string,
        or ``None`` on failure / timeout.
        """
        service_data: dict[str, Any] = {
            "entity_id": entity_id,
            "timeout": timeout,
            "device": device,
            "command": command,
        }
        if command_type.lower() == "rf":
            service_data["command_type"] = "rf"

        _LOGGER.info(
            "Starting learn_command (%s) on %s, timeout=%ds",
            command_type,
            entity_id,
            timeout,
        )

        wait_timeout = timeout * 1.5 if command_type.lower() == "rf" else timeout

        try:
            await asyncio.wait_for(
                self._hass.services.async_call(
                    "remote",
                    "learn_command",
                    service_data,
                    blocking=True,
                ),
                timeout=wait_timeout,
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Learn command timed out on %s", entity_id)
            return None
        except Exception:
            _LOGGER.exception("Error during learn_command on %s", entity_id)
            return None

        _LOGGER.info(
            "learn_command completed for %s — reading code from storage", entity_id
        )
        code = await self._async_read_stored_code(entity_id, device, command)
        if code:
            _LOGGER.info(
                "Learned %s code on %s (length=%d)", command_type, entity_id, len(code)
            )
            return _b64_to_hex(code)

        _LOGGER.warning(
            "learn_command returned but no code found in storage for device=%s command=%s",
            device,
            command,
        )
        return None

    async def _async_read_stored_code(self, entity_id: str, device: str, command: str) -> str | None:
        """Read a learned code from HA integration storage after learn_command completes.

        Resolves the storage file prefix from the remote entity's manufacturer
        via _get_storage_file_prefix(), which is the only brand-specific part.
        """
        import json
        import os

        entry = er.async_get(self._hass).async_get(entity_id)
        manufacturer = ""
        if entry and entry.device_id:
            dev = dr.async_get(self._hass).async_get(entry.device_id)
            if dev:
                manufacturer = (dev.manufacturer or "").lower()

        prefix = _get_storage_file_prefix(manufacturer)
        if not prefix:
            _LOGGER.warning(
                "No storage prefix known for %s (manufacturer=%r); cannot retrieve learned code",
                entity_id,
                manufacturer,
            )
            return None

        storage_dir = self._hass.config.path(".storage")

        def _read() -> str | None:
            try:
                files = os.listdir(storage_dir)
            except OSError:
                return None
            for fname in sorted(files):
                if not fname.startswith(prefix) or not fname.endswith("_codes"):
                    continue
                fpath = os.path.join(storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    code = data.get("data", {}).get(device, {}).get(command)
                    if isinstance(code, str) and code:
                        return code
                except Exception:
                    continue
            return None

        return await self._hass.async_add_executor_job(_read)

    async def _async_read_stored_frequency(self, entity_id: str, device: str, command: str) -> float | None:
        """Read the RF frequency stored alongside a learned command in HA storage."""
        import json
        import os

        entry = er.async_get(self._hass).async_get(entity_id)
        manufacturer = ""
        if entry and entry.device_id:
            dev = dr.async_get(self._hass).async_get(entry.device_id)
            if dev:
                manufacturer = (dev.manufacturer or "").lower()

        prefix = _get_storage_file_prefix(manufacturer)
        if not prefix:
            return None

        storage_dir = self._hass.config.path(".storage")

        def _read_freq() -> float | None:
            try:
                files = os.listdir(storage_dir)
            except OSError:
                return None
            for fname in sorted(files):
                if not fname.startswith(prefix) or not fname.endswith("_codes"):
                    continue
                fpath = os.path.join(storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    freq = data.get("data", {}).get(device, {}).get("frequency")
                    if freq is not None:
                        return float(freq)
                except Exception:
                    continue
            return None

        return await self._hass.async_add_executor_job(_read_freq)

    async def async_get_stored_codes(self) -> list[dict]:
        """Return all learned codes found in HA storage across known remote integrations.

        Discovers which storage file prefixes are relevant by inspecting the
        manufacturer of every connected remote entity.
        """
        import json
        import os

        storage_dir = self._hass.config.path(".storage")
        result: list[dict] = []

        prefixes: dict[str, str] = {}
        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)
        for state in self._hass.states.async_all("remote"):
            entry = entity_registry.async_get(state.entity_id)
            if not (entry and entry.device_id):
                continue
            dev = device_registry.async_get(entry.device_id)
            if not dev:
                continue
            manufacturer = (dev.manufacturer or "").lower()
            prefix = _get_storage_file_prefix(manufacturer)
            if prefix and prefix not in prefixes:
                prefixes[prefix] = manufacturer

        if not prefixes:
            return result

        META_KEYS = {"model", "frequency", "type", "manufacturer"}

        def _read_all() -> list[dict]:
            try:
                files = os.listdir(storage_dir)
            except OSError:
                return []
            found: list[dict] = []
            for fname in sorted(files):
                if fname.endswith((".bak", ".orig")):
                    continue
                matched_prefix = next((p for p in prefixes if fname.startswith(p)), None)
                if not matched_prefix or not fname.endswith("_codes"):
                    continue
                fpath = os.path.join(storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                source = prefixes[matched_prefix]
                identifier = fname
                for strip in (matched_prefix, "_codes", "_flags"):
                    identifier = identifier.replace(strip, "")
                for device_name, commands in (data.get("data") or {}).items():
                    if not isinstance(commands, dict):
                        continue
                    for cmd_name, cmd_value in commands.items():
                        if not isinstance(cmd_value, str) or cmd_name in META_KEYS:
                            continue
                        preview = cmd_value[:60] + ("\u2026" if len(cmd_value) > 60 else "")
                        found.append({
                            "identifier": identifier,
                            "source": source,
                            "device": device_name,
                            "command": cmd_name,
                            "code": cmd_value,
                            "code_preview": preview,
                            "code_length": len(cmd_value),
                        })
            return found

        return await self._hass.async_add_executor_job(_read_all)


    async def async_get_ble_adapters(self) -> list[dict]:
        """Return local BLE adapters (via ``ble_emitter.get_ble_adapters``)."""
        from .ble_emitter import get_ble_adapters

        return await self._hass.async_add_executor_job(get_ble_adapters)

    async def async_ensure_ble_monitoring(self) -> str | None:
        """Register a real-time BLE advertisement callback if not already active.

        Returns an error string on failure, or ``None`` on success.
        """
        if self._ble_cancel_cb is not None:
            return None

        try:
            from homeassistant.components import bluetooth
            from homeassistant.components.bluetooth import BluetoothScanningMode
            from homeassistant.core import callback as ha_callback
            import time as _time

            @ha_callback
            def _on_adv(service_info, change) -> None:
                addr = service_info.address
                mfr_data: dict[str, str] = {}
                if service_info.manufacturer_data:
                    for mid, raw in service_info.manufacturer_data.items():
                        mfr_data[str(mid)] = raw.hex()
                svc_data: dict[str, str] = {}
                if service_info.service_data:
                    for uuid, raw_bytes in service_info.service_data.items():
                        svc_data[uuid] = raw_bytes.hex()
                raw_bytes = getattr(service_info, "raw", None)
                if raw_bytes is None:
                    _adv = getattr(service_info, "advertisement", None)
                    raw_bytes = getattr(_adv, "raw", None)
                raw_hex = raw_bytes.hex() if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes else ""
                t = getattr(service_info, "time", _time.monotonic())
                self._ble_buffer[addr] = {
                    "address": addr,
                    "name": service_info.name or "",
                    "rssi": getattr(service_info, "rssi", None),
                    "source": service_info.source,
                    "manufacturer_data": mfr_data,
                    "service_data": svc_data,
                    "raw": raw_hex,
                    "time": t,
                }

            self._ble_cancel_cb = bluetooth.async_register_callback(
                self._hass,
                _on_adv,
                {},
                BluetoothScanningMode.PASSIVE,
            )
            _LOGGER.info("Whispeer BLE advertisement monitoring started")
            return None
        except ImportError:
            return "HA Bluetooth integration not found — enable it in Settings > Integrations."
        except Exception as exc:
            _LOGGER.error("Failed to start BLE monitoring: %s", exc)
            return str(exc)

    async def async_scan_ble_devices(
        self, adapter_mac: str
    ) -> tuple[list[dict], str | None]:
        """Return BLE advertisements seen by *adapter_mac* since the last call.

        Pops returned entries from the buffer so each poll only delivers
        advertisements that arrived after the previous one — mirroring how
        HA's bluetooth websocket subscription stream works.
        """
        import time as _time

        error = await self.async_ensure_ble_monitoring()
        if error and not self._ble_buffer:
            return [], error

        needle = adapter_mac.upper().replace("-", ":")
        now = _time.monotonic()
        result: list[dict] = []
        to_pop: list[str] = []

        for addr, info in list(self._ble_buffer.items()):
            src = (info.get("source") or "").upper()
            if src != needle:
                continue
            t = info.get("time", 0)
            last_seen_ago = round(now - t, 1) if t else None
            result.append({**info, "last_seen_ago": last_seen_ago})
            to_pop.append(addr)

        for addr in to_pop:
            self._ble_buffer.pop(addr, None)

        return result, None

    async def async_find_remote_by_identifier(self, identifier: str) -> str | None:
        """Return the ``remote.*`` entity_id whose device matches *identifier*.

        *identifier* is a MAC-style string (e.g. ``e87072ba6c04``).
        We normalise both sides by stripping ``:`` and ``-`` before comparing.
        """
        needle = identifier.lower().replace(":", "").replace("-", "")

        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)

        for state in self._hass.states.async_all("remote"):
            entry = entity_registry.async_get(state.entity_id)
            if not (entry and entry.device_id):
                continue
            dev = device_registry.async_get(entry.device_id)
            if not dev:
                continue
            for con_type, con_val in dev.connections:
                if con_type == "mac":
                    if con_val.lower().replace(":", "").replace("-", "") == needle:
                        return state.entity_id
            for _domain, ident_val in dev.identifiers:
                if needle in ident_val.lower().replace(":", "").replace("-", ""):
                    return state.entity_id

        return None



def _ensure_base64(data: str) -> str:
    """Return *data* as a valid base64 string.

    If *data* looks like hex (even-length, all hex digits) it is first
    decoded to bytes and then re-encoded as base64.  If it already is
    base64 it is returned unchanged.
    """
    stripped = data.strip()

    stripped = "".join(stripped.split())

    _HEX_CHARS = frozenset("0123456789abcdefABCDEF")
    if len(stripped) % 2 == 0 and all(c in _HEX_CHARS for c in stripped):
        try:
            raw = bytes.fromhex(stripped)
            return base64.b64encode(raw).decode("ascii")
        except ValueError:
            pass

    return stripped


def _b64_to_hex(data: str) -> str:
    """Convert a base64 string to hex."""
    try:
        raw = base64.b64decode(data)
        return raw.hex()
    except Exception:
        return data


def _get_storage_file_prefix(manufacturer: str) -> str | None:
    """Map a remote device manufacturer to its HA storage file prefix.

    This is the brand-specific part of the code-retrieval flow.
    Add new manufacturers here as support is added.
    """
    if "broadlink" in manufacturer:
        return "broadlink_remote_"
    return None


def _get_capabilities(state, device_entry=None) -> list[str]:
    caps = ["ir"]

    features = state.attributes.get("supported_features", 0)
    can_learn = bool(features & 1)

    if not can_learn:
        return []

    if device_entry:
        manufacturer = (device_entry.manufacturer or "").lower()
        model = (device_entry.model or "").lower()

        if "broadlink" in manufacturer:
            if "pro" in model:
                caps.append("rf")

        elif "bond" in manufacturer:
            caps.append("rf")

        elif "logitech" in manufacturer or "global caché" in manufacturer:
            pass

    if "rf" in state.entity_id.lower() and "rf" not in caps:
        caps.append("rf")

    return list(set(caps))
