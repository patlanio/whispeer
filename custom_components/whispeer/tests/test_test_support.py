from __future__ import annotations

import asyncio
import threading

import pytest

from whispeer.test_support import WhispeerTestHarness


class DummySession:
    def __init__(self, session_id: str, command_type: str, hub_entity_id: str) -> None:
        self.session_id = session_id
        self.command_type = command_type
        self.hub_entity_id = hub_entity_id
        self.status = "preparing"
        self.phase = "sweeping"
        self.command_data = None
        self.detected_frequency = None
        self.error_message = None

    def update_status(self, status: str, command_data=None, error_message=None) -> None:
        self.status = status
        if command_data is not None:
            self.command_data = command_data
        if error_message is not None:
            self.error_message = error_message


@pytest.mark.backend
@pytest.mark.whispeer_title(
    "Ensures 'WhispeerTestHarness' applies interface configuration and provides a 'send_command' override when configured."
)
def test_harness_configures_interfaces_and_send_override() -> None:
    harness = WhispeerTestHarness(enabled=True)
    state = harness.configure({
        "interfaces": {
            "rf": [
                {"label": "RM4 Pro", "entity_id": "remote.rm4_pro"},
            ]
        },
        "send_command": {
            "enabled": True,
            "success": False,
            "match": {"command_name": "power"},
        },
    })

    assert state["config"]["interfaces"]["rf"][0]["entity_id"] == "remote.rm4_pro"
    override = harness.get_send_command_override(
        device_id="living_room",
        device_type="ir",
        command_name="power",
    )
    assert override is not None
    assert override["success"] is False


@pytest.mark.backend
@pytest.mark.whispeer_title(
    "Confirms the learn override queue is matched and consumed exactly once for a given device/interface."
)
def test_harness_consumes_matching_learn_override_once() -> None:
    harness = WhispeerTestHarness(enabled=True)
    harness.configure({
        "learn": {
            "replace": True,
            "queue": [
                {
                    "match": {
                        "device_type": "rf",
                        "entity_id": "remote.rm4_pro",
                    },
                    "status": "completed",
                    "detected_frequency": 433.92,
                    "command_data": "a1b2c3",
                }
            ],
        }
    })

    override = harness.consume_learn_override(
        device_type="rf",
        entity_id="remote.rm4_pro",
    )

    assert override is not None
    assert override["command_data"] == "a1b2c3"
    assert harness.consume_learn_override(
        device_type="rf",
        entity_id="remote.rm4_pro",
    ) is None


@pytest.mark.backend
@pytest.mark.whispeer_title(
    "Validates session override transition flow and resulting journal entries during a simulated learning session."
)
def test_harness_runs_default_session_override_transitions() -> None:
    harness = WhispeerTestHarness(enabled=True)
    session = DummySession("session-1", "rf", "remote.rm4_pro")

    failure: list[BaseException] = []

    def _runner() -> None:
        try:
            asyncio.run(
                harness.async_run_session_override(
                    session,
                    {
                        "status": "completed",
                        "detected_frequency": 433.92,
                        "command_data": "deadbeef",
                    },
                    default_phase="sweeping",
                    journal_category="learn",
                )
            )
        except BaseException as exc:  # pragma: no cover - propagated to the test thread
            failure.append(exc)

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()

    if failure:
        raise failure[0]

    assert session.status == "completed"
    assert session.phase == "completed"
    assert session.detected_frequency == pytest.approx(433.92)
    assert session.command_data == "deadbeef"
    assert harness.snapshot()["journal_size"] >= 2
