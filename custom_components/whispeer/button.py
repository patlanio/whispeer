"""Button platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_TYPE_BUTTON,
    CMD_TYPE_GROUP,
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
    """Set up Whispeer button entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerButton]:
        result: list[WhispeerButton] = []
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            cmd_type = cmd_cfg.get("type")
            if cmd_type == CMD_TYPE_BUTTON:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                if uid not in registered:
                    result.append(WhispeerButton(device, cmd_name, cmd_cfg, api))
                    registered.add(uid)
            elif cmd_type == CMD_TYPE_GROUP:
                for option_key, option_code in (cmd_cfg.get("values") or {}).items():
                    uid = f"whispeer_{device['id']}_{cmd_name}_{option_key}"
                    if uid not in registered:
                        result.append(
                            WhispeerGroupButton(
                                device, cmd_name, cmd_cfg, option_key, option_code, api
                            )
                        )
                        registered.add(uid)
        return result

    devices = await api.async_get_devices()
    entities: list[WhispeerButton] = []
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
        new: list[WhispeerButton] = []
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


class WhispeerButton(WhispeerBaseEntity, ButtonEntity):
    """Representation of a Whispeer IR/RF button (single-press action).

    ButtonEntity has no persistent state to restore, but async_added_to_hass
    is still called so the super() chain works cleanly.
    """

    async def async_press(self) -> None:
        """Send the button code."""
        code = self._command_cfg.get("values", {}).get("code", "")
        if code:
            await self._async_send_code(code)
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "action": "press",
        })


class WhispeerGroupButton(WhispeerBaseEntity, ButtonEntity):
    """One ButtonEntity representing a single option inside a 'group' command.

    A 'group' command groups multiple IR/RF codes visually in the panel.
    Each option is exposed as an independent ButtonEntity in Home Assistant.
    """

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        option_key: str,
        option_code: str,
        api_client: Any,
    ) -> None:
        super().__init__(device_data, command_name, command_cfg, api_client)
        self._option_key = option_key
        self._option_code = option_code
        self._attr_unique_id = f"whispeer_{device_data['id']}_{command_name}_{option_key}"
        self._attr_name = f"{command_name} {option_key}"

    @property
    def suggested_object_id(self) -> str:
        """Suggest an entity object_id with whispeer prefix and device name."""
        device_name = self._device_data.get("name", self._device_data["id"])
        return f"whispeer_{device_name}_{self._command_name}_{self._option_key}"

    async def async_press(self) -> None:
        """Send the code for this option."""
        if self._option_code:
            await self._async_send_code(self._option_code)
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "option_key": self._option_key,
            "action": "press",
        })

