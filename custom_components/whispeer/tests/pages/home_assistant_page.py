from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class HomeAssistantOtherDevicesPage:
    def __init__(self, page, settings) -> None:
        self.page = page
        self.settings = settings

    def _ensure_authenticated_shell(self, shell_url: str) -> None:
        from whispeer.tests.browser_support import _is_login_required, _login_in_page

        self.page.goto(shell_url, wait_until="domcontentloaded")
        if _is_login_required(self.page):
            _login_in_page(self.page, self.settings)

    def open(self, url: str, access_token: str | None = None) -> None:
        split = urlsplit(url)
        target_path = split.path or "/home/other-devices"

        if access_token:
            query = dict(parse_qsl(split.query, keep_blank_values=True))
            query["access_token"] = access_token
            url = urlunsplit(
                (split.scheme, split.netloc, split.path, urlencode(query), split.fragment)
            )

        shell_url = urlunsplit((split.scheme, split.netloc, "/home/overview", "", ""))
        self._ensure_authenticated_shell(shell_url)
        self.page.wait_for_function(
            """() => {
                const path = window.location.pathname || "";
                return !path.includes("/auth") && !!document.body;
            }""",
            timeout=self.settings.timeout_ms,
        )
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
            arg=target_path,
            timeout=self.settings.timeout_ms,
        )

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
