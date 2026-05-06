"""Broadlink-direct learn provider.

Uses the ``python-broadlink`` library to talk directly to the Broadlink
device, giving us fine-grained control over each phase so we can mark the
session as 'learning' only after the hardware command has been acknowledged.

Handles:
  • Full RF learning: frequency sweep → capture
  • Fast RF learning: skip sweep (known frequency) → capture
  • Sweep-only: detect frequency without capturing a command
"""
from __future__ import annotations

import logging
from typing import Any

from .learn_provider import LearnProvider, LearnSession

_LOGGER = logging.getLogger(__package__)


def _broadlink_connect(ip: str, mac: str | None = None, device_type: str | None = None):
    """Connect and authenticate to a Broadlink device.

    If *mac* and *device_type* are provided the connection is made directly
    without a network discovery scan (fast path).  Returns the authenticated
    device object or ``None`` on failure.
    """
    import broadlink

    try:
        if mac and device_type:
            mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
            device = broadlink.gendevice(int(device_type, 16), (ip, 80), mac_bytes)
        else:
            devices = broadlink.discover(timeout=5)
            device = next((d for d in devices if d.host[0] == ip), None)
            if not device:
                return None

        return device if device.auth() else None
    except Exception:
        return None


class BroadlinkLearnProvider(LearnProvider):
    """Learn IR/RF commands by talking directly to the Broadlink device.

    Selection rule: RF commands on a Broadlink interface.
    All other combinations fall through to ``HassLearnProvider``.
    """

    NAME = "broadlink"

    @classmethod
    def can_handle(cls, device_type: str, manufacturer: str) -> bool:
        return device_type.lower() == "rf" and "broadlink" in manufacturer.lower()


    async def start(self, session: LearnSession) -> None:
        """Start learning an RF command.

        Routes to the fast path when a known frequency is already stored on
        the session, otherwise performs the full sweep+capture cycle.
        """
        try:
            _LOGGER.info(
                "BroadlinkLearnProvider: starting session %s on %s",
                session.session_id, session.hub_entity_id,
            )

            ip_address, mac_address = await self._resolve_connection(session)
            if not ip_address:
                return

            if session.detected_frequency:
                await self._hass.async_add_executor_job(
                    self._do_fast_rf_learn,
                    session, ip_address, mac_address, session.detected_frequency,
                )
            else:
                await self._hass.async_add_executor_job(
                    self._do_full_rf_learn,
                    session, ip_address, mac_address,
                )

        except Exception as exc:
            _LOGGER.exception(
                "BroadlinkLearnProvider: session %s failed", session.session_id
            )
            session.update_status("error", error_message=str(exc))

    async def find_frequency(self, session: LearnSession) -> None:
        """Sweep only — detect RF frequency without capturing a command."""
        try:
            _LOGGER.info(
                "BroadlinkLearnProvider: frequency sweep for session %s on %s",
                session.session_id, session.hub_entity_id,
            )

            ip_address, mac_address = await self._resolve_connection(session)
            if not ip_address:
                return

            await self._hass.async_add_executor_job(
                self._do_sweep_only, session, ip_address, mac_address
            )

        except Exception as exc:
            _LOGGER.exception(
                "BroadlinkLearnProvider: frequency sweep %s failed", session.session_id
            )
            session.update_status("error", error_message=str(exc))


    def _do_full_rf_learn(
        self,
        session: LearnSession,
        ip_address: str,
        mac_address: str | None,
    ) -> None:
        """Full RF learning: sweep to identify frequency, then capture command."""
        import time as _time

        device = _broadlink_connect(ip_address, mac_address)
        if not device:
            session.update_status(
                "error", error_message="Failed to connect to Broadlink device"
            )
            return

        device.sweep_frequency()
        session.update_status("learning")

        freq = None
        for _ in range(60):
            _time.sleep(1)
            try:
                found, detected_freq = device.check_frequency()
                if found:
                    freq = detected_freq
                    break
            except Exception:
                continue

        if freq is None:
            session.update_status(
                "timeout", error_message="No frequency detected within timeout"
            )
            return

        session.detected_frequency = freq

        device.find_rf_packet(freq)
        session.phase = "capturing"

        code = self._poll_check_data(device)
        if code:
            session.phase = "completed"
            session.update_status("completed", command_data=code)
        elif session.status not in ("error", "timeout"):
            session.update_status(
                "timeout", error_message="No code received within timeout"
            )

    def _do_fast_rf_learn(
        self,
        session: LearnSession,
        ip_address: str,
        mac_address: str | None,
        frequency: float,
    ) -> None:
        """Fast RF learning: skip sweep, go directly to capture with known frequency."""
        device = _broadlink_connect(ip_address, mac_address)
        if not device:
            session.update_status(
                "error", error_message="Failed to connect to Broadlink device"
            )
            return

        device.find_rf_packet(frequency)
        session.update_status("learning")

        code = self._poll_check_data(device, max_attempts=30)
        if code:
            session.phase = "completed"
            session.update_status("completed", command_data=code)
        else:
            session.update_status(
                "timeout", error_message="No RF code received within timeout"
            )

    def _do_sweep_only(
        self,
        session: LearnSession,
        ip_address: str,
        mac_address: str | None,
    ) -> None:
        """Sweep-only: detect frequency without capturing a command."""
        import time as _time

        device = _broadlink_connect(ip_address, mac_address)
        if not device:
            session.update_status(
                "error", error_message="Failed to connect to Broadlink device"
            )
            return

        device.sweep_frequency()

        freq = None
        for _ in range(30):
            _time.sleep(1)
            try:
                found, detected_freq = device.check_frequency()
                if found:
                    freq = detected_freq
                    break
            except Exception:
                continue

        if freq:
            session.detected_frequency = freq
            session.phase = "completed"
            session.update_status("completed")
        else:
            session.update_status(
                "timeout", error_message="No frequency detected within timeout"
            )

    def _poll_check_data(self, device, max_attempts: int = 90) -> str | None:
        """Poll device.check_data() until a code arrives or attempts are exhausted."""
        import time as _time

        for _ in range(max_attempts):
            _time.sleep(1)
            try:
                packet = device.check_data()
                if packet:
                    return packet.hex()
            except Exception:
                continue
        return None


    async def _resolve_connection(
        self, session: LearnSession
    ) -> tuple[str | None, str | None]:
        """Resolve (ip_address, mac_address) for the Broadlink hub backing *session*.

        Returns ``(None, None)`` and marks the session as error if resolution fails.
        """
        from homeassistant.helpers import entity_registry as er, device_registry as dr

        entry = er.async_get(self._hass).async_get(session.hub_entity_id)
        if not entry or not entry.device_id:
            session.update_status(
                "error", error_message="Cannot resolve device for entity"
            )
            return None, None

        dev = dr.async_get(self._hass).async_get(entry.device_id)
        if not dev:
            session.update_status(
                "error", error_message="Device not found in registry"
            )
            return None, None

        mac_address: str | None = None
        for con_type, con_val in dev.connections:
            if con_type == "mac":
                mac_address = con_val.replace(":", "").replace("-", "")
                break
        if not mac_address:
            for _domain, ident_val in dev.identifiers:
                clean = ident_val.replace(":", "").replace("-", "")
                if len(clean) == 12:
                    mac_address = clean
                    break

        ip_address: str | None = None
        for ce in self._hass.config_entries.async_entries():
            if ce.domain == "broadlink" and ce.data.get("host"):
                ce_mac = (ce.unique_id or "").replace(":", "").replace("-", "").lower()
                if ce_mac == (mac_address or "").lower():
                    ip_address = ce.data["host"]
                    break

        if not ip_address:
            state = self._hass.states.get(session.hub_entity_id)
            if state:
                ip_address = (
                    state.attributes.get("host")
                    or state.attributes.get("ip_address")
                )

        if not ip_address:
            session.update_status(
                "error", error_message="Cannot determine Broadlink device IP"
            )
            return None, None

        return ip_address, mac_address
