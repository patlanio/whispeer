"""Shared pytest configuration for the Whispeer test suite."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_TRUTHY = {"1", "true", "yes", "on"}

PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from whispeer.tests.runtime import build_test_settings


@dataclass
class WhispeerRSpecSession:
    settings: object
    context: object
    page: object
    access_token: str
    panel: object
    other_devices: object
    call_ws: object
    created_devices: dict[str, dict] = field(default_factory=dict)


def _truthy(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in _TRUTHY


def _live_report_enabled(config: pytest.Config) -> bool:
    option_value = config.getoption("whispeer_live_report")
    if option_value is not None:
        return _truthy(option_value)
    return _truthy(os.environ.get("WHISPEER_LIVE_REPORT"))


def _preserve_state_enabled() -> bool:
    return _truthy(os.environ.get("WHISPEER_PRESERVE_STATE"))


def _report_title(item: pytest.Item) -> str:
    marker = item.get_closest_marker("whispeer_title")
    if marker and marker.args:
        return str(marker.args[0])
    return item.nodeid


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
    group.addoption(
        "--whispeer-live-report",
        action="store",
        dest="whispeer_live_report",
        help="Print RUN/PASS/FAIL lines as pytest advances through the suite.",
    )


def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "backend: backend-level contract tests",
        "integration: Home Assistant websocket/API integration tests",
        "e2e: browser-driven end-to-end scenarios",
        "ble: Bluetooth-focused scenarios",
        "rf_fast: fast-learning RF scenarios",
        "slow: long-running scenarios",
        "whispeer_title(title): human-friendly title for live pytest reporting",
        "whispeer_case(case_id): stable case id for range-based one-pass execution",
    ):
        config.addinivalue_line("markers", marker)


def _case_id(item: pytest.Item) -> str:
    marker = item.get_closest_marker("whispeer_case")
    if marker and marker.args:
        return str(marker.args[0])
    return item.nodeid


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    start_at = (os.environ.get("WHISPEER_E2E_START_AT") or "").strip()
    stop_after = (os.environ.get("WHISPEER_E2E_STOP_AFTER") or "").strip()
    if not start_at and not stop_after:
        return

    case_ids = [_case_id(item) for item in items]
    if start_at and start_at not in case_ids:
        raise pytest.UsageError(f"Unknown WHISPEER_E2E_START_AT case id: {start_at}")
    if stop_after and stop_after not in case_ids:
        raise pytest.UsageError(f"Unknown WHISPEER_E2E_STOP_AFTER case id: {stop_after}")

    selected: list[pytest.Item] = []
    started = not start_at
    for item in items:
        current_case_id = _case_id(item)
        if not started:
            if current_case_id != start_at:
                continue
            started = True
        selected.append(item)
        if stop_after and current_case_id == stop_after:
            break

    deselected = [item for item in items if item not in selected]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_runtest_setup(item: pytest.Item) -> None:
    if not _live_report_enabled(item.config):
        return
    reporter = item.config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"[ RUN ] {_report_title(item)}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    outcome = yield
    report = outcome.get_result()

    if not _live_report_enabled(item.config):
        return
    if report.when != "call":
        return

    reporter = item.config.pluginmanager.getplugin("terminalreporter")
    if reporter is None:
        return

    title = _report_title(item)
    if report.passed:
        reporter.write_line(f"[ PASS ] {title}")
    elif report.failed:
        reporter.write_line(f"[ FAIL ] {title}")
    elif report.skipped:
        reporter.write_line(f"[ SKIP ] {title}")


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


@pytest.fixture(scope="session")
def whispeer_rspec_session(whispeer_browser, whispeer_test_settings):
    from whispeer.tests.browser_support import (
        assert_ws_success,
        call_ha_ws_command,
        ensure_test_mode_enabled,
        get_access_token,
        open_authenticated_page,
    )
    from whispeer.tests.pages import HomeAssistantOtherDevicesPage, WhispeerPage

    context, page = open_authenticated_page(whispeer_browser, whispeer_test_settings)
    settings = whispeer_test_settings

    page.set_default_timeout(settings.timeout_ms)
    page.set_default_navigation_timeout(settings.timeout_ms)
    access_token = get_access_token(page, settings)
    ensure_test_mode_enabled(page, settings, access_token=access_token)
    context.set_extra_http_headers({"Authorization": f"Bearer {access_token}"})

    def _call(command_type: str, **payload):
        return assert_ws_success(
            call_ha_ws_command(
                page,
                settings,
                {"type": command_type, **payload},
                access_token=access_token,
            ),
            f"Whispeer websocket command '{command_type}' failed.",
        )

    preserve_state = _preserve_state_enabled()
    if not preserve_state:
        _call(
            "whispeer/test/reset",
            clear_config=True,
            clear_learning_sessions=True,
        )

    panel = WhispeerPage(page, settings)
    other_devices = HomeAssistantOtherDevicesPage(page, settings)

    yield WhispeerRSpecSession(
        settings=settings,
        context=context,
        page=page,
        access_token=access_token,
        panel=panel,
        other_devices=other_devices,
        call_ws=_call,
    )

    if not preserve_state:
        _call(
            "whispeer/test/reset",
            clear_config=True,
            clear_learning_sessions=True,
        )
    context.close()


@pytest.fixture()
def whispeer_test_harness(whispeer_rspec_session):
    from whispeer.tests.browser_support import (
        assert_ws_success,
        call_ha_ws_command,
        ensure_test_mode_enabled,
    )

    page = whispeer_rspec_session.page
    settings = whispeer_rspec_session.settings
    access_token = whispeer_rspec_session.access_token
    preserve_state = _preserve_state_enabled()

    ensure_test_mode_enabled(page, settings, access_token=access_token)
    if not preserve_state:
        assert_ws_success(
            call_ha_ws_command(
                page,
                settings,
                {
                    "type": "whispeer/test/reset",
                    "clear_config": True,
                    "clear_learning_sessions": True,
                },
                access_token=access_token,
            ),
            "Failed to reset the Whispeer test harness before the test.",
        )

    def _call(command_type: str, **payload):
        return assert_ws_success(
            call_ha_ws_command(
                page,
                settings,
                {"type": command_type, **payload},
                access_token=access_token,
            ),
            f"Whispeer websocket command '{command_type}' failed.",
        )

    yield _call

    if not preserve_state:
        assert_ws_success(
            call_ha_ws_command(
                page,
                settings,
                {
                    "type": "whispeer/test/reset",
                    "clear_config": True,
                    "clear_learning_sessions": True,
                },
                access_token=access_token,
            ),
            "Failed to reset the Whispeer test harness after the test.",
        )

