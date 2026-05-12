"""Test-mode helpers for deterministic Whispeer integration testing."""
from __future__ import annotations

import asyncio
import os
import time
from copy import deepcopy
from typing import Any

from .const import DOMAIN, TEST_HARNESS_KEY, WHISPEER_TEST_MODE_ENV

_TRUTHY = {"1", "true", "yes", "on"}


def is_test_mode_enabled() -> bool:
    """Return True when the integration should expose test hooks."""
    value = os.getenv(WHISPEER_TEST_MODE_ENV, "")
    return value.strip().lower() in _TRUTHY


def get_test_harness(hass) -> "WhispeerTestHarness":
    """Return the shared test harness instance for *hass*."""
    if hass is None:
        return WhispeerTestHarness(enabled=False)

    domain_data = hass.data.setdefault(DOMAIN, {})
    harness = domain_data.get(TEST_HARNESS_KEY)
    if harness is None:
        harness = WhispeerTestHarness(enabled=is_test_mode_enabled())
        domain_data[TEST_HARNESS_KEY] = harness
    return harness


class WhispeerTestHarness:
    """Holds test-mode overrides and a backend event journal."""

    MAX_JOURNAL_ENTRIES = 500

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._reset_config()
        self.clear_journal()

    def _reset_config(self) -> None:
        self._interfaces: dict[str, list[dict[str, Any]]] = {}
        self._learn_queue: list[dict[str, Any]] = []
        self._frequency_queue: list[dict[str, Any]] = []
        self._send_command: dict[str, Any] = {
            "enabled": False,
            "success": True,
            "message": "Mock send_command completed",
            "result": {},
        }
        self._ble_scan: dict[str, dict[str, Any]] = {}
        self._ble_emit: dict[str, Any] = {
            "enabled": False,
            "success": True,
            "message": "Mock BLE emit completed",
            "result": {},
        }

    def clear_journal(self) -> None:
        self._journal: list[dict[str, Any]] = []
        self._sequence = 0

    def reset(self, clear_config: bool = True) -> None:
        if clear_config:
            self._reset_config()
        self.clear_journal()

    def configure(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()

        if payload.get("reset"):
            self.reset(clear_config=True)
        elif payload.get("clear_journal"):
            self.clear_journal()

        interfaces = payload.get("interfaces")
        if isinstance(interfaces, dict):
            if payload.get("replace_interfaces"):
                self._interfaces = {}
            for device_type, entries in interfaces.items():
                if isinstance(entries, list):
                    self._interfaces[str(device_type).lower()] = deepcopy(entries)

        learn = payload.get("learn")
        if isinstance(learn, dict):
            queue = learn.get("queue")
            if learn.get("replace"):
                self._learn_queue = []
            if isinstance(queue, list):
                self._learn_queue.extend(deepcopy(queue))

        frequency = payload.get("frequency")
        if isinstance(frequency, dict):
            queue = frequency.get("queue")
            if frequency.get("replace"):
                self._frequency_queue = []
            if isinstance(queue, list):
                self._frequency_queue.extend(deepcopy(queue))

        send_command = payload.get("send_command")
        if isinstance(send_command, dict):
            updated = deepcopy(self._send_command)
            updated.update(deepcopy(send_command))
            self._send_command = updated

        ble_scan = payload.get("ble_scan")
        if isinstance(ble_scan, dict):
            if payload.get("replace_ble_scan"):
                self._ble_scan = {}
            for adapter_mac, override in ble_scan.items():
                if isinstance(override, dict):
                    self._ble_scan[str(adapter_mac)] = deepcopy(override)

        ble_emit = payload.get("ble_emit")
        if isinstance(ble_emit, dict):
            updated = deepcopy(self._ble_emit)
            updated.update(deepcopy(ble_emit))
            self._ble_emit = updated

        self.record("test_harness", "configured", payload=payload)
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "journal_size": len(self._journal),
            "journal": deepcopy(self._journal),
            "config": {
                "interfaces": deepcopy(self._interfaces),
                "learn": {"queue": deepcopy(self._learn_queue)},
                "frequency": {"queue": deepcopy(self._frequency_queue)},
                "send_command": deepcopy(self._send_command),
                "ble_scan": deepcopy(self._ble_scan),
                "ble_emit": deepcopy(self._ble_emit),
            },
        }

    def record(self, category: str, action: str, **details: Any) -> None:
        if not self.enabled:
            return

        self._sequence += 1
        entry = {
            "seq": self._sequence,
            "timestamp": time.time(),
            "category": category,
            "action": action,
            "details": self._normalize_value(details),
        }
        self._journal.append(entry)
        if len(self._journal) > self.MAX_JOURNAL_ENTRIES:
            self._journal = self._journal[-self.MAX_JOURNAL_ENTRIES :]

    def get_interface_override(self, device_type: str) -> list[dict[str, Any]] | None:
        key = (device_type or "").strip().lower()
        if key in self._interfaces:
            return deepcopy(self._interfaces[key])
        return None

    def get_send_command_override(
        self,
        *,
        device_id: str,
        device_type: str,
        command_name: str,
    ) -> dict[str, Any] | None:
        if not self._send_command.get("enabled"):
            return None

        criteria = {
            "device_id": str(device_id),
            "device_type": str(device_type),
            "command_name": str(command_name),
        }
        if not self._matches(self._send_command.get("match"), criteria):
            return None
        return deepcopy(self._send_command)

    def get_ble_scan_override(self, adapter_mac: str) -> dict[str, Any] | None:
        if adapter_mac in self._ble_scan:
            return deepcopy(self._ble_scan[adapter_mac])
        if "*" in self._ble_scan:
            return deepcopy(self._ble_scan["*"])
        return None

    def get_ble_emit_override(self, *, adapter: str) -> dict[str, Any] | None:
        if not self._ble_emit.get("enabled"):
            return None

        criteria = {"adapter": str(adapter)}
        if not self._matches(self._ble_emit.get("match"), criteria):
            return None
        return deepcopy(self._ble_emit)

    def consume_learn_override(
        self,
        *,
        device_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None:
        return self._consume_matching(
            self._learn_queue,
            {
                "device_type": str(device_type).lower(),
                "entity_id": str(entity_id),
            },
        )

    def consume_frequency_override(self, *, entity_id: str) -> dict[str, Any] | None:
        return self._consume_matching(
            self._frequency_queue,
            {"entity_id": str(entity_id)},
        )

    async def async_run_session_override(
        self,
        session,
        override: dict[str, Any],
        *,
        default_phase: str,
        journal_category: str,
    ) -> None:
        transitions = self._build_transitions(override, default_phase)
        self.record(
            journal_category,
            "override_started",
            session_id=session.session_id,
            hub_entity_id=session.hub_entity_id,
            default_phase=default_phase,
            transition_count=len(transitions),
        )

        for transition in transitions:
            delay = transition.get("delay") or 0
            try:
                sleep_time = float(delay)
            except (TypeError, ValueError):
                sleep_time = 0
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            phase = transition.get("phase")
            if phase:
                session.phase = str(phase)

            detected_frequency = transition.get("detected_frequency")
            if detected_frequency is not None:
                try:
                    session.detected_frequency = float(detected_frequency)
                except (TypeError, ValueError):
                    session.detected_frequency = detected_frequency

            status = str(transition.get("status") or "learning")
            command_data = transition.get("command_data")
            error_message = transition.get("error_message")
            session.update_status(
                status,
                command_data=command_data,
                error_message=error_message,
            )
            self.record(
                journal_category,
                "session_transition",
                session_id=session.session_id,
                status=status,
                phase=session.phase,
                detected_frequency=session.detected_frequency,
                has_command_data=bool(session.command_data),
                error_message=error_message,
            )

    def _consume_matching(
        self,
        queue: list[dict[str, Any]],
        criteria: dict[str, Any],
    ) -> dict[str, Any] | None:
        for index, candidate in enumerate(queue):
            if self._matches(candidate.get("match"), criteria):
                return deepcopy(queue.pop(index))
        return None

    def _build_transitions(
        self,
        override: dict[str, Any],
        default_phase: str,
    ) -> list[dict[str, Any]]:
        transitions = override.get("transitions")
        if isinstance(transitions, list) and transitions:
            return deepcopy(transitions)

        final_status = str(override.get("status") or "completed")
        final_phase = str(override.get("phase") or "completed")
        delay = override.get("delay") or 0
        detected_frequency = override.get("detected_frequency")
        command_data = override.get("command_data")
        error_message = override.get("error_message")

        derived: list[dict[str, Any]] = [
            {"status": "learning", "phase": default_phase, "delay": 0}
        ]

        if (
            final_status == "completed"
            and default_phase == "sweeping"
            and detected_frequency is not None
            and command_data
        ):
            derived.append(
                {
                    "status": "learning",
                    "phase": "capturing",
                    "detected_frequency": detected_frequency,
                    "delay": delay,
                }
            )
            delay = 0

        derived.append(
            {
                "status": final_status,
                "phase": final_phase,
                "detected_frequency": detected_frequency,
                "command_data": command_data,
                "error_message": error_message,
                "delay": delay,
            }
        )
        return derived

    def _matches(self, match: Any, criteria: dict[str, Any]) -> bool:
        if not isinstance(match, dict) or not match:
            return True

        for key, expected in match.items():
            if expected in (None, "*"):
                continue
            actual = criteria.get(str(key))
            if actual == expected:
                continue
            if str(actual) != str(expected):
                return False
        return True

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(key): self._normalize_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._normalize_value(item) for item in value]
        return str(value)
