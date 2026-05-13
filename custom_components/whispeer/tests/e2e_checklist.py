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
        "panel_shell",
        "panel shell",
        case("opens_whispeer", "it opens /whispeer", runner="panel_shell.opens_whispeer"),
        case(
            "shows_add_device_button",
            "it shows the add device button",
            runner="panel_shell.shows_add_device_button",
        ),
    ),
    section(
        "device_modal",
        "device modal",
        case(
            "renders_core_fields",
            "it renders the core fields",
            runner="device_modal.renders_core_fields",
        ),
        section(
            "type_conditionals",
            "type conditionals",
            case(
                "rf_shows_frequency_and_hides_community_code",
                "rf shows frequency and hides community code",
                runner="device_modal.type_conditionals.rf",
            ),
            case(
                "ir_hides_frequency_and_shows_community_code",
                "ir hides frequency and shows community code",
                runner="device_modal.type_conditionals.ir",
            ),
            case(
                "ble_lists_hci_interfaces",
                "ble lists the mocked hci interfaces",
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
                "it creates a default ir device with all command types learned",
                runner="device_creation.default.ir",
            ),
            case(
                "creates_rf_device_with_all_command_types",
                "it creates a default rf device at 433.92 with all command types learned",
                runner="device_creation.default.rf",
            ),
        ),
        section(
            "community_devices",
            "community devices",
            case(
                "creates_climate_from_code_1000",
                "it creates the climate device from community code 1000",
                runner="device_creation.community.climate",
            ),
            case(
                "creates_fan_from_code_1000",
                "it creates the fan device from community code 1000",
                runner="device_creation.community.fan",
            ),
            case(
                "creates_light_from_code_1000",
                "it creates the light device from community code 1000",
                runner="device_creation.community.light",
            ),
            case(
                "creates_media_player_from_code_1000",
                "it creates the media player device from community code 1000",
                runner="device_creation.community.media_player",
            ),
        ),
        section(
            "ble_devices",
            "ble devices",
            case(
                "creates_fan_device_from_ble_scanner",
                "it creates a ble fan device from scanner picks",
                runner="device_creation.ble.fan",
            ),
            case(
                "creates_default_device_from_ble_scanner",
                "it creates a ble default-domain xmas device from scanner picks",
                runner="device_creation.ble.default",
            ),
        ),
        case(
            "shows_expected_device_list",
            "it shows the expected device list in the panel",
            runner="device_creation.expected_list",
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
                "it executes the power command and shows a toast",
                runner="panel_actions.default.power",
            ),
            case(
                "updates_toggle_and_group_state",
                "it updates toggle and grouped states after service changes",
                runner="panel_actions.default.state_sync",
            ),
        ),
    ),
    section(
        "other_devices",
        "other devices",
        case(
            "lists_all_created_devices",
            "it lists all created devices in /home/other-devices",
            runner="other_devices.lists_all_created_devices",
        ),
        case(
            "shows_buttons_switches_selects_and_numbers",
            "it shows buttons, switches, selects and numeric controls where expected",
            runner="other_devices.shows_expected_controls",
        ),
        case(
            "changes_values_from_official_ui",
            "it changes values from the official home assistant ui",
            runner="other_devices.changes_values",
        ),
    ),
    section(
        "state_reflection",
        "state reflection",
        case(
            "captures_call_service_events",
            "it captures call_service events while the official ui is used",
            runner="state_reflection.call_service_events",
        ),
        case(
            "reflects_other_devices_changes_in_whispeer",
            "it reflects those changes back in the whispeer panel",
            runner="state_reflection.panel_updates",
        ),
    ),
)