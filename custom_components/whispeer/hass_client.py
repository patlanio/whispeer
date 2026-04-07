"""Home Assistant API client for Whispeer.

Centralises all communication with HA services (remote.send_command,
remote.learn_command) and state queries so that no other module needs
to interact with the broadlink library or raw network sockets.
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

    # ------------------------------------------------------------------
    # Hub / interface discovery
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def async_send_command(
        self,
        entity_id: str,
        command_data: str,
    ) -> bool:
        """Send an IR/RF code via ``remote.send_command``.

        ``command_data`` is the hex (or base64) string stored in the
        device command slot.  The Broadlink HA integration expects a
        base64-encoded string inside the *command* list.
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

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    async def async_learn_command(
        self,
        entity_id: str,
        command: str,
        command_type: str = "ir",
        timeout: int = 30,
        device: str = "default_device",
    ) -> str | None:
        """Put the hub into learning mode via ``remote.learn_command``.

        The HA Broadlink integration fires ``broadlink.remote_received``
        events when a code is captured.  We listen for that event and
        return the learned code as a hex string, or ``None`` on timeout.
        """
        learned_code: asyncio.Future[str] = self._hass.loop.create_future()

        def _on_event(event):
            """Handle broadlink learned-code event."""
            data = event.data or {}
            # The Broadlink integration fires the event with a "packet"
            # key containing the base64-encoded data.
            packet = data.get("packet") or data.get("code") or ""
            if packet and not learned_code.done():
                learned_code.set_result(packet)

        unsub = self._hass.bus.async_listen(
            "broadlink.remote_received", _on_event
        )

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

        try:
            await self._hass.services.async_call(
                "remote",
                "learn_command",
                service_data,
                blocking=False,
            )

            code = await asyncio.wait_for(learned_code, timeout=timeout)
            _LOGGER.info("Learned %s code on %s (length=%d)", command_type, entity_id, len(code))
            return _b64_to_hex(code)
        except asyncio.TimeoutError:
            _LOGGER.warning("Learn command timed out on %s", entity_id)
            return None
        except Exception:
            _LOGGER.exception("Error during learn_command on %s", entity_id)
            return None
        finally:
            unsub()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ensure_base64(data: str) -> str:
    """Return *data* as a valid base64 string.

    If *data* looks like hex (even-length, all hex digits) it is first
    decoded to bytes and then re-encoded as base64.  If it already is
    base64 it is returned unchanged.
    """
    stripped = data.strip()

    # Quick check: if it already decodes as base64 → return as-is.
    try:
        raw = base64.b64decode(stripped, validate=True)
        if len(raw) > 4:
            return stripped
    except Exception:
        pass

    # Assume hex
    try:
        raw = bytes.fromhex(stripped)
        return base64.b64encode(raw).decode("ascii")
    except ValueError:
        pass

    # Fallback — return as-is and let the service handle it.
    return stripped


def _b64_to_hex(data: str) -> str:
    """Convert a base64 string to hex."""
    try:
        raw = base64.b64decode(data)
        return raw.hex()
    except Exception:
        return data


def _get_capabilities(state, device_entry=None) -> list[str]:
    caps = ["ir"]  # Assume IR by default in the remote domain

    # 1. Check supported_features (Bitmask)
    features = state.attributes.get("supported_features", 0)
    can_learn = bool(features & 1)  # Bit 0 is LEARN_COMMAND

    if not can_learn:
        return []  # If it cannot learn, it is not useful for the "learning" UI

    # 2. Logic by Manufacturer (Add known cases cleanly)
    if device_entry:
        manufacturer = (device_entry.manufacturer or "").lower()
        model = (device_entry.model or "").lower()

        # Broadlink case: "pro" is the standard for RF
        if "broadlink" in manufacturer:
            if "pro" in model:
                caps.append("rf")

        # Bond case: It is a hub that is natively RF
        elif "bond" in manufacturer:
            caps.append("rf")

        # Global Caché or Logitech case: They are 99% IR
        elif "logitech" in manufacturer or "global caché" in manufacturer:
            pass  # Only IR

    # 3. Fallback: If the device name contains RF (user-assisted)
    if "rf" in state.entity_id.lower() and "rf" not in caps:
        caps.append("rf")

    return list(set(caps))
