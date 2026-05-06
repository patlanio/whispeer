"""Constants for Whispeer."""

# Base component constants
NAME = "Whispeer"
DOMAIN = "whispeer"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.1.0"

ATTRIBUTION = "Data provided by Whispeer"
ISSUE_URL = "https://github.com/patlanio/whispeer/issues"

# Icons
ICON = "mdi:remote"

# Dispatcher signals
SIGNAL_WHISPEER_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_WHISPEER_DATA_UPDATED = f"{DOMAIN}_data_updated"

# Command types (JSON command.type → HA platform)
CMD_TYPE_BUTTON = "button"
CMD_TYPE_SWITCH = "switch"
CMD_TYPE_LIGHT = "light"
# "numeric" renders as a NumberEntity (stepper/range).
CMD_TYPE_NUMERIC = "numeric"
# "group" renders as individual ButtonEntities — one per option value.
CMD_TYPE_GROUP = "group"
# "options" renders as a SelectEntity.
CMD_TYPE_OPTIONS = "options"
# "climate" renders as a ClimateEntity driven by an IR code table.
CMD_TYPE_CLIMATE = "climate"

# Device domains — decouple physical layer (type) from HA entity model.
DEVICE_DOMAIN_DEFAULT = "default"
DEVICE_DOMAIN_CLIMATE = "climate"
DEVICE_DOMAIN_FAN = "fan"
DEVICE_DOMAIN_MEDIA_PLAYER = "media_player"
DEVICE_DOMAIN_LIGHT = "light"

# Platforms
PLATFORMS = ["switch", "button", "light", "select", "number", "climate", "fan", "media_player"]

# Configuration and options
CONF_ENABLED = "enabled"

# Defaults
DEFAULT_NAME = DOMAIN

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
