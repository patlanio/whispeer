"""Climate platform for Whispeer — IR-controlled AC units."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_DOMAIN_CLIMATE,
    DOMAIN,
    SIGNAL_WHISPEER_DATA_UPDATED,
    SIGNAL_WHISPEER_NEW_DEVICE,
)
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)

_HVAC_MODE_MAP: dict[str, HVACMode] = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
    "heat_cool": HVACMode.HEAT_COOL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Whispeer climate entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerClimate]:
        if device.get("domain") != DEVICE_DOMAIN_CLIMATE:
            return []
        uid = f"whispeer_{device['id']}_climate"
        if uid in registered:
            return []
        registered.add(uid)
        return [WhispeerClimate(device, api)]

    devices = await api.async_get_devices()
    entities: list[WhispeerClimate] = []
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
        new: list[WhispeerClimate] = []
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


class WhispeerClimate(WhispeerBaseEntity, ClimateEntity):
    """Representation of an IR-controlled AC unit via Whispeer."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        # Use a synthetic "climate" command name so the base entity builds a
        # stable unique_id: whispeer_{device_id}_climate
        super().__init__(device_data, "climate", {}, api_client)

        config = device_data.get("config") or {}
        modes = config.get("modes") or ["cool", "heat", "fan_only"]
        fan_modes = config.get("fan_modes") or ["auto", "low", "mid", "high"]

        self._attr_hvac_modes = [HVACMode.OFF] + [
            _HVAC_MODE_MAP[m] for m in modes if m in _HVAC_MODE_MAP
        ]
        self._attr_fan_modes = fan_modes
        self._attr_min_temp = float(config.get("min_temp", 16))
        self._attr_max_temp = float(config.get("max_temp", 30))
        self._attr_target_temperature_step = 1.0

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = fan_modes[0] if fan_modes else "auto"
        self._attr_target_temperature = self._attr_min_temp

    # ------------------------------------------------------------------
    # State restoration
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _on_data_updated(_current_device_ids: set[str]) -> None:
            """Refresh device_data from storage when devices are saved."""
            self.hass.async_create_task(self._async_refresh_device_data())

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_WHISPEER_DATA_UPDATED, _on_data_updated
            )
        )

        last = await self.async_get_last_state()
        if last is None:
            return
        if last.state and last.state not in ("unavailable", "unknown"):
            if last.state == HVACMode.OFF:
                self._attr_hvac_mode = HVACMode.OFF
            else:
                for k, v in _HVAC_MODE_MAP.items():
                    if v == last.state or k == last.state:
                        self._attr_hvac_mode = v
                        break
        attrs = last.attributes
        if "fan_mode" in attrs:
            self._attr_fan_mode = attrs["fan_mode"]
        if "temperature" in attrs:
            try:
                self._attr_target_temperature = float(attrs["temperature"])
            except (ValueError, TypeError):
                pass
        self.async_write_ha_state()

    async def _async_refresh_device_data(self) -> None:
        """Reload device JSON from storage so table codes stay current."""
        device_id = self._device_data["id"]
        all_devices = await self._api.async_get_devices()
        for dev in all_devices:
            if dev["id"] == device_id:
                self._device_data = dev
                _LOGGER.debug("WhispeerClimate %s: device_data refreshed", device_id)
                return

    # ------------------------------------------------------------------
    # HA climate interface
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            code = (self._device_data.get("commands") or {}).get("off", "")
            if code:
                await self._async_send_code(code)
            self._attr_hvac_mode = HVACMode.OFF
        else:
            mode_key = _mode_key(hvac_mode)
            code = self._resolve_code(mode_key, self._attr_fan_mode, self._attr_target_temperature)
            if code:
                await self._async_send_code(code)
            self._attr_hvac_mode = hvac_mode

        self.async_write_ha_state()
        self._fire_state_update()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        self._attr_target_temperature = temp
        if self._attr_hvac_mode != HVACMode.OFF:
            mode_key = _mode_key(self._attr_hvac_mode)
            code = self._resolve_code(mode_key, self._attr_fan_mode, temp)
            if code:
                await self._async_send_code(code)
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        if self._attr_hvac_mode != HVACMode.OFF:
            mode_key = _mode_key(self._attr_hvac_mode)
            code = self._resolve_code(mode_key, fan_mode, self._attr_target_temperature)
            if code:
                await self._async_send_code(code)
        self.async_write_ha_state()
        self._fire_state_update()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_code(self, mode: str, fan: str, temp: float | None) -> str:
        """Look up the IR code for a given mode / fan / temperature combo."""
        table = self._device_data.get("table") or {}
        by_fan = table.get(mode) or {}
        by_temp = by_fan.get(fan) or {}
        if temp is not None:
            return by_temp.get(str(int(temp)), "")
        return ""

    def _fire_state_update(self) -> None:
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "climate",
            "state": self._attr_hvac_mode,
        })


def _mode_key(hvac_mode: HVACMode) -> str:
    """Return the SmartIR-compatible mode string for a given HVACMode."""
    for k, v in _HVAC_MODE_MAP.items():
        if v == hvac_mode:
            return k
    return str(hvac_mode)
