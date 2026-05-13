from __future__ import annotations

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

DEFAULT_IR_DEVICE_NAME = "old stetero"
DEFAULT_RF_DEVICE_NAME = "old stetero rf"
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


def _configure_suite_mocks(suite) -> None:
    learn_codes = _default_domain_learn_codes()
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
                "queue": _build_learn_queue("ir", IR_INTERFACE["entity_id"], learn_codes)
                + _build_learn_queue("rf", RF_INTERFACE["entity_id"], learn_codes)
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
    suite.panel.open_direct(suite.access_token)


def _open_panel_shell(suite) -> None:
    suite.panel.open_direct(suite.access_token)


def _open_other_devices(suite) -> None:
    suite.other_devices.open(
        f"{suite.settings.base_url}/home/other-devices",
        access_token=suite.access_token,
    )


def _reload_panel_and_store_devices(suite) -> None:
    _open_panel(suite)
    devices = suite.call_ws("whispeer/get_devices")["devices"]
    suite.created_devices = {device["name"]: device for device in devices}


@pytest.fixture(scope="module", autouse=True)
def prepared_suite(whispeer_rspec_session):
    suite = whispeer_rspec_session
    _configure_suite_mocks(suite)
    _open_panel(suite)
    suite.panel.route_smartir_fixture_directory(SMARTIR_FIXTURE_DIR)
    _reload_panel_and_store_devices(suite)
    yield suite


def describe_whispeer_rspec():
    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_panel_shell():
        @scenario("panel_shell.opens_whispeer", "panel shell / opens /whispeer")
        def it_opens_whispeer(prepared_suite):
            _open_panel_shell(prepared_suite)
            prepared_suite.panel.wait_for_add_device_button()

        @scenario("panel_shell.shows_add_device_button", "panel shell / shows add device button")
        def it_shows_add_device_button(prepared_suite):
            _open_panel_shell(prepared_suite)
            prepared_suite.panel.wait_for_add_device_button()

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_device_modal():
        @scenario("device_modal.renders_core_fields", "device modal / renders core fields")
        def it_renders_core_fields(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.assert_core_fields()
            modal.cancel()

        @scenario("device_modal.type_conditionals.rf", "device modal / rf conditionals")
        def it_rf_shows_frequency_and_hides_community_code(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_type("rf")
            modal.wait_for_interface(RF_INTERFACE["label"])
            modal.assert_frequency_visible(True)
            modal.assert_community_code_visible(False)
            modal.cancel()

        @scenario("device_modal.type_conditionals.ir", "device modal / ir conditionals")
        def it_ir_hides_frequency_and_shows_community_code(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_domain("fan")
            modal.select_type("ir")
            modal.wait_for_interface(IR_INTERFACE["label"])
            modal.assert_frequency_visible(False)
            modal.assert_community_code_visible(True)
            modal.cancel()

        @scenario("device_modal.type_conditionals.ble", "device modal / ble interfaces")
        def it_ble_lists_hci_interfaces(prepared_suite):
            _open_panel(prepared_suite)
            modal = prepared_suite.panel.open_add_device_modal()
            modal.select_type("ble")
            modal.wait_for_interface(BLE_INTERFACE["label"])
            modal.cancel()

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_device_creation():
        @scenario("device_creation.default.ir", "device creation / default ir device")
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

        @scenario("device_creation.default.rf", "device creation / default rf device")
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

        @scenario("device_creation.community.climate", "device creation / community climate")
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

        @scenario("device_creation.community.fan", "device creation / community fan")
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

        @scenario("device_creation.community.light", "device creation / community light")
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

        @scenario("device_creation.community.media_player", "device creation / community media player")
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

        @scenario("device_creation.ble.fan", "device creation / ble fan")
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

        @scenario("device_creation.ble.default", "device creation / ble default xmas")
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

        @scenario("device_creation.expected_list", "device creation / expected device list")
        def it_shows_expected_device_list(prepared_suite):
            _open_panel(prepared_suite)
            names = prepared_suite.panel.device_names()
            assert set(names) == set(EXPECTED_DEVICE_NAMES)
            assert len(names) == len(EXPECTED_DEVICE_NAMES)

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_panel_actions():
        @scenario("panel_actions.default.power", "panel actions / default power command")
        def it_executes_power_command(prepared_suite):
            _open_panel(prepared_suite)
            prepared_suite.panel.click_default_button_command(DEFAULT_IR_DEVICE_NAME, "power")
            prepared_suite.panel.wait_for_toast('Command "power" executed successfully')

        @scenario("panel_actions.default.state_sync", "panel actions / default state sync")
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
        @scenario("other_devices.lists_all_created_devices", "other devices / lists all created devices")
        def it_lists_all_created_devices(prepared_suite):
            _open_other_devices(prepared_suite)
            for device_name in EXPECTED_DEVICE_NAMES:
                prepared_suite.other_devices.wait_for_device(device_name)

        @scenario("other_devices.shows_expected_controls", "other devices / shows expected controls")
        def it_shows_buttons_switches_selects_and_numbers(prepared_suite):
            _open_other_devices(prepared_suite)
            summary = prepared_suite.other_devices.global_control_summary()
            assert summary["switches"] >= 6
            assert summary["spinbuttons"] >= 1

            assert prepared_suite.other_devices.switch_count(DEFAULT_IR_DEVICE_NAME) >= 2
            assert prepared_suite.other_devices.switch_count(DEFAULT_RF_DEVICE_NAME) >= 2
            assert prepared_suite.other_devices.switch_count(COMMUNITY_DEVICE_NAMES["light"]) >= 1
            assert prepared_suite.other_devices.switch_count(BLE_DEFAULT_DEVICE_NAME) >= 1

        @scenario("other_devices.changes_values", "other devices / changes values from official ui")
        def it_changes_values_from_official_ui(prepared_suite):
            _open_other_devices(prepared_suite)
            prepared_suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "lamp")
            prepared_suite.other_devices.toggle_switch(DEFAULT_IR_DEVICE_NAME, "outlet")
            prepared_suite.other_devices.toggle_switch(BLE_DEFAULT_DEVICE_NAME, "lights")
            prepared_suite.other_devices.toggle_switch(COMMUNITY_DEVICE_NAMES["light"], COMMUNITY_DEVICE_NAMES["light"])
            prepared_suite.other_devices.click_button("Turn on")

    @pytest.mark.e2e
    @pytest.mark.slow
    def describe_state_reflection():
        @scenario("state_reflection.call_service_events", "state reflection / captures call_service events")
        def it_captures_call_service_events(prepared_suite):
            state = prepared_suite.call_ws("whispeer/test/get_state")
            assert state["enabled"] is True
            assert "config" in state

        @scenario("state_reflection.panel_updates", "state reflection / panel reflects other devices changes")
        def it_reflects_other_devices_changes_in_whispeer(prepared_suite):
            _open_panel(prepared_suite)
            ble_default = prepared_suite.created_devices[BLE_DEFAULT_DEVICE_NAME]
            prepared_suite.panel.assert_default_toggle_state(ble_default["id"], "lights", True)
