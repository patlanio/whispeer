"""Number platform for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_TYPE_NUMERIC,
    DEVICE_DOMAIN_CLIMATE,
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
    """Set up Whispeer number entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[NumberEntity]:
        result: list[NumberEntity] = []
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if not isinstance(cmd_cfg, dict):
                continue
            if cmd_cfg.get("type") == CMD_TYPE_NUMERIC:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                if uid not in registered:
                    result.append(WhispeerNumber(device, cmd_name, cmd_cfg, api))
                    registered.add(uid)

        if device.get("domain") == DEVICE_DOMAIN_CLIMATE:
            uid = f"whispeer_{device['id']}_climate_temperature"
            if uid not in registered:
                result.append(WhispeerClimateTemperatureNumber(device, api))
                registered.add(uid)

        return result

    devices = await api.async_get_devices()
    entities: list[NumberEntity] = []
    for device in devices:
        entities.extend(_entities_from_device(device))

    if entities:
        async_add_entities(entities)

    @callback
    def _async_add_new_entities(device_data: dict[str, Any]) -> None:
        new = _entities_from_device(device_data)
        if new:
            async_add_entities(new)

    @callback
    def _on_data_updated(current_device_ids: set[str]) -> None:
        hass.async_create_task(_async_refresh(current_device_ids))

    async def _async_refresh(known_ids: set[str]) -> None:
        all_devices = await api.async_get_devices()
        new: list[NumberEntity] = []
        for device in all_devices:
            if device["id"] in known_ids:
                new.extend(_entities_from_device(device))
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_WHISPEER_NEW_DEVICE, _async_add_new_entities
        )
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_WHISPEER_DATA_UPDATED, _on_data_updated)
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


class WhispeerClimateTemperatureNumber(WhispeerBaseEntity, NumberEntity):
    """Helper NumberEntity to set temperature for climate domain devices."""

    _attr_mode = NumberMode.BOX

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        super().__init__(device_data, "climate_temperature", {}, api_client)
        cfg = device_data.get("config") or {}
        self._attr_native_min_value = float(cfg.get("min_temp", 16))
        self._attr_native_max_value = float(cfg.get("max_temp", 30))
        self._attr_native_step = 1.0
        self._attr_native_value = self._attr_native_min_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._attr_native_value = float(last.state)
            except (TypeError, ValueError):
                pass

    async def async_set_native_value(self, value: float) -> None:
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
                "set_temperature",
                {"entity_id": target_entity_id, "temperature": value},
                blocking=True,
            )

        self._attr_native_value = value
        self.async_write_ha_state()
