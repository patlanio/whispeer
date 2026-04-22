"""Number platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_TYPE_NUMERIC, DOMAIN, SIGNAL_WHISPEER_NEW_DEVICE
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer number entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    devices = await api.async_get_devices()
    entities: list[WhispeerNumber] = []
    for device in devices:
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_NUMERIC:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                entities.append(WhispeerNumber(device, cmd_name, cmd_cfg, api))
                registered.add(uid)

    if entities:
        async_add_entities(entities)

    @callback
    def _async_add_new_entities(device_data: dict[str, Any]) -> None:
        new: list[WhispeerNumber] = []
        device_id = device_data["id"]
        for cmd_name, cmd_cfg in (device_data.get("commands") or {}).items():
            if cmd_cfg.get("type") == CMD_TYPE_NUMERIC:
                uid = f"whispeer_{device_id}_{cmd_name}"
                if uid not in registered:
                    new.append(WhispeerNumber(device_data, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_NEW_DEVICE, _async_add_new_entities
        )
    )


class WhispeerNumber(WhispeerBaseEntity, NumberEntity):
    """Representation of a Whispeer IR/RF numeric control (e.g. fan speed)."""

    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        api_client: Any,
    ) -> None:
        super().__init__(device_data, command_name, command_cfg, api_client)
        values = command_cfg.get("values") or {}
        numeric_keys = sorted(
            int(k) for k in values if k.lstrip("-").isdigit()
        )
        self._attr_native_min_value = float(numeric_keys[0]) if numeric_keys else 0
        self._attr_native_max_value = float(numeric_keys[-1]) if numeric_keys else 0
        self._attr_native_step = 1.0
        self._attr_native_value = self._attr_native_min_value

    async def async_set_native_value(self, value: float) -> None:
        """Send the code for the selected numeric level."""
        key = str(int(value))
        code = self._command_cfg.get("values", {}).get(key, "")
        if code:
            await self._async_send_code(code)
        self._attr_native_value = value
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "state": key,
            "type": "number",
        })
