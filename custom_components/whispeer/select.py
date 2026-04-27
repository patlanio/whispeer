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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_TYPE_OPTIONS,
    DOMAIN,
    SIGNAL_WHISPEER_DATA_UPDATED,
    SIGNAL_WHISPEER_NEW_DEVICE,
)
from .entity import WhispeerBaseEntity

_LOGGER = logging.getLogger(__name__)

# Only the "options" command type is rendered as a SelectEntity.
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

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerSelect]:
        result: list[WhispeerSelect] = []
        for cmd_name, cmd_cfg in (device.get("commands") or {}).items():
            if not isinstance(cmd_cfg, dict):
                continue
            if cmd_cfg.get("type") in _SELECT_TYPES:
                uid = f"whispeer_{device['id']}_{cmd_name}"
                if uid not in registered:
                    result.append(WhispeerSelect(device, cmd_name, cmd_cfg, api))
                    registered.add(uid)
        return result

    # Load entities that already exist in storage.
    devices = await api.async_get_devices()
    entities: list[WhispeerSelect] = []
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
        new: list[WhispeerSelect] = []
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
        # Preserve insertion order (Python 3.7+).
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

