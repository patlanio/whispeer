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

from typing import Any

from .learn_provider import LearnProvider, LearnSession

_RF_COMMON_FREQS = (315.0, 433.92)


def _parse_check_frequency_result(result: Any) -> tuple[bool, float | None]:
    """Normalize broadlink check_frequency() output.

    Some broadlink variants return `(found, freq)`, while others can expose
    a usable `freq` even when `found` is false.
    """
    found = False
    detected_freq: float | None = None

    if isinstance(result, (tuple, list)) and len(result) >= 2:
        first, second = result[0], result[1]
        if isinstance(first, bool):
            found = first
            try:
                detected_freq = float(second)
            except (TypeError, ValueError):
                detected_freq = None
        elif isinstance(second, bool):
            found = second
            try:
                detected_freq = float(first)
            except (TypeError, ValueError):
                detected_freq = None
        else:
            try:
                detected_freq = float(second)
            except (TypeError, ValueError):
                detected_freq = None
    return found, detected_freq


def _is_plausible_rf_frequency(freq: float | None) -> bool:
    """Return True when *freq* looks like a real RF carrier for RM4 use-cases."""
    if freq is None:
        return False
    return any(abs(freq - base) <= 5.0 for base in _RF_COMMON_FREQS)


def _normalize_rf_frequency(freq: float | None) -> float | None:
    """Normalize a detected RF frequency to canonical values when close enough.

    Broadlink can report approximate values (for example ~430.0 for 433.92).
    """
    if freq is None:
        return None
    nearest = min(_RF_COMMON_FREQS, key=lambda base: abs(freq - base))
    if abs(freq - nearest) <= 6.0:
        return nearest
    return freq


def _is_storage_full_error(exc: Exception) -> bool:
    """Return True when Broadlink reports the known transient storage-full error."""
    msg = str(exc)
    return "[Errno -5]" in msg and "storage is full" in msg.lower()


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

        authenticated = device.auth()
        return device if authenticated else None
    except Exception:
        return None


class BroadlinkLearnProvider(LearnProvider):
    """Learn IR/RF commands by talking directly to the Broadlink device.

    Selection rule: RF commands on a Broadlink interface.
    All other combinations fall through to ``HassLearnProvider``.
    """

    NAME = "broadlink"
    PHASE_TIMEOUT_SECONDS = 30

    @classmethod
    def can_handle(cls, device_type: str, manufacturer: str) -> bool:
        return device_type.lower() == "rf" and "broadlink" in manufacturer.lower()


    async def start(self, session: LearnSession) -> None:
        """Start learning an RF command.

        Routes to the fast path when a known frequency is already stored on
        the session, otherwise performs the full sweep+capture cycle.
        """
        try:
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
            session.update_status("error", error_message=str(exc))

    async def find_frequency(self, session: LearnSession) -> None:
        """Sweep only — detect RF frequency without capturing a command."""
        try:
            ip_address, mac_address = await self._resolve_connection(session)
            if not ip_address:
                return

            await self._hass.async_add_executor_job(
                self._do_sweep_only, session, ip_address, mac_address
            )

        except Exception as exc:
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
        candidate_hits = 0
        last_candidate: float | None = None
        try:
            for attempt in range(1, self.PHASE_TIMEOUT_SECONDS + 1):
                _time.sleep(1)
                try:
                    found, detected_freq = _parse_check_frequency_result(
                        device.check_frequency()
                    )
                    if found:
                        normalized = _normalize_rf_frequency(detected_freq)
                        freq = normalized
                        break

                    if _is_plausible_rf_frequency(detected_freq):
                        if last_candidate is not None and abs(detected_freq - last_candidate) <= 1.0:
                            candidate_hits += 1
                        else:
                            candidate_hits = 1
                        last_candidate = detected_freq

                        if candidate_hits >= 2:
                            normalized = _normalize_rf_frequency(detected_freq)
                            freq = normalized
                            break
                except Exception:
                    continue
        finally:
            self._cancel_sweep_frequency(device, session.session_id, "full-sweep")

        if freq is None:
            session.update_status(
                "timeout", error_message="No frequency detected within timeout"
            )
            return

        session.detected_frequency = freq

        session.phase = "capturing"

        code = self._capture_with_frequency_fallback(
            device,
            session_id=session.session_id,
            preferred_frequency=freq,
            context="capture",
        )
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
        normalized_frequency = _normalize_rf_frequency(frequency)

        device = _broadlink_connect(ip_address, mac_address)
        if not device:
            session.update_status(
                "error", error_message="Failed to connect to Broadlink device"
            )
            return

        session.update_status("learning")

        code = self._capture_with_frequency_fallback(
            device,
            session_id=session.session_id,
            preferred_frequency=normalized_frequency,
            context="fast-capture",
        )
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
        candidate_hits = 0
        last_candidate: float | None = None
        try:
            for attempt in range(1, self.PHASE_TIMEOUT_SECONDS + 1):
                _time.sleep(1)
                try:
                    found, detected_freq = _parse_check_frequency_result(
                        device.check_frequency()
                    )
                    if found:
                        normalized = _normalize_rf_frequency(detected_freq)
                        freq = normalized
                        break

                    if _is_plausible_rf_frequency(detected_freq):
                        if last_candidate is not None and abs(detected_freq - last_candidate) <= 1.0:
                            candidate_hits += 1
                        else:
                            candidate_hits = 1
                        last_candidate = detected_freq

                        if candidate_hits >= 2:
                            normalized = _normalize_rf_frequency(detected_freq)
                            freq = normalized
                            break
                except Exception:
                    continue
        finally:
            self._cancel_sweep_frequency(device, session.session_id, "sweep-only")

        if freq:
            session.detected_frequency = freq
            session.phase = "completed"
            session.update_status("completed")
        else:
            session.update_status(
                "timeout", error_message="No frequency detected within timeout"
            )

    def _poll_check_data(
        self,
        device,
        max_attempts: int = 30,
        session_id: str | None = None,
        context: str = "capture",
    ) -> str | None:
        """Poll device.check_data() until a code arrives or attempts are exhausted."""
        import time as _time

        attempt = 0
        wall_attempt = 0
        max_wall_attempts = max_attempts

        while attempt < max_attempts and wall_attempt < max_wall_attempts:
            wall_attempt += 1
            _time.sleep(1)
            try:
                packet = device.check_data()
                if packet:
                    return packet.hex()
                attempt += 1
            except Exception as exc:
                if _is_storage_full_error(exc):
                    continue

                attempt += 1
                continue
        return None

    def _capture_with_frequency_fallback(
        self,
        device,
        session_id: str,
        preferred_frequency: float | None,
        context: str,
    ) -> str | None:
        """Capture RF packet trying preferred frequency first, then no-frequency fallback."""
        total_budget = self.PHASE_TIMEOUT_SECONDS

        preferred_budget = total_budget
        if preferred_frequency is not None:
            preferred_budget = max(20, total_budget - 10)

        self._start_rf_capture(device, preferred_frequency, session_id, context)
        code = self._poll_check_data(
            device,
            max_attempts=preferred_budget,
            session_id=session_id,
            context=context,
        )
        if code or preferred_frequency is None or preferred_budget >= total_budget:
            return code

        fallback_budget = total_budget - preferred_budget
        self._start_rf_capture(device, None, session_id, f"{context}-fallback")
        return self._poll_check_data(
            device,
            max_attempts=fallback_budget,
            session_id=session_id,
            context=f"{context}-fallback",
        )

    def _start_rf_capture(
        self,
        device,
        frequency: float | None,
        session_id: str,
        context: str,
    ) -> None:
        """Start RF capture mode, preferring explicit frequency when provided."""
        try:
            if frequency is None:
                device.find_rf_packet()
            else:
                device.find_rf_packet(frequency)
        except TypeError:
            device.find_rf_packet()

    def _cancel_sweep_frequency(self, device, session_id: str, context: str) -> None:
        """Best-effort sweep cancellation after RF detection phase."""
        try:
            device.cancel_sweep_frequency()
        except Exception:
            pass


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
