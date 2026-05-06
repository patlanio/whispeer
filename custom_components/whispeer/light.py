"""Light platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_TYPE_LIGHT,
    DEVICE_DOMAIN_LIGHT,
    DOMAIN,
    SIGNAL_WHISPEER_DATA_UPDATED,
    SIGNAL_WHISPEER_NEW_DEVICE,
)
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

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerLight]:
        result: list[WhispeerLight] = []
        if device.get("domain") == DEVICE_DOMAIN_LIGHT:
            uid = f"whispeer_{device['id']}_domain_light"
            if uid not in registered:
                result.append(WhispeerDomainLight(device, api))
                registered.add(uid)
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if not isinstance(cmd_cfg, dict):
                continue
            if cmd_cfg.get("type") == CMD_TYPE_LIGHT:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                if uid not in registered:
                    result.append(WhispeerLight(device, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        return result

    devices = await api.async_get_devices()
    entities: list[WhispeerLight] = []
    for device in devices:
        entities.extend(_entities_from_device(device))
    if entities:
        async_add_entities(entities)

    @callback
    def _on_new_device(device_data: dict[str, Any]) -> None:
        new = _entities_from_device(device_data)
        if new:
            async_add_entities(new)

    @callback
    def _on_data_updated(current_device_ids: set[str]) -> None:
        hass.async_create_task(_async_refresh(current_device_ids))

    async def _async_refresh(known_ids: set[str]) -> None:
        all_devices = await api.async_get_devices()
        new: list[WhispeerLight] = []
        for device in all_devices:
            if device["id"] in known_ids:
                new.extend(_entities_from_device(device))
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_WHISPEER_NEW_DEVICE, _on_new_device)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_WHISPEER_DATA_UPDATED, _on_data_updated)
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

    async def async_added_to_hass(self) -> None:
        """Restore last state from the recorder on startup."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the ON code and update state optimistically."""
        code = self._command_cfg.get("values", {}).get("on", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "state": "on",
        })

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the OFF code and update state optimistically."""
        code = self._command_cfg.get("values", {}).get("off", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "state": "off",
        })


class WhispeerDomainLight(WhispeerBaseEntity, LightEntity):
    """Device-level IR light with incremental brightness/color-temp controls."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        super().__init__(device_data, "domain_light", {}, api_client)
        self._commands = device_data.get("commands") or {}
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        code = self._commands.get("on", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "domain_light",
            "type": "light",
            "state": "on",
        })

    async def async_turn_off(self, **kwargs: Any) -> None:
        code = self._commands.get("off", "")
        if code:
            await self._async_send_code(code)
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "domain_light",
            "type": "light",
            "state": "off",
        })

