"""Shared pytest configuration for the Whispeer test suite."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from whispeer.tests.runtime import build_test_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("whispeer")
    group.addoption(
        "--whispeer-base-url",
        action="store",
        dest="whispeer_base_url",
        help="Home Assistant base URL used by the unified Whispeer suite.",
    )
    group.addoption(
        "--whispeer-ws-url",
        action="store",
        dest="whispeer_ws_url",
        help="Explicit WebSocket URL. Defaults to <base-url>/api/websocket.",
    )
    group.addoption(
        "--whispeer-username",
        action="store",
        dest="whispeer_username",
        help="Username used for Home Assistant authentication.",
    )
    group.addoption(
        "--whispeer-password",
        action="store",
        dest="whispeer_password",
        help="Password used for Home Assistant authentication.",
    )
    group.addoption(
        "--whispeer-storage-state",
        action="store",
        dest="whispeer_storage_state",
        help="Path to the Playwright storage_state JSON file.",
    )
    group.addoption(
        "--whispeer-container-name",
        action="store",
        dest="whispeer_container_name",
        help="Optional container name for helper scripts and future orchestration.",
    )
    group.addoption(
        "--whispeer-container-host",
        action="store",
        dest="whispeer_container_host",
        help="Optional remote container host or IP used by helper scripts.",
    )
    group.addoption(
        "--whispeer-headed",
        action="store_const",
        const=True,
        default=None,
        dest="whispeer_headed",
        help="Run browser scenarios in headed mode.",
    )
    group.addoption(
        "--whispeer-headless",
        action="store_const",
        const=False,
        dest="whispeer_headed",
        help="Run browser scenarios in headless mode.",
    )
    group.addoption(
        "--whispeer-browser",
        action="store",
        dest="whispeer_browser",
        help="Browser name used by Playwright scenarios.",
    )
    group.addoption(
        "--whispeer-slowmo-ms",
        action="store",
        dest="whispeer_slowmo_ms",
        help="Optional Playwright slow motion delay in milliseconds for headed runs.",
    )
    group.addoption(
        "--whispeer-timeout-ms",
        action="store",
        dest="whispeer_timeout_ms",
        help="Default timeout in milliseconds for long-running test actions.",
    )


def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "backend: backend-level contract tests",
        "integration: Home Assistant websocket/API integration tests",
        "e2e: browser-driven end-to-end scenarios",
        "ble: Bluetooth-focused scenarios",
        "rf_fast: fast-learning RF scenarios",
        "slow: long-running scenarios",
    ):
        config.addinivalue_line("markers", marker)


@pytest.fixture(scope="session")
def whispeer_test_settings(pytestconfig: pytest.Config):
    options = {
        "whispeer_base_url": pytestconfig.getoption("whispeer_base_url"),
        "whispeer_ws_url": pytestconfig.getoption("whispeer_ws_url"),
        "whispeer_username": pytestconfig.getoption("whispeer_username"),
        "whispeer_password": pytestconfig.getoption("whispeer_password"),
        "whispeer_storage_state": pytestconfig.getoption("whispeer_storage_state"),
        "whispeer_container_name": pytestconfig.getoption("whispeer_container_name"),
        "whispeer_container_host": pytestconfig.getoption("whispeer_container_host"),
        "whispeer_headed": pytestconfig.getoption("whispeer_headed"),
        "whispeer_browser": pytestconfig.getoption("whispeer_browser"),
        "whispeer_slowmo_ms": pytestconfig.getoption("whispeer_slowmo_ms"),
        "whispeer_timeout_ms": pytestconfig.getoption("whispeer_timeout_ms"),
    }
    return build_test_settings(options=options, env=os.environ)


@pytest.fixture(scope="session")
def whispeer_storage_state_path(whispeer_test_settings):
    whispeer_test_settings.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    return whispeer_test_settings.storage_state_path


@pytest.fixture(scope="session")
def whispeer_playwright_api():
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="Install Playwright to run Whispeer integration and E2E tests.",
    )
    with sync_api.sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def whispeer_browser(whispeer_playwright_api, whispeer_test_settings):
    from whispeer.tests.browser_support import launch_browser

    browser = launch_browser(whispeer_playwright_api, whispeer_test_settings)
    yield browser
    browser.close()


@pytest.fixture()
def whispeer_authenticated_page(whispeer_browser, whispeer_test_settings):
    from whispeer.tests.browser_support import open_authenticated_page

    context, page = open_authenticated_page(whispeer_browser, whispeer_test_settings)
    yield page
    context.close()


@pytest.fixture()
def whispeer_panel_page(whispeer_browser, whispeer_test_settings):
    from whispeer.tests.browser_support import open_panel_page

    context, page = open_panel_page(whispeer_browser, whispeer_test_settings)
    yield page
    context.close()


@pytest.fixture()
def whispeer_test_harness(whispeer_authenticated_page, whispeer_test_settings):
    from whispeer.tests.browser_support import (
        assert_ws_success,
        call_ha_ws_command,
        ensure_test_mode_enabled,
    )

    page = whispeer_authenticated_page
    settings = whispeer_test_settings

    ensure_test_mode_enabled(page, settings)
    assert_ws_success(
        call_ha_ws_command(
            page,
            settings,
            {
                "type": "whispeer/test/reset",
                "clear_config": True,
                "clear_learning_sessions": True,
            },
        ),
        "Failed to reset the Whispeer test harness before the test.",
    )

    def _call(command_type: str, **payload):
        return assert_ws_success(
            call_ha_ws_command(
                page,
                settings,
                {"type": command_type, **payload},
            ),
            f"Whispeer websocket command '{command_type}' failed.",
        )

    yield _call

    assert_ws_success(
        call_ha_ws_command(
            page,
            settings,
            {
                "type": "whispeer/test/reset",
                "clear_config": True,
                "clear_learning_sessions": True,
            },
        ),
        "Failed to reset the Whispeer test harness after the test.",
    )

