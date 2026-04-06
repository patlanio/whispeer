"""Button platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_TYPE_BUTTON, DOMAIN, SIGNAL_WHISPEER_NEW_DEVICE
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer button entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    devices = await api.async_get_devices()
    entities: list[WhispeerButton] = []
    for device in devices:
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_BUTTON:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                entities.append(WhispeerButton(device, cmd_name, cmd_cfg, api))
                registered.add(uid)

    if entities:
        async_add_entities(entities)

    @callback
    def _async_add_new_entities(device_data: dict[str, Any]) -> None:
        new: list[WhispeerButton] = []
        device_id = device_data["id"]
        for cmd_name, cmd_cfg in (device_data.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_BUTTON:
                uid = f"whispeer_{device_id}_{cmd_name}"
                if uid not in registered:
                    new.append(WhispeerButton(device_data, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_NEW_DEVICE, _async_add_new_entities
        )
    )


class WhispeerButton(WhispeerBaseEntity, ButtonEntity):
    """Representation of a Whispeer IR/RF button (single-press action)."""

    async def async_press(self) -> None:
        """Send the button code."""
        code = self._command_cfg.get("values", {}).get("code", "")
        if code:
            await self._async_send_code(code)
