"""Fan platform for Whispeer — IR-controlled fans."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_DOMAIN_FAN,
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
    """Set up Whispeer fan entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerFan]:
        if device.get("domain") != DEVICE_DOMAIN_FAN:
            return []
        uid = f"whispeer_{device['id']}_fan"
        if uid in registered:
            return []
        registered.add(uid)
        return [WhispeerFan(device, api)]

    devices = await api.async_get_devices()
    entities: list[WhispeerFan] = []
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
        new: list[WhispeerFan] = []
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


class WhispeerFan(WhispeerBaseEntity, FanEntity):
    """Representation of an IR-controlled fan via Whispeer.

    Supports two models defined by device config:
    - ``direct``: one IR code per discrete speed preset.
    - ``incremental``: a single code that advances speed by one step;
      the entity cycles from off and sends it N times to reach the target.
    """

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        super().__init__(device_data, "fan", {}, api_client)
        self._attr_has_entity_name = False
        self._attr_name = device_data.get("name", device_data.get("id", "fan"))
        self._config = device_data.get("config") or {}
        self._commands = device_data.get("commands") or {}
        self._fan_model: str = self._config.get("fan_model", "direct")
        self._speeds: list[str] = self._config.get("speeds", [])
        self._speed_codes: dict[str, str] = self._extract_speed_codes(self._commands)
        self._speeds_count: int = int(self._config.get("speeds_count", 3))
        self._current_preset: str | None = None
        self._current_level: int = 0
        self._is_on: bool = False

        base_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

        if self._fan_model == "direct" and not self._speeds:
            self._speeds = list(self._speed_codes.keys())

        if self._fan_model == "incremental":
            self._attr_supported_features = base_features | FanEntityFeature.SET_SPEED
            self._attr_percentage_step = 100.0 / self._speeds_count
        else:
            self._attr_supported_features = base_features | FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = self._speeds

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        return self._current_preset

    @property
    def percentage(self) -> int | None:
        if self._fan_model != "incremental":
            return None
        if self._current_level == 0:
            return 0
        return round(self._current_level / self._speeds_count * 100)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if self._fan_model == "incremental":
            target = 1 if percentage is None else max(1, round(percentage / 100 * self._speeds_count))
            await self._async_set_incremental_level(target)
        else:
            speed = preset_mode or (self._speeds[0] if self._speeds else None)
            if speed:
                await self.async_set_preset_mode(speed)

    async def async_turn_off(self, **kwargs: Any) -> None:
        code = self._commands.get("off")
        if code:
            await self._async_send_code(code)
        self._is_on = False
        self._current_preset = None
        self._current_level = 0
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        code = self._speed_codes.get(preset_mode)
        if not code:
            _LOGGER.warning("No IR code for fan speed '%s'", preset_mode)
            return
        await self._async_send_code(code)
        self._is_on = True
        self._current_preset = preset_mode
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_set_percentage(self, percentage: int) -> None:
        target = round(percentage / 100 * self._speeds_count)
        if target == 0:
            await self.async_turn_off()
        else:
            await self._async_set_incremental_level(target)

    async def _async_set_incremental_level(self, target: int) -> None:
        """Send OFF then tap the speed button N times to reach the target level."""
        code = self._commands.get("speed")
        if not code:
            _LOGGER.warning("No incremental speed code learned for this fan")
            return
        off_code = self._commands.get("off")
        if off_code:
            await self._async_send_code(off_code)
            await asyncio.sleep(0.4)
        for i in range(target):
            await self._async_send_code(code)
            if i < target - 1:
                await asyncio.sleep(0.4)
        self._is_on = target > 0
        self._current_level = target
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("off", "unavailable", "unknown"):
            self._is_on = True
            if self._fan_model == "direct":
                self._current_preset = last_state.attributes.get("preset_mode")
            else:
                pct = last_state.attributes.get("percentage", 0) or 0
                self._current_level = round(pct / 100 * self._speeds_count)

    def _fire_state_update(self) -> None:
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "fan",
            "type": "fan",
            "state": "on" if self._is_on else "off",
            "attributes": {
                "preset_mode": self._current_preset,
                "percentage": self.percentage,
            },
        })

    @staticmethod
    def _extract_speed_codes(commands: dict[str, Any]) -> dict[str, str]:
        """Return direct fan speed codes from new and legacy schemas."""
        if not isinstance(commands, dict):
            return {}

        structured = commands.get("speeds")
        if isinstance(structured, dict):
            return {
                str(k): v
                for k, v in structured.items()
                if isinstance(v, str) and v
            }

        ignored = {"off", "speed", "forward", "reverse", "default", "speeds"}
        return {
            str(k): v
            for k, v in commands.items()
            if isinstance(v, str) and k not in ignored and v
        }
