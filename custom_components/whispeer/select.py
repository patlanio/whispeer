"""Select platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_TYPE_GROUP, DOMAIN, SIGNAL_WHISPEER_NEW_DEVICE
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer select entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    devices = await api.async_get_devices()
    entities: list[WhispeerSelect] = []
    for device in devices:
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_GROUP:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                entities.append(WhispeerSelect(device, cmd_name, cmd_cfg, api))
                registered.add(uid)

    if entities:
        async_add_entities(entities)

    @callback
    def _async_add_new_entities(device_data: dict[str, Any]) -> None:
        new: list[WhispeerSelect] = []
        device_id = device_data["id"]
        for cmd_name, cmd_cfg in (device_data.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_GROUP:
                uid = f"whispeer_{device_id}_{cmd_name}"
                if uid not in registered:
                    new.append(WhispeerSelect(device_data, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_NEW_DEVICE, _async_add_new_entities
        )
    )


class WhispeerSelect(WhispeerBaseEntity, SelectEntity):
    """Representation of a Whispeer IR/RF group selector (e.g. light tone)."""

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        api_client: Any,
    ) -> None:
        super().__init__(device_data, command_name, command_cfg, api_client)
        values = command_cfg.get("values") or {}
        self._attr_options = list(values.keys())
        self._attr_current_option = (
            self._attr_options[0] if self._attr_options else None
        )

    async def async_select_option(self, option: str) -> None:
        """Send the code for the selected option."""
        code = self._command_cfg.get("values", {}).get(option, "")
        if code:
            await self._async_send_code(code)
        self._attr_current_option = option
        self.async_write_ha_state()
