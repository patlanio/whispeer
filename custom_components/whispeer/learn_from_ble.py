"""BLE (Bluetooth Low Energy) provider.

Handles BLE adapter discovery, advertisement scanning, and command emission.
BLE 'learning' is done through the advertisement scanner UI rather than the
standard IR/RF session flow, so ``start()`` is not applicable here.
"""
from __future__ import annotations

import logging
from typing import Any

from .learn_provider import LearnProvider, LearnSession

_LOGGER = logging.getLogger(__package__)


class BleLearnProvider(LearnProvider):
    """BLE provider: adapter discovery, scanning, and command emission.

    This provider does not participate in the standard learn session flow
    (``start()`` raises ``NotImplementedError``).  BLE 'learning' is handled
    by the frontend scanner which captures raw advertisements directly.
    """

    NAME = "ble"

    @classmethod
    def can_handle(cls, device_type: str, manufacturer: str) -> bool:
        return device_type.lower() == "ble"

    async def start(self, session: LearnSession) -> None:
        raise NotImplementedError(
            "BLE learning is done through the advertisement scanner, not the learn session flow"
        )

    # ------------------------------------------------------------------
    # Interface discovery
    # ------------------------------------------------------------------

    async def get_interfaces(self) -> list[dict]:
        """Return all available BLE adapters."""
        from .hass_client import HassClient

        client = HassClient(self._hass)
        return await client.async_get_ble_adapters()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    async def scan(self, adapter_mac: str) -> tuple[list[dict], str | None]:
        """Return BLE advertisements visible to *adapter_mac* since last call."""
        from .hass_client import HassClient

        client = HassClient(self._hass)
        return await client.async_scan_ble_devices(adapter_mac)

    # ------------------------------------------------------------------
    # Command emission
    # ------------------------------------------------------------------

    async def send_command(self, command_code: str, adapter: str) -> dict:
        """Emit a BLE command on *adapter*.

        Accepts either a JSON descriptor ``{ad_type, field_id, data_hex}`` or
        a raw BLE advertisement hex string.
        """
        import json as _json

        try:
            desc = _json.loads(command_code)
            success = await self.emit(
                adapter,
                desc.get("ad_type", ""),
                desc.get("field_id", 0),
                desc.get("data_hex", ""),
            )
        except (ValueError, TypeError):
            success = await self.emit_raw(adapter, command_code)

        return {"status": "success" if success else "error"}

    async def emit(
        self,
        adapter: str,
        ad_type: str,
        field_id: int | str,
        data_hex: str,
    ) -> bool:
        """Emit a structured BLE advertisement."""
        from .ble_emitter import emit_ble

        return await self._hass.async_add_executor_job(
            emit_ble, adapter, ad_type, field_id, data_hex
        )

    async def emit_raw(self, adapter: str, raw_hex: str) -> bool:
        """Emit a raw BLE advertisement PDU."""
        from .ble_emitter import emit_ble_raw

        return await self._hass.async_add_executor_job(emit_ble_raw, adapter, raw_hex)
