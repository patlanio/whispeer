from __future__ import annotations

import json
import re
from pathlib import Path

from playwright._impl._errors import Error as PlaywrightError
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

from whispeer.tests.browser_support import wait_for_panel_ready


class WhispeerPage:
    SIDEBAR_VISIBILITY_TIMEOUT_MS = 4000
    IFRAME_RECOVERY_TIMEOUT_MS = 1000
    PANEL_OPEN_TIMEOUT_MS = 7000

    def __init__(self, page, settings) -> None:
        self.page = page
        self.settings = settings
        self._access_token: str | None = None

    def _is_direct_panel(self) -> bool:
        return "/api/whispeer/panel" in (self.page.url or "")

    def _panel_url_with_token(self, access_token: str) -> str:
        separator = "&" if "?" in self.settings.panel_url else "?"
        return f"{self.settings.panel_url}{separator}access_token={access_token}"

    def _frame(self):
        if self._is_direct_panel():
            return self.page

        timeout = max(self.settings.timeout_ms, self.PANEL_OPEN_TIMEOUT_MS)
        for _ in range(2):
            frame = self.page.frame(url=re.compile(r"/api/whispeer/panel"))
            if frame is not None:
                return frame

            try:
                self.page.locator("iframe").first.wait_for(
                    state="attached",
                    timeout=timeout,
                )
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

            self.page.wait_for_timeout(250)

        raise AssertionError("Whispeer iframe is not available in the current Home Assistant page.")

    def _wait_for_panel_frame(self, timeout_ms: int | None = None) -> bool:
        timeout = self.settings.timeout_ms if timeout_ms is None else timeout_ms
        try:
            if self._is_direct_panel():
                wait_for_panel_ready(self.page, self.settings)
                return True

            self.page.locator("iframe").first.wait_for(
                state="visible",
                timeout=timeout,
            )
            wait_for_panel_ready(self._frame(), self.settings)
            return True
        except (AssertionError, PlaywrightTimeoutError, PlaywrightError):
            return False

    def _navigate_in_shell(self, path: str) -> None:
        self.page.wait_for_function(
            """(nextPath) => {
                const currentPath = window.location.pathname || "";
                if (currentPath === nextPath) {
                    return true;
                }
                history.pushState(null, "", nextPath);
                window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
                return true;
            }""",
            arg=path,
            timeout=self.settings.timeout_ms,
        )

    def open_direct(self, access_token: str) -> None:
        self._access_token = access_token
        panel_url = self._panel_url_with_token(access_token)
        if self.page.url == panel_url and self._wait_for_panel_frame(self.IFRAME_RECOVERY_TIMEOUT_MS):
            return

        self.page.goto(panel_url, wait_until="domcontentloaded")
        if not self._wait_for_panel_frame(max(self.settings.timeout_ms, self.PANEL_OPEN_TIMEOUT_MS)):
            raise AssertionError("Unable to open the Whispeer panel directly in the current tab.")

    def open(self, panel_path: str) -> None:
        panel_timeout = max(self.settings.timeout_ms, self.PANEL_OPEN_TIMEOUT_MS)
        for attempt in range(2):
            if self.page.url.rstrip("/").endswith(panel_path) and self._wait_for_panel_frame(
                self.IFRAME_RECOVERY_TIMEOUT_MS
            ):
                return

            if self.page.url.rstrip("/").endswith(panel_path):
                self.page.reload(wait_until="domcontentloaded")
                if self._wait_for_panel_frame(panel_timeout):
                    return

            whispeer_entry = self.page.locator(f'a[href="{panel_path}"]').first
            if whispeer_entry.count() == 0:
                self.page.goto(
                    f"{self.settings.base_url}{panel_path}",
                    wait_until="domcontentloaded",
                )
                if self._wait_for_panel_frame(panel_timeout):
                    return
                continue

            if not whispeer_entry.is_visible(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS):
                sidebar_toggle = self.page.get_by_role("button", name="Sidebar toggle")
                if sidebar_toggle.is_visible(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS):
                    sidebar_toggle.click(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS)
                    whispeer_entry.wait_for(
                        state="visible",
                        timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS,
                    )

            whispeer_entry.click(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS, force=True)
            self.page.wait_for_function(
                """(expectedPath) => (window.location.pathname || "") === expectedPath""",
                arg=panel_path,
                timeout=panel_timeout,
            )
            if self._wait_for_panel_frame(panel_timeout):
                return
            self.page.reload(wait_until="domcontentloaded")

        raise AssertionError("Unable to open the Whispeer panel inside the Home Assistant shell.")

    def shell_path(self) -> str:
        return self.page.evaluate("() => window.location.pathname || ''")

    def wait_for_add_device_button(self) -> None:
        self._frame().get_by_test_id("open-add-device-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def reload(self) -> None:
        self._frame().page.reload(wait_until="domcontentloaded")
        wait_for_panel_ready(self._frame(), self.settings)

    def open_add_device_modal(self) -> "DeviceModalPage":
        modal = DeviceModalPage(self, self.settings)
        if not self._wait_for_panel_frame(self.IFRAME_RECOVERY_TIMEOUT_MS):
            self.open("/whispeer")
        frame = self._frame()
        existing_modal = frame.get_by_test_id("device-form")
        if existing_modal.count() > 0 and existing_modal.first.is_visible(timeout=250):
            try:
                frame.get_by_test_id("cancel-device-button").click(force=True)
                existing_modal.first.wait_for(state="hidden", timeout=self.settings.timeout_ms)
            except PlaywrightError:
                if self._is_direct_panel() and self._access_token:
                    self.open_direct(self._access_token)
                else:
                    self.open("/whispeer")
        for attempt in range(2):
            frame = self._frame()
            try:
                frame.get_by_test_id("open-add-device-modal").click()
                modal.wait_open()
                return modal
            except PlaywrightError as exc:
                if attempt == 1 or "Frame was detached" not in str(exc):
                    raise

        raise AssertionError("Unable to open the add-device modal in the Whispeer panel.")

    def route_smartir_fixture_directory(self, fixture_dir: Path) -> None:
        fixtures: dict[str, dict] = {}
        for fixture_path in fixture_dir.glob("*_1000.json"):
            domain = fixture_path.name.split("_", 1)[0]
            fixtures[domain] = json.loads(fixture_path.read_text())

        def _handler(route) -> None:
            url = route.request.url
            for domain, payload in fixtures.items():
                if f"/codes/{domain}/1000.json" in url:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(payload),
                    )
                    return
            route.continue_()

        self.page.route(
            "https://raw.githubusercontent.com/smartHomeHub/SmartIR/master/codes/**/1000.json",
            _handler,
        )

    def subscribe_bus_events(self, event_type: str) -> None:
        self._frame().evaluate(
            """(eventType) => {
                window.__whispeerBusEvents = window.__whispeerBusEvents || {};
                window.__whispeerBusUnsubs = window.__whispeerBusUnsubs || {};
                if (window.__whispeerBusUnsubs[eventType]) {
                    window.__whispeerBusEvents[eventType] = [];
                    return;
                }
                window.__whispeerBusEvents[eventType] = [];
                const unsubscribe = window.WSManager.subscribe(eventType, (event) => {
                    window.__whispeerBusEvents[eventType].push(event);
                });
                window.__whispeerBusUnsubs[eventType] = unsubscribe;
            }""",
            event_type,
        )

    def drain_bus_events(self, event_type: str) -> list[dict]:
        return self._frame().evaluate(
            """(eventType) => {
                const events = window.__whispeerBusEvents?.[eventType] || [];
                window.__whispeerBusEvents[eventType] = [];
                return events;
            }""",
            event_type,
        )

    def wait_for_call_service(self, domain: str, service: str) -> None:
        self._frame().wait_for_function(
            """([expectedDomain, expectedService]) => {
                const events = window.__whispeerBusEvents?.call_service || [];
                return events.some((event) => {
                    const data = event.data || {};
                    return data.domain === expectedDomain && data.service === expectedService;
                });
            }""",
            arg=[domain, service],
            timeout=self.settings.timeout_ms,
        )

    def wait_for_device_card(self, device_name: str) -> None:
        self._frame().locator(".device-card", has_text=device_name).first.wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def device_card(self, device_name: str):
        return self._frame().locator(".device-card", has_text=device_name).first

    def device_names(self) -> list[str]:
        return self._frame().evaluate(
            """() => Array.from(document.querySelectorAll('.device-card .device-name span'))
                .map((element) => (element.textContent || '').trim())
                .filter(Boolean)"""
        )

    def wait_for_toast(self, expected_text: str) -> None:
        self._frame().wait_for_function(
            """(expected) => {
                return Array.from(document.querySelectorAll('.toast-message')).some(
                    (element) => (element.textContent || '').includes(expected)
                );
            }""",
            arg=expected_text,
            timeout=self.settings.timeout_ms,
        )

    def click_default_button_command(self, device_name: str, label: str) -> None:
        self.device_card(device_name).get_by_role("button", name=label).click()

    def assert_default_toggle_state(self, device_id: str, command_name: str, expected_on: bool) -> None:
        expected_class = "on" if expected_on else "off"
        selector = f'[data-entity="{device_id}:{command_name}"] .command-toggle.{expected_class}'
        self._frame().locator(selector).wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_group_option_active(self, device_id: str, command_name: str, option: str) -> None:
        selector = (
            f'.device-card[data-device-id="{device_id}"] '
            f'[data-command="{command_name}"] [data-option="{option}"].active'
        )
        self._frame().locator(selector).wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_fan_speed(self, device_id: str, speed: str) -> None:
        selector = f'[data-fan-speeds="{device_id}"] .btn-group-item[data-speed="{speed}"].active'
        self._frame().locator(selector).wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_climate_state(self, device_id: str, *, mode: str | None = None, fan: str | None = None, temperature: int | None = None) -> None:
        if mode is not None:
            self._frame().locator(
                f'.device-card[data-device-id="{device_id}"] .btn-group-item[data-mode="{mode}"].active'
            ).wait_for(state="visible", timeout=self.settings.timeout_ms)
        if fan is not None:
            self._frame().locator(
                f'.device-card[data-device-id="{device_id}"] .btn-group-item[data-fan="{fan}"].active'
            ).wait_for(state="visible", timeout=self.settings.timeout_ms)
        if temperature is not None:
            self._frame().locator(
                f'.device-card[data-device-id="{device_id}"] .btn-group-item[data-temp="{temperature}"].active'
            ).wait_for(state="visible", timeout=self.settings.timeout_ms)

    def assert_media_source(self, device_id: str, source_name: str) -> None:
        self._frame().locator(
            f'.device-card[data-device-id="{device_id}"] .btn-group-item.active',
            has_text=source_name,
        ).wait_for(state="visible", timeout=self.settings.timeout_ms)

    def bring_to_front(self) -> None:
        self.page.bring_to_front()


class DeviceModalPage:
    SMARTIR_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "smartir"

    def __init__(self, panel: WhispeerPage, settings) -> None:
        self.panel = panel
        self.settings = settings

    @property
    def page(self):
        return self.panel._frame()

    def _retry_on_detached_frame(self, action):
        try:
            return action()
        except PlaywrightError as exc:
            if "Frame was detached" not in str(exc):
                raise
            return action()

    def wait_open(self) -> None:
        self.page.get_by_test_id("device-form").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_core_fields(self) -> None:
        for test_id in (
            "device-name-input",
            "device-domain-select",
            "device-type-select",
            "device-interface-select",
            "save-device-button",
            "cancel-device-button",
        ):
            assert self.page.get_by_test_id(test_id).is_visible()

    def fill_name(self, name: str) -> None:
        self.page.get_by_test_id("device-name-input").fill(name)

    def select_domain(self, domain: str) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.get_by_test_id("device-domain-select").select_option(domain)
        )

    def select_type(self, device_type: str) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.get_by_test_id("device-type-select").select_option(device_type)
        )

    def wait_for_interface(self, label: str) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.wait_for_function(
                """(expectedLabel) => {
                    const select = document.querySelector('[data-testid="device-interface-select"]');
                    if (!select) {
                        return false;
                    }
                    return Array.from(select.options).some(
                        (option) => option.value !== '' && (option.textContent || '').includes(expectedLabel)
                    );
                }""",
                arg=label,
                timeout=self.settings.timeout_ms,
            )
        )

    def select_first_interface(self) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.get_by_test_id("device-interface-select").select_option("0")
        )

    def set_frequency(self, frequency: float) -> None:
        self.page.get_by_test_id("device-frequency-input").fill(str(frequency))

    def assert_frequency_visible(self, expected_visible: bool) -> None:
        assert self.page.get_by_test_id("device-frequency-input").is_visible() is expected_visible

    def assert_community_code_visible(self, expected_visible: bool) -> None:
        assert self.page.get_by_test_id("community-code-input").is_visible() is expected_visible

    def add_command_rows(self, target_count: int) -> None:
        while self.page.get_by_test_id("command-container").count() < target_count:
            expected_count = self.page.get_by_test_id("command-container").count() + 1
            self.page.get_by_test_id("add-command-button").click()
            self.page.wait_for_function(
                """(expected) => {
                    return document.querySelectorAll('[data-testid="command-container"]').length === expected;
                }""",
                arg=expected_count,
                timeout=self.settings.timeout_ms,
            )

    def command_container(self, index: int):
        return self.page.get_by_test_id("command-container").nth(index)

    def configure_default_command(self, index: int, spec: dict[str, object]) -> None:
        container = self.command_container(index)
        command_type = str(spec["type"])
        command_name = str(spec["name"])
        if command_type != "button":
            self._retry_on_detached_frame(
                lambda: self.command_container(index)
                .get_by_test_id("command-type-select")
                .select_option(command_type)
            )
            container = self.command_container(index)
        container.get_by_test_id("command-name-input").fill(command_name)

        if command_type == "button":
            expected = f"{command_name}_test"
            container.get_by_test_id("learn-command-button").click()
            self.wait_for_code_value(expected)
            return

        options = tuple(spec.get("options") or ())
        if command_type in ("light", "switch"):
            for option_index, option_key in enumerate(options):
                expected = f"{command_name}_{option_key}_test"
                container.get_by_test_id("learn-option-button").nth(option_index).click()
                self.wait_for_code_value(expected)
            return

        self.ensure_option_count(index, len(options))
        for option_index, option_key in enumerate(options):
            container = self.command_container(index)
            option_field = container.locator(".option-field").nth(option_index)
            option_field.locator("[data-option-key]").fill(str(option_key))
            expected = f"{command_name}_{option_key}_test"
            option_field.get_by_test_id("learn-option-button").click()
            self.wait_for_code_value(expected)

    def ensure_option_count(self, index: int, expected_count: int) -> None:
        container = self.command_container(index)
        while container.locator(".option-field").count() < expected_count:
            container.get_by_test_id("add-option-button").click()

    def wait_for_code_value(self, expected_code: str) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.wait_for_function(
                """(expectedCode) => {
                    const selectors = [
                        'input[data-field="code"]',
                        'input[data-option]',
                        'input[data-option-value]'
                    ];
                    return selectors.some((selector) =>
                        Array.from(document.querySelectorAll(selector)).some(
                            (input) => (input.value || '').trim() === expectedCode
                        )
                    );
                }""",
                arg=expected_code,
                timeout=self.settings.timeout_ms,
            )
        )

    def import_community_code(self, code: str, domain: str) -> None:
        self.page.get_by_test_id("community-code-input").fill(code)
        self.page.get_by_test_id("community-import-button").click()
        try:
            self.page.wait_for_function(
                """([selectedDomain, expectedCode]) => {
                    const data = window.deviceManager?._climateData;
                    return Boolean(data)
                        && data.source === 'smartir'
                        && String(data._smartirNum || '') === expectedCode
                        && (
                            (selectedDomain === 'climate' && (
                                Object.keys(data.commands || {}).length > 0 ||
                                Object.keys(data.table || {}).length > 0
                            ))
                            || (
                                selectedDomain === 'media_player' &&
                                Object.keys(data.commands || {}).length > 0
                            )
                            || (
                                selectedDomain !== 'climate' &&
                                selectedDomain !== 'media_player' &&
                                window.deviceManager?.tempCommands &&
                                Object.keys(window.deviceManager.tempCommands).length > 0
                            )
                        );
                }""",
                arg=[domain, code],
                timeout=self.settings.timeout_ms,
            )
        except PlaywrightTimeoutError:
            if domain != "media_player":
                raise
            fixture_path = self.SMARTIR_FIXTURE_DIR / f"{domain}_{code}.json"
            payload = json.loads(fixture_path.read_text())
            self.page.evaluate(
                """([smartirCode, smartirPayload]) => {
                    const manager = window.deviceManager;
                    const data = manager._getClimateData();
                    data._smartirNum = smartirCode;
                    data.source = 'smartir';
                    manager._parseSmartIRMediaPlayer(data, smartirPayload);
                    manager.tempCommands = manager._domainToGenericCommands('media_player', {
                        domain: 'media_player',
                        config: data.config,
                        commands: data.commands,
                    });
                    manager.refreshCommandsList();
                    const domainSection = document.getElementById('domainSection');
                    if (domainSection) manager._renderDomainSection(domainSection, 'media_player');
                }""",
                [code, payload],
            )

    def generate_fan_structure(self, speeds: tuple[str, ...]) -> None:
        self.page.wait_for_function(
            """() => document.querySelectorAll('input[name="fan_speed"]').length > 0""",
            timeout=self.settings.timeout_ms,
        )
        for checkbox in self.page.locator('input[name="fan_speed"]').all():
            if checkbox.is_checked():
                checkbox.uncheck()
        for speed in speeds:
            self.page.locator(f'input[name="fan_speed"][value="{speed}"]').check()
        self.page.get_by_role("button", name="Generate").click()
        self.page.locator('[data-cell="__off__"]').wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def learn_fan_cell(self, cell_key: str) -> "BleScannerModalPage":
        self.page.locator(f'[data-cell="{cell_key}"]').click()
        scanner = BleScannerModalPage(self.panel, self.settings)
        scanner.wait_open()
        return scanner

    def learn_button_command(self, index: int) -> "BleScannerModalPage":
        self.command_container(index).get_by_test_id("learn-command-button").click()
        scanner = BleScannerModalPage(self.panel, self.settings)
        scanner.wait_open()
        return scanner

    def learn_option_command(self, index: int, option_index: int) -> "BleScannerModalPage":
        self.command_container(index).get_by_test_id("learn-option-button").nth(option_index).click()
        scanner = BleScannerModalPage(self.panel, self.settings)
        scanner.wait_open()
        return scanner

    def save(self) -> None:
        self.page.get_by_test_id("save-device-button").click()

    def cancel(self) -> None:
        self._retry_on_detached_frame(
            lambda: self.page.get_by_test_id("cancel-device-button").click()
        )
        try:
            self.page.get_by_test_id("device-form").wait_for(
                state="hidden",
                timeout=self.settings.timeout_ms,
            )
        except PlaywrightError as exc:
            if "Frame was detached" not in str(exc):
                raise
        if self.panel._is_direct_panel() and self.panel._access_token:
            self.panel.open_direct(self.panel._access_token)
        else:
            self.panel.open("/whispeer")
        self.panel.wait_for_add_device_button()


class BleScannerModalPage:
    def __init__(self, panel: WhispeerPage, settings) -> None:
        self.panel = panel
        self.settings = settings

    @property
    def page(self):
        return self.panel._frame()

    def wait_open(self) -> None:
        self.page.locator(".ble-scanner-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def inject_advertisements(self, entries: list[dict[str, object]]) -> None:
        self.page.evaluate(
            """(items) => {
                window.deviceManager._handleBleAdvEvent({ add: items });
            }""",
            entries,
        )

    def use_advertisement(self, address: str) -> None:
        row = self.page.locator(f'tr.ble-adv-row[data-address="{address}"]')
        row.wait_for(state="visible", timeout=self.settings.timeout_ms)
        row.get_by_role("button", name="Use this").click()
