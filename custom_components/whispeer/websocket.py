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
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .learn_provider import LEARNING_SESSIONS
from .test_support import get_test_harness

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


def _get_enabled_test_harness(hass: HomeAssistant):
    harness = get_test_harness(hass)
    return harness if harness.enabled else None


def _record_test_event(
    hass: HomeAssistant,
    category: str,
    action: str,
    **details: Any,
) -> None:
    harness = _get_enabled_test_harness(hass)
    if harness is None:
        return
    harness.record(category, action, **details)


def _serialize_learning_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for session_id, session in LEARNING_SESSIONS.items():
        sessions.append({
            "session_id": session_id,
            "command_type": session.command_type,
            "hub_entity_id": session.hub_entity_id,
            "status": session.status,
            "phase": session.phase,
            "command_data": session.command_data,
            "detected_frequency": session.detected_frequency,
            "error_message": session.error_message,
            "created_at": session.created_at,
        })
    sessions.sort(key=lambda item: item["created_at"])
    return sessions


def _build_test_state(hass: HomeAssistant) -> dict[str, Any]:
    harness = _get_enabled_test_harness(hass)
    if harness is None:
        return {"enabled": False, "learning_sessions": []}

    state = harness.snapshot()
    state["learning_sessions"] = _serialize_learning_sessions()
    return state


async def _async_clear_whispeer_registry_entries(
    hass: HomeAssistant,
    entry_id: str | None = None,
) -> dict[str, int]:
    """Remove all Whispeer entities from entity registry and stale Whispeer devices."""
    entity_registry = er.async_get(hass)
    removed_entities = 0

    whispeer_entities = [
        entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN
    ]
    for eid in whispeer_entities:
        entity_registry.async_remove(eid)
        removed_entities += 1

    removed_devices = 0
    if entry_id:
        device_registry = dr.async_get(hass)
        for dev_entry in dr.async_entries_for_config_entry(device_registry, entry_id):
            if any(domain == DOMAIN for domain, _ in dev_entry.identifiers):
                try:
                    device_registry.async_remove_device(dev_entry.id)
                    removed_devices += 1
                except Exception as exc:
                    _LOGGER.debug("Failed removing device registry entry %s: %s", dev_entry.id, exc)

    return {
        "removed_entities": removed_entities,
        "removed_devices": removed_devices,
    }


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
        entry_id, _coordinator = _get_coordinator(hass)
        api = _get_api(hass)
        if not api:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return
        result = await api.async_remove_device(msg["device_id"])

        if result.get("status") == "success" and entry_id:
            try:
                await hass.config_entries.async_reload(entry_id)
                result["reloaded"] = True
            except Exception as reload_err:
                _LOGGER.error(
                    "Failed to reload entry %s after remove: %s", entry_id, reload_err
                )
                result["reloaded"] = False

        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/clear_entities",
    })
    @websocket_api.async_response
    async def ws_clear_entities(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry_id, coordinator = _get_coordinator(hass)
        if not coordinator:
            connection.send_error(msg["id"], "not_found", "Whispeer not initialized")
            return

        cleanup = await _async_clear_whispeer_registry_entries(hass, entry_id)
        result: dict[str, Any] = {
            "status": "success",
            "message": "Whispeer entities cleared",
            **cleanup,
        }

        try:
            await hass.config_entries.async_reload(entry_id)
            result["reloaded"] = True
        except Exception as reload_err:
            _LOGGER.error(
                "Failed to reload entry %s after clear_entities: %s",
                entry_id,
                reload_err,
            )
            result["reloaded"] = False

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

        result = await coordinator.api.async_clear_devices()
        result.update(await _async_clear_whispeer_registry_entries(hass, entry_id))

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
        _record_test_event(
            hass,
            "websocket",
            "send_command_requested",
            device_id=msg["device_id"],
            device_type=msg["device_type"],
            command_name=msg["command_name"],
            sub_command=msg.get("sub_command"),
        )

        sub_command = msg.get("sub_command")

        if sub_command in ("on", "off"):
            uid = f"whispeer_{msg['device_id']}_{msg['command_name']}"
            entity_reg = er.async_get(hass)
            target_entity_id = None
            target_domain = None
            for reg_entry in entity_reg.entities.values():
                if reg_entry.platform == DOMAIN and reg_entry.unique_id == uid:
                    target_entity_id = reg_entry.entity_id
                    target_domain = reg_entry.domain
                    break

            if target_entity_id and target_domain in ("switch", "light"):
                service = "turn_on" if sub_command == "on" else "turn_off"
                try:
                    await hass.services.async_call(
                        target_domain,
                        service,
                        {"entity_id": target_entity_id},
                        blocking=True,
                    )
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain=target_domain,
                        service=service,
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        success=True,
                    )
                    connection.send_result(msg["id"], {"status": "success"})
                    return
                except Exception as exc:
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain=target_domain,
                        service=service,
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        success=False,
                        error_message=str(exc),
                    )
                    _LOGGER.warning(
                        "Failed to call %s.%s for %s, falling back to direct send: %s",
                        target_domain, service, target_entity_id, exc,
                    )

        elif sub_command is not None:
            uid = f"whispeer_{msg['device_id']}_{msg['command_name']}"
            entity_reg = er.async_get(hass)
            target_entity_id = None
            target_domain = None
            for reg_entry in entity_reg.entities.values():
                if reg_entry.platform == DOMAIN and reg_entry.unique_id == uid:
                    target_entity_id = reg_entry.entity_id
                    target_domain = reg_entry.domain
                    break

            if target_entity_id and target_domain == "select":
                try:
                    await hass.services.async_call(
                        "select",
                        "select_option",
                        {"entity_id": target_entity_id, "option": sub_command},
                        blocking=True,
                    )
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain="select",
                        service="select_option",
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        option=sub_command,
                        success=True,
                    )
                    connection.send_result(msg["id"], {"status": "success"})
                    return
                except Exception as exc:
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain="select",
                        service="select_option",
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        option=sub_command,
                        success=False,
                        error_message=str(exc),
                    )
                    _LOGGER.warning(
                        "Failed to call select.select_option for %s, falling back: %s",
                        target_entity_id, exc,
                    )
            elif target_entity_id and target_domain == "number":
                try:
                    native_value = float(sub_command)
                    await hass.services.async_call(
                        "number",
                        "set_value",
                        {"entity_id": target_entity_id, "value": native_value},
                        blocking=True,
                    )
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain="number",
                        service="set_value",
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        value=native_value,
                        success=True,
                    )
                    connection.send_result(msg["id"], {"status": "success"})
                    return
                except Exception as exc:
                    _record_test_event(
                        hass,
                        "service",
                        "direct_command_completed",
                        domain="number",
                        service="set_value",
                        entity_id=target_entity_id,
                        device_id=msg["device_id"],
                        command_name=msg["command_name"],
                        value=sub_command,
                        success=False,
                        error_message=str(exc),
                    )
                    _LOGGER.warning(
                        "Failed to call number.set_value for %s, falling back: %s",
                        target_entity_id, exc,
                    )

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
        _record_test_event(
            hass,
            "websocket",
            "send_command_completed",
            device_id=msg["device_id"],
            command_name=msg["command_name"],
            result=result,
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

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_entity_states",
    })
    @websocket_api.async_response
    async def ws_get_entity_states(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return current HA state for all whispeer switch/light/select/number entities.

        Response: {"states": {"<device_id>:<command_name>": "<state>", ...}}
        """
        entity_reg = er.async_get(hass)
        states: dict[str, str] = {}
        domain_states: dict[str, dict] = {}
        for reg_entry in entity_reg.entities.values():
            if reg_entry.platform != DOMAIN:
                continue
            if reg_entry.domain not in (
                "switch", "light", "select", "number", "climate", "fan", "media_player"
            ):
                continue
            uid = reg_entry.unique_id or ""
            if not uid.startswith("whispeer_"):
                continue
            rest = uid[len("whispeer_"):]
            try:
                sep = rest.index("_")
            except ValueError:
                continue
            device_id = rest[:sep]
            command_name = rest[sep + 1:]
            state_obj = hass.states.get(reg_entry.entity_id)
            if state_obj is None:
                continue
            raw = state_obj.state
            if reg_entry.domain == "number":
                try:
                    raw = str(int(float(raw)))
                except (ValueError, TypeError):
                    pass
            key = f"{device_id}:{command_name}"
            states[key] = raw

            if reg_entry.domain in ("climate", "fan", "media_player") or command_name == "domain_light":
                domain_states[key] = {
                    "entity_id": reg_entry.entity_id,
                    "entity_domain": reg_entry.domain,
                    "state": raw,
                    "attributes": {
                        "fan_mode": state_obj.attributes.get("fan_mode"),
                        "temperature": state_obj.attributes.get("temperature"),
                        "preset_mode": state_obj.attributes.get("preset_mode"),
                        "percentage": state_obj.attributes.get("percentage"),
                        "source": state_obj.attributes.get("source"),
                    },
                }
        connection.send_result(msg["id"], {
            "states": states,
            "domain_states": domain_states,
        })

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/domain_action",
        vol.Required("device_id"): str,
        vol.Required("domain"): str,
        vol.Required("action"): str,
        vol.Optional("mode"): str,
        vol.Optional("fan_mode"): str,
        vol.Optional("temperature"): vol.Any(int, float),
        vol.Optional("preset_mode"): str,
        vol.Optional("percentage"): vol.Any(int, float),
        vol.Optional("source"): str,
    })
    @websocket_api.async_response
    async def ws_domain_action(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        _record_test_event(
            hass,
            "websocket",
            "domain_action_requested",
            device_id=msg["device_id"],
            domain=msg.get("domain"),
            action=msg.get("action"),
        )

        entity_reg = er.async_get(hass)
        domain = (msg.get("domain") or "").lower()
        action = (msg.get("action") or "").lower()
        device_id = msg["device_id"]

        command_name_map = {
            "climate": "climate",
            "fan": "fan",
            "media_player": "media_player",
            "light": "domain_light",
        }
        command_name = command_name_map.get(domain)
        if not command_name:
            connection.send_result(msg["id"], {
                "status": "error",
                "message": f"Unsupported domain '{domain}'",
            })
            return

        uid = f"whispeer_{device_id}_{command_name}"
        reg_entry = next(
            (
                entry for entry in entity_reg.entities.values()
                if entry.platform == DOMAIN and (entry.unique_id or "") == uid
            ),
            None,
        )
        if not reg_entry:
            connection.send_result(msg["id"], {
                "status": "error",
                "message": f"Entity not found for {uid}",
            })
            return

        entity_id = reg_entry.entity_id

        try:
            if domain == "climate":
                if action == "off":
                    await hass.services.async_call(
                        "climate", "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": "off"},
                        blocking=True,
                    )
                elif action == "set_mode":
                    mode = msg.get("mode")
                    if mode:
                        await hass.services.async_call(
                            "climate", "set_hvac_mode",
                            {"entity_id": entity_id, "hvac_mode": mode},
                            blocking=True,
                        )
                elif action == "set_fan_mode":
                    fan_mode = msg.get("fan_mode")
                    if fan_mode:
                        await hass.services.async_call(
                            "climate", "set_fan_mode",
                            {"entity_id": entity_id, "fan_mode": fan_mode},
                            blocking=True,
                        )
                elif action == "set_temperature":
                    if msg.get("temperature") is not None:
                        await hass.services.async_call(
                            "climate", "set_temperature",
                            {"entity_id": entity_id, "temperature": msg.get("temperature")},
                            blocking=True,
                        )
                else:
                    connection.send_result(msg["id"], {
                        "status": "error",
                        "message": f"Unsupported climate action '{action}'",
                    })
                    return

            elif domain == "fan":
                if action == "off":
                    await hass.services.async_call(
                        "fan", "turn_off", {"entity_id": entity_id}, blocking=True
                    )
                elif action == "set":
                    data: dict[str, Any] = {"entity_id": entity_id}
                    if msg.get("preset_mode") is not None:
                        data["preset_mode"] = msg.get("preset_mode")
                    if msg.get("percentage") is not None:
                        data["percentage"] = msg.get("percentage")
                    await hass.services.async_call(
                        "fan", "turn_on", data, blocking=True
                    )
                else:
                    connection.send_result(msg["id"], {
                        "status": "error",
                        "message": f"Unsupported fan action '{action}'",
                    })
                    return

            elif domain == "media_player":
                media_actions = {
                    "on": ("turn_on", None),
                    "off": ("turn_off", None),
                    "volume_up": ("volume_up", None),
                    "volume_down": ("volume_down", None),
                    "mute": ("volume_mute", {"is_volume_muted": True}),
                    "previous": ("media_previous_track", None),
                    "next": ("media_next_track", None),
                    "select_source": ("select_source", {"source": msg.get("source")}),
                }
                mapping = media_actions.get(action)
                if not mapping:
                    connection.send_result(msg["id"], {
                        "status": "error",
                        "message": f"Unsupported media_player action '{action}'",
                    })
                    return
                service, extra = mapping
                data = {"entity_id": entity_id}
                if extra:
                    data.update(extra)
                await hass.services.async_call(
                    "media_player", service, data, blocking=True
                )

            elif domain == "light":
                if action not in ("on", "off"):
                    connection.send_result(msg["id"], {
                        "status": "error",
                        "message": f"Unsupported light action '{action}'",
                    })
                    return
                service = "turn_on" if action == "on" else "turn_off"
                await hass.services.async_call(
                    "light", service, {"entity_id": entity_id}, blocking=True
                )

            _record_test_event(
                hass,
                "service",
                "domain_action_completed",
                device_id=device_id,
                domain=domain,
                action=action,
                entity_id=entity_id,
                success=True,
            )
            connection.send_result(msg["id"], {
                "status": "success",
                "entity_id": entity_id,
            })
        except Exception as exc:
            _record_test_event(
                hass,
                "service",
                "domain_action_completed",
                device_id=device_id,
                domain=domain,
                action=action,
                entity_id=entity_id,
                success=False,
                error_message=str(exc),
            )
            connection.send_result(msg["id"], {
                "status": "error",
                "message": str(exc),
                "entity_id": entity_id,
            })

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/test/get_state",
    })
    @websocket_api.async_response
    async def ws_test_get_state(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        harness = _get_enabled_test_harness(hass)
        if harness is None:
            connection.send_error(msg["id"], "not_allowed", "Whispeer test mode is disabled")
            return
        connection.send_result(msg["id"], _build_test_state(hass))

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/test/configure",
        vol.Required("config"): dict,
    })
    @websocket_api.async_response
    async def ws_test_configure(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        harness = _get_enabled_test_harness(hass)
        if harness is None:
            connection.send_error(msg["id"], "not_allowed", "Whispeer test mode is disabled")
            return
        harness.configure(msg["config"])
        connection.send_result(msg["id"], {
            "status": "success",
            "state": _build_test_state(hass),
        })

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/test/reset",
        vol.Optional("clear_config", default=True): bool,
        vol.Optional("clear_learning_sessions", default=True): bool,
    })
    @websocket_api.async_response
    async def ws_test_reset(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        harness = _get_enabled_test_harness(hass)
        if harness is None:
            connection.send_error(msg["id"], "not_allowed", "Whispeer test mode is disabled")
            return

        harness.reset(clear_config=msg.get("clear_config", True))
        cleared_learning_sessions = 0
        if msg.get("clear_learning_sessions", True):
            cleared_learning_sessions = len(LEARNING_SESSIONS)
            LEARNING_SESSIONS.clear()

        connection.send_result(msg["id"], {
            "status": "success",
            "cleared_learning_sessions": cleared_learning_sessions,
            "state": _build_test_state(hass),
        })

    @websocket_api.websocket_command({
        vol.Required("type"): "whispeer/get_ha_entities",
        vol.Optional("domains"): list,
    })
    @websocket_api.async_response
    async def ws_get_ha_entities(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return HA entities filtered by domain(s).

        Response: {"entities": [{"entity_id": ..., "friendly_name": ..., "domain": ...}]}
        """
        allowed_domains = set(msg.get("domains") or ["sensor", "binary_sensor"])
        entities = []
        for state in hass.states.async_all():
            domain = state.entity_id.split(".")[0]
            if domain not in allowed_domains:
                continue
            entities.append({
                "entity_id": state.entity_id,
                "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                "domain": domain,
                "device_class": state.attributes.get("device_class", ""),
            })
        entities.sort(key=lambda e: e["entity_id"])
        connection.send_result(msg["id"], {"entities": entities})

    for _handler in [
        ws_get_devices,
        ws_add_device,
        ws_remove_device,
        ws_clear_entities,
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
        ws_get_entity_states,
        ws_domain_action,
        ws_get_ha_entities,
        ws_test_get_state,
        ws_test_configure,
        ws_test_reset,
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
