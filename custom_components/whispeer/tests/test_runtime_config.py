from __future__ import annotations

from pathlib import Path

from whispeer.tests.runtime import build_test_settings


def test_build_test_settings_prefers_options_over_environment(tmp_path: Path) -> None:
    settings = build_test_settings(
        options={
            "whispeer_base_url": "http://localhost:9123",
            "whispeer_username": "alice",
            "whispeer_password": "secret",
            "whispeer_storage_state": str(tmp_path / "state.json"),
            "whispeer_headed": False,
            "whispeer_slowmo_ms": "250",
            "whispeer_browser": "firefox",
            "whispeer_timeout_ms": "45000",
        },
        env={
            "WHISPEER_BASE_URL": "http://localhost:8125",
            "WHISPEER_USERNAME": "john",
            "WHISPEER_PASSWORD": "doe",
            "WHISPEER_HEADED": "1",
        },
    )

    assert settings.base_url == "http://localhost:9123"
    assert settings.ws_url == "ws://localhost:9123/api/websocket"
    assert settings.login_url == "http://localhost:9123"
    assert settings.username == "alice"
    assert settings.password == "secret"
    assert settings.storage_state_path == tmp_path / "state.json"
    assert settings.headed is False
    assert settings.slowmo_ms == 250
    assert settings.browser_name == "firefox"
    assert settings.timeout_ms == 45000


def test_build_test_settings_uses_defaults_when_values_missing() -> None:
    settings = build_test_settings(options={}, env={})

    assert settings.base_url == "http://localhost:8125"
    assert settings.ws_url == "ws://localhost:8125/api/websocket"
    assert settings.panel_url == "http://localhost:8125/api/whispeer/panel"
    assert settings.username == "john"
    assert settings.password == "doe"
    assert settings.storage_state_path == Path(".pytest-cache/whispeer-storage-state.json")
    assert settings.container_name == "homeassistant-dev"
    assert settings.headed is False
    assert settings.slowmo_ms == 0
    assert settings.browser_name == "chromium"
    assert settings.timeout_ms == 30000
