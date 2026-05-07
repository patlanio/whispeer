[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]
[![Status][beta-shield]][releases]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

Remote control made easy for Home Assistant.

Whispeer provides a practical remote-learning workflow for IR, RF, and BLE devices, with direct Home Assistant learning integration and a synchronized control panel.

**Highlights**

- IR and RF learning using Home Assistant native learning services.
- Fast RF learning path for Broadlink devices.
- BLE scan and command emission support.
- Multi-domain entities: switch, button, light, select, number, climate, fan, and media_player.
- Bidirectional synchronization between Home Assistant and panel UI.

**Known limitation (beta)**

- BLE is not fully stable yet, but it works if you retry when needed.

**This integration sets up the following Home Assistant entity platforms.**

| Platform        | Description                         |
| --------------- | ----------------------------------- |
| `switch`        | Toggle-style remote commands.       |
| `button`        | Trigger instant commands.           |
| `light`         | Light control mappings.             |
| `select`        | Option-based command mappings.      |
| `number`        | Numeric value command mappings.     |
| `climate`       | HVAC command entities.              |
| `fan`           | Fan command entities.               |
| `media_player`  | Media command entities.             |

![Whispeer logo][logoimg]

{% if not installed %}

## Installation

1. In HACS go to Integrations -> menu (three dots) -> Custom repositories.
1. Add repository URL: https://github.com/patlanio/whispeer
1. Select category: Integration.
1. Install Whispeer from HACS.
1. Restart Home Assistant.
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Whispeer".

{% endif %}

## Configuration is done in the UI

<!---->

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[beta-shield]: https://img.shields.io/badge/status-beta%20testing-ff9800.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/patlanio
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/patlanio/whispeer.svg?style=for-the-badge
[commits]: https://github.com/patlanio/whispeer/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[logoimg]: whispeer.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license]: https://github.com/patlanio/whispeer/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/patlanio/whispeer.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40patlanio-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/patlanio/whispeer.svg?style=for-the-badge
[releases]: https://github.com/patlanio/whispeer/releases
[user_profile]: https://github.com/patlanio
