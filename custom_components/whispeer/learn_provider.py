"""Shared learning session model and abstract provider interface.

All learn providers (Broadlink, HA-native, BLE) import from here so they
share a common contract and a single in-process session registry.
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

_LOGGER = logging.getLogger(__package__)

# Active learning sessions keyed by session_id — shared across all providers.
LEARNING_SESSIONS: Dict[str, "LearnSession"] = {}


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
        self.phase = "sweeping" if command_type.lower() == "rf" else "capturing"
        self.command_data: Optional[str] = None
        self.detected_frequency: Optional[float] = None
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


class LearnProvider(ABC):
    """Common interface that all learn providers must implement.

    Providers are selected by ``can_handle()`` and then instantiated with
    the HA ``hass`` object.  The ``start()`` coroutine drives the learning
    flow, updating the shared ``LearnSession`` as it progresses.
    """

    NAME: str = ""

    def __init__(self, hass: Any) -> None:
        self._hass = hass

    @classmethod
    @abstractmethod
    def can_handle(cls, device_type: str, manufacturer: str) -> bool:
        """Return True if this provider can handle the given device/manufacturer."""

    @abstractmethod
    async def start(self, session: LearnSession) -> None:
        """Start the learning process, updating *session* as it progresses."""
