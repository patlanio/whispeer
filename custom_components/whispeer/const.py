"""Constants for Whispeer."""

NAME = "Whispeer"
DOMAIN = "whispeer"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.1.0"

ATTRIBUTION = "Data provided by Whispeer"
ISSUE_URL = "https://github.com/patlanio/whispeer/issues"

ICON = "mdi:remote"

SIGNAL_WHISPEER_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_WHISPEER_DATA_UPDATED = f"{DOMAIN}_data_updated"

CMD_TYPE_BUTTON = "button"
CMD_TYPE_SWITCH = "switch"
CMD_TYPE_LIGHT = "light"
CMD_TYPE_NUMERIC = "numeric"
CMD_TYPE_GROUP = "group"
CMD_TYPE_OPTIONS = "options"
CMD_TYPE_CLIMATE = "climate"

DEVICE_DOMAIN_DEFAULT = "default"
DEVICE_DOMAIN_CLIMATE = "climate"
DEVICE_DOMAIN_FAN = "fan"
DEVICE_DOMAIN_MEDIA_PLAYER = "media_player"
DEVICE_DOMAIN_LIGHT = "light"

PLATFORMS = ["switch", "button", "light", "select", "number", "climate", "fan", "media_player"]

CONF_ENABLED = "enabled"

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
