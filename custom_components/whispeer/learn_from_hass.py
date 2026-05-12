"""Home Assistant native learn provider.

Delegates to HA's ``remote.learn_command`` service.  This is the default
provider for IR (and RF on non-Broadlink hardware) — no direct hardware
access required.
"""
from __future__ import annotations

import logging

from .learn_provider import LearnProvider, LearnSession
from .hass_client import HassClient
from .test_support import get_test_harness

_LOGGER = logging.getLogger(__package__)


class HassLearnProvider(LearnProvider):
    """Learn commands via HA's ``remote.learn_command`` service.

    This is the default provider: handles any device type / manufacturer not
    claimed by a more specific provider.
    """

    NAME = "hass"

    @classmethod
    def can_handle(cls, device_type: str, manufacturer: str) -> bool:
        return True

    def _record_test_event(self, action: str, **details) -> None:
        get_test_harness(self._hass).record("learn", action, **details)

    async def start(self, session: LearnSession) -> None:
        """Delegate to ``remote.learn_command`` and wait for the button press.

        HA's service call is blocking (waits until the device captures a code
        or times out), so we mark the session as 'learning' right before it
        to let the frontend prompt the user immediately.
        """
        try:
            _LOGGER.info(
                "HassLearnProvider: starting session %s on %s (%s)",
                session.session_id, session.hub_entity_id, session.command_type,
            )

            client = HassClient(self._hass)
            per_phase_timeout = 45 if session.command_type.lower() == "rf" else 30

            session.update_status("learning")
            self._record_test_event(
                "hass_provider_started",
                session_id=session.session_id,
                entity_id=session.hub_entity_id,
                command_type=session.command_type,
                timeout=per_phase_timeout,
            )

            code = await client.async_learn_command(
                entity_id=session.hub_entity_id,
                command="default_command",
                command_type=session.command_type,
                timeout=per_phase_timeout,
            )

            if code:
                session.phase = "completed"
                session.update_status("completed", command_data=code)
                self._record_test_event(
                    "hass_provider_completed",
                    session_id=session.session_id,
                    status=session.status,
                    code_length=len(code),
                )
            else:
                session.update_status(
                    "timeout", error_message="No code received within timeout"
                )
                self._record_test_event(
                    "hass_provider_completed",
                    session_id=session.session_id,
                    status=session.status,
                )

        except Exception as exc:
            _LOGGER.exception(
                "HassLearnProvider: session %s failed", session.session_id
            )
            self._record_test_event(
                "hass_provider_failed",
                session_id=session.session_id,
                error_message=str(exc),
            )
            session.update_status("error", error_message=str(exc))
