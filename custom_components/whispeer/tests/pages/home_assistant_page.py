from __future__ import annotations

import re

from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

from whispeer.tests.browser_support import wait_for_authenticated_shell


class HomeAssistantOtherDevicesPage:
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

    def _sidebar_entry(self, *labels: str):
        candidates = []
        for label in labels:
            pattern = re.compile(rf"^{re.escape(label)}$", re.IGNORECASE)
            candidates.append(self.page.get_by_role("link", name=pattern))
            candidates.append(self.page.get_by_text(pattern))
        return self._first_existing_locator(*candidates)

    def _open_sidebar_item(self, *labels: str) -> None:
        entry = self._sidebar_entry(*labels)
        if entry is None:
            raise AssertionError(
                f"Unable to find a Home Assistant sidebar entry matching: {', '.join(labels)}"
            )

        try:
            if not entry.is_visible(timeout=250):
                toggle = self._sidebar_toggle()
                if toggle is not None:
                    toggle.click(timeout=self.settings.timeout_ms)
                entry.wait_for(state="visible", timeout=self.settings.timeout_ms)
        except Exception:
            toggle = self._sidebar_toggle()
            if toggle is not None:
                toggle.click(timeout=self.settings.timeout_ms)
            entry.wait_for(state="visible", timeout=self.settings.timeout_ms)

        entry.click(timeout=self.settings.timeout_ms, force=True)

    def _open_devices_tab(self) -> None:
        current_path = self.page.evaluate("() => window.location.pathname || ''")
        devices_link = self._first_existing_locator(
            self.page.get_by_role("link", name=re.compile(r"^devices$|^dispositivos$", re.IGNORECASE)),
            self.page.get_by_role("button", name=re.compile(r"^devices$|^dispositivos$", re.IGNORECASE)),
            self.page.get_by_text(re.compile(r"^Devices$|^Dispositivos$", re.IGNORECASE)),
        )
        if devices_link is None:
            raise AssertionError("Unable to find the Devices navigation control in Home Assistant.")
        devices_link.click(timeout=self.settings.timeout_ms, force=True)
        self.page.wait_for_function(
            """(previousPath) => {
                const currentPath = window.location.pathname || "";
                return currentPath !== previousPath && /devices/i.test(currentPath);
            }""",
            arg=current_path,
            timeout=self.settings.timeout_ms,
        )

    def open(self) -> None:
        if not (self.page.url or "").startswith(self.settings.base_url):
            self.page.goto(self.settings.base_url, wait_until="domcontentloaded")

        wait_for_authenticated_shell(self.page, self.settings)
        self._open_sidebar_item("Overview", "Vista general")
        try:
            self.page.get_by_text(re.compile(r"^Areas$|^\u00c1reas$", re.IGNORECASE)).wait_for(
                state="visible",
                timeout=self.settings.timeout_ms,
            )
        except PlaywrightTimeoutError:
            pass
        self._open_devices_tab()

    def bring_to_front(self) -> None:
        self.page.bring_to_front()

    def wait_for_device(self, device_name: str) -> None:
        self.page.get_by_role("button", name=re.compile(re.escape(device_name), re.IGNORECASE)).first.wait_for(
            state="visible",
            timeout=self.settings.timeout_ms,
        )

    def global_control_summary(self) -> dict[str, int]:
        return {
            "buttons": self.page.get_by_role("button").count(),
            "switches": self.page.get_by_role("switch").count(),
            "comboboxes": self.page.get_by_role("combobox").count(),
            "spinbuttons": self.page.get_by_role("spinbutton").count(),
        }

    def switch_count(self, device_name: str) -> int:
        return self.page.locator(f'ha-switch[aria-label*="{device_name}"]').count()

    def toggle_switch(self, device_name: str, entity_label: str) -> None:
        if entity_label.strip().lower() == device_name.strip().lower():
            selector = f'ha-switch[aria-label*="{device_name}"]'
        else:
            selector = f'ha-switch[aria-label*="{device_name}"][aria-label*="{entity_label}"]'
        self.page.locator(selector).first.click()

    def click_button(self, label: str) -> None:
        self.page.get_by_role(
            "button",
            name=re.compile(re.escape(label), re.IGNORECASE),
        ).first.click()
