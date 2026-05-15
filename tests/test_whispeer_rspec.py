from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pytest


IR_INTERFACE = {
    "label": "RM4 Mini Bench",
    "entity_id": "remote.rm4_ir_playwright_bench",
    "manufacturer": "Broadlink",
}
RF_INTERFACE = {
    "label": "RM4 Pro Bench",
    "entity_id": "remote.rm4_rf_playwright_bench",
    "manufacturer": "Broadlink",
}
BLE_INTERFACE = {
    "label": "hci0 - 00:11:22:33:44:55",
    "hci_name": "hci0",
    "mac": "00:11:22:33:44:55",
    "status": "UP",
    "can_emit": True,
    "source": "ble",
}
RF_FREQUENCY = 433.92
SMARTIR_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "whispeer" / "tests" / "fixtures" / "smartir"
REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_IR_DEVICE_NAME = "old stetero"
DEFAULT_RF_DEVICE_NAME = "old stetero rf"
GARAGE_FAST_LEARN_DEVICE_NAME = "garage 315 fast learn"
SCRATCH_CLIMATE_DEVICE_NAME = "scratch ac"
BLE_FAN_DEVICE_NAME = "bt fan"
BLE_DEFAULT_DEVICE_NAME = "xmas"
COMMUNITY_DEVICE_NAMES = {
    "climate": "Comm. AC",
    "fan": "Comm. Fan",
    "light": "Comm. Light",
    "media_player": "Comm. Media Player",
}
EXPECTED_DEVICE_NAMES = [
    DEFAULT_IR_DEVICE_NAME,
    DEFAULT_RF_DEVICE_NAME,
    GARAGE_FAST_LEARN_DEVICE_NAME,
    SCRATCH_CLIMATE_DEVICE_NAME,
    BLE_FAN_DEVICE_NAME,
    BLE_DEFAULT_DEVICE_NAME,
    COMMUNITY_DEVICE_NAMES["fan"],
    COMMUNITY_DEVICE_NAMES["climate"],
    COMMUNITY_DEVICE_NAMES["light"],
    COMMUNITY_DEVICE_NAMES["media_player"],
]

DEFAULT_DOMAIN_COMMAND_SPECS = (
    {"name": "power", "type": "button"},
    {"name": "lamp", "type": "light", "options": ("on", "off")},
    {"name": "outlet", "type": "switch", "options": ("on", "off")},
    {"name": "level", "type": "numeric", "options": ("10", "20", "30")},
    {"name": "mode", "type": "group", "options": ("cool", "heat", "dry")},
    {"name": "scene", "type": "options", "options": ("movie", "music", "sleep")},
)

CLIMATE_TEMPERATURES = (16, 24, 30)
CLIMATE_MODES = ("cool", "heat")
CLIMATE_FAN_MODES = ("slow", "fast")
CLIMATE_FAST_LEARN_CELLS = (
    ("cool", "slow", 16),
    ("cool", "slow", 24),
    ("cool", "slow", 30),
)
CLIMATE_MANUAL_LEARN_CELLS = (
    ("cool", "fast", 16),
    ("cool", "fast", 24),
    ("cool", "fast", 30),
    ("heat", "slow", 16),
    ("heat", "slow", 24),
    ("heat", "slow", 30),
    ("heat", "fast", 16),
    ("heat", "fast", 24),
    ("heat", "fast", 30),
)
CLIMATE_TEST_MODE_CELLS = (
    ("cool", "slow", 16),
    ("cool", "fast", 24),
    ("heat", "fast", 30),
)
CLIMATE_OFF_CODE = "climate_off_test"
GARAGE_RF_FREQUENCY = 315.0
GARAGE_FAST_LEARN_CODES = (
    "garage_open_test",
    "garage_close_test",
)
CARD_ACTION_SAMPLE_SEED = 20260518
EDIT_MODAL_SAMPLE_SEED = 20260516
STORED_CODES_FIXTURE_FILENAME = "broadlink_remote_playwright_existing_codes"
STORED_CODES_EXPECTED_GROUPS = {
    "Legacy TV": ("power", "mute", "hdmi1"),
    "Retro AC": ("on", "off"),
}
STORED_CODES_FIXTURE_DATA = {
    "Legacy TV": {
        "power": "legacy_tv_power_code",
        "mute": "legacy_tv_mute_code",
        "hdmi1": "legacy_tv_hdmi1_code",
    },
    "Retro AC": {
        "on": "retro_ac_on_code",
        "off": "retro_ac_off_code",
    },
}
ADVANCED_ARTIFACTS: dict[str, Path] = {}

BLE_ADVERTISEMENTS = {
    "fan_off": {
        "address": "AA:AA:AA:AA:AA:01",
        "name": "Fan Off",
        "source": BLE_INTERFACE["mac"],
        "rssi": -50,
        "raw": "a1b2c3d4e501",
        "time": 1,
        "manufacturer_data": {},
        "service_data": {},
    },
    "fan_low": {
        "address": "AA:AA:AA:AA:AA:02",
        "name": "Fan Low",
        "source": BLE_INTERFACE["mac"],
        "rssi": -49,
        "raw": "a1b2c3d4e502",
        "time": 2,
        "manufacturer_data": {},
        "service_data": {},
    },
    "fan_medium": {
        "address": "AA:AA:AA:AA:AA:03",
        "name": "Fan Medium",
        "source": BLE_INTERFACE["mac"],
        "rssi": -48,
        "raw": "a1b2c3d4e503",
        "time": 3,
        "manufacturer_data": {},
        "service_data": {},
    },
    "fan_high": {
        "address": "AA:AA:AA:AA:AA:04",
        "name": "Fan High",
        "source": BLE_INTERFACE["mac"],
        "rssi": -47,
        "raw": "a1b2c3d4e504",
        "time": 4,
        "manufacturer_data": {},
        "service_data": {},
    },
    "lights_on": {
        "address": "BB:BB:BB:BB:BB:01",
        "name": "Lights On",
        "source": BLE_INTERFACE["mac"],
        "rssi": -46,
        "raw": "b1c2d3e4f501",
        "time": 5,
        "manufacturer_data": {},
        "service_data": {},
    },
    "lights_off": {
        "address": "BB:BB:BB:BB:BB:02",
        "name": "Lights Off",
        "source": BLE_INTERFACE["mac"],
        "rssi": -45,
        "raw": "b1c2d3e4f502",
        "time": 6,
        "manufacturer_data": {},
        "service_data": {},
    },
}


def scenario(case_id: str, title: str):
    def _decorate(func):
        func = pytest.mark.whispeer_case(case_id)(func)
        func = pytest.mark.whispeer_title(title)(func)
        return func

    return _decorate


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


def _climate_cell_code(mode: str, fan_mode: str, temperature: int) -> str:
    return f"climate_{mode}_{fan_mode}_{temperature}_test"


def _scratch_climate_learn_codes() -> list[str]:
    codes = [_climate_cell_code(mode, fan_mode, temperature) for mode, fan_mode, temperature in CLIMATE_FAST_LEARN_CELLS]
    codes.extend(
        _climate_cell_code(mode, fan_mode, temperature)
        for mode, fan_mode, temperature in CLIMATE_MANUAL_LEARN_CELLS
    )
    codes.append(CLIMATE_OFF_CODE)
    return codes


def _build_learn_queue(device_type: str, entity_id: str, codes: list[str]) -> list[dict[str, object]]:
    return [
        {
            "match": {
                "device_type": device_type,
                "entity_id": entity_id,
            },
            "command_data": code,
            "delay": 0.01,
        }
        for code in codes
    ]


def _runtime_config_dir(suite) -> Path:
    container_name = (suite.settings.container_name or "").strip().lower()
    runtime_name = "dev" if container_name == "hass-dev" else "test"
    return REPO_ROOT / ".homeassistant" / runtime_name


def _stored_codes_fixture_path(suite) -> Path:
    return _runtime_config_dir(suite) / ".storage" / STORED_CODES_FIXTURE_FILENAME


def _write_stored_codes_fixture(suite) -> Path:
    fixture_path = _stored_codes_fixture_path(suite)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps({"data": STORED_CODES_FIXTURE_DATA}, indent=2),
        encoding="utf-8",
    )
    return fixture_path


def _remove_stored_codes_fixture(suite) -> None:
    fixture_path = _stored_codes_fixture_path(suite)
    if fixture_path.exists():
        fixture_path.unlink()


def _sample_device_names(device_names: list[str], *, seed: int, count: int = 3) -> list[str]:
    return random.Random(seed).sample(sorted(device_names), count)


def _requested_backend_entries(state: dict, *, device_id: str | None = None) -> list[dict]:
    requested = []
    for entry in state.get("journal", []):
        if (entry.get("category"), entry.get("action")) not in {
            ("api", "send_command_requested"),
            ("websocket", "domain_action_requested"),
        }:
            continue
        if device_id is not None and entry.get("details", {}).get("device_id") != device_id:
            continue
        requested.append(entry)
    return requested


def _api_send_entries(state: dict, *, device_id: str | None = None) -> list[dict]:
    entries = []
    for entry in state.get("journal", []):
        if (entry.get("category"), entry.get("action")) != ("api", "send_command_requested"):
            continue
        if device_id is not None and entry.get("details", {}).get("device_id") != device_id:
            continue
        entries.append(entry)
    return entries


def _wait_for_requested_backend_activity(suite, *, minimum: int) -> list[dict]:
    deadline = time.monotonic() + 4.0
    latest_state = None

    while time.monotonic() < deadline:
        latest_state = suite.call_ws("whispeer/test/get_state")
        entries = _requested_backend_entries(latest_state)
        if len(entries) >= minimum:
            return entries
        suite.page.wait_for_timeout(100)

    assert latest_state is not None
    return _requested_backend_entries(latest_state)


def _whispeer_entity_entries(suite) -> list[dict]:
    entries = suite.call_ws("config/entity_registry/list")
    return [
        entry
        for entry in entries
        if str(entry.get("unique_id") or "").startswith("whispeer_")
        or str(entry.get("entity_id") or "").split(".", 1)[-1].startswith("whispeer_")
    ]


def _whispeer_device_entries(suite) -> list[dict]:
    entries = suite.call_ws("config/device_registry/list")
    return [
        entry
        for entry in entries
        if any(identifier and identifier[0] == "whispeer" for identifier in entry.get("identifiers", []))
    ]


def _configure_suite_mocks(suite) -> None:
    learn_codes = _default_domain_learn_codes()
    scratch_climate_codes = _scratch_climate_learn_codes()
    suite.call_ws(
        "whispeer/test/reset",
        clear_config=True,
        clear_learning_sessions=True,
    )
    suite.call_ws(
        "whispeer/test/configure",
        config={
            "interfaces": {
                "ir": [IR_INTERFACE],
                "rf": [RF_INTERFACE],
                "ble": [BLE_INTERFACE],
            },
            "learn": {
                "queue": _build_learn_queue(
                    "ir",
                    IR_INTERFACE["entity_id"],
                    learn_codes + scratch_climate_codes,
                )
                + _build_learn_queue(
                    "rf",
                    RF_INTERFACE["entity_id"],
                    learn_codes + list(GARAGE_FAST_LEARN_CODES),
                )
            },
            "frequency": {
                "queue": [
                    {
                        "match": {"entity_id": RF_INTERFACE["entity_id"]},
                        "detected_frequency": GARAGE_RF_FREQUENCY,
                        "delay": 0.01,
                    }
                ]
            },
            "send_command": {
                "enabled": True,
                "success": True,
                "message": "RSpec suite mock send completed",
                "result": {"status": "success", "source": "rspec"},
            },
            "ble_emit": {
                "enabled": True,
                "success": True,
                "message": "Mock BLE emit completed",
                "result": {"status": "success", "source": "rspec"},
            },
        },
    )


def _open_panel(suite) -> None:
    if not suite.created_devices:
        suite.page.goto(suite.settings.base_url, wait_until="domcontentloaded")
        suite.page.locator('a[href="/whispeer"]').first.wait_for(
            state="attached",
            timeout=10000,
        )
        suite.page.goto(f"{suite.settings.base_url}/whispeer", wait_until="domcontentloaded")
        suite.panel.wait_for_add_device_button()
        return

    suite.panel.open("/whispeer")


def _open_panel_shell(suite) -> None:
    suite.panel.open("/whispeer")


def _open_other_devices(suite) -> None:
    suite.other_devices.open()


def _apply_official_ui_changes(suite) -> None:
    _open_other_devices(suite)
    suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "lamp")
    suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "outlet")
    suite.other_devices.toggle_switch(BLE_DEFAULT_DEVICE_NAME, "lights")


def _apply_official_ui_changes_from_shell_route(suite) -> None:
    suite.page.goto(f"{suite.settings.base_url}/home/other-devices", wait_until="domcontentloaded")
    suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "lamp")
    suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "outlet")
    suite.other_devices.toggle_switch(BLE_DEFAULT_DEVICE_NAME, "lights")


def _reload_panel_and_store_devices(suite) -> None:
    _open_panel(suite)
    devices = suite.call_ws("whispeer/get_devices")["devices"]
    suite.created_devices = {device["name"]: device for device in devices}


@pytest.fixture(scope="module", autouse=True)
def prepared_suite(whispeer_rspec_session):
    suite = whispeer_rspec_session
    _remove_stored_codes_fixture(suite)
    _configure_suite_mocks(suite)
    _open_panel(suite)
    suite.panel.route_smartir_fixture_directory(SMARTIR_FIXTURE_DIR)
    _reload_panel_and_store_devices(suite)
    yield suite
    _remove_stored_codes_fixture(suite)


def describe_whispeer_rspec():
    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_overview():
        @scenario(
            "overview.opens_whispeer_panel",
            "Opens the Whispeer panel in Home Assistant and confirms the panel loads successfully.",
        )
        def it_opens_whispeer(prepared_suite):
            _open_panel_shell(prepared_suite)
            assert prepared_suite.panel.shell_path() == "/whispeer"
            prepared_suite.panel.wait_for_add_device_button()

        @scenario(
            "overview.shows_add_device_button",
            'Verifies the "Add device" button is visible in the panel shell UI.',
        )
        def it_shows_add_device_button(prepared_suite):
            _open_panel_shell(prepared_suite)
            prepared_suite.panel.wait_for_add_device_button()

        @scenario(
            "overview.shows_sidebar_and_header",
            'Checks that Home Assistant shows "Whispeer" in the sidebar and "Whispeer - Remote control made simple" in the header.',
        )
        def it_shows_sidebar_and_header(prepared_suite):
            _open_panel_shell(prepared_suite)
            prepared_suite.panel.wait_for_sidebar_entry()
            prepared_suite.panel.wait_for_shell_title("Whispeer - Remote control made simple")

        @scenario(
            "overview.shows_panel_header_controls",
            "Checks that the Whispeer header shows the logo, name, settings button, and add-device button.",
        )
        def it_shows_panel_header_controls(prepared_suite):
            _open_panel(prepared_suite)
            prepared_suite.panel.assert_panel_header_controls()

        @scenario(
            "overview.shows_empty_state",
            "Confirms the panel cards section shows the empty-state text when no devices have been created yet.",
        )
        def it_shows_empty_state(prepared_suite):
            _open_panel(prepared_suite)
            prepared_suite.panel.assert_empty_state(
                "No devices found",
                "Add your first device to get started",
            )

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_stored_codes():
        @scenario(
            "stored_codes.hidden_when_empty",
            'Confirms the "Existing codes in Home Assistant" section stays hidden when Home Assistant has no previously learned codes.',
        )
        def it_hides_stored_codes_section_when_empty(prepared_suite):
            _remove_stored_codes_fixture(prepared_suite)
            _open_panel(prepared_suite)
            prepared_suite.panel.reload_stored_codes()
            prepared_suite.panel.assert_stored_codes_hidden()
            assert prepared_suite.call_ws("whispeer/get_stored_codes")["codes"] == []

        @scenario(
            "stored_codes.groups_existing_codes",
            "Injects previously learned Home Assistant codes without using the Whispeer UI and verifies the panel groups them by device.",
        )
        def it_groups_existing_stored_codes_by_device(prepared_suite):
            _write_stored_codes_fixture(prepared_suite)
            _open_panel(prepared_suite)
            prepared_suite.panel.reload_stored_codes()

            backend_codes = prepared_suite.call_ws("whispeer/get_stored_codes")["codes"]
            assert len(backend_codes) == sum(
                len(commands) for commands in STORED_CODES_EXPECTED_GROUPS.values()
            )

            groups = prepared_suite.panel.stored_code_groups()
            assert set(groups) == set(STORED_CODES_EXPECTED_GROUPS)
            for device_name, commands in STORED_CODES_EXPECTED_GROUPS.items():
                assert sorted(groups[device_name]) == sorted(commands)

            _remove_stored_codes_fixture(prepared_suite)
            prepared_suite.panel.reload_stored_codes()
            prepared_suite.panel.assert_stored_codes_hidden()

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_device_modal():
        @scenario(
            "device_modal.renders_core_fields",
            "Opens the add-device modal and checks core input fields (name, domain, type) render correctly.",
        )
        def it_renders_core_fields(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.assert_core_fields()
            modal.cancel()

        @scenario(
            "device_modal.type_conditionals.rf",
            "Selects RF type and checks that the frequency field is visible and community code input is hidden.",
        )
        def it_rf_shows_frequency_and_hides_community_code(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_type("rf")
            modal.wait_for_interface(RF_INTERFACE["label"])
            modal.assert_frequency_visible(True)
            modal.assert_community_code_visible(False)
            modal.cancel()

        @scenario(
            "device_modal.type_conditionals.ir",
            "Selects IR type and checks that community code input appears while frequency is hidden.",
        )
        def it_ir_hides_frequency_and_shows_community_code(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_domain("fan")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.assert_frequency_visible(False)
            modal.assert_community_code_visible(True)
            modal.cancel()

        @scenario(
            "device_modal.type_conditionals.ble",
            "Selects BLE type and verifies available HCI BLE interfaces are listed in the modal.",
        )
        def it_ble_lists_hci_interfaces(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_type("ble")
            modal.wait_for_interface(BLE_INTERFACE["label"])
            modal.cancel()

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_device_creation():
        @scenario(
            "device_creation.default.ir",
            "Creates a default IR device with all default command types and ensures it appears in the device list.",
        )
        def it_creates_default_ir_device_with_all_command_types(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(DEFAULT_IR_DEVICE_NAME)
            modal.select_domain("default")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.add_command_rows(len(DEFAULT_DOMAIN_COMMAND_SPECS))
            for index, spec in enumerate(DEFAULT_DOMAIN_COMMAND_SPECS):
                modal.configure_default_command(index, spec)
            modal.save()
            prepared_suite.panel.wait_for_device_card(DEFAULT_IR_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)
            assert DEFAULT_IR_DEVICE_NAME in prepared_suite.created_devices

        @scenario(
            "device_creation.default.rf",
            "Creates a default RF device, sets frequency, and verifies the device persists with correct frequency.",
        )
        def it_creates_default_rf_device_with_all_command_types(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(DEFAULT_RF_DEVICE_NAME)
            modal.select_domain("default")
            modal.select_type("rf")
            modal.wait_for_interface(RF_INTERFACE["label"])
            modal.select_first_interface()
            modal.set_frequency(RF_FREQUENCY)
            modal.add_command_rows(len(DEFAULT_DOMAIN_COMMAND_SPECS))
            for index, spec in enumerate(DEFAULT_DOMAIN_COMMAND_SPECS):
                modal.configure_default_command(index, spec)
            modal.save()
            prepared_suite.panel.wait_for_device_card(DEFAULT_RF_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)
            assert prepared_suite.created_devices[DEFAULT_RF_DEVICE_NAME]["frequency"] == pytest.approx(RF_FREQUENCY)

        @scenario(
            "device_creation.default.rf_fast_learn",
            'Creates a default RF device named "garage 315 fast learn", auto-fills 315 MHz from the Broadlink sweep, learns open/close with fast learn, and saves it.',
        )
        def it_creates_garage_rf_device_with_fast_learn(prepared_suite):
            prepared_suite.call_ws("whispeer/test/configure", config={"clear_journal": True})
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(GARAGE_FAST_LEARN_DEVICE_NAME)
            modal.select_domain("default")
            modal.select_type("rf")
            modal.wait_for_interface(RF_INTERFACE["label"])
            modal.select_first_interface()
            modal.set_command_name(0, "open")
            modal.start_fast_learn_once(GARAGE_FAST_LEARN_CODES[0])
            modal.wait_for_frequency_value(GARAGE_RF_FREQUENCY)

            modal.add_command_rows(2)
            modal.set_command_name(1, "close")
            modal.start_fast_learn_once(GARAGE_FAST_LEARN_CODES[1])
            modal.save()
            prepared_suite.panel.wait_for_device_card(GARAGE_FAST_LEARN_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)

            device = prepared_suite.created_devices[GARAGE_FAST_LEARN_DEVICE_NAME]
            assert device["frequency"] == pytest.approx(GARAGE_RF_FREQUENCY)
            assert device["commands"]["open"]["values"]["code"] == GARAGE_FAST_LEARN_CODES[0]
            assert device["commands"]["close"]["values"]["code"] == GARAGE_FAST_LEARN_CODES[1]
            assert device["emitter"]["entity_id"] == RF_INTERFACE["entity_id"]

            state = prepared_suite.call_ws("whispeer/test/get_state")
            assert any(
                entry.get("category") == "frequency"
                and entry.get("action") == "override_selected"
                for entry in state.get("journal", [])
            )
            assert len(
                [
                    entry
                    for entry in state.get("journal", [])
                    if entry.get("category") == "learn"
                    and entry.get("action") == "override_selected"
                ]
            ) >= 2

        @scenario(
            "device_creation.scratch.climate",
            "Builds a scratch climate IR device for 16, 24, and 30 degrees, uses fast learn for the cool/slow column, learns the remaining cells and off command, switches between learn and test mode, verifies three preview sends reach the backend, and saves the device.",
        )
        def it_creates_scratch_climate_device_with_discrete_temperatures(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(SCRATCH_CLIMATE_DEVICE_NAME)
            modal.select_domain("climate")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.set_climate_modes(CLIMATE_MODES)
            modal.set_climate_fan_modes(CLIMATE_FAN_MODES)
            modal.set_climate_temperature_list(CLIMATE_TEMPERATURES)
            modal.generate_climate_table()
            modal.assert_climate_table(
                modes=CLIMATE_MODES,
                fan_modes=CLIMATE_FAN_MODES,
                temperatures=CLIMATE_TEMPERATURES,
            )
            modal.assert_climate_mode_toggle("learn mode")
            modal.start_climate_fast_learn(
                mode="cool",
                fan_mode="slow",
                expected_codes_by_temperature={
                    temperature: _climate_cell_code("cool", "slow", temperature)
                    for temperature in CLIMATE_TEMPERATURES
                },
            )
            for mode, fan_mode, temperature in CLIMATE_MANUAL_LEARN_CELLS:
                modal.learn_climate_cell(
                    mode=mode,
                    fan_mode=fan_mode,
                    temperature=temperature,
                    expected_code=_climate_cell_code(mode, fan_mode, temperature),
                )
            modal.learn_climate_off(CLIMATE_OFF_CODE)

            prepared_suite.call_ws("whispeer/test/configure", config={"clear_journal": True})
            modal.toggle_climate_mode()
            modal.assert_climate_mode_toggle("test mode")
            for mode, fan_mode, temperature in CLIMATE_TEST_MODE_CELLS:
                modal.click_climate_cell(
                    mode=mode,
                    fan_mode=fan_mode,
                    temperature=temperature,
                )
                prepared_suite.panel.wait_for_toast(
                    f"Sent: {mode} / {fan_mode} / {temperature}°C"
                )

            state = prepared_suite.call_ws("whispeer/test/get_state")
            preview_commands = [
                entry.get("details", {}).get("command_name")
                for entry in state.get("journal", [])
                if entry.get("category") == "api"
                and entry.get("action") == "send_command_requested"
                and entry.get("details", {}).get("device_id") == "preview"
            ]
            assert preview_commands == [
                f"{mode}_{fan_mode}_{temperature}"
                for mode, fan_mode, temperature in CLIMATE_TEST_MODE_CELLS
            ]

            modal.toggle_climate_mode()
            modal.assert_climate_mode_toggle("learn mode")
            modal.save()
            prepared_suite.panel.wait_for_device_card(SCRATCH_CLIMATE_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)

            device = prepared_suite.created_devices[SCRATCH_CLIMATE_DEVICE_NAME]
            assert device["config"]["modes"] == list(CLIMATE_MODES)
            assert device["config"]["fan_modes"] == list(CLIMATE_FAN_MODES)
            assert device["config"]["temperatures"] == list(CLIMATE_TEMPERATURES)
            assert device["commands"]["off"] == CLIMATE_OFF_CODE
            for mode, fan_mode, temperature in (*CLIMATE_FAST_LEARN_CELLS, *CLIMATE_MANUAL_LEARN_CELLS):
                assert device["table"][mode][fan_mode][str(temperature)] == _climate_cell_code(
                    mode,
                    fan_mode,
                    temperature,
                )
            for mode in CLIMATE_MODES:
                for fan_mode in CLIMATE_FAN_MODES:
                    assert sorted(
                        int(temp_key)
                        for temp_key in device["table"][mode][fan_mode].keys()
                    ) == list(CLIMATE_TEMPERATURES)

            climate_card = prepared_suite.panel.device_card(SCRATCH_CLIMATE_DEVICE_NAME)
            assert climate_card.locator(
                "[data-climate-temps] .btn-group-item"
            ).all_inner_texts() == [str(temperature) for temperature in CLIMATE_TEMPERATURES]

        @scenario(
            "device_creation.community.climate",
            "Imports a SmartIR community climate code ('1000') and saves a climate device via the modal.",
        )
        def it_creates_climate_from_code_1000(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(COMMUNITY_DEVICE_NAMES["climate"])
            modal.select_domain("climate")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.import_community_code("1000", "climate")
            modal.save()
            prepared_suite.panel.wait_for_device_card(COMMUNITY_DEVICE_NAMES["climate"])
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.community.fan",
            "Imports a SmartIR community fan code ('1000') and saves a fan device via the modal.",
        )
        def it_creates_fan_from_code_1000(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(COMMUNITY_DEVICE_NAMES["fan"])
            modal.select_domain("fan")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.import_community_code("1000", "fan")
            modal.save()
            prepared_suite.panel.wait_for_device_card(COMMUNITY_DEVICE_NAMES["fan"])
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.community.light",
            "Imports a SmartIR community light code ('1000') and saves a light device via the modal.",
        )
        def it_creates_light_from_code_1000(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(COMMUNITY_DEVICE_NAMES["light"])
            modal.select_domain("light")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.import_community_code("1000", "light")
            modal.save()
            prepared_suite.panel.wait_for_device_card(COMMUNITY_DEVICE_NAMES["light"])
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.community.media_player",
            "Imports a SmartIR community media player code ('1000') and saves a media player device via the modal.",
        )
        def it_creates_media_player_from_code_1000(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(COMMUNITY_DEVICE_NAMES["media_player"])
            modal.select_domain("media_player")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.select_first_interface()
            modal.import_community_code("1000", "media_player")
            modal.save()
            prepared_suite.panel.wait_for_device_card(COMMUNITY_DEVICE_NAMES["media_player"])
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.ble.fan",
            "Creates a BLE fan device using the BLE scanner modal and learned advertisements for speed cells.",
        )
        def it_creates_ble_fan_device_from_scanner(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(BLE_FAN_DEVICE_NAME)
            modal.select_domain("fan")
            modal.select_type("ble")
            modal.wait_for_interface(BLE_INTERFACE["label"])
            modal.select_first_interface()
            modal.generate_fan_structure(("low", "medium", "high"))
            for cell_key, advertisement_key in (
                ("__off__", "fan_off"),
                ("__speed_low__", "fan_low"),
                ("__speed_medium__", "fan_medium"),
                ("__speed_high__", "fan_high"),
            ):
                scanner = modal.learn_fan_cell(cell_key)
                scanner.inject_advertisements([BLE_ADVERTISEMENTS[advertisement_key]])
                scanner.use_advertisement(BLE_ADVERTISEMENTS[advertisement_key]["address"])
            modal.save()
            prepared_suite.panel.wait_for_device_card(BLE_FAN_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.ble.default",
            'Creates a BLE "xmas" default device by learning on/off advertisements and saving the device.',
        )
        def it_creates_ble_default_device_from_scanner(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.fill_name(BLE_DEFAULT_DEVICE_NAME)
            modal.select_domain("default")
            modal.select_type("ble")
            modal.wait_for_interface(BLE_INTERFACE["label"])
            modal.select_first_interface()
            container = modal.command_container(0)
            container.get_by_test_id("command-type-select").select_option("light")
            container = modal.command_container(0)
            container.get_by_test_id("command-name-input").fill("lights")
            scanner = modal.learn_option_command(0, 0)
            scanner.inject_advertisements([BLE_ADVERTISEMENTS["lights_on"]])
            scanner.use_advertisement(BLE_ADVERTISEMENTS["lights_on"]["address"])
            scanner = modal.learn_option_command(0, 1)
            scanner.inject_advertisements([BLE_ADVERTISEMENTS["lights_off"]])
            scanner.use_advertisement(BLE_ADVERTISEMENTS["lights_off"]["address"])
            modal.save()
            prepared_suite.panel.wait_for_device_card(BLE_DEFAULT_DEVICE_NAME)
            _reload_panel_and_store_devices(prepared_suite)

        @scenario(
            "device_creation.expected_list",
            "Asserts the panel shows the full set of expected device names after creation.",
        )
        def it_shows_expected_device_list(prepared_suite):
            _open_panel(prepared_suite)
            names = prepared_suite.panel.device_names()
            assert set(names) == set(EXPECTED_DEVICE_NAMES)
            assert len(names) == len(EXPECTED_DEVICE_NAMES)

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_cards_list():
        @scenario(
            "cards_list.clicks_all_controls_for_three_devices",
            "Selects three deterministic sample devices from the cards list, presses every card control, and verifies the backend receives every request.",
        )
        def it_clicks_all_controls_for_three_sample_devices(prepared_suite):
            _open_panel(prepared_suite)
            sampled_devices = _sample_device_names(
                EXPECTED_DEVICE_NAMES,
                seed=CARD_ACTION_SAMPLE_SEED,
            )
            prepared_suite.call_ws("whispeer/test/configure", config={"clear_journal": True})

            clicked_counts: dict[str, int] = {}
            for device_name in sampled_devices:
                clicked_counts[device_name] = prepared_suite.panel.click_all_card_controls(device_name)

            total_clicks = sum(clicked_counts.values())
            assert len(_wait_for_requested_backend_activity(prepared_suite, minimum=total_clicks)) >= total_clicks

        @scenario(
            "cards_list.edit_modal_tests_three_devices",
            "Opens three deterministic existing devices from the cards list, enters edit mode, presses every modal Test button, and verifies the backend receives every request.",
        )
        def it_clicks_all_edit_modal_test_buttons_for_three_devices(prepared_suite):
            _open_panel(prepared_suite)
            sampled_devices = _sample_device_names(
                [
                    DEFAULT_IR_DEVICE_NAME,
                    DEFAULT_RF_DEVICE_NAME,
                    GARAGE_FAST_LEARN_DEVICE_NAME,
                ],
                seed=EDIT_MODAL_SAMPLE_SEED,
            )
            prepared_suite.call_ws("whispeer/test/configure", config={"clear_journal": True})

            clicked_counts: dict[str, int] = {}
            for device_name in sampled_devices:
                modal = prepared_suite.panel.open_device_modal(device_name)
                clicked_counts[device_name] = modal.click_all_test_buttons()
                modal.cancel()

            state = prepared_suite.call_ws("whispeer/test/get_state")
            for device_name, clicked_count in clicked_counts.items():
                device_id = prepared_suite.created_devices[device_name]["id"]
                assert len(_api_send_entries(state, device_id=device_id)) >= clicked_count

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_panel_actions():
        @scenario(
            "panel_actions.default.power",
            "Executes the default 'power' command on a device and checks for a success toast in the UI.",
        )
        def it_executes_power_command(prepared_suite):
            _open_panel(prepared_suite)
            prepared_suite.panel.click_default_button_command(DEFAULT_IR_DEVICE_NAME, "power")
            prepared_suite.panel.wait_for_toast('Command "power" executed successfully')

        @scenario(
            "panel_actions.default.state_sync",
            "Verifies device card toggles and option group controls are visible and update as expected.",
        )
        def it_updates_toggle_and_group_state(prepared_suite):
            _open_panel(prepared_suite)
            ir_device = prepared_suite.created_devices[DEFAULT_IR_DEVICE_NAME]
            prepared_suite.panel.device_card(DEFAULT_IR_DEVICE_NAME).locator(
                f'[data-entity="{ir_device["id"]}:lamp"] .command-toggle'
            ).wait_for(state="visible", timeout=prepared_suite.settings.timeout_ms)
            prepared_suite.panel.device_card(DEFAULT_IR_DEVICE_NAME).locator(
                f'[data-command="mode"] [data-option="cool"]'
            ).wait_for(state="visible", timeout=prepared_suite.settings.timeout_ms)

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_other_devices():
        @scenario(
            "other_devices.lists_all_created_devices",
            'Opens Home Assistant\'s "Other Devices" view and ensures every created device is listed.',
        )
        def it_lists_all_created_devices(prepared_suite):
            _open_other_devices(prepared_suite)
            for device_name in EXPECTED_DEVICE_NAMES:
                prepared_suite.other_devices.wait_for_device(device_name)

        @scenario(
            "other_devices.shows_expected_controls",
            "Checks the official UI exposes switches, spinbuttons, and other controls for the devices.",
        )
        def it_shows_buttons_switches_selects_and_numbers(prepared_suite):
            _open_other_devices(prepared_suite)
            summary = prepared_suite.other_devices.global_control_summary()
            assert summary["switches"] >= 6
            assert summary["spinbuttons"] >= 1

            assert prepared_suite.other_devices.switch_count(DEFAULT_IR_DEVICE_NAME) >= 2
            assert prepared_suite.other_devices.switch_count(DEFAULT_RF_DEVICE_NAME) >= 2
            assert prepared_suite.other_devices.switch_count(COMMUNITY_DEVICE_NAMES["light"]) >= 1
            assert prepared_suite.other_devices.switch_count(BLE_DEFAULT_DEVICE_NAME) >= 1

        @scenario(
            "other_devices.changes_values",
            "Interacts with official UI controls to toggle device switches and click media player control.",
        )
        def it_changes_values_from_official_ui(prepared_suite):
            _apply_official_ui_changes(prepared_suite)

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_state_reflection():
        @scenario(
            "state_reflection.call_service_events",
            "Reads the test state via WebSocket to confirm 'call_service' events are present in the journal.",
        )
        def it_captures_call_service_events(prepared_suite):
            _apply_official_ui_changes_from_shell_route(prepared_suite)
            state = prepared_suite.call_ws("whispeer/test/get_state")
            assert state["enabled"] is True
            assert any(
                entry.get("category") == "call_service"
                and entry.get("action") == "event"
                for entry in state.get("journal", [])
            )

        @scenario(
            "state_reflection.panel_updates",
            "Confirms changes made in the official UI are reflected in the Whispeer panel device toggles.",
        )
        def it_reflects_other_devices_changes_in_whispeer(prepared_suite):
            _apply_official_ui_changes_from_shell_route(prepared_suite)
            _open_panel(prepared_suite)
            default_ir = prepared_suite.created_devices[DEFAULT_IR_DEVICE_NAME]
            ble_default = prepared_suite.created_devices[BLE_DEFAULT_DEVICE_NAME]
            prepared_suite.panel.assert_default_toggle_state(default_ir["id"], "lamp", True)
            prepared_suite.panel.assert_default_toggle_state(default_ir["id"], "outlet", True)
            prepared_suite.panel.assert_default_toggle_state(ble_default["id"], "lights", True)

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_advanced_modal():
        @scenario(
            "advanced_modal.export_devices",
            "Exports the learned devices from the Advanced modal, saves the download, and validates the JSON payload contains every created device and its commands.",
        )
        def it_exports_all_created_devices(prepared_suite, tmp_path):
            _open_panel(prepared_suite)
            advanced = prepared_suite.panel.open_settings_modal()
            export_path = advanced.export_devices(tmp_path / "whispeer-export.json")
            payload = json.loads(export_path.read_text(encoding="utf-8"))

            assert payload["version"] == 1
            exported_devices = payload["devices"]
            assert {device["name"] for device in exported_devices} == set(EXPECTED_DEVICE_NAMES)
            for device in exported_devices:
                assert device.get("commands") or device.get("table")

            ADVANCED_ARTIFACTS["export_file"] = export_path
            advanced.close()

        @scenario(
            "advanced_modal.clear_entities",
            'Uses the Advanced modal to clear Whispeer entities and verifies Home Assistant no longer has entities or devices registered under the "whispeer" prefix.',
        )
        def it_clears_all_whispeer_entities(prepared_suite):
            _open_panel(prepared_suite)
            advanced = prepared_suite.panel.open_settings_modal()
            advanced.clear_entities()

            assert _whispeer_entity_entries(prepared_suite) == []
            assert _whispeer_device_entries(prepared_suite) == []

            _open_panel(prepared_suite)
            assert set(prepared_suite.panel.device_names()) == set(EXPECTED_DEVICE_NAMES)

        @scenario(
            "advanced_modal.clear_devices",
            "Uses the Advanced modal to clear Whispeer devices and verifies both Whispeer and Home Assistant no longer list them.",
        )
        def it_clears_all_whispeer_devices(prepared_suite):
            _open_panel(prepared_suite)
            advanced = prepared_suite.panel.open_settings_modal()
            advanced.clear_devices()

            prepared_suite.panel.assert_empty_state(
                "No devices found",
                "Add your first device to get started",
            )
            _reload_panel_and_store_devices(prepared_suite)
            assert prepared_suite.created_devices == {}
            assert _whispeer_entity_entries(prepared_suite) == []
            assert _whispeer_device_entries(prepared_suite) == []

        @scenario(
            "advanced_modal.import_devices",
            "Uses the Advanced modal to import the previously exported JSON file and verifies the full expected device list is restored.",
        )
        def it_imports_devices_from_exported_json(prepared_suite):
            export_path = ADVANCED_ARTIFACTS.get("export_file")
            assert export_path is not None and export_path.exists()

            _open_panel(prepared_suite)
            advanced = prepared_suite.panel.open_settings_modal()
            advanced.import_devices(export_path)
            prepared_suite.panel.wait_for_toast("Import complete:")
            advanced.close()

            for device_name in EXPECTED_DEVICE_NAMES:
                prepared_suite.panel.wait_for_device_card(device_name)
            _reload_panel_and_store_devices(prepared_suite)
            assert set(prepared_suite.created_devices) == set(EXPECTED_DEVICE_NAMES)

        @scenario(
            "advanced_modal.closes",
            "Opens the Advanced modal and closes it with the header close button.",
        )
        def it_closes_the_advanced_modal(prepared_suite):
            _open_panel(prepared_suite)
            advanced = prepared_suite.panel.open_settings_modal()
            advanced.close()
