"""Sample API Client."""
import asyncio
import logging
import os
import socket
import subprocess
from typing import Dict, Any, List, Optional

import aiohttp
import async_timeout
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


def _create_success_response(message: str, **kwargs) -> Dict[str, Any]:
    """Create a standardized success response."""
    return {
        "status": "success",
        "message": message,
        **kwargs
    }


def _create_error_response(message: str, **kwargs) -> Dict[str, Any]:
    """Create a standardized error response."""
    return {
        "status": "error",
        "message": message,
        **kwargs
    }


def _get_script_path(script_name: str) -> str:
    """Get the absolute path to a script in the same directory."""
    current_dir = os.path.dirname(__file__)
    return os.path.join(current_dir, script_name)


def _import_whispeer_ble():
    """Import the whispeer_ble module with error handling."""
    try:
        from . import whispeer_ble
        return whispeer_ble, None
    except ImportError as e:
        error_msg = f"Could not import whispeer_ble module: {e}"
        _LOGGER.error(error_msg)
        return None, error_msg


def _run_subprocess(cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Run a subprocess command with standardized error handling."""
    try:
        _LOGGER.info(f"Executing command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        _LOGGER.info(f"Command output: {result.stdout}")
        if result.stderr:
            _LOGGER.warning(f"Command stderr: {result.stderr}")
        
        if result.returncode == 0:
            return {
                "success": True,
                "return_code": result.returncode,
                "stdout": result.stdout.strip() if result.stdout else None,
                "stderr": result.stderr.strip() if result.stderr else None
            }
        else:
            # Command failed with non-zero exit code
            error_details = []
            if result.stdout:
                error_details.append(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                error_details.append(f"stderr: {result.stderr.strip()}")
            
            error_msg = f"Command failed with exit code {result.returncode}"
            if error_details:
                error_msg += f". Details: {'; '.join(error_details)}"
            
            return {
                "success": False,
                "message": error_msg,
                "return_code": result.returncode,
                "stdout": result.stdout.strip() if result.stdout else None,
                "stderr": result.stderr.strip() if result.stderr else None
            }
        
    except subprocess.TimeoutExpired:
        error_msg = f"Command execution timed out after {timeout} seconds"
        _LOGGER.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "error_type": "timeout"
        }
        
    except FileNotFoundError:
        error_msg = f"Command not found: {' '.join(cmd)}"
        _LOGGER.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "error_type": "file_not_found"
        }
        
    except Exception as e:
        error_msg = f"Command execution failed: {str(e)}"
        _LOGGER.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "error_type": "execution_error"
        }


def _execute_ble_script(script_args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Execute whispeer_ble.py script with standardized error handling."""
    script_path = _get_script_path("whispeer_ble.py")
    
    # Check if script exists
    if not os.path.exists(script_path):
        return {
            "success": False,
            "message": f"BLE script not found at {script_path}"
        }
    
    # Build complete command
    cmd = ["python3", script_path] + script_args
    
    return _run_subprocess(cmd, timeout)


class WhispeerApiClient:
    def __init__(
        self, username: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        """Sample API Client."""
        self._username = username
        self._passeword = password
        self._session = session

    async def async_get_data(self) -> dict:
        """Get data from the API."""
        url = "https://jsonplaceholder.typicode.com/posts/1"
        return await self.api_wrapper("get", url)

    async def async_set_title(self, value: str) -> None:
        """Get data from the API."""
        url = "https://jsonplaceholder.typicode.com/posts/1"
        await self.api_wrapper("patch", url, data={"title": value}, headers=HEADERS)

    async def async_get_devices(self) -> list:
        """Get list of Whispeer devices."""
        # For now, return mock data - implement actual device discovery
        return [
            {
                "id": 1,
                "name": "Living Room Microphone",
                "type": "microphone",
                "status": "online",
                "address": "192.168.1.100",
                "last_seen": "2025-01-14T12:00:00Z",
            },
            {
                "id": 2,
                "name": "Kitchen Speaker",
                "type": "speaker",
                "status": "offline",
                "address": "192.168.1.101",
                "last_seen": "2025-01-14T11:55:00Z",
            },
        ]

    async def async_add_device(self, device_data: dict) -> dict:
        """Add a new Whispeer device."""
        # Implement actual device addition logic
        device_id = len(await self.async_get_devices()) + 1
        return _create_success_response(
            "Device added successfully",
            id=device_id,
            **device_data
        )

    async def async_remove_device(self, device_id: int) -> dict:
        """Remove a Whispeer device."""
        # Implement actual device removal logic
        return _create_success_response(f"Device {device_id} removed successfully")

    async def async_send_command(self, device_id: str, device_type: str, command_name: str, command_code: str) -> dict:
        """Send a command to a device."""
        # Implement actual command sending logic based on device type
        if device_type == "ble":
            return await self._send_ble_command(device_id, command_name, command_code)
        elif device_type == "rf":
            return await self._send_rf_command(device_id, command_name, command_code)
        elif device_type == "ir":
            return await self._send_ir_command(device_id, command_name, command_code)
        else:
            return _create_error_response(f"Unsupported device type: {device_type}")

    async def async_send_ble_signal(self, data_hex: str, interface: str = None) -> dict:
        """Send a raw BLE signal using whispeer_ble module functions."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            _LOGGER.info(f"Sending BLE signal - Data: {data_hex}, Interface: {interface}")
            
            success = whispeer_ble.emit_signal(data_hex, interface)
            
            if success:
                return _create_success_response(
                    f"BLE signal sent successfully - Data: {data_hex}",
                    data_hex=data_hex,
                    interface=interface,
                    mode="hardware" if whispeer_ble.check_bluetooth_availability()["available"] else "simulation"
                )
            else:
                return _create_error_response(
                    f"Failed to send BLE signal - Data: {data_hex}",
                    data_hex=data_hex,
                    interface=interface
                )
                
        except Exception as e:
            _LOGGER.error(f"Error sending BLE signal: {e}")
            return _create_error_response(f"BLE signal execution failed: {str(e)}")

    async def _send_ble_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send BLE command using emit_signal mode with the hex data."""
        if not command_code:
            return _create_error_response(
                f"No command code provided for command '{command_name}' on device '{device_id}'"
            )
        
        # Use emit_signal mode directly with the hex data
        result = _execute_ble_script(["emit_signal", command_code])
        
        if not result["success"]:
            return _create_error_response(
                result["message"],
                command_code=command_code,
                device_id=device_id,
                command_name=command_name,
                script_output=result.get("stdout"),
                script_error=result.get("stderr"),
                return_code=result.get("return_code")
            )
        
        return _create_success_response(
            f"BLE command '{command_name}' sent successfully for device '{device_id}'",
            command_code=command_code,
            device_id=device_id,
            command_name=command_name,
            script_output=result["stdout"],
            return_code=result["return_code"]
        )

    async def _send_ble_signal(self, data_hex: str, interface: str = None) -> dict:
        """Send a raw BLE signal using emit_signal mode."""
        # Build script arguments
        script_args = ["emit_signal", data_hex]
        if interface:
            script_args.extend(["--interface", interface])
        
        result = _execute_ble_script(script_args)
        
        if not result["success"]:
            return _create_error_response(
                result["message"],
                data_hex=data_hex,
                script_output=result.get("stdout"),
                script_error=result.get("stderr"),
                return_code=result.get("return_code")
            )
        
        return _create_success_response(
            f"BLE signal sent - Data: {data_hex}",
            data_hex=data_hex,
            interface=interface,
            script_output=result["stdout"],
            return_code=result["return_code"]
        )

    async def async_get_ble_interfaces(self) -> dict:
        """Get available Bluetooth interfaces using whispeer_ble module."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            interfaces = whispeer_ble.get_available_interfaces()
            return _create_success_response(
                f"Found {len(interfaces)} Bluetooth interface(s)",
                interfaces=interfaces
            )
            
        except Exception as e:
            _LOGGER.error(f"Error getting BLE interfaces: {e}")
            return _create_error_response(f"Error getting BLE interfaces: {str(e)}")

    async def _send_ble_command_via_ha(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send BLE command using Home Assistant's Bluetooth integration."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            if device_id not in whispeer_ble.DEVICES:
                return _create_error_response(f"Device '{device_id}' not found in device registry")
            
            device = whispeer_ble.DEVICES[device_id]
            
            if command_name not in device["commands"]:
                return _create_error_response(
                    f"Command '{command_name}' not found for device '{device_id}'",
                    available_commands=list(device["commands"].keys())
                )
            
            # Get command data and build payload
            data = device["commands"][command_name]
            payload = whispeer_ble.build_adv_payload(device["uuid"], data)
            
            # For now, log the command that would be sent
            _LOGGER.info(f"Would send BLE advertisement:")
            _LOGGER.info(f"  Device: {device_id}")
            _LOGGER.info(f"  Command: {command_name}")
            _LOGGER.info(f"  Data: {data}")
            _LOGGER.info(f"  Payload: {' '.join(payload)}")
            
            # TODO: Integrate with Home Assistant's Bluetooth component
            
            return _create_success_response(
                f"BLE command '{command_name}' prepared for '{device_id}'",
                command_code=command_code,
                device_id=device_id,
                payload=payload,
                note="Command prepared - Bluetooth integration needed for actual transmission"
            )
            
        except Exception as e:
            _LOGGER.error(f"Error preparing BLE command: {e}")
            return _create_error_response(f"BLE command preparation failed: {str(e)}")

    async def _send_rf_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send RF command."""
        # Implement RF command sending logic
        return _create_success_response(
            f"RF command '{command_name}' sent to '{device_id}'",
            command_code=command_code
        )

    async def _send_ir_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send IR command."""
        # Implement IR command sending logic
        return _create_success_response(
            f"IR command '{command_name}' sent to '{device_id}'",
            command_code=command_code
        )

    async def async_sync_devices(self, devices: dict) -> dict:
        """Sync devices with the backend."""
        # Implement device synchronization logic
        return _create_success_response(
            f"Synced {len(devices)} devices",
            device_count=len(devices)
        )

    async def async_test_device(self, device_id: int) -> dict:
        """Test a Whispeer device."""
        # Implement device testing logic
        return _create_success_response(
            f"Device {device_id} test completed",
            test_result="passed"
        )

    async def api_wrapper(
        self, method: str, url: str, data: dict = {}, headers: dict = {}
    ) -> dict:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(TIMEOUT):
                if method == "get":
                    response = await self._session.get(url, headers=headers)
                    return await response.json()

                elif method == "put":
                    await self._session.put(url, headers=headers, json=data)

                elif method == "patch":
                    await self._session.patch(url, headers=headers, json=data)

                elif method == "post":
                    await self._session.post(url, headers=headers, json=data)

        except asyncio.TimeoutError as exception:
            _LOGGER.error(
                "Timeout error fetching information from %s - %s",
                url,
                exception,
            )

        except (KeyError, TypeError) as exception:
            _LOGGER.error(
                "Error parsing information from %s - %s",
                url,
                exception,
            )
        except (aiohttp.ClientError, socket.gaierror) as exception:
            _LOGGER.error(
                "Error fetching information from %s - %s",
                url,
                exception,
            )
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error("Something really wrong happened! - %s", exception)


class WhispeerInterfacesView(HomeAssistantView):
    """View to handle interface retrieval."""

    url = "/api/services/whispeer/get_interfaces"
    name = "api:whispeer:get_interfaces"
    requires_auth = True

    async def post(self, request):
        """Get available interfaces for a device type."""
        try:
            data = await request.json()
            device_type = data.get('type', '').lower()
            
            if not device_type:
                return web.json_response({
                    "error": "Missing required field: type"
                }, status=400)
            
            if device_type not in ['ble', 'rf', 'ir']:
                return web.json_response({
                    "error": f"Unsupported device type: {device_type}"
                }, status=400)
            
            _LOGGER.info(f"Getting interfaces for device type: {device_type}")
            
            hass = request.app["hass"]
            domain_data = hass.data.get("whispeer", {})
            
            # Get the first coordinator entry to access the API client
            coordinator = None
            for entry_data in domain_data.values():
                if hasattr(entry_data, 'api'):
                    coordinator = entry_data
                    break
            
            if not coordinator:
                return web.json_response({
                    "error": "Whispeer coordinator not available"
                }, status=500)
            
            # Get interfaces based on device type using the API client
            if device_type == 'ble':
                result = await coordinator.api.async_get_ble_interfaces()
            elif device_type == 'rf':
                # For now, return mock RF interfaces - implement actual logic later
                result = {
                    "status": "success",
                    "message": "RF interfaces retrieved",
                    "interfaces": [
                        {"id": "rf0", "name": "RF Transceiver 0", "description": "433MHz RF module"},
                        {"id": "rf1", "name": "RF Transceiver 1", "description": "868MHz RF module"}
                    ]
                }
            elif device_type == 'ir':
                # For now, return mock IR interfaces - implement actual logic later
                result = {
                    "status": "success", 
                    "message": "IR interfaces retrieved",
                    "interfaces": [
                        {"id": "ir0", "name": "IR Blaster 0", "description": "Built-in IR transmitter"},
                        {"id": "ir1", "name": "IR Blaster 1", "description": "External IR transmitter"}
                    ]
                }
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error getting interfaces: {e}")
            return web.json_response({"error": str(e)}, status=500)
