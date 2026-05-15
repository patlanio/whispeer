from __future__ import annotations

import json
import re
from pathlib import Path

from playwright._impl._errors import Error as PlaywrightError
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

from whispeer.tests.browser_support import wait_for_authenticated_shell, wait_for_panel_ready


class WhispeerPage:
    SIDEBAR_VISIBILITY_TIMEOUT_MS = 4000
    IFRAME_RECOVERY_TIMEOUT_MS = 1000
    PANEL_OPEN_TIMEOUT_MS = 10000

    def __init__(self, page, settings) -> None:
        self.page = page
        self.settings = settings

    def _first_existing_locator(self, *locators):
        for locator in locators:
            if locator.count() > 0:
                return locator.first
        return None

    def _sidebar_toggle(self):
        return self._first_existing_locator(
            self.page.get_by_role("button", name=re.compile(r"sidebar|menu", re.IGNORECASE)),
            self.page.locator("ha-menu-button"),
        )

    def _sidebar_entry(self, panel_path: str, *labels: str):
        candidates = [self.page.locator(f'a[href="{panel_path}"]')]
        for label in labels:
            pattern = re.compile(rf"^{re.escape(label)}$", re.IGNORECASE)
            candidates.append(self.page.get_by_role("link", name=pattern))
        return self._first_existing_locator(*candidates)

    def _ensure_sidebar_item_visible(self, panel_path: str, *labels: str):
        anchor = self.page.locator(f'a[href="{panel_path}"]').first
        try:
            anchor.wait_for(
                state="attached",
                timeout=max(self.SIDEBAR_VISIBILITY_TIMEOUT_MS, self.PANEL_OPEN_TIMEOUT_MS),
            )
        except PlaywrightError:
            anchor = None

        entry = anchor or self._sidebar_entry(panel_path, *labels)

        if entry is None:
            raise AssertionError(f"Unable to find the Home Assistant sidebar entry for '{panel_path}'.")

        try:
            if entry.is_visible(timeout=250):
                return entry
        except PlaywrightError:
            pass

        toggle = self._sidebar_toggle()
        if toggle is not None:
            try:
                toggle.click(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS)
            except PlaywrightError:
                pass

        entry.wait_for(state="visible", timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS)
        return entry

    def _frame(self):
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
            self.page.locator("iframe").first.wait_for(
                state="visible",
                timeout=timeout,
            )
            wait_for_panel_ready(self._frame(), self.settings)
            return True
        except (AssertionError, PlaywrightTimeoutError, PlaywrightError):
            return False

    def wait_for_sidebar_entry(self, label: str = "Whispeer") -> None:
        self._ensure_sidebar_item_visible("/whispeer", label)

    def wait_for_shell_title(self, expected_title: str) -> None:
        self.page.wait_for_function(
            """(expected) => {
                const targetClasses = new Set(["main-title", "toolbar-title"]);
                const visit = (root) => {
                    if (!root) {
                        return false;
                    }
                    const elements = root.querySelectorAll ? root.querySelectorAll("*") : [];
                    for (const element of elements) {
                        if (element.shadowRoot && visit(element.shadowRoot)) {
                            return true;
                        }
                        if (!element.classList) {
                            continue;
                        }
                        const hasTargetClass = [...targetClasses].some((cls) => element.classList.contains(cls));
                        if (!hasTargetClass) {
                            continue;
                        }
                        if ((element.textContent || "").trim() === expected) {
                            return true;
                        }
                    }
                    return false;
                };

                return visit(document) || (document.title || "") === expected;
            }""",
            arg=expected_title,
            timeout=max(self.settings.timeout_ms, self.PANEL_OPEN_TIMEOUT_MS),
        )

    def open(self, panel_path: str) -> None:
        panel_timeout = max(self.settings.timeout_ms, self.PANEL_OPEN_TIMEOUT_MS)
        panel_url = f"{self.settings.base_url.rstrip('/')}{panel_path}"
        for attempt in range(2):
            if not (self.page.url or "").rstrip("/").endswith(panel_path):
                self.page.goto(self.settings.base_url, wait_until="domcontentloaded")

            wait_for_authenticated_shell(self.page, self.settings)

            if self.page.url.rstrip("/").endswith(panel_path) and self._wait_for_panel_frame(
                self.IFRAME_RECOVERY_TIMEOUT_MS
            ):
                return

            if self.page.url.rstrip("/").endswith(panel_path):
                self.page.reload(wait_until="domcontentloaded")
                if self._wait_for_panel_frame(panel_timeout):
                    return

            whispeer_entry = self._ensure_sidebar_item_visible(panel_path, "Whispeer")
            whispeer_entry.click(timeout=self.SIDEBAR_VISIBILITY_TIMEOUT_MS, force=True)
            try:
                self.page.wait_for_function(
                    """(expectedPath) => {
                        const currentPath = window.location.pathname || "";
                        return currentPath === expectedPath || currentPath.endsWith(expectedPath);
                    }""",
                    arg=panel_path,
                    timeout=panel_timeout,
                )
            except PlaywrightTimeoutError:
                pass
            if self._wait_for_panel_frame(panel_timeout):
                return

            self.page.goto(panel_url, wait_until="domcontentloaded")
            if self._wait_for_panel_frame(panel_timeout):
                return

            self.page.goto(self.settings.base_url, wait_until="domcontentloaded")

        raise AssertionError("Unable to open the Whispeer panel inside the Home Assistant shell.")

    def shell_path(self) -> str:
        return self.page.evaluate("() => window.location.pathname || ''")

    def wait_for_add_device_button(self) -> None:
        self._frame().get_by_test_id("open-add-device-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_panel_header_controls(self) -> None:
        frame = self._frame()
        frame.locator(".brand-title").wait_for(state="visible", timeout=self.settings.timeout_ms)
        frame.locator(".brand-logo").wait_for(state="visible", timeout=self.settings.timeout_ms)
        frame.get_by_test_id("open-settings-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )
        frame.get_by_test_id("open-add-device-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_empty_state(self, title: str, message: str) -> None:
        frame = self._frame()
        frame.locator(".empty-state", has_text=title).wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )
        frame.locator(".empty-state", has_text=message).wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )
        frame.get_by_test_id("add-device-card").wait_for(
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

    def open_settings_modal(self) -> "AdvancedModalPage":
        modal = AdvancedModalPage(self, self.settings)
        frame = self._frame()
        frame.get_by_test_id("open-settings-modal").click()
        modal.wait_open()
        return modal

    def open_device_modal(self, device_name: str) -> "DeviceModalPage":
        modal = DeviceModalPage(self, self.settings)
        for attempt in range(2):
            try:
                self.device_card(device_name).locator(".device-type-badge").click()
                modal.wait_open()
                return modal
            except PlaywrightError as exc:
                if attempt == 1 or "Frame was detached" not in str(exc):
                    raise
        raise AssertionError(f"Unable to open the edit modal for '{device_name}'.")

    def route_smartir_fixture_directory(self, fixture_dir: Path) -> None:
        fixtures: dict[str, dict] = {}
        for fixture_path in fixture_dir.glob("*_1000.json"):
            domain = fixture_path.stem.rsplit("_", 1)[0]
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

    def reload_stored_codes(self) -> None:
        self._frame().evaluate(
            """async () => {
                await window.deviceManager.loadAndRenderStoredCodes();
            }"""
        )

    def assert_stored_codes_hidden(self) -> None:
        hidden = self._frame().evaluate(
            """() => {
                return !document.querySelector('.stored-codes-divider')
                    && !document.querySelector('.stored-codes-title')
                    && !document.querySelector('.no-stored-codes')
                    && document.querySelectorAll('.stored-device-card').length === 0;
            }"""
        )
        assert hidden is True

    def stored_code_groups(self) -> dict[str, list[str]]:
        return self._frame().evaluate(
            """() => {
                const groups = {};
                document.querySelectorAll('.stored-device-card').forEach((card) => {
                    const deviceName = (card.querySelector('.device-name')?.textContent || '').trim();
                    if (!deviceName) {
                        return;
                    }
                    groups[deviceName] = Array.from(card.querySelectorAll('.stored-cmd-btn'))
                        .map((button) => {
                            const textOnly = Array.from(button.childNodes)
                                .filter((node) => node.nodeType === Node.TEXT_NODE)
                                .map((node) => node.textContent || '')
                                .join('')
                                .trim();
                            return textOnly || (button.textContent || '').trim();
                        })
                        .filter(Boolean);
                });
                return groups;
            }"""
        )

    def click_all_card_controls(self, device_name: str) -> int:
        return self._frame().evaluate(
            """async ({ deviceName, delayMs }) => {
                const findCard = () => Array.from(document.querySelectorAll('.device-card'))
                    .find((card) => {
                        if (card.classList.contains('stored-device-card')) {
                            return false;
                        }
                        const name = (card.querySelector('.device-name')?.textContent || '').trim();
                        return name === deviceName;
                    });

                const buildRelativePath = (element, root) => {
                    const parts = [];
                    let current = element;

                    while (current && current !== root) {
                        const parent = current.parentElement;
                        if (!parent) {
                            return null;
                        }
                        const index = Array.from(parent.children).indexOf(current) + 1;
                        parts.unshift(`${current.tagName.toLowerCase()}:nth-child(${index})`);
                        current = parent;
                    }

                    return parts.join(' > ');
                };

                const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const initialCard = findCard();
                if (!initialCard) {
                    return 0;
                }

                const selectors = Array.from(
                    initialCard.querySelectorAll('.device-commands button, .device-commands .command-toggle')
                )
                    .map((element) => buildRelativePath(element, initialCard))
                    .filter(Boolean);

                for (const selector of selectors) {
                    const currentCard = findCard();
                    if (!currentCard) {
                        continue;
                    }
                    const target = currentCard.querySelector(selector);
                    if (!(target instanceof HTMLElement)) {
                        continue;
                    }
                    target.click();
                    await sleep(delayMs);
                }

                await sleep(300);
                return selectors.length;
            }""",
            {"deviceName": device_name, "delayMs": 150},
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

    def wait_for_frequency_value(self, expected_frequency: float) -> None:
        self.page.wait_for_function(
            """(expectedFrequency) => {
                const input = document.querySelector('[data-testid="device-frequency-input"]');
                if (!input) {
                    return false;
                }
                const parsed = Number.parseFloat(input.value || '');
                return Number.isFinite(parsed) && Math.abs(parsed - expectedFrequency) < 0.01;
            }""",
            arg=expected_frequency,
            timeout=self.settings.timeout_ms,
        )

    def assert_frequency_visible(self, expected_visible: bool) -> None:
        assert self.page.get_by_test_id("device-frequency-input").is_visible() is expected_visible

    def assert_community_code_visible(self, expected_visible: bool) -> None:
        assert self.page.get_by_test_id("community-code-input").is_visible() is expected_visible

    def _set_checkbox_values(self, field_name: str, selected_values: tuple[str, ...]) -> None:
        selected = set(selected_values)
        checkboxes = self.page.locator(f'input[name="{field_name}"]')
        for index in range(checkboxes.count()):
            checkbox = checkboxes.nth(index)
            value = checkbox.get_attribute("value") or ""
            if value in selected:
                if not checkbox.is_checked():
                    checkbox.check()
                continue
            if checkbox.is_checked():
                checkbox.uncheck()

    def set_climate_temperature_list(self, temperatures: tuple[int, ...]) -> None:
        self.page.locator("#climateTempList").fill(
            ", ".join(str(temperature) for temperature in temperatures)
        )

    def set_climate_modes(self, modes: tuple[str, ...]) -> None:
        self._set_checkbox_values("climate_mode", modes)

    def set_climate_fan_modes(self, fan_modes: tuple[str, ...]) -> None:
        self._set_checkbox_values("climate_fan", fan_modes)

    def generate_climate_table(self) -> None:
        self.page.get_by_role("button", name="Generate table").click()
        self.page.locator("#climateTableSection .climate-table").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def assert_climate_table(
        self,
        *,
        modes: tuple[str, ...],
        fan_modes: tuple[str, ...],
        temperatures: tuple[int, ...],
    ) -> None:
        self.page.wait_for_function(
            """([expectedModes, expectedFanModes, expectedTemps]) => {
                const modeHeaders = Array.from(document.querySelectorAll('th.climate-mode-header'))
                    .map((element) => (element.textContent || '').trim());
                const expectedFanHeaders = expectedModes.flatMap(() => expectedFanModes);
                const fanHeaders = Array.from(document.querySelectorAll('th.climate-fan-header'))
                    .map((element) => (element.textContent || '').trim());
                const tempHeaders = Array.from(document.querySelectorAll('th.climate-temp-header'))
                    .map((element) => Number.parseInt((element.textContent || '').replace(/\D+/g, ''), 10));
                const cellCount = document.querySelectorAll('td.climate-cell[data-cell]').length;
                return JSON.stringify(modeHeaders) === JSON.stringify(expectedModes)
                    && JSON.stringify(fanHeaders) === JSON.stringify(expectedFanHeaders)
                    && JSON.stringify(tempHeaders) === JSON.stringify(expectedTemps)
                    && cellCount === expectedModes.length * expectedFanModes.length * expectedTemps.length;
            }""",
            arg=[list(modes), list(fan_modes), list(temperatures)],
            timeout=self.settings.timeout_ms,
        )

    def start_climate_fast_learn(
        self,
        *,
        mode: str,
        fan_mode: str,
        expected_codes_by_temperature: dict[int, str],
    ) -> None:
        self.page.locator(
            f'button[title="Fast learn {mode} / {fan_mode}"]'
        ).click()
        self.page.wait_for_function(
            """([expectedMode, expectedFanMode, expectedCodes]) => {
                const table = window.deviceManager?._climateData?.table || {};
                const fanTable = (table[expectedMode] || {})[expectedFanMode] || {};
                return Object.entries(expectedCodes).every(([temp, code]) => fanTable[String(temp)] === code);
            }""",
            arg=[mode, fan_mode, {str(temp): code for temp, code in expected_codes_by_temperature.items()}],
            timeout=self.settings.timeout_ms,
        )

    def learn_climate_cell(self, *, mode: str, fan_mode: str, temperature: int, expected_code: str) -> None:
        self.page.locator(f'[data-cell="{mode}__{fan_mode}__{temperature}"]').click()
        self.page.wait_for_function(
            """([expectedMode, expectedFanMode, expectedTemp, expectedCode]) => {
                const table = window.deviceManager?._climateData?.table || {};
                return (((table[expectedMode] || {})[expectedFanMode] || {})[String(expectedTemp)] || '') === expectedCode;
            }""",
            arg=[mode, fan_mode, temperature, expected_code],
            timeout=self.settings.timeout_ms,
        )

    def learn_climate_off(self, expected_code: str) -> None:
        self.page.locator('[data-cell="__off__"]').click()
        self.page.wait_for_function(
            """(expectedCode) => {
                const commands = window.deviceManager?._climateData?.commands || {};
                return (commands.off || '') === expectedCode;
            }""",
            arg=expected_code,
            timeout=self.settings.timeout_ms,
        )

    def assert_climate_mode_toggle(self, expected_label: str) -> None:
        self.page.wait_for_function(
            """(expectedLabel) => {
                const toggle = document.querySelector('.climate-mode-toggle');
                return Boolean(toggle) && ((toggle.textContent || '').trim() === expectedLabel);
            }""",
            arg=expected_label,
            timeout=self.settings.timeout_ms,
        )

    def toggle_climate_mode(self) -> None:
        self.page.locator('.climate-mode-toggle').click()

    def click_climate_cell(self, *, mode: str, fan_mode: str, temperature: int) -> None:
        self.page.locator(f'[data-cell="{mode}__{fan_mode}__{temperature}"]').click()

    def add_command_rows(self, target_count: int) -> None:
        while self.page.get_by_test_id("command-container").count() < target_count:
            expected_count = self.page.get_by_test_id("command-container").count() + 1
            self._retry_on_detached_frame(
                lambda: self.page.get_by_test_id("add-command-button").click()
            )
            self._retry_on_detached_frame(
                lambda: self.page.wait_for_function(
                    """(expected) => {
                        return document.querySelectorAll('[data-testid="command-container"]').length >= expected;
                    }""",
                    arg=expected_count,
                    timeout=self.settings.timeout_ms,
                )
            )

    def command_container(self, index: int):
        return self.page.get_by_test_id("command-container").nth(index)

    def set_command_name(self, index: int, name: str) -> None:
        self.command_container(index).get_by_test_id("command-name-input").fill(name)

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

    def start_fast_learn_once(self, expected_code: str) -> None:
        self.page.get_by_test_id("fast-learn-button").click()
        self.page.get_by_test_id("fast-learn-stop-button").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )
        self.page.get_by_test_id("fast-learn-stop-button").click()
        self.wait_for_code_value(expected_code)
        self.page.wait_for_function(
            """() => {
                const button = document.getElementById('fastLearnBtn');
                const stop = document.getElementById('fastLearnStopBtn');
                if (!button || !stop) {
                    return false;
                }
                return !button.disabled
                    && (button.textContent || '').includes('Fast Learn')
                    && window.getComputedStyle(stop).display === 'none';
            }""",
            timeout=self.settings.timeout_ms,
        )

    def import_community_code(self, code: str, domain: str) -> None:
        self.page.get_by_test_id("community-code-input").fill(code)
        self.page.get_by_test_id("community-import-button").click()
        self.page.wait_for_function(
            """([selectedDomain, expectedCode]) => {
                const manager = window.deviceManager;
                const data = manager?._climateData;
                if (!data || data.source !== 'smartir' || String(data._smartirNum || '') !== expectedCode) {
                    return false;
                }
                if (selectedDomain === 'climate') {
                    return Object.keys(data.table || {}).length > 0;
                }
                if (selectedDomain === 'media_player') {
                    return Object.keys(data.commands || {}).length > 0
                        && Boolean(document.getElementById('mpTableSection'));
                }
                if (selectedDomain === 'fan') {
                    return Object.keys(data.commands || {}).length > 0
                        && Boolean(document.getElementById('fanTableSection'));
                }
                if (selectedDomain === 'light') {
                    return Object.keys(data.commands || {}).length > 0
                        && Boolean(document.getElementById('lightTableSection'));
                }
                return Boolean(manager?.tempCommands)
                    && Object.keys(manager.tempCommands).length > 0;
            }""",
            arg=[domain, code],
            timeout=self.settings.timeout_ms,
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

    def click_all_test_buttons(self) -> int:
        buttons = self.page.locator(".command-inline-btn.test")
        count = buttons.count()
        for index in range(count):
            buttons.nth(index).click()
            self.page.wait_for_timeout(50)
        return count

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


class AdvancedModalPage:
    def __init__(self, panel: WhispeerPage, settings) -> None:
        self.panel = panel
        self.settings = settings

    @property
    def page(self):
        return self.panel._frame()

    def wait_open(self) -> None:
        self.page.locator(".settings-modal").wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def wait_closed(self) -> None:
        frame = self.panel.page.frame(url=re.compile(r"/api/whispeer/panel"))
        if frame is None:
            return

        try:
            frame.locator(".settings-modal").wait_for(
                state="hidden",
                timeout=self.settings.timeout_ms,
            )
        except PlaywrightError as error:
            if "Frame was detached" not in str(error):
                raise

    def export_devices(self, destination: Path) -> Path:
        with self.panel.page.expect_download(timeout=self.settings.timeout_ms) as download_info:
            self.page.locator(".settings-modal #advancedExportBtn").click()
        download = download_info.value
        download.save_as(str(destination))
        return destination

    def import_devices(self, file_path: Path) -> None:
        self.page.locator('input[type="file"]').set_input_files(str(file_path))

    def clear_entities(self) -> None:
        self.page.locator(".settings-modal #advancedClearEntitiesBtn").click()
        self.wait_closed()

    def clear_devices(self) -> None:
        self.page.locator(".settings-modal #advancedClearBtn").click()
        self.wait_closed()

    def close(self) -> None:
        self.page.locator(".settings-modal .close-btn").click()
        self.wait_closed()
