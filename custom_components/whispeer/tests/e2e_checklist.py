from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class E2ECase:
    key: str
    title: str
    runner: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class E2ESection:
    key: str
    title: str
    children: tuple["E2ESection | E2ECase", ...]


def section(key: str, title: str, *children: E2ESection | E2ECase) -> E2ESection:
    return E2ESection(key=key, title=title, children=children)


def case(
    key: str,
    title: str,
    *,
    runner: str | None = None,
    enabled: bool = True,
) -> E2ECase:
    return E2ECase(key=key, title=title, runner=runner, enabled=enabled)


def iter_e2e_cases(
    sections: tuple[E2ESection, ...],
    path: tuple[E2ESection, ...] = (),
) -> Iterator[tuple[tuple[E2ESection, ...], E2ECase]]:
    for node in sections:
        current_path = (*path, node)
        for child in node.children:
            if isinstance(child, E2ECase):
                yield current_path, child
                continue
            yield from iter_e2e_cases((child,), current_path)


E2E_CHECKLIST = (
    section(
        "overview",
        "overview",
        case(
            "opens_whispeer_panel",
            "Opens the Whispeer panel in Home Assistant and confirms the panel loads successfully.",
            runner="overview.opens_whispeer_panel",
        ),
        case(
            "shows_add_device_button",
            'Verifies the "Add device" button is visible in the panel shell UI.',
            runner="overview.shows_add_device_button",
        ),
        case(
            "shows_sidebar_and_header",
            'Checks that Home Assistant shows "Whispeer" in the sidebar and "Whispeer - Remote control made simple" in the header.',
            runner="overview.shows_sidebar_and_header",
        ),
        case(
            "shows_panel_header_controls",
            "Checks that the Whispeer header shows the logo, name, settings button, and add-device button.",
            runner="overview.shows_panel_header_controls",
        ),
        case(
            "shows_empty_state",
            "Confirms the panel cards section shows the empty-state text when no devices have been created yet.",
            runner="overview.shows_empty_state",
        ),
    ),
    section(
        "stored_codes",
        "stored codes",
        case(
            "hides_section_when_empty",
            'Confirms the "Existing codes in Home Assistant" section stays hidden when Home Assistant has no previously learned codes.',
            runner="stored_codes.hidden_when_empty",
        ),
        case(
            "groups_existing_codes_by_device",
            "Injects previously learned Home Assistant codes without using the Whispeer UI and verifies the panel groups them by device.",
            runner="stored_codes.groups_existing_codes",
        ),
    ),
    section(
        "device_modal",
        "device modal",
        case(
            "renders_core_fields",
            "Opens the add-device modal and checks core input fields (name, domain, type) render correctly.",
            runner="device_modal.renders_core_fields",
        ),
        section(
            "type_conditionals",
            "type conditionals",
            case(
                "rf_shows_frequency_and_hides_community_code",
                "Selects RF type and checks that the frequency field is visible and community code input is hidden.",
                runner="device_modal.type_conditionals.rf",
            ),
            case(
                "ir_hides_frequency_and_shows_community_code",
                "Selects IR type and checks that community code input appears while frequency is hidden.",
                runner="device_modal.type_conditionals.ir",
            ),
            case(
                "ble_lists_hci_interfaces",
                "Selects BLE type and verifies available HCI BLE interfaces are listed in the modal.",
                runner="device_modal.type_conditionals.ble",
            ),
        ),
    ),
    section(
        "device_creation",
        "device creation",
        section(
            "default_domain_devices",
            "default domain devices",
            case(
                "creates_ir_device_with_all_command_types",
                "Creates a default IR device with all default command types and ensures it appears in the device list.",
                runner="device_creation.default.ir",
            ),
            case(
                "creates_rf_device_with_all_command_types",
                "Creates a default RF device, sets frequency, and verifies the device persists with correct frequency.",
                runner="device_creation.default.rf",
            ),
            case(
                "creates_garage_rf_device_with_fast_learn",
                'Creates a default RF device named "garage 315 fast learn", auto-fills 315 MHz from the Broadlink sweep, learns open/close with fast learn, and saves it.',
                runner="device_creation.default.rf_fast_learn",
            ),
        ),
        section(
            "scratch_domain_devices",
            "scratch domain devices",
            case(
                "creates_scratch_climate_device_with_discrete_temperatures",
                "Builds a scratch climate IR device for 16, 24, and 30 degrees, uses fast learn for the cool/slow column, learns the remaining cells and off command, switches between learn and test mode, verifies three preview sends reach the backend, and saves the device.",
                runner="device_creation.scratch.climate",
            ),
        ),
        section(
            "community_devices",
            "community devices",
            case(
                "creates_climate_from_code_1000",
                "Imports a SmartIR community climate code ('1000') and saves a climate device via the modal.",
                runner="device_creation.community.climate",
            ),
            case(
                "creates_fan_from_code_1000",
                "Imports a SmartIR community fan code ('1000') and saves a fan device via the modal.",
                runner="device_creation.community.fan",
            ),
            case(
                "creates_light_from_code_1000",
                "Imports a SmartIR community light code ('1000') and saves a light device via the modal.",
                runner="device_creation.community.light",
            ),
            case(
                "creates_media_player_from_code_1000",
                "Imports a SmartIR community media player code ('1000') and saves a media player device via the modal.",
                runner="device_creation.community.media_player",
            ),
        ),
        section(
            "ble_devices",
            "ble devices",
            case(
                "creates_fan_device_from_ble_scanner",
                "Creates a BLE fan device using the BLE scanner modal and learned advertisements for speed cells.",
                runner="device_creation.ble.fan",
            ),
            case(
                "creates_default_device_from_ble_scanner",
                'Creates a BLE "xmas" default device by learning on/off advertisements and saving the device.',
                runner="device_creation.ble.default",
            ),
        ),
        case(
            "shows_expected_device_list",
            "Asserts the panel shows the full set of expected device names after creation.",
            runner="device_creation.expected_list",
        ),
    ),
    section(
        "cards_list",
        "cards list",
        case(
            "clicks_all_controls_for_three_devices",
            "Selects three deterministic sample devices from the cards list, presses every card control, and verifies the backend receives every request.",
            runner="cards_list.clicks_all_controls_for_three_devices",
        ),
        case(
            "edit_modal_tests_three_devices",
            "Opens three deterministic existing devices from the cards list, enters edit mode, presses every modal Test button, and verifies the backend receives every request.",
            runner="cards_list.edit_modal_tests_three_devices",
        ),
    ),
    section(
        "panel_actions",
        "panel actions",
        section(
            "default_device_card",
            "default device card",
            case(
                "executes_power_command",
                "Executes the default 'power' command on a device and checks for a success toast in the UI.",
                runner="panel_actions.default.power",
            ),
            case(
                "updates_toggle_and_group_state",
                "Verifies device card toggles and option group controls are visible and update as expected.",
                runner="panel_actions.default.state_sync",
            ),
        ),
    ),
    section(
        "other_devices",
        "other devices",
        case(
            "lists_all_created_devices",
            'Opens Home Assistant\'s "Other Devices" view and ensures every created device is listed.',
            runner="other_devices.lists_all_created_devices",
        ),
        case(
            "shows_buttons_switches_selects_and_numbers",
            "Checks the official UI exposes switches, spinbuttons, and other controls for the devices.",
            runner="other_devices.shows_expected_controls",
        ),
        case(
            "changes_values_from_official_ui",
            "Interacts with official UI controls to toggle device switches and click media player control.",
            runner="other_devices.changes_values",
        ),
    ),
    section(
        "state_reflection",
        "state reflection",
        case(
            "captures_call_service_events",
            "Reads the test state via WebSocket to confirm 'call_service' events are present in the journal.",
            runner="state_reflection.call_service_events",
        ),
        case(
            "reflects_other_devices_changes_in_whispeer",
            "Confirms changes made in the official UI are reflected in the Whispeer panel device toggles.",
            runner="state_reflection.panel_updates",
        ),
    ),
    section(
        "advanced_modal",
        "advanced modal",
        case(
            "exports_all_created_devices",
            "Exports the learned devices from the Advanced modal, saves the download, and validates the JSON payload contains every created device and its commands.",
            runner="advanced_modal.export_devices",
        ),
        case(
            "clears_all_whispeer_entities",
            'Uses the Advanced modal to clear Whispeer entities and verifies Home Assistant no longer has entities or devices registered under the "whispeer" prefix.',
            runner="advanced_modal.clear_entities",
        ),
        case(
            "clears_all_whispeer_devices",
            "Uses the Advanced modal to clear Whispeer devices and verifies both Whispeer and Home Assistant no longer list them.",
            runner="advanced_modal.clear_devices",
        ),
        case(
            "imports_devices_from_exported_json",
            "Uses the Advanced modal to import the previously exported JSON file and verifies the full expected device list is restored.",
            runner="advanced_modal.import_devices",
        ),
        case(
            "closes_the_advanced_modal",
            "Opens the Advanced modal and closes it with the header close button.",
            runner="advanced_modal.closes",
        ),
    ),
)
