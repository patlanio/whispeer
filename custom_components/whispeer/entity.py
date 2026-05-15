"""Entity classes for Whispeer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME, VERSION
from .test_support import get_test_harness

_LOGGER = logging.getLogger(__name__)


class WhispeerBaseEntity(RestoreEntity):
    """Base entity for Whispeer command-driven entities.

    All command entities (switch, button, light, select) inherit from this
    class.  It provides:

    - A stable ``unique_id`` derived from *device_id* + *command_name*.
    - A shared ``DeviceInfo`` so every entity from the same JSON device object
      is grouped under one device in the HA device registry.
    - A helper ``_async_send_code`` that delegates to the API client.
    - ``should_poll = False`` — state is updated optimistically.
    - ``RestoreEntity`` support so the last persisted state is reloaded on
      startup without polling the (stateless) IR hardware.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        device_data: dict[str, Any],
        command_name: str,
        command_cfg: dict[str, Any],
        api_client: Any,
    ) -> None:
        device_id = device_data["id"]
        self._device_data = device_data
        self._command_name = command_name
        self._command_cfg = command_cfg
        self._api = api_client
        self._attr_unique_id = f"whispeer_{device_id}_{command_name}"
        self._attr_name = command_name

    @property
    def suggested_object_id(self) -> str:
        """Suggest an entity object_id with whispeer prefix and device name."""
        device_name = self._device_data.get("name", self._device_data["id"])
        return f"whispeer_{device_name}_{self._command_name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return DeviceInfo shared by every entity of the same physical device."""
        device_id = self._device_data["id"]
        emitter = self._device_data.get("emitter") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._device_data.get("name", device_id),
            manufacturer=emitter.get("manufacturer", NAME),
            model=emitter.get("model", "IR/RF Device"),
            sw_version=VERSION,
        )

    async def _async_send_code(self, code: str) -> None:
        """Send an IR / RF / BLE code through the configured emitter."""
        if getattr(self, "hass", None) is not None and getattr(self, "entity_id", None):
            get_test_harness(self.hass).record(
                "call_service",
                "event",
                domain=str(self.entity_id).split(".", 1)[0],
                entity_ids=[self.entity_id],
                device_id=self._device_data["id"],
                command_name=self._command_name,
            )

        emitter = self._device_data.get("emitter") or {}
        device_type = self._device_data.get("type", "ir")
        await self._api.async_send_command(
            device_id=self._device_data["id"],
            device_type=device_type,
            command_name=self._command_name,
            command_code=code,
            emitter_data=emitter,
        )


class WhispeerEntity(CoordinatorEntity):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return self.config_entry.entry_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
        }

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }
