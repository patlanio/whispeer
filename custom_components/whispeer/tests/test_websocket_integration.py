from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.whispeer_title(
    "Asserts the WebSocket 'get_state' response contains expected fields (enabled, journal, learning sessions, interfaces)."
)
def test_test_state_reports_expected_shape(
    whispeer_test_harness,
) -> None:
    state = whispeer_test_harness("whispeer/test/get_state")

    assert state["enabled"] is True
    assert state["journal_size"] == 0
    assert state["journal"] == []
    assert state["learning_sessions"] == []
    assert "interfaces" in state["config"]
    assert "send_command" in state["config"]


@pytest.mark.integration
@pytest.mark.whispeer_title(
    "Tests that the 'configure' command applies settings (interfaces, send_command), that the journal increases, and that 'reset' clears queues and config."
)
def test_test_commands_configure_and_reset_round_trip(
    whispeer_test_harness,
) -> None:
    configured = whispeer_test_harness(
        "whispeer/test/configure",
        config={
            "interfaces": {
                "rf": [
                    {
                        "label": "RM4 Test Bench",
                        "entity_id": "remote.rm4_test_bench",
                        "manufacturer": "Broadlink",
                    }
                ]
            },
            "send_command": {
                "enabled": True,
                "success": True,
                "match": {"command_name": "power"},
            },
        },
    )

    state = configured["state"]
    assert state["config"]["interfaces"]["rf"][0]["label"] == "RM4 Test Bench"
    assert state["config"]["interfaces"]["rf"][0]["entity_id"] == "remote.rm4_test_bench"
    assert state["config"]["send_command"]["enabled"] is True
    assert state["journal_size"] >= 1

    fetched = whispeer_test_harness("whispeer/test/get_state")
    assert fetched["config"]["interfaces"]["rf"][0]["manufacturer"] == "Broadlink"
    assert fetched["journal_size"] >= state["journal_size"]

    reset = whispeer_test_harness(
        "whispeer/test/reset",
        clear_config=True,
        clear_learning_sessions=True,
    )
    assert reset["cleared_learning_sessions"] == 0

    reset_state = reset["state"]
    assert reset_state["journal_size"] == 0
    assert reset_state["config"]["interfaces"] == {}
    assert reset_state["config"]["learn"]["queue"] == []
    assert reset_state["config"]["frequency"]["queue"] == []
    assert reset_state["config"]["send_command"]["enabled"] is False
