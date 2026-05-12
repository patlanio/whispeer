"""Shared Playwright helpers for Whispeer integration and E2E tests."""
from __future__ import annotations

import os
import platform
import re
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_VIEWPORT = {"width": 1600, "height": 1000}


def launch_browser(playwright_api, settings):
    """Launch the requested Playwright browser."""
    try:
        browser_type = getattr(playwright_api, settings.browser_name)
    except AttributeError as exc:
        raise ValueError(
            f"Unsupported Playwright browser '{settings.browser_name}'"
        ) from exc

    headless = _should_launch_headless(settings)
    return browser_type.launch(
        headless=headless,
        slow_mo=settings.slowmo_ms,
    )


def open_authenticated_page(browser, settings):
    """Open an authenticated Home Assistant page using cached storage state."""
    context = _create_authenticated_context(browser, settings)
    page = context.new_page()
    _configure_page(page, settings)
    page.goto(settings.base_url, wait_until="domcontentloaded")
    return context, page


def open_panel_page(browser, settings):
    """Open the Whispeer panel in an authenticated browser context."""
    context, page = open_authenticated_page(browser, settings)
    token = get_access_token(page, settings)
    page.goto(_with_query_param(settings.panel_url, "access_token", token), wait_until="domcontentloaded")
    wait_for_panel_ready(page, settings)
    return context, page


def wait_for_panel_ready(page, settings) -> None:
    """Wait for the Whispeer panel shell to become interactive."""
    page.locator(".brand-title").wait_for(
        state="visible",
        timeout=settings.timeout_ms,
    )
    page.get_by_test_id("open-add-device-modal").wait_for(
        state="visible",
        timeout=settings.timeout_ms,
    )
    page.wait_for_function(
        """() => Boolean(window.WSManager && window.WSManager._ready)""",
        timeout=settings.timeout_ms,
    )
    page.wait_for_function(
        """() => Boolean(
            document.querySelector('.devices-grid') ||
            document.querySelector('.empty-state')
        )""",
        timeout=settings.timeout_ms,
    )


def get_access_token(page, settings=None) -> str:
    """Read the Home Assistant access token from the browser context."""
    timeout_ms = settings.timeout_ms if settings is not None else 30000
    page.wait_for_function(_access_token_script(), timeout=timeout_ms)
    token = page.evaluate(_access_token_script())

    if not token:
        raise AssertionError("No Home Assistant access token was available in the browser context.")
    return token


def call_ha_ws_command(page, settings, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a single Home Assistant websocket command through the browser."""
    token = get_access_token(page, settings)
    command = {**payload, "id": int(payload.get("id", 1))}
    return page.evaluate(
        """async ({ wsUrl, token, command, timeoutMs }) => {
            return await new Promise((resolve) => {
                const socket = new WebSocket(wsUrl);
                let finished = false;

                const finalize = (value) => {
                    if (finished) {
                        return;
                    }
                    finished = true;
                    clearTimeout(timer);
                    try {
                        socket.close();
                    } catch (_) {}
                    resolve(value);
                };

                const timer = setTimeout(() => {
                    finalize({
                        success: false,
                        result: null,
                        error: {
                            code: "timeout",
                            message: `Timed out waiting for websocket response to ${command.type}`,
                        },
                    });
                }, timeoutMs);

                socket.addEventListener("error", () => {
                    finalize({
                        success: false,
                        result: null,
                        error: {
                            code: "socket_error",
                            message: "WebSocket transport error",
                        },
                    });
                });

                socket.addEventListener("close", () => {
                    if (!finished) {
                        finalize({
                            success: false,
                            result: null,
                            error: {
                                code: "socket_closed",
                                message: "WebSocket closed before a result message was received",
                            },
                        });
                    }
                });

                socket.addEventListener("message", (event) => {
                    let message;
                    try {
                        message = JSON.parse(event.data);
                    } catch (_) {
                        return;
                    }

                    if (message.type === "auth_required") {
                        socket.send(JSON.stringify({
                            type: "auth",
                            access_token: token,
                        }));
                        return;
                    }

                    if (message.type === "auth_invalid") {
                        finalize({
                            success: false,
                            result: null,
                            error: {
                                code: "auth_invalid",
                                message: message.message || "Home Assistant rejected the access token",
                            },
                        });
                        return;
                    }

                    if (message.type === "auth_ok") {
                        socket.send(JSON.stringify(command));
                        return;
                    }

                    if (message.type === "result" && message.id === command.id) {
                        finalize({
                            success: Boolean(message.success),
                            result: message.result ?? null,
                            error: message.error ?? null,
                        });
                    }
                });
            });
        }""",
        {
            "wsUrl": settings.ws_url,
            "token": token,
            "command": command,
            "timeoutMs": settings.timeout_ms,
        },
    )


def assert_ws_success(response: dict[str, Any], message: str) -> dict[str, Any]:
    """Return the websocket result payload or raise a helpful assertion."""
    if response.get("success"):
        return response.get("result")

    error = response.get("error") or {}
    code = error.get("code", "unknown_error")
    error_message = error.get("message", "Unknown websocket error")
    raise AssertionError(f"{message} [{code}] {error_message}")


def ensure_test_mode_enabled(page, settings) -> dict[str, Any]:
    """Skip the test cleanly when Home Assistant test mode is disabled."""
    import pytest

    response = call_ha_ws_command(
        page,
        settings,
        {"type": "whispeer/test/get_state"},
    )
    if not response.get("success"):
        error = response.get("error") or {}
        if error.get("code") == "not_allowed":
            pytest.skip(
                "Enable WHISPEER_TEST_MODE=1 in the Home Assistant runtime to run websocket and Playwright tests."
            )
        raise AssertionError(
            f"Unable to query the Whispeer test harness: {error.get('message', 'Unknown error')}"
        )

    state = response.get("result") or {}
    if not state.get("enabled"):
        pytest.skip(
            "Whispeer test mode is disabled in the Home Assistant runtime."
        )
    return state


def _create_authenticated_context(browser, settings):
    storage_state_path = _ensure_authenticated_storage_state(browser, settings)
    context = _new_context(browser, settings, storage_state=storage_state_path)
    page = context.new_page()
    _configure_page(page, settings)
    page.goto(settings.base_url, wait_until="domcontentloaded")

    if _is_login_required(page):
        context.close()
        if storage_state_path.exists():
            storage_state_path.unlink()
        storage_state_path = _ensure_authenticated_storage_state(browser, settings)
        context = _new_context(browser, settings, storage_state=storage_state_path)
    else:
        page.close()

    return context


def _ensure_authenticated_storage_state(browser, settings) -> Path:
    storage_state_path = settings.storage_state_path
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    if storage_state_path.exists() and _storage_state_is_valid(
        browser,
        settings,
        storage_state_path,
    ):
        return storage_state_path

    _login_and_persist_storage_state(browser, settings, storage_state_path)
    return storage_state_path


def _storage_state_is_valid(browser, settings, storage_state_path: Path) -> bool:
    context = _new_context(browser, settings, storage_state=storage_state_path)
    try:
        page = context.new_page()
        _configure_page(page, settings)
        page.goto(settings.base_url, wait_until="domcontentloaded")
        return not _is_login_required(page)
    except Exception:
        return False
    finally:
        context.close()


def _login_and_persist_storage_state(browser, settings, storage_state_path: Path) -> None:
    context = _new_context(browser, settings)
    try:
        page = context.new_page()
        _configure_page(page, settings)
        page.goto(settings.login_url, wait_until="domcontentloaded")

        if not _is_login_required(page):
            context.storage_state(path=str(storage_state_path))
            return

        username = page.locator('input[name="username"], input[type="text"]').first
        password = page.locator('input[name="password"], input[type="password"]').first

        username.wait_for(state="visible", timeout=settings.timeout_ms)
        username.fill(settings.username)
        password.fill(settings.password)

        try:
            page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).click()
        except Exception:
            page.locator('button[type="submit"], input[type="submit"], ha-progress-button, mwc-button').first.click()

        page.wait_for_function(
            """() => {
                const path = window.location.pathname || "";
                return !path.includes("/auth");
            }""",
            timeout=settings.timeout_ms,
        )
        context.storage_state(path=str(storage_state_path))
    finally:
        context.close()


def _new_context(browser, settings, storage_state: Path | None = None):
    kwargs = {
        "ignore_https_errors": True,
        "viewport": DEFAULT_VIEWPORT,
    }
    if storage_state is not None:
        kwargs["storage_state"] = str(storage_state)
    return browser.new_context(**kwargs)


def _configure_page(page, settings) -> None:
    page.set_default_timeout(settings.timeout_ms)
    page.set_default_navigation_timeout(settings.timeout_ms)


def _is_login_required(page) -> bool:
    for attempt in range(3):
        try:
            return bool(
                page.evaluate(
                    """() => {
                        const path = window.location.pathname || "";
                        const hasAuthRoute = path.includes("/auth");
                        const hasLoginForm = Boolean(
                            document.querySelector('input[name="username"], input[type="password"], ha-auth-flow, ha-auth-form')
                        );
                        return hasAuthRoute || hasLoginForm;
                    }"""
                )
            )
        except Exception as exc:
            if attempt == 2 or "Execution context was destroyed" not in str(exc):
                raise
            page.wait_for_load_state("domcontentloaded")

    return False


def _access_token_script() -> str:
    return """() => {
        if (typeof window.getHomeAssistantToken === "function") {
            const injected = window.getHomeAssistantToken();
            if (injected) {
                return injected;
            }
        }

        try {
            const conn = window.hassConnection || window.parent?.hassConnection;
            const connectionToken = conn?.options?.auth?.accessToken;
            if (connectionToken) {
                return connectionToken;
            }
        } catch (_) {}

        try {
            const raw = localStorage.getItem("hassTokens");
            if (raw) {
                const parsed = JSON.parse(raw);
                if (parsed?.access_token) {
                    return parsed.access_token;
                }
            }
        } catch (_) {}

        try {
            const el = window.parent?.document?.querySelector("home-assistant");
            const appToken = el?.__hass?.auth?.data?.access_token || el?.hass?.auth?.data?.access_token;
            if (appToken) {
                return appToken;
            }
        } catch (_) {}

        return null;
    }"""


def _should_launch_headless(settings) -> bool:
    if not settings.headed:
        return True

    if platform.system() != "Linux":
        return False

    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return False

    warnings.warn(
        "Requested headed Playwright run without DISPLAY/WAYLAND_DISPLAY on Linux; falling back to headless mode.",
        RuntimeWarning,
        stacklevel=2,
    )
    return True


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
