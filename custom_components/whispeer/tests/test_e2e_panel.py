from __future__ import annotations

import json

import pytest

from whispeer.tests.browser_support import (
    assert_ws_success,
    call_ha_ws_command,
    wait_for_panel_ready,
)


IR_INTERFACE = {
    "label": "RM4 IR Playwright Bench",
    "entity_id": "remote.rm4_ir_playwright_bench",
    "manufacturer": "Broadlink",
}
RF_INTERFACE = {
    "label": "RM4 Playwright Bench",
    "entity_id": "remote.rm4_playwright_bench",
    "manufacturer": "Broadlink",
}
RF_FAST_LEARN_INTERFACE = {
    "label": "RM4 Fast Learn Bench",
    "entity_id": "remote.rm4_fast_learn_bench",
    "manufacturer": "Broadlink",
}
RF_MANUAL_CODE = "mock-rf-manual-code"
RF_FAST_LEARN_CODE = "mock-rf-fast-learn-code"
RF_FREQUENCY = 433.92
SMARTIR_COMMUNITY_CODE = "1000"

DEFAULT_DOMAIN_COMMAND_SPECS = (
    {"name": "power", "type": "button"},
    {"name": "lamp", "type": "light", "options": ("on", "off")},
    {"name": "outlet", "type": "switch", "options": ("on", "off")},
    {"name": "level", "type": "numeric", "options": ("10", "20", "30")},
    {"name": "mode", "type": "group", "options": ("cool", "heat", "dry")},
    {"name": "scene", "type": "options", "options": ("movie", "music", "sleep")},
)

SMARTIR_FIXTURES = {
    "climate": {
        "minTemperature": 24,
        "maxTemperature": 24,
        "operationModes": ["cool"],
        "fanModes": ["auto"],
        "commands": {
            "off": "climate_off_1000",
            "cool": {"auto": {"24": "climate_cool_auto_24_1000"}},
        },
    },
    "fan": {
        "speed": ["low", "medium", "high"],
        "commands": {
            "off": "fan_off_1000",
            "low": "fan_low_1000",
            "medium": "fan_medium_1000",
            "high": "fan_high_1000",
        },
    },
    "media_player": {
        "commands": {
            "on": "media_on_1000",
            "off": "media_off_1000",
            "mute": "media_mute_1000",
            "volumeUp": "media_volume_up_1000",
            "volumeDown": "media_volume_down_1000",
            "previousChannel": "media_previous_channel_1000",
            "nextChannel": "media_next_channel_1000",
            "sources": {
                "HDMI1": "media_source_hdmi1_1000",
                "HDMI2": "media_source_hdmi2_1000",
            },
        },
    },
    "light": {
        "commands": {
            "on": "light_on_1000",
            "off": "light_off_1000",
            "brighten": "light_brighten_1000",
            "dim": "light_dim_1000",
            "warmer": "light_warmer_1000",
            "colder": "light_colder_1000",
            "night": "light_night_1000",
        },
    },
}

COMMUNITY_DOMAIN_CASES = (
    {
        "domain": "climate",
        "name": "Playwright Climate Community Device",
    },
    {
        "domain": "fan",
        "name": "Playwright Fan Community Device",
    },
    {
        "domain": "media_player",
        "name": "Playwright Media Player Community Device",
    },
    {
        "domain": "light",
        "name": "Playwright Light Community Device",
    },
)


def _reload_panel(page, settings) -> None:
    page.reload(wait_until="domcontentloaded")
    wait_for_panel_ready(page, settings)


def _clear_devices(page, settings) -> None:
    assert_ws_success(
        call_ha_ws_command(
            page,
            settings,
            {"type": "whispeer/clear_devices"},
        ),
        "Failed to clear Whispeer devices before the Playwright scenario.",
    )
    _reload_panel(page, settings)


def _get_devices(page, settings) -> list[dict]:
    result = assert_ws_success(
        call_ha_ws_command(
            page,
            settings,
            {"type": "whispeer/get_devices"},
        ),
        "Failed to fetch Whispeer devices from the panel session.",
    )
    return result["devices"]


def _find_device_by_name(devices: list[dict], name: str) -> dict:
    return next(device for device in devices if device["name"] == name)


def _open_add_device_modal(page, settings) -> None:
    page.get_by_test_id("open-add-device-modal").click()
    page.get_by_test_id("device-form").wait_for(
        state="visible",
        timeout=settings.timeout_ms,
    )


def _wait_for_interface(page, settings, label: str) -> None:
    page.wait_for_function(
        """(expectedLabel) => {
            const select = document.querySelector('[data-testid="device-interface-select"]');
            if (!select) {
                return false;
            }
            return Array.from(select.options).some(
                (option) => option.value !== '' && option.textContent.includes(expectedLabel)
            );
        }""",
        arg=label,
        timeout=settings.timeout_ms,
    )


def _wait_for_command_count(page, settings, expected_count: int) -> None:
    page.wait_for_function(
        """(expected) => {
            return document.querySelectorAll('[data-testid="command-container"]').length === expected;
        }""",
        arg=expected_count,
        timeout=settings.timeout_ms,
    )


def _wait_for_code_value(page, settings, expected_code: str) -> None:
    page.wait_for_function(
        """(expectedCode) => {
            const selectors = [
                'input[data-field="code"]',
                'input[data-option]',
                'input[data-option-value]',
            ];
            return selectors.some((selector) =>
                Array.from(document.querySelectorAll(selector)).some(
                    (input) => input.value.trim() === expectedCode
                )
            );
        }""",
        arg=expected_code,
        timeout=settings.timeout_ms,
    )


def _journal_has_entry(state: dict, category: str, action: str) -> bool:
    return any(
        entry.get("category") == category and entry.get("action") == action
        for entry in state.get("journal", [])
    )


def _learned_codes_for_spec(spec: dict[str, object]) -> list[str]:
    name = str(spec["name"])
    options = spec.get("options")
    if not options:
        return [f"{name}_test"]
    return [f"{name}_{option}_test" for option in options]


def _default_domain_learn_codes() -> list[str]:
    codes: list[str] = []
    for spec in DEFAULT_DOMAIN_COMMAND_SPECS:
        codes.extend(_learned_codes_for_spec(spec))
    return codes


def _build_learn_queue(
    *,
    device_type: str,
    entity_id: str,
    codes: list[str],
) -> list[dict[str, object]]:
    return [
        {
            "match": {
                "device_type": device_type,
                "entity_id": entity_id,
            },
            "command_data": code,
            "delay": 0.05,
        }
        for code in codes
    ]


def _command_container(page, index: int):
    return page.get_by_test_id("command-container").nth(index)


def _add_command_rows(page, settings, target_count: int) -> None:
    while page.get_by_test_id("command-container").count() < target_count:
        next_count = page.get_by_test_id("command-container").count() + 1
        page.get_by_test_id("add-command-button").click()
        _wait_for_command_count(page, settings, next_count)


def _ensure_option_count(page, index: int, expected_count: int) -> None:
    container = _command_container(page, index)
    while container.locator(".option-field").count() < expected_count:
        container.get_by_test_id("add-option-button").click()


def _configure_default_command(page, settings, index: int, spec: dict[str, object]) -> None:
    name = str(spec["name"])
    command_type = str(spec["type"])
    container = _command_container(page, index)

    if command_type != "button":
        container.get_by_test_id("command-type-select").select_option(command_type)
        container = _command_container(page, index)

    container.get_by_test_id("command-name-input").fill(name)

    if command_type == "button":
        expected_code = f"{name}_test"
        container.get_by_test_id("learn-command-button").click()
        _wait_for_code_value(page, settings, expected_code)
        assert container.get_by_test_id("command-code-input").input_value() == expected_code
        return

    options = tuple(spec.get("options") or ())
    if command_type in ("light", "switch"):
        for option_index, option_key in enumerate(options):
            expected_code = f"{name}_{option_key}_test"
            container.get_by_test_id("learn-option-button").nth(option_index).click()
            _wait_for_code_value(page, settings, expected_code)
            assert (
                container.get_by_test_id("command-option-code-input").nth(option_index).input_value()
                == expected_code
            )
        return

    _ensure_option_count(page, index, len(options))
    for option_index, option_key in enumerate(options):
        container = _command_container(page, index)
        option_field = container.locator(".option-field").nth(option_index)
        option_field.locator("[data-option-key]").fill(option_key)
        expected_code = f"{name}_{option_key}_test"
        option_field.get_by_test_id("learn-option-button").click()
        _wait_for_code_value(page, settings, expected_code)
        assert option_field.get_by_test_id("command-option-code-input").input_value() == expected_code


def _fill_device_form(
    page,
    settings,
    *,
    device_name: str,
    device_type: str,
    interface_label: str,
    domain: str = "default",
    frequency: float | None = None,
) -> None:
    page.get_by_test_id("device-name-input").fill(device_name)
    page.get_by_test_id("device-domain-select").select_option(domain)
    page.get_by_test_id("device-type-select").select_option(device_type)

    _wait_for_interface(page, settings, interface_label)

    page.get_by_test_id("device-interface-select").select_option("0")
    if frequency is not None:
        page.get_by_test_id("device-frequency-input").fill(str(frequency))


def _save_device(page, settings, device_name: str) -> None:
    page.get_by_test_id("save-device-button").click()
    page.locator(".device-card", has_text=device_name).first.wait_for(
        state="visible",
        timeout=settings.timeout_ms,
    )
    _reload_panel(page, settings)
    page.locator(".device-card", has_text=device_name).first.wait_for(
        state="visible",
        timeout=settings.timeout_ms,
    )


def _create_default_domain_device(
    page,
    settings,
    *,
    device_name: str,
    device_type: str,
    interface_label: str,
    frequency: float | None = None,
) -> None:
    _open_add_device_modal(page, settings)
    _fill_device_form(
        page,
        settings,
        device_name=device_name,
        device_type=device_type,
        interface_label=interface_label,
        frequency=frequency,
    )
    _add_command_rows(page, settings, len(DEFAULT_DOMAIN_COMMAND_SPECS))
    for index, spec in enumerate(DEFAULT_DOMAIN_COMMAND_SPECS):
        _configure_default_command(page, settings, index, spec)
    _save_device(page, settings, device_name)


def _assert_default_domain_device(
    device: dict,
    *,
    expected_type: str,
    expected_interface: dict[str, str],
    expected_frequency: float | None = None,
) -> None:
    assert device["domain"] == "default"
    assert device["type"] == expected_type
    assert device["emitter"]["entity_id"] == expected_interface["entity_id"]
    assert device["emitter"]["manufacturer"] == expected_interface["manufacturer"]
    if expected_frequency is None:
        assert "frequency" not in device or device["frequency"] in (None, "")
    else:
        assert device["frequency"] == pytest.approx(expected_frequency)

    commands = device["commands"]
    for spec in DEFAULT_DOMAIN_COMMAND_SPECS:
        name = str(spec["name"])
        command = commands[name]
        assert command["type"] == spec["type"]
        values = command["values"]
        if spec["type"] == "button":
            assert values["code"] == f"{name}_test"
            continue
        for option_key in spec.get("options") or ():
            assert values[option_key] == f"{name}_{option_key}_test"


def _mock_smartir_imports(page) -> None:
    def _handler(route) -> None:
        url = route.request.url
        for domain, payload in SMARTIR_FIXTURES.items():
            if f"/codes/{domain}/1000.json" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                )
                return
        route.continue_()

    page.route(
        "https://raw.githubusercontent.com/smartHomeHub/SmartIR/master/codes/**/1000.json",
        _handler,
    )


def _wait_for_smartir_import(page, settings, domain: str) -> None:
    if domain == "climate":
        page.wait_for_function(
            """() => {
                const data = window.deviceManager?._climateData;
                return Boolean(data)
                    && data.source === 'smartir'
                    && data._smartirNum === '1000'
                    && Object.keys(data.table || {}).length > 0;
            }""",
            timeout=settings.timeout_ms,
        )
        return

    page.wait_for_function(
        """() => {
            const manager = window.deviceManager;
            const data = manager?._climateData;
            return Boolean(data)
                && data.source === 'smartir'
                && data._smartirNum === '1000'
                && Object.keys(manager?.tempCommands || {}).length > 0;
        }""",
        timeout=settings.timeout_ms,
    )


def _create_community_domain_device(
    page,
    settings,
    *,
    device_name: str,
    domain: str,
) -> None:
    _open_add_device_modal(page, settings)
    _fill_device_form(
        page,
        settings,
        device_name=device_name,
        domain=domain,
        device_type="ir",
        interface_label=IR_INTERFACE["label"],
    )
    page.get_by_test_id("community-code-input").fill(SMARTIR_COMMUNITY_CODE)
    page.get_by_test_id("community-import-button").click()
    _wait_for_smartir_import(page, settings, domain)
    _save_device(page, settings, device_name)


def _assert_community_domain_device(device: dict, domain: str) -> None:
    assert device["domain"] == domain
    assert device["type"] == "ir"
    assert device["emitter"]["entity_id"] == IR_INTERFACE["entity_id"]
    assert device["source"] == "smartir"
    assert device["_smartirNum"] == SMARTIR_COMMUNITY_CODE

    if domain == "climate":
        assert device["config"]["modes"] == ["cool"]
        assert device["config"]["fan_modes"] == ["auto"]
        assert device["commands"]["off"] == "climate_off_1000"
        assert device["table"]["cool"]["auto"]["24"] == "climate_cool_auto_24_1000"
        return

    if domain == "fan":
        assert device["config"]["fan_model"] == "direct"
        assert device["config"]["speeds"] == ["low", "medium", "high"]
        assert device["commands"]["off"] == "fan_off_1000"
        assert device["commands"]["speeds"]["low"] == "fan_low_1000"
        assert device["commands"]["speeds"]["medium"] == "fan_medium_1000"
        assert device["commands"]["speeds"]["high"] == "fan_high_1000"
        return

    if domain == "media_player":
        assert device["commands"]["on"] == "media_on_1000"
        assert device["commands"]["off"] == "media_off_1000"
        assert device["commands"]["sources"]["HDMI1"] == "media_source_hdmi1_1000"
        assert device["commands"]["sources"]["HDMI2"] == "media_source_hdmi2_1000"
        return

    if domain == "light":
        assert device["commands"]["on"] == "light_on_1000"
        assert device["commands"]["off"] == "light_off_1000"
        assert device["commands"]["brighten"] == "light_brighten_1000"
        assert device["commands"]["night"] == "light_night_1000"


@pytest.mark.e2e
def test_panel_add_device_modal_is_visible_in_headed_mode(
    whispeer_test_harness,
    whispeer_panel_page,
    whispeer_test_settings,
) -> None:
    whispeer_test_harness(
        "whispeer/test/configure",
        config={"interfaces": {"rf": [RF_INTERFACE]}},
    )

    page = whispeer_panel_page
    _clear_devices(page, whispeer_test_settings)
    _open_add_device_modal(page, whispeer_test_settings)

    page.get_by_test_id("device-name-input").fill("Playwright RF Demo")
    page.get_by_test_id("device-type-select").select_option("rf")

    _wait_for_interface(page, whispeer_test_settings, RF_INTERFACE["label"])

    assert page.get_by_test_id("save-device-button").is_visible()
    assert page.get_by_test_id("cancel-device-button").is_visible()


@pytest.mark.e2e
def test_panel_creates_rf_device_from_modal(
    whispeer_test_harness,
    whispeer_panel_page,
    whispeer_test_settings,
) -> None:
    device_name = "Playwright Manual RF Device"

    whispeer_test_harness(
        "whispeer/test/configure",
        config={"interfaces": {"rf": [RF_INTERFACE]}},
    )

    page = whispeer_panel_page
    _clear_devices(page, whispeer_test_settings)
    _open_add_device_modal(page, whispeer_test_settings)

    page.get_by_test_id("device-name-input").fill(device_name)
    page.get_by_test_id("device-type-select").select_option("rf")
    _wait_for_interface(page, whispeer_test_settings, RF_INTERFACE["label"])

    page.get_by_test_id("device-interface-select").select_option("0")
    page.get_by_test_id("device-frequency-input").fill(str(RF_FREQUENCY))
    page.get_by_test_id("command-name-input").first.fill("power")
    page.get_by_test_id("command-code-input").first.fill(RF_MANUAL_CODE)
    page.get_by_test_id("save-device-button").click()

    page.locator(".device-card", has_text=device_name).first.wait_for(
        state="visible",
        timeout=whispeer_test_settings.timeout_ms,
    )

    devices = _get_devices(page, whispeer_test_settings)
    created_device = _find_device_by_name(devices, device_name)

    assert created_device["type"] == "rf"
    assert created_device["emitter"]["entity_id"] == RF_INTERFACE["entity_id"]
    assert created_device["emitter"]["manufacturer"] == RF_INTERFACE["manufacturer"]
    assert created_device["commands"]["power"]["values"]["code"] == RF_MANUAL_CODE
    assert created_device["frequency"] == pytest.approx(RF_FREQUENCY)

    state = whispeer_test_harness("whispeer/test/get_state")
    assert _journal_has_entry(state, "device", "added")


@pytest.mark.e2e
@pytest.mark.rf_fast
def test_panel_rf_fast_learn_populates_frequency_and_command(
    whispeer_test_harness,
    whispeer_panel_page,
    whispeer_test_settings,
) -> None:
    device_name = "Playwright RF Fast Learn Device"

    whispeer_test_harness(
        "whispeer/test/configure",
        config={
            "interfaces": {"rf": [RF_FAST_LEARN_INTERFACE]},
            "frequency": {
                "queue": [
                    {
                        "match": {"entity_id": RF_FAST_LEARN_INTERFACE["entity_id"]},
                        "detected_frequency": RF_FREQUENCY,
                        "delay": 0.1,
                    }
                ]
            },
            "learn": {
                "queue": [
                    {
                        "match": {
                            "device_type": "rf",
                            "entity_id": RF_FAST_LEARN_INTERFACE["entity_id"],
                        },
                        "command_data": RF_FAST_LEARN_CODE,
                        "delay": 0.1,
                    }
                ]
            },
        },
    )

    page = whispeer_panel_page
    _clear_devices(page, whispeer_test_settings)
    _open_add_device_modal(page, whispeer_test_settings)

    page.get_by_test_id("device-name-input").fill(device_name)
    page.get_by_test_id("device-type-select").select_option("rf")
    _wait_for_interface(page, whispeer_test_settings, RF_FAST_LEARN_INTERFACE["label"])

    page.get_by_test_id("device-interface-select").select_option("0")
    page.get_by_test_id("command-name-input").first.fill("power")
    page.get_by_test_id("fast-learn-button").click()
    page.get_by_test_id("fast-learn-stop-button").wait_for(
        state="visible",
        timeout=whispeer_test_settings.timeout_ms,
    )
    page.get_by_test_id("fast-learn-stop-button").click()

    page.wait_for_function(
        """(expectedCode) => {
            const codeInput = document.querySelector('[data-testid="command-code-input"]');
            return Boolean(codeInput) && codeInput.value.trim() === expectedCode;
        }""",
        arg=RF_FAST_LEARN_CODE,
        timeout=whispeer_test_settings.timeout_ms,
    )
    page.wait_for_function(
        """() => {
            const frequencyInput = document.querySelector('[data-testid="device-frequency-input"]');
            if (!frequencyInput) {
                return false;
            }
            return Number.parseFloat(frequencyInput.value) > 0;
        }""",
        timeout=whispeer_test_settings.timeout_ms,
    )
    page.wait_for_function(
        """() => {
            const button = document.getElementById('fastLearnBtn');
            const stop = document.getElementById('fastLearnStopBtn');
            if (!button || !stop) {
                return false;
            }
            return !button.disabled
                && button.textContent.includes('Fast Learn')
                && window.getComputedStyle(stop).display === 'none';
        }""",
        timeout=whispeer_test_settings.timeout_ms,
    )

    assert float(page.get_by_test_id("device-frequency-input").input_value()) == pytest.approx(RF_FREQUENCY)
    assert page.get_by_test_id("command-code-input").first.input_value() == RF_FAST_LEARN_CODE

    page.get_by_test_id("save-device-button").click()
    page.locator(".device-card", has_text=device_name).first.wait_for(
        state="visible",
        timeout=whispeer_test_settings.timeout_ms,
    )

    devices = _get_devices(page, whispeer_test_settings)
    created_device = _find_device_by_name(devices, device_name)

    assert created_device["frequency"] == pytest.approx(RF_FREQUENCY)
    assert created_device["commands"]["power"]["values"]["code"] == RF_FAST_LEARN_CODE
    assert created_device["emitter"]["entity_id"] == RF_FAST_LEARN_INTERFACE["entity_id"]

    state = whispeer_test_harness("whispeer/test/get_state")
    assert _journal_has_entry(state, "frequency", "override_selected")
    assert _journal_has_entry(state, "learn", "override_selected")


@pytest.mark.e2e
@pytest.mark.slow
def test_panel_creates_default_ir_and_rf_devices_with_all_command_types(
    whispeer_test_harness,
    whispeer_panel_page,
    whispeer_test_settings,
) -> None:
    learn_codes = _default_domain_learn_codes()
    whispeer_test_harness(
        "whispeer/test/configure",
        config={
            "interfaces": {
                "ir": [IR_INTERFACE],
                "rf": [RF_INTERFACE],
            },
            "learn": {
                "queue": (
                    _build_learn_queue(
                        device_type="ir",
                        entity_id=IR_INTERFACE["entity_id"],
                        codes=learn_codes,
                    )
                    + _build_learn_queue(
                        device_type="rf",
                        entity_id=RF_INTERFACE["entity_id"],
                        codes=learn_codes,
                    )
                )
            },
        },
    )

    page = whispeer_panel_page
    _clear_devices(page, whispeer_test_settings)

    _create_default_domain_device(
        page,
        whispeer_test_settings,
        device_name="Playwright Default IR Device",
        device_type="ir",
        interface_label=IR_INTERFACE["label"],
    )
    _create_default_domain_device(
        page,
        whispeer_test_settings,
        device_name="Playwright Default RF Device",
        device_type="rf",
        interface_label=RF_INTERFACE["label"],
        frequency=RF_FREQUENCY,
    )

    devices = _get_devices(page, whispeer_test_settings)
    ir_device = _find_device_by_name(devices, "Playwright Default IR Device")
    rf_device = _find_device_by_name(devices, "Playwright Default RF Device")

    _assert_default_domain_device(
        ir_device,
        expected_type="ir",
        expected_interface=IR_INTERFACE,
    )
    _assert_default_domain_device(
        rf_device,
        expected_type="rf",
        expected_interface=RF_INTERFACE,
        expected_frequency=RF_FREQUENCY,
    )

    state = whispeer_test_harness("whispeer/test/get_state")
    learn_override_hits = [
        entry
        for entry in state["journal"]
        if entry.get("category") == "learn"
        and entry.get("action") == "override_selected"
    ]
    added_devices = [
        entry
        for entry in state["journal"]
        if entry.get("category") == "device"
        and entry.get("action") == "added"
    ]

    assert len(learn_override_hits) == len(learn_codes) * 2
    assert len(added_devices) >= 2


@pytest.mark.e2e
@pytest.mark.slow
def test_panel_creates_non_default_domain_devices_from_community_code(
    whispeer_test_harness,
    whispeer_panel_page,
    whispeer_test_settings,
) -> None:
    whispeer_test_harness(
        "whispeer/test/configure",
        config={
            "interfaces": {"ir": [IR_INTERFACE]},
        },
    )

    page = whispeer_panel_page
    _mock_smartir_imports(page)
    _clear_devices(page, whispeer_test_settings)

    for case in COMMUNITY_DOMAIN_CASES:
        _create_community_domain_device(
            page,
            whispeer_test_settings,
            device_name=case["name"],
            domain=case["domain"],
        )

    devices = _get_devices(page, whispeer_test_settings)
    for case in COMMUNITY_DOMAIN_CASES:
        device = _find_device_by_name(devices, case["name"])
        _assert_community_domain_device(device, case["domain"])

    state = whispeer_test_harness("whispeer/test/get_state")
    added_devices = [
        entry
        for entry in state["journal"]
        if entry.get("category") == "device"
        and entry.get("action") == "added"
    ]
    assert len(added_devices) >= 4