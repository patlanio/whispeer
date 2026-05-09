"""Media player platform for Whispeer — IR-controlled TVs and AV receivers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_DOMAIN_MEDIA_PLAYER,
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
    """Set up Whispeer media player entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api

    registered: set[str] = set()

    def _entities_from_device(device: dict[str, Any]) -> list[WhispeerMediaPlayer]:
        if device.get("domain") != DEVICE_DOMAIN_MEDIA_PLAYER:
            return []
        uid = f"whispeer_{device['id']}_media_player"
        if uid in registered:
            return []
        registered.add(uid)
        return [WhispeerMediaPlayer(device, api)]

    devices = await api.async_get_devices()
    entities: list[WhispeerMediaPlayer] = []
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
        new: list[WhispeerMediaPlayer] = []
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


class WhispeerMediaPlayer(WhispeerBaseEntity, MediaPlayerEntity):
    """Representation of an IR-controlled media player via Whispeer."""

    def __init__(self, device_data: dict[str, Any], api_client: Any) -> None:
        super().__init__(device_data, "media_player", {}, api_client)
        self._attr_has_entity_name = False
        self._attr_name = device_data.get("name", device_data.get("id", "media_player"))
        self._commands = device_data.get("commands") or {}
        self._sources: list[str] = list((self._commands.get("sources") or {}).keys())
        self._is_on: bool = False
        self._current_source: str | None = None

        features = MediaPlayerEntityFeature(0)
        if self._commands.get("on") or self._commands.get("off"):
            features |= MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if self._commands.get("volumeUp") or self._commands.get("volumeDown"):
            features |= MediaPlayerEntityFeature.VOLUME_STEP
        if self._commands.get("mute"):
            features |= MediaPlayerEntityFeature.VOLUME_MUTE
        if self._commands.get("previousChannel"):
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        if self._commands.get("nextChannel"):
            features |= MediaPlayerEntityFeature.NEXT_TRACK
        if self._sources:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE

        self._attr_supported_features = features
        self._attr_source_list = self._sources

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self._is_on else MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        return self._current_source

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send("on")
        self._is_on = True
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send("off")
        self._is_on = False
        self.async_write_ha_state()
        self._fire_state_update()

    async def async_volume_up(self, **kwargs: Any) -> None:
        await self._send("volumeUp")

    async def async_volume_down(self, **kwargs: Any) -> None:
        await self._send("volumeDown")

    async def async_mute_volume(self, mute: bool, **kwargs: Any) -> None:
        await self._send("mute")

    async def async_media_previous_track(self, **kwargs: Any) -> None:
        await self._send("previousChannel")

    async def async_media_next_track(self, **kwargs: Any) -> None:
        await self._send("nextChannel")

    async def async_select_source(self, source: str, **kwargs: Any) -> None:
        codes = (self._commands.get("sources") or {}).get(source)
        if not codes:
            _LOGGER.warning("No IR code for source '%s'", source)
            return
        code_list = codes if isinstance(codes, list) else [codes]
        for i, code in enumerate(code_list):
            await self._async_send_code(code)
            if i < len(code_list) - 1:
                await asyncio.sleep(0.4)
        self._current_source = source
        self.async_write_ha_state()
        self._fire_state_update()

    async def _send(self, key: str) -> None:
        code = self._commands.get(key)
        if not code:
            _LOGGER.warning("No IR code learned for command '%s'", key)
            return
        await self._async_send_code(code)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state:
            self._is_on = last_state.state == MediaPlayerState.ON
            self._current_source = last_state.attributes.get("source")

    def _fire_state_update(self) -> None:
        self.hass.bus.async_fire("whispeer_state_update", {
            "entity_id": self.entity_id,
            "device_id": self._device_data["id"],
            "command_name": "media_player",
            "type": "media_player",
            "state": "on" if self._is_on else "off",
            "attributes": {
                "source": self._current_source,
            },
        })
