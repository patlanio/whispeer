"""Shared pytest runtime configuration for the Whispeer test suite."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WhispeerTestSettings:
    """Runtime settings used by backend, integration, and E2E test layers."""

    base_url: str
    ws_url: str
    login_url: str
    panel_url: str
    username: str
    password: str
    storage_state_path: Path
    container_name: str | None
    container_host: str | None
    headed: bool
    slowmo_ms: int
    browser_name: str
    timeout_ms: int


def build_test_settings(
    *,
    options: Mapping[str, Any],
    env: Mapping[str, str],
) -> WhispeerTestSettings:
    """Build settings from pytest options and environment variables."""
    base_url = str(
        _coalesce(
            options.get("whispeer_base_url"),
            env.get("WHISPEER_BASE_URL"),
            "http://localhost:8125",
        )
    ).rstrip("/")
    ws_url = str(
        _coalesce(
            options.get("whispeer_ws_url"),
            env.get("WHISPEER_WS_URL"),
            _default_ws_url(base_url),
        )
    )
    username = str(
        _coalesce(
            options.get("whispeer_username"),
            env.get("WHISPEER_USERNAME"),
            "john",
        )
    )
    password = str(
        _coalesce(
            options.get("whispeer_password"),
            env.get("WHISPEER_PASSWORD"),
            "doe",
        )
    )
    storage_state_raw = str(
        _coalesce(
            options.get("whispeer_storage_state"),
            env.get("WHISPEER_STORAGE_STATE"),
            ".pytest-cache/whispeer-storage-state.json",
        )
    )
    container_name = _coalesce(
        options.get("whispeer_container_name"),
        env.get("WHISPEER_CONTAINER_NAME"),
        "homeassistant-dev",
    )
    container_host = _coalesce(
        options.get("whispeer_container_host"),
        env.get("WHISPEER_CONTAINER_HOST"),
    )
    headed = _coerce_bool(
        _coalesce(
            options.get("whispeer_headed"),
            env.get("WHISPEER_HEADED"),
        ),
        default=False,
    )
    browser_name = str(
        _coalesce(
            options.get("whispeer_browser"),
            env.get("WHISPEER_BROWSER"),
            "chromium",
        )
    )
    slowmo_ms = _coerce_int(
        _coalesce(
            options.get("whispeer_slowmo_ms"),
            env.get("WHISPEER_SLOWMO_MS"),
        ),
        default=0,
    )
    timeout_ms = _coerce_int(
        _coalesce(
            options.get("whispeer_timeout_ms"),
            env.get("WHISPEER_TIMEOUT_MS"),
        ),
        default=30000,
    )

    storage_state_path = Path(storage_state_raw).expanduser()

    return WhispeerTestSettings(
        base_url=base_url,
        ws_url=ws_url,
        login_url=base_url,
        panel_url=f"{base_url}/api/whispeer/panel",
        username=username,
        password=password,
        storage_state_path=storage_state_path,
        container_name=str(container_name) if container_name else None,
        container_host=str(container_host) if container_host else None,
        headed=headed,
        slowmo_ms=slowmo_ms,
        browser_name=browser_name,
        timeout_ms=timeout_ms,
    )


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _coerce_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}/api/websocket"
