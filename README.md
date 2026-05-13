# Whispeer

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]
[![HACS Custom][hacsbadge]][hacs]
[![Status][beta-shield]][releases]
[![Project Maintenance][maintenance-shield]][user_profile]

Remote control made easy for Home Assistant.

Whispeer is a custom integration focused on building and using remote commands quickly, with a practical learning flow for IR, RF, and BLE devices.

![Whispeer logo][logoimg]

## Why Whispeer

- Unified remote-control experience in a dedicated panel.
- IR and RF learning integrated directly with Home Assistant native learning services.
- Fast RF path for Broadlink devices (frequency sweep + capture, or fast learn with known frequency).
- BLE support for scan, capture, and command emission workflows.
- Multi-domain entities in Home Assistant: switch, button, light, select, number, climate, fan, and media_player.
- Bidirectional synchronization between Home Assistant state and Whispeer panel UI.

## Beta Scope

Current beta focus:

- Remote learning and command management workflow reliability.
- Device/domain UX in the custom panel.
- End-to-end sync between backend state and frontend controls.

## Installation

1. Install from HACS (recommended) using Custom Repository:
	- HACS -> Integrations -> menu (three dots) -> Custom repositories.
	- Repository: https://github.com/patlanio/whispeer
	- Category: Integration
	- Add, then install Whispeer from HACS.
2. Restart Home Assistant.
3. Go to Settings -> Devices & Services -> Add Integration.
4. Search for Whispeer.
5. Manual install alternative: open your Home Assistant config directory (where configuration.yaml lives), create custom_components if needed, and copy this repository custom component folder into custom_components/whispeer.

Expected structure:

```text
custom_components/whispeer/__init__.py
custom_components/whispeer/api.py
custom_components/whispeer/config_flow.py
custom_components/whispeer/const.py
custom_components/whispeer/manifest.json
custom_components/whispeer/websocket.py
custom_components/whispeer/panel/index.html
custom_components/whispeer/panel/app.js
custom_components/whispeer/translations/nb.json
```

## Documentation

- HACS summary card: [info.md](info.md)
- Panel architecture notes: [custom_components/whispeer/panel/README.md](custom_components/whispeer/panel/README.md)
- Test workflow notes: [custom_components/whispeer/tests/README.md](custom_components/whispeer/tests/README.md)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Report issues: [GitHub Issues][issues]

## Development Test Flow

The repository test entrypoint is now a single command:

```bash
make test
```

That command runs the backend pytest suite first, then recreates the `hass-test` runtime and executes the websocket integration plus the one-window, one-tab Playwright flow against `http://localhost:8126`.

Useful debug targets still exist when you need to isolate a layer:

- `make fastest` for backend-only pytest
- `make e2e_master` for the full websocket + browser flow against `hass-test`
- `make e2e_master_dev` for the same browser flow against `hass-dev`

## Known Limitations

- BLE is not fully stable yet in this beta stage.
- BLE workflows do work, but you may need to retry when discovery or capture is inconsistent.

## Credits

Initially scaffolded from Home Assistant Cookiecutter and evolved into a Whispeer-specific integration and UI architecture.

---

[beta-shield]: https://img.shields.io/badge/status-beta%20testing-ff9800.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/patlanio/whispeer.svg?style=for-the-badge
[commits]: https://github.com/patlanio/whispeer/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[issues]: https://github.com/patlanio/whispeer/issues
[license]: https://github.com/patlanio/whispeer/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/patlanio/whispeer.svg?style=for-the-badge
[logoimg]: whispeer.png
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40patlanio-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/patlanio/whispeer.svg?style=for-the-badge
[releases]: https://github.com/patlanio/whispeer/releases
[user_profile]: https://github.com/patlanio
