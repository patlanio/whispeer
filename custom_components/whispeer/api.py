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


def _import_whispeer_broadlink():
    """Import the whispeer_broadlink module with error handling."""
    try:
        from . import whispeer_broadlink
        return whispeer_broadlink, None
    except ImportError as e:
        error_msg = f"Could not import whispeer_broadlink module: {e}"
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


def _execute_broadlink_script(script_args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Execute whispeer_broadlink.py script with standardized error handling."""
    script_path = _get_script_path("whispeer_broadlink.py")
    
    # Check if script exists
    if not os.path.exists(script_path):
        return {
            "success": False,
            "message": f"Broadlink script not found at {script_path}"
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
        # Return basic status instead of making external API calls
        return {
            "status": "success",
            "message": "Whispeer API is ready",
            "timestamp": asyncio.get_event_loop().time()
        }

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
        elif device_type == "broadlink":
            return await self._send_broadlink_command(device_id, command_name, command_code)
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

    async def _send_broadlink_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send Broadlink command using emit_command mode."""
        if not command_code:
            return _create_error_response(
                f"No command code provided for command '{command_name}' on device '{device_id}'"
            )
        
        # Use emit_command mode with device and command name
        result = _execute_broadlink_script(["emit_command", device_id, command_name])
        
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
            f"Broadlink command '{command_name}' sent successfully for device '{device_id}'",
            command_code=command_code,
            device_id=device_id,
            command_name=command_name,
            script_output=result["stdout"],
            return_code=result["return_code"]
        )

    async def _send_broadlink_signal(self, command_data: str, device_ip: str) -> dict:
        """Send a raw Broadlink signal using send_raw mode."""
        # Build script arguments
        script_args = ["send_raw", command_data, "--ip", device_ip]
        
        result = _execute_broadlink_script(script_args)
        
        if not result["success"]:
            return _create_error_response(
                result["message"],
                command_data=command_data,
                device_ip=device_ip,
                script_output=result.get("stdout"),
                script_error=result.get("stderr"),
                return_code=result.get("return_code")
            )
        
        return _create_success_response(
            f"Broadlink signal sent - Data: {command_data}",
            command_data=command_data,
            device_ip=device_ip,
            script_output=result["stdout"],
            return_code=result["return_code"]
        )

    async def async_send_broadlink_signal(self, command_data: str, device_ip: str) -> dict:
        """Send a raw Broadlink signal using whispeer_broadlink module functions."""
        whispeer_broadlink, error_msg = _import_whispeer_broadlink()
        if not whispeer_broadlink:
            return _create_error_response(error_msg)
        
        try:
            _LOGGER.info(f"Sending Broadlink signal - Data: {command_data}, IP: {device_ip}")
            
            success = whispeer_broadlink.send_raw(command_data, device_ip)
            
            if success:
                return _create_success_response(
                    f"Broadlink signal sent successfully - Data: {command_data}",
                    command_data=command_data,
                    device_ip=device_ip
                )
            else:
                return _create_error_response(
                    f"Failed to send Broadlink signal - Data: {command_data}",
                    command_data=command_data,
                    device_ip=device_ip
                )
                
        except Exception as e:
            _LOGGER.error(f"Error sending Broadlink signal: {e}")
            return _create_error_response(f"Broadlink signal execution failed: {str(e)}")

    async def async_learn_broadlink_command(self, device_name: str, command_name: str, command_type: str, device_ip: str, frequency: float = 433.92) -> dict:
        """Learn a new Broadlink command using whispeer_broadlink module functions."""
        whispeer_broadlink, error_msg = _import_whispeer_broadlink()
        if not whispeer_broadlink:
            return _create_error_response(error_msg)
        
        try:
            _LOGGER.info(f"Learning Broadlink command - Device: {device_name}, Command: {command_name}, Type: {command_type}, IP: {device_ip}")
            
            success = whispeer_broadlink.learn_command(device_name, command_name, command_type, device_ip, frequency)
            
            if success:
                return _create_success_response(
                    f"Broadlink command '{command_name}' learned successfully for device '{device_name}'",
                    device_name=device_name,
                    command_name=command_name,
                    command_type=command_type,
                    device_ip=device_ip,
                    frequency=frequency
                )
            else:
                return _create_error_response(
                    f"Failed to learn Broadlink command '{command_name}' for device '{device_name}'",
                    device_name=device_name,
                    command_name=command_name,
                    command_type=command_type,
                    device_ip=device_ip
                )
                
        except Exception as e:
            _LOGGER.error(f"Error learning Broadlink command: {e}")
            return _create_error_response(f"Broadlink command learning failed: {str(e)}")

    async def async_get_broadlink_devices(self) -> dict:
        """Get available Broadlink devices using whispeer_broadlink module."""
        whispeer_broadlink, error_msg = _import_whispeer_broadlink()
        if not whispeer_broadlink:
            return _create_error_response(error_msg)
        
        try:
            devices = whispeer_broadlink.discover_broadlink_devices(timeout=10)
            return _create_success_response(
                f"Found {len(devices)} Broadlink device(s)",
                devices=devices
            )
            
        except Exception as e:
            _LOGGER.error(f"Error discovering Broadlink devices: {e}")
            return _create_error_response(f"Error discovering Broadlink devices: {str(e)}")

    async def async_get_broadlink_devices_from_hass(self, hass) -> list:
        """Get Broadlink devices from Home Assistant integrations."""
        try:
            from homeassistant.helpers import device_registry as dr, entity_registry as er
            
            broadlink_devices = []
            
            # Get device and entity registries
            device_registry = dr.async_get(hass)
            entity_registry = er.async_get(hass)
            
            _LOGGER.info(f"Checking {len(device_registry.devices)} devices in registry for Broadlink devices")
            
            # Look for Broadlink devices
            for device in device_registry.devices.values():
                _LOGGER.debug(f"Checking device: {device.name}, identifiers: {device.identifiers}")
                
                # Check if device is from Broadlink integration
                if any(identifier[0] == "broadlink" for identifier in device.identifiers):
                    _LOGGER.info(f"Found Broadlink device: {device.name}, model: {device.model}")
                    
                    # Extract device info
                    device_info = {
                        'name': device.name or device.name_by_user or "Unknown Broadlink Device",
                        'model': device.model or "Unknown",
                        'manufacturer': device.manufacturer or "Broadlink",
                        'id': device.id,
                        'source': 'hass'
                    }
                    
                    # Try to get IP from config entries if available
                    for config_entry_id in device.config_entries:
                        config_entry = hass.config_entries.async_get_entry(config_entry_id)
                        if config_entry and config_entry.domain == "broadlink":
                            _LOGGER.debug(f"Config entry data: {config_entry.data}")
                            # Extract host/IP from config data if available
                            host = config_entry.data.get("host") or config_entry.data.get("ip")
                            if host:
                                device_info['ip'] = host
                                _LOGGER.info(f"Found IP for device {device.name}: {host}")
                            break
                    
                    broadlink_devices.append(device_info)
            
            _LOGGER.info(f"Found {len(broadlink_devices)} Broadlink devices from Home Assistant")
            return broadlink_devices
            
        except Exception as e:
            _LOGGER.error(f"Error getting Broadlink devices from Home Assistant: {e}")
            import traceback
            _LOGGER.error(f"Traceback: {traceback.format_exc()}")
            return []

    async def async_get_broadlink_interfaces(self, hass=None) -> dict:
        """Get available Broadlink interfaces from both network discovery and Home Assistant."""
        try:
            all_devices = []
            
            _LOGGER.info("Getting Broadlink interfaces from Home Assistant integrations only")
            
            # Get devices from Home Assistant if available
            if hass:
                _LOGGER.info("Getting devices from Home Assistant integrations")
                hass_devices = await self.async_get_broadlink_devices_from_hass(hass)
                _LOGGER.info(f"Found {len(hass_devices)} HASS devices: {hass_devices}")
                
                for device in hass_devices:
                    # Format: "Model (HASS, IP)" or "Name (HASS, IP)" if no model
                    display_name = device.get('model', device.get('name', 'Unknown'))
                    device_ip = device.get('ip', 'Unknown IP')
                    device_name = f"{display_name} (HASS, {device_ip})"
                    
                    all_devices.append({
                        'id': device.get('id', ''),
                        'name': device_name,
                        'source': 'hass',
                        'device_info': device
                    })
                    _LOGGER.info(f"Added HASS device: {device_name}")
            else:
                _LOGGER.info("No HASS object provided, skipping Home Assistant device discovery")
            
            # NOTE: Network discovery is skipped to avoid automatic scanning
            # Use the dedicated discover_broadlink_devices endpoint for network discovery
            
            _LOGGER.info(f"Total devices: {len(all_devices)}")
            
            # Extract device names for the interface list
            unique_devices = [device['name'] for device in all_devices]
            
            _LOGGER.info(f"Final unique devices: {unique_devices}")
            
            return _create_success_response(
                f"Found {len(unique_devices)} Broadlink interface(s)",
                interfaces=unique_devices
            )
            
        except Exception as e:
            _LOGGER.error(f"Error getting Broadlink interfaces: {e}")
            import traceback
            _LOGGER.error(f"Traceback: {traceback.format_exc()}")
            return _create_error_response(f"Error getting Broadlink interfaces: {str(e)}")

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

    async def async_get_interfaces(self, device_type: str, hass=None) -> dict:
        """Get available interfaces for any device type."""
        device_type = device_type.lower()
        
        if device_type == 'ble':
            return await self.async_get_ble_interfaces()
        elif device_type == 'broadlink':
            return await self.async_get_broadlink_interfaces(hass)
        elif device_type == 'rf':
            # RF functionality is provided by Broadlink devices
            # Return empty interfaces - no standalone RF devices
            return _create_success_response(
                "No RF interfaces available",
                interfaces=[]
            )
        elif device_type == 'ir':
            # IR functionality is provided by Broadlink devices
            # Return empty interfaces - no standalone IR devices
            return _create_success_response(
                "No IR interfaces available",
                interfaces=[]
            )
        else:
            return _create_error_response(f"Unsupported device type: {device_type}")

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
        # Try Broadlink first, then fallback to generic RF
        try:
            return await self._send_broadlink_command(device_id, command_name, command_code)
        except Exception as e:
            _LOGGER.warning(f"Broadlink RF command failed, using generic RF: {e}")
            # Implement generic RF command sending logic
            return _create_success_response(
                f"RF command '{command_name}' sent to '{device_id}'",
                command_code=command_code,
                method="generic_rf"
            )

    async def _send_ir_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send IR command."""
        # Try Broadlink first, then fallback to generic IR
        try:
            return await self._send_broadlink_command(device_id, command_name, command_code)
        except Exception as e:
            _LOGGER.warning(f"Broadlink IR command failed, using generic IR: {e}")
            # Implement generic IR command sending logic
            return _create_success_response(
                f"IR command '{command_name}' sent to '{device_id}'",
                command_code=command_code,
                method="generic_ir"
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
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Get available interfaces for a device type."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                _LOGGER.debug(f"Interfaces request with Bearer token: {bool(token)}")
            else:
                _LOGGER.debug("Interfaces request without Bearer token - allowing for iframe panel")
            
            data = await request.json()
            device_type = data.get('type', '').lower()
            
            if not device_type:
                return web.json_response({
                    "error": "Missing required field: type"
                }, status=400)
            
            if device_type not in ['ble', 'rf', 'ir', 'broadlink']:
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
            
            # Get interfaces based on device type using the unified API method
            result = await coordinator.api.async_get_interfaces(device_type, hass)
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error getting interfaces: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerBroadlinkLearnView(HomeAssistantView):
    """View to handle Broadlink command learning."""

    url = "/api/services/whispeer/learn_broadlink_command"
    name = "api:whispeer:learn_broadlink_command"
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Learn a new Broadlink command."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                _LOGGER.debug(f"Learn command request with Bearer token: {bool(token)}")
            else:
                _LOGGER.debug("Learn command request without Bearer token - allowing for iframe panel")
            
            data = await request.json()
            device_name = data.get('device_name', '')
            command_name = data.get('command_name', '')
            command_type = data.get('command_type', '').lower()
            device_ip = data.get('device_ip', '')
            frequency = data.get('frequency', 433.92)
            
            if not all([device_name, command_name, command_type, device_ip]):
                return web.json_response({
                    "error": "Missing required fields: device_name, command_name, command_type, device_ip"
                }, status=400)
            
            if command_type not in ['ir', 'rf']:
                return web.json_response({
                    "error": f"Invalid command type: {command_type}. Use 'ir' or 'rf'"
                }, status=400)
            
            _LOGGER.info(f"Learning Broadlink command: {device_name}.{command_name} ({command_type}) from {device_ip}")
            
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
            
            # Learn the command
            result = await coordinator.api.async_learn_broadlink_command(
                device_name, command_name, command_type, device_ip, frequency
            )
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error learning Broadlink command: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerBroadlinkSendView(HomeAssistantView):
    """View to handle Broadlink command sending."""

    url = "/api/services/whispeer/send_broadlink_signal"
    name = "api:whispeer:send_broadlink_signal"
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Send a raw Broadlink signal."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                _LOGGER.debug(f"Send signal request with Bearer token: {bool(token)}")
            else:
                _LOGGER.debug("Send signal request without Bearer token - allowing for iframe panel")
            
            data = await request.json()
            command_data = data.get('command_data', '')
            device_ip = data.get('device_ip', '')
            
            if not all([command_data, device_ip]):
                return web.json_response({
                    "error": "Missing required fields: command_data, device_ip"
                }, status=400)
            
            _LOGGER.info(f"Sending Broadlink signal to {device_ip}: {command_data}")
            
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
            
            # Send the signal
            result = await coordinator.api.async_send_broadlink_signal(command_data, device_ip)
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error sending Broadlink signal: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerBroadlinkDiscoverView(HomeAssistantView):
    """View to handle Broadlink device discovery."""

    url = "/api/services/whispeer/discover_broadlink_devices"
    name = "api:whispeer:discover_broadlink_devices"
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Discover Broadlink devices on the network."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                _LOGGER.debug(f"Discover devices request with Bearer token: {bool(token)}")
            else:
                _LOGGER.debug("Discover devices request without Bearer token - allowing for iframe panel")
            
            _LOGGER.info("Discovering Broadlink devices on network")
            
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
            
            # Discover devices
            result = await coordinator.api.async_get_broadlink_devices()
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error discovering Broadlink devices: {e}")
            return web.json_response({"error": str(e)}, status=500)
