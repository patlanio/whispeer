"""Select platform for Whispeer.

Handles command type that produces a fixed option set:

- ``type: "options"``  — named options (e.g. ``warm``, ``neutral``, ``cold``).

Using SelectEntity enables the built-in ``select.select_next`` /
``select.select_previous`` services for free.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_TYPE_OPTIONS,
    DEVICE_DOMAIN_CLIMATE,
    DEVICE_DOMAIN_FAN,
    DEVICE_DOMAIN_MEDIA_PLAYER,
    DOMAIN,
    SIGNAL_WHISPEER_DATA_UPDATED,
    SIGNAL_WHISPEER_NEW_DEVICE,
)
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)

_SELECT_TYPES = {CMD_TYPE_OPTIONS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer select entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[SelectEntity]:
        result: list[SelectEntity] = []
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if not isinstance(cmd_cfg, dict):
                continue
            if cmd_cfg.get("type") in _SELECT_TYPES:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                if uid not in registered:
                    result.append(WhispeerSelect(device, cmd_name, cmd_cfg, api))
                    registered.add(uid)

        domain = device.get("domain")
        if domain == DEVICE_DOMAIN_MEDIA_PLAYER:
            sources = (device.get("commands") or {}).get("sources")
            if isinstance(sources, dict) and sources:
                uid = f"whispeer_{device['id']}_media_player_source"
                if uid not in registered:
                    result.append(WhispeerMediaPlayerSourceSelect(device, api))
                    registered.add(uid)

        if domain == DEVICE_DOMAIN_FAN:
            speeds = _extract_fan_speed_options(device)
            if speeds:
                uid = f"whispeer_{device['id']}_fan_speed"
                if uid not in registered:
                    result.append(WhispeerFanSpeedSelect(device, api, speeds))
                    registered.add(uid)

        if domain == DEVICE_DOMAIN_CLIMATE:
            fan_modes = list((device.get("config") or {}).get("fan_modes") or [])
            if fan_modes:
                uid = f"whispeer_{device['id']}_climate_fan_mode"
                if uid not in registered:
                    result.append(WhispeerClimateFanModeSelect(device, api, fan_modes))
                    registered.add(uid)

        return result

    devices = await api.async_get_devices()
    entities: list[SelectEntity] = []
    for device in devices:
        entities.extend(_entities_from_device(device))
    if entities:
        async_add_entities(entities)

    @callback
    def _on_new_device(device_data: dict[str, Any]) -> None:
        """Handle SIGNAL_WHISPEER_NEW_DEVICE — one new device arrived."""
        new = _entities_from_device(device_data)
        if new:
            async_add_entities(new)

    @callback
    def _on_data_updated(new_device_ids: set[str]) -> None:
        """Handle SIGNAL_WHISPEER_DATA_UPDATED — adds entities for new IDs.

        ``new_device_ids`` is the set of device IDs that were just added in
        this sync batch; __init__.py sends it so we only query the devices we
        actually need.
        """
        hass.async_create_task(_async_refresh(new_device_ids))

    async def _async_refresh(new_ids: set[str]) -> None:
        all_devices = await api.async_get_devices()
        new: list[SelectEntity] = []
        for device in all_devices:
            if device["id"] in new_ids:
                new.extend(_entities_from_device(device))
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_WHISPEER_NEW_DEVICE, _on_new_device)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_WHISPEER_DATA_UPDATED, _on_data_updated)
    )


class WhispeerSelect(WhispeerBaseEntity, SelectEntity):
    """A SelectEntity backed by a fixed list of IR/RF codes.

    Supports both named groups ('warm', 'neutral') and numeric step sets
    ('0', '1', '2', '6', '10').  The option list is always treated as
    strings so the UI is consistent regardless of underlying value type.

    State is restored from the recorder on startup via RestoreEntity so the
    last selected option survives a restart without polling the hardware.
    """

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        api_client: Any,
    ) -> None:
        super().__init__(device_data, command_name, command_cfg, api_client)
        values = command_cfg.get("values") or {}
        self._attr_options = [str(k) for k in values]
        self._attr_current_option = (
            self._attr_options[0] if self._attr_options else None
        )

    async def async_added_to_hass(self) -> None:
        """Restore last selected option from the recorder on startup."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        """Send the code for the selected option and update state optimistically."""
        code = self._command_cfg.get("values", {}).get(option, "")
        if code:
            await self._async_send_code(code)
        self._attr_current_option = option
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": self._command_name,
            "state": option,
            "type": "select",
        })


def _extract_fan_speed_options(device: dict[str, Any]) -> list[str]:
    """Return fan speed option labels from new and legacy command schemas."""
    cfg = device.get("config") or {}
    if isinstance(cfg.get("speeds"), list) and cfg.get("speeds"):
        return [str(s) for s in cfg.get("speeds")]

    commands = device.get("commands") or {}
    speeds_map = commands.get("speeds") if isinstance(commands.get("speeds"), dict) else None
    if speeds_map:
        return [str(k) for k in speeds_map.keys()]

    forward = commands.get("forward") if isinstance(commands.get("forward"), dict) else None
    if forward:
        return [str(k) for k in forward.keys() if str(k) not in {"off", "default", "speed", "forward", "reverse"}]

    return [
        str(k) for k, v in commands.items()
        if isinstance(v, str) and str(k) not in {"off", "default", "speed", "forward", "reverse", "sources"}
    ]


class WhispeerMediaPlayerSourceSelect(WhispeerBaseEntity, SelectEntity):
    """Select input/source for domain media_player devices."""

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        super().__init__(device_data, "media_player_source", {}, api_client)
        sources = (device_data.get("commands") or {}).get("sources") or {}
        self._sources = sources if isinstance(sources, dict) else {}
        self._attr_options = [str(k) for k in self._sources.keys()]
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        codes = self._sources.get(option)
        code_list = codes if isinstance(codes, list) else [codes]
        for code in code_list:
            if isinstance(code, str) and code:
                await self._async_send_code(code)
        self._attr_current_option = option
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "media_player",
            "state": option,
            "type": "select",
        })


class WhispeerFanSpeedSelect(WhispeerBaseEntity, SelectEntity):
    """Select fan speed for domain fan devices."""

    def __init__(
        self,
        device_data: dict[str, Any],
        api_client: Any,
        speed_options: list[str],
    ) -> None:
        super().__init__(device_data, "fan_speed", {}, api_client)
        self._attr_options = [str(s) for s in speed_options]
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        commands = self._device_data.get("commands") or {}
        speed_maps: list[dict[str, Any]] = []
        if isinstance(commands.get("speeds"), dict):
            speed_maps.append(commands.get("speeds"))
        if isinstance(commands.get("forward"), dict):
            speed_maps.append(commands.get("forward"))
        speed_maps.append(commands)

        code = ""
        for speed_map in speed_maps:
            raw = speed_map.get(option)
            if isinstance(raw, str) and raw:
                code = raw
                break
            if isinstance(raw, dict) and isinstance(raw.get("code"), str) and raw.get("code"):
                code = raw.get("code")
                break

        if code:
            await self._async_send_code(code)
        self._attr_current_option = option
        self.async_write_ha_state()
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "fan",
            "state": "on",
            "attributes": {
                "preset_mode": option,
            },
            "type": "fan",
        })


class WhispeerClimateFanModeSelect(WhispeerBaseEntity, SelectEntity):
    """Helper select to set climate fan mode from automations/device actions."""

    def __init__(
        self,
        device_data: dict[str, Any],
        api_client: Any,
        fan_modes: list[str],
    ) -> None:
        super().__init__(device_data, "climate_fan_mode", {}, api_client)
        self._attr_options = [str(m) for m in fan_modes]
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        registry = er.async_get(self.hass)
        target_uid = f"whispeer_{self._device_data['id']}_climate"
        target_entity_id = None
        for reg_entry in registry.entities.values():
            if reg_entry.platform == DOMAIN and (reg_entry.unique_id or "") == target_uid:
                target_entity_id = reg_entry.entity_id
                break

        if target_entity_id:
            await self.hass.services.async_call(
                "climate",
                "set_fan_mode",
                {"entity_id": target_entity_id, "fan_mode": option},
                blocking=True,
            )

        self._attr_current_option = option
        self.async_write_ha_state()

