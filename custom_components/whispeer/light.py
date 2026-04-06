"""Light platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_TYPE_LIGHT, DOMAIN, SIGNAL_WHISPEER_NEW_DEVICE
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer light entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    devices = await api.async_get_devices()
    entities: list[WhispeerLight] = []
    for device in devices:
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_LIGHT:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                entities.append(WhispeerLight(device, cmd_name, cmd_cfg, api))
                registered.add(uid)

    if entities:
        async_add_entities(entities)

    @callback
    def _async_add_new_entities(device_data: dict[str, Any]) -> None:
        new: list[WhispeerLight] = []
        device_id = device_data["id"]
        for cmd_name, cmd_cfg in (device_data.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_LIGHT:
                uid = f"whispeer_{device_id}_{cmd_name}"
                if uid not in registered:
                    new.append(WhispeerLight(device_data, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_NEW_DEVICE, _async_add_new_entities
        )
    )


class WhispeerLight(WhispeerBaseEntity, LightEntity):
    """Representation of a Whispeer IR/RF light (on/off only)."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        api_client: Any,
    ) -> None:
        super().__init__(device_data, command_name, command_cfg, api_client)
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the ON code and update state optimistically."""
        code = self._command_cfg.get("values", {}).get("on", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the OFF code and update state optimistically."""
        code = self._command_cfg.get("values", {}).get("off", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = False
        self.async_write_ha_state()
