"""WebSocket command handlers for the Whispeer integration."""
from __future__ import annotations

import asyncio
import json as _json
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .learn_provider import LEARNING_SESSIONS

_LOGGER = logging.getLogger(__name__)


def _get_api(hass: HomeAssistant):
    """Return the first available WhispeerApiClient from hass.data."""
    domain_data = hass.data.get(DOMAIN, {})
    for entry_data in domain_data.values():
        if hasattr(entry_data, "api"):
            return entry_data.api
    return None


def _get_coordinator(hass: HomeAssistant):
    """Return (entry_id, coordinator) for the first available coordinator."""
    domain_data = hass.data.get(DOMAIN, {})
    for entry_id, entry_data in domain_data.items():
        if hasattr(entry_data, "api"):
            return entry_id, entry_data
    return None, None


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register all Whispeer WebSocket commands."""

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_devices",
    })
    @websocket_api.async_response
    async def ws_get_devices(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        devices = await api.async_get_devices()
        connection.send_result(msg["id"], {"devices": devices})

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/add_device",
        vol.Required("device"): dict,
    })
    @websocket_api.async_response
    async def ws_add_device(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_add_device(msg["device"])
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/remove_device",
        vol.Required("device_id"): str,
    })
    @websocket_api.async_response
    async def ws_remove_device(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_remove_device(msg["device_id"])
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/sync_devices",
        vol.Required("devices"): dict,
    })
    @websocket_api.async_response
    async def ws_sync_devices(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_sync_devices(msg["devices"])
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/clear_devices",
    })
    @websocket_api.async_response
    async def ws_clear_devices(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry_id, coordinator = _get_coordinator(hass)
        if not coordinator:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return

        entity_registry = er.async_get(hass)
        whispeer_entities = [
            entry.entity_id
            for entry in entity_registry.entities.values()
            if entry.platform == DOMAIN
        ]
        for eid in whispeer_entities:
            entity_registry.async_remove(eid)

        result = await coordinator.api.async_clear_devices()

        try:
            await hass.config_entries.async_reload(entry_id)
            result["reloaded"] = True
        except Exception as reload_err:
            _LOGGER.error(
                "Failed to reload entry %s after clear: %s", entry_id, reload_err
            )
            result["reloaded"] = False

        try:
            connection.send_result(msg["id"], result)
        except Exception:
            pass

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/send_command",
        vol.Required("device_id"): str,
        vol.Required("device_type"): str,
        vol.Required("command_name"): str,
        vol.Required("command_code"): str,
        vol.Optional("sub_command"): str,
        vol.Optional("emitter"): dict,
    })
    @websocket_api.async_response
    async def ws_send_command(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_send_command(
            msg["device_id"],
            msg["device_type"],
            msg["command_name"],
            msg["command_code"],
            msg.get("emitter"),
        )
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_automations",
    })
    @websocket_api.async_response
    async def ws_get_automations(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_result(
                msg["id"], {"automations": [], "device_automations": {}}
            )
            return

        devices = await api.async_get_devices()
        device_ids = [str(d["id"]) for d in devices]

        entity_registry = er.async_get(hass)
        uuid_to_device_id: dict[str, str] = {}
        for entry in entity_registry.entities.values():
            uid = entry.unique_id or ""
            if not uid.startswith("whispeer_"):
                continue
            parts = uid.split("_", 2)
            if len(parts) < 3:
                continue
            did = parts[1]
            if did in device_ids:
                uuid_to_device_id[entry.id] = did

        config_dir = hass.config.config_dir
        storage_path = os.path.join(config_dir, ".storage", "core.automation")

        def _read_automation_configs():
            configs = []
            yaml_path = os.path.join(config_dir, "automations.yaml")
            try:
                import yaml
                with open(yaml_path, "r", encoding="utf-8") as fh:
                    yaml_data = yaml.safe_load(fh) or []
                if isinstance(yaml_data, list):
                    configs.extend(yaml_data)
            except Exception:
                pass
            try:
                with open(storage_path, "r", encoding="utf-8") as fh:
                    raw = _json.load(fh)
                for item in raw.get("data", {}).get("items", []):
                    auto_id = str(item.get("id", "")).strip()
                    if auto_id and not any(
                        str(c.get("id", "")) == auto_id for c in configs
                    ):
                        configs.append(item)
            except Exception:
                pass
            return configs

        automation_configs = await hass.async_add_executor_job(_read_automation_configs)

        device_automations: dict[str, list] = {did: [] for did in device_ids}
        automation_by_id: dict[str, Any] = {}

        for cfg in automation_configs:
            auto_id = str(cfg.get("id", "")).strip()
            if not auto_id:
                continue
            info = {
                "id": auto_id,
                "name": cfg.get("alias") or f"Automation {auto_id}",
            }
            automation_by_id[auto_id] = info
            cfg_str = _json.dumps(cfg)
            matched_devices: set[str] = set()
            for reg_uuid, did in uuid_to_device_id.items():
                if reg_uuid in cfg_str and did not in matched_devices:
                    device_automations[did].append(info)
                    matched_devices.add(did)

        connection.send_result(msg["id"], {
            "automations": list(automation_by_id.values()),
            "device_automations": device_automations,
        })

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_interfaces",
        vol.Required("device_type"): str,
    })
    @websocket_api.async_response
    async def ws_get_interfaces(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_get_interfaces(msg["device_type"], hass)
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_stored_codes",
    })
    @websocket_api.async_response
    async def ws_get_stored_codes(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_result(msg["id"], {"codes": []})
            return
        result = await api.async_get_stored_codes()
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/send_stored_code",
        vol.Required("identifier"): str,
        vol.Required("code"): str,
        vol.Optional("source"): str,
        vol.Optional("device"): str,
        vol.Optional("command"): str,
    })
    @websocket_api.async_response
    async def ws_send_stored_code(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_send_stored_code(
            msg["identifier"],
            msg["code"],
            msg.get("device", ""),
            msg.get("command", ""),
        )
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/ble_scan",
        vol.Required("adapter_mac"): str,
    })
    @websocket_api.async_response
    async def ws_ble_scan(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_scan_ble(msg["adapter_mac"])
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/ble_emit",
        vol.Required("adapter"): str,
        vol.Optional("raw_hex"): str,
        vol.Optional("ad_type"): str,
        vol.Optional("field_id"): vol.Any(int, str),
        vol.Optional("data_hex"): str,
    })
    @websocket_api.async_response
    async def ws_ble_emit(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        raw_hex = msg.get("raw_hex", "")
        if raw_hex:
            result = await api.async_emit_ble_raw(msg["adapter"], raw_hex)
        else:
            result = await api.async_emit_ble(
                msg["adapter"],
                msg.get("ad_type", ""),
                msg.get("field_id", 0),
                msg.get("data_hex", ""),
            )
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/prepare_to_learn",
        vol.Required("device_type"): str,
        vol.Required("emitter"): dict,
    })
    @websocket_api.async_response
    async def ws_prepare_to_learn(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return

        emitter = msg["emitter"]
        device_type = msg["device_type"]
        entity_id = emitter.get("entity_id", "")
        manufacturer = emitter.get("manufacturer", "")
        frequency = emitter.get("frequency")

        result = await api.async_prepare_to_learn(
            device_type, entity_id, manufacturer, frequency
        )

        connection.send_result(msg["id"], result)

        if result.get("status") == "success":
            session_id = result.get("session_id")
            hass.async_create_task(
                _watch_learn_session(hass, session_id, device_type)
            )

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/find_frequency",
        vol.Required("entity_id"): str,
    })
    @websocket_api.async_response
    async def ws_find_frequency(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return

        result = await api.async_find_frequency(msg["entity_id"])
        connection.send_result(msg["id"], result)

        if result.get("status") == "success":
            session_id = result.get("session_id")
            hass.async_create_task(_watch_frequency_session(hass, session_id))

    for _handler in [
        ws_get_devices,
        ws_add_device,
        ws_remove_device,
        ws_sync_devices,
        ws_clear_devices,
        ws_send_command,
        ws_get_automations,
        ws_get_interfaces,
        ws_get_stored_codes,
        ws_send_stored_code,
        ws_ble_scan,
        ws_ble_emit,
        ws_prepare_to_learn,
        ws_find_frequency,
    ]:
        websocket_api.async_register_command(hass, _handler)

    _LOGGER.info("Whispeer WebSocket commands registered")


async def _watch_learn_session(
    hass: HomeAssistant, session_id: str, device_type: str
) -> None:
    """Watch a learn session and fire HA events when its status changes."""
    last_status: str | None = None
    last_phase: str | None = None

    for _ in range(200):
        await asyncio.sleep(0.5)
        session = LEARNING_SESSIONS.get(session_id)
        if not session:
            break

        current_status = session.status
        current_phase = getattr(session, "phase", "")

        if current_status == last_status and current_phase == last_phase:
            if current_status in ("completed", "error", "timeout"):
                break
            continue

        last_status = current_status
        last_phase = current_phase

        event_data: dict[str, Any] = {
            "session_id": session_id,
            "learning_status": current_status,
            "phase": current_phase,
            "device_type": device_type,
        }

        if current_status == "completed":
            event_data["command_data"] = session.command_data
            if session.detected_frequency is not None:
                event_data["detected_frequency"] = session.detected_frequency
            hass.bus.async_fire("whispeer_learn_update", event_data)
            break

        if current_status in ("error", "timeout"):
            event_data["message"] = getattr(
                session, "error_message", "Learning failed"
            )
            hass.bus.async_fire("whispeer_learn_update", event_data)
            break

        hass.bus.async_fire("whispeer_learn_update", event_data)


async def _watch_frequency_session(
    hass: HomeAssistant, session_id: str
) -> None:
    """Watch a frequency-sweep session and fire HA events when its status changes."""
    last_status: str | None = None

    for _ in range(100):
        await asyncio.sleep(0.5)
        session = LEARNING_SESSIONS.get(session_id)
        if not session:
            break

        current_status = session.status
        if current_status == last_status:
            if current_status in ("completed", "error", "timeout"):
                break
            continue

        last_status = current_status

        event_data: dict[str, Any] = {
            "session_id": session_id,
            "status": current_status,
            "phase": getattr(session, "phase", ""),
        }

        if current_status == "completed":
            if session.detected_frequency is not None:
                event_data["frequency"] = session.detected_frequency
            hass.bus.async_fire("whispeer_frequency_update", event_data)
            break

        if current_status in ("error", "timeout"):
            event_data["message"] = getattr(
                session, "error_message", "Frequency sweep failed"
            )
            hass.bus.async_fire("whispeer_frequency_update", event_data)
            break

        hass.bus.async_fire("whispeer_frequency_update", event_data)
