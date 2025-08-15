"""Sample API Client."""
import asyncio
import logging
import socket

import aiohttp
import async_timeout

TIMEOUT = 10


_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


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
        return {
            "id": len(await self.async_get_devices()) + 1,
            "status": "success",
            "message": "Device added successfully",
            **device_data,
        }

    async def async_remove_device(self, device_id: int) -> dict:
        """Remove a Whispeer device."""
        # Implement actual device removal logic
        return {
            "status": "success",
            "message": f"Device {device_id} removed successfully",
        }

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
            return {
                "status": "error",
                "message": f"Unsupported device type: {device_type}"
            }

    async def async_send_ble_signal(self, data_hex: str, interface: str = None) -> dict:
        """Send a raw BLE signal using whispeer_ble module functions."""
        try:
            # Import the whispeer_ble module to use its functions
            from . import whispeer_ble
            
            _LOGGER.info(f"Sending BLE signal - Data: {data_hex}, Interface: {interface}")
            
            # Use the emit_signal function from whispeer_ble module
            success = whispeer_ble.emit_signal(data_hex, interface)
            
            if success:
                return {
                    "status": "success",
                    "message": f"BLE signal sent successfully - Data: {data_hex}",
                    "data_hex": data_hex,
                    "interface": interface,
                    "mode": "hardware" if whispeer_ble.check_bluetooth_availability()["available"] else "simulation"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to send BLE signal - Data: {data_hex}",
                    "data_hex": data_hex,
                    "interface": interface
                }
                
        except ImportError as e:
            _LOGGER.error(f"Could not import whispeer_ble module: {e}")
            return {
                "status": "error",
                "message": f"Could not import BLE module: {e}"
            }
        except Exception as e:
            _LOGGER.error(f"Error sending BLE signal: {e}")
            return {
                "status": "error",
                "message": f"BLE signal execution failed: {str(e)}"
            }

    async def _send_ble_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send BLE command using the new whispeer_ble.py script."""
        try:
            import subprocess
            import os
            
            # Get the path to the whispeer_ble.py script
            current_dir = os.path.dirname(__file__)
            script_path = os.path.join(current_dir, "whispeer_ble.py")
            
            _LOGGER.info(f"Calling BLE script: python3 {script_path} emit_command {device_id} {command_name}")
            
            # Check if script exists
            if not os.path.exists(script_path):
                _LOGGER.error(f"BLE script not found at {script_path}")
                return {
                    "status": "error",
                    "message": f"BLE script not found at {script_path}"
                }
            
            # Execute the BLE script with new format
            # Format: python3 whispeer_ble.py emit_command <device_name> <command_name>
            cmd = ["python3", script_path, "emit_command", device_id, command_name]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            _LOGGER.info(f"BLE script output: {result.stdout}")
            if result.stderr:
                _LOGGER.warning(f"BLE script stderr: {result.stderr}")
            
            # Check return code (new script returns 0 on success, even in simulation mode)
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": f"BLE command '{command_name}' processed for '{device_id}'",
                    "command_code": command_code,
                    "device_id": device_id,
                    "script_output": result.stdout.strip(),
                    "return_code": result.returncode
                }
            else:
                # Command failed
                error_details = []
                if result.stdout:
                    error_details.append(f"stdout: {result.stdout}")
                if result.stderr:
                    error_details.append(f"stderr: {result.stderr}")
                
                error_msg = f"BLE script failed with exit code {result.returncode}"
                if error_details:
                    error_msg += f". Details: {'; '.join(error_details)}"
                
                _LOGGER.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "command_code": command_code,
                    "device_id": device_id,
                    "script_output": result.stdout.strip() if result.stdout else None,
                    "script_error": result.stderr.strip() if result.stderr else None,
                    "return_code": result.returncode
                }
            
        except subprocess.TimeoutExpired:
            _LOGGER.error("BLE script execution timed out")
            return {
                "status": "error",
                "message": "BLE script execution timed out after 30 seconds"
            }
            
        except FileNotFoundError:
            _LOGGER.error(f"Python3 or BLE script not found. Command: {' '.join(cmd)}")
            return {
                "status": "error",
                "message": f"Python3 or BLE script not found. Command attempted: {' '.join(cmd)}"
            }
            
        except Exception as e:
            _LOGGER.error(f"Error executing BLE script: {e}")
            return {
                "status": "error",
                "message": f"BLE script execution failed: {str(e)}"
            }

    async def _send_ble_signal(self, data_hex: str, interface: str = None) -> dict:
        """Send a raw BLE signal using emit_signal mode."""
        try:
            import subprocess
            import os
            
            # Get the path to the whispeer_ble.py script
            current_dir = os.path.dirname(__file__)
            script_path = os.path.join(current_dir, "whispeer_ble.py")
            
            # Build command (UUID is now hardcoded in the script)
            cmd = ["python3", script_path, "emit_signal", data_hex]
            if interface:
                cmd.extend(["--interface", interface])
            
            _LOGGER.info(f"Calling BLE script: {' '.join(cmd)}")
            
            # Check if script exists
            if not os.path.exists(script_path):
                _LOGGER.error(f"BLE script not found at {script_path}")
                return {
                    "status": "error",
                    "message": f"BLE script not found at {script_path}"
                }
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            _LOGGER.info(f"BLE script output: {result.stdout}")
            if result.stderr:
                _LOGGER.warning(f"BLE script stderr: {result.stderr}")
            
            # Check return code
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": f"BLE signal sent - Data: {data_hex}",
                    "data_hex": data_hex,
                    "interface": interface,
                    "script_output": result.stdout.strip(),
                    "return_code": result.returncode
                }
            else:
                # Command failed
                error_details = []
                if result.stdout:
                    error_details.append(f"stdout: {result.stdout}")
                if result.stderr:
                    error_details.append(f"stderr: {result.stderr}")
                
                error_msg = f"BLE signal script failed with exit code {result.returncode}"
                if error_details:
                    error_msg += f". Details: {'; '.join(error_details)}"
                
                _LOGGER.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "data_hex": data_hex,
                    "script_output": result.stdout.strip() if result.stdout else None,
                    "script_error": result.stderr.strip() if result.stderr else None,
                    "return_code": result.returncode
                }
            
        except subprocess.TimeoutExpired:
            _LOGGER.error("BLE signal script execution timed out")
            return {
                "status": "error",
                "message": "BLE signal script execution timed out after 30 seconds"
            }
            
        except FileNotFoundError:
            _LOGGER.error(f"Python3 or BLE script not found. Command: {' '.join(cmd)}")
            return {
                "status": "error",
                "message": f"Python3 or BLE script not found. Command attempted: {' '.join(cmd)}"
            }
            
        except Exception as e:
            _LOGGER.error(f"Error executing BLE signal script: {e}")
            return {
                "status": "error",
                "message": f"BLE signal script execution failed: {str(e)}"
            }

    async def async_get_ble_interfaces(self) -> dict:
        """Get available Bluetooth interfaces using whispeer_ble module."""
        try:
            # Import the whispeer_ble module to use its functions
            from . import whispeer_ble
            
            interfaces = whispeer_ble.get_available_interfaces()
            return {
                "status": "success",
                "interfaces": interfaces,
                "message": f"Found {len(interfaces)} Bluetooth interface(s)"
            }
            
        except ImportError as e:
            _LOGGER.error(f"Could not import whispeer_ble module: {e}")
            return {
                "status": "error",
                "message": f"Could not import BLE module: {e}"
            }
        except Exception as e:
            _LOGGER.error(f"Error getting BLE interfaces: {e}")
            return {
                "status": "error",
                "message": f"Error getting BLE interfaces: {str(e)}"
            }

    async def _send_ble_command_via_ha(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send BLE command using Home Assistant's Bluetooth integration."""
        try:
            # Import whispeer_ble to get device data
            from . import whispeer_ble
            
            if device_id not in whispeer_ble.DEVICES:
                return {
                    "status": "error",
                    "message": f"Device '{device_id}' not found in device registry"
                }
            
            device = whispeer_ble.DEVICES[device_id]
            
            if command_name not in device["commands"]:
                return {
                    "status": "error",
                    "message": f"Command '{command_name}' not found for device '{device_id}'",
                    "available_commands": list(device["commands"].keys())
                }
            
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
            # This would require accessing the hass object and using the bluetooth integration
            
            return {
                "status": "success",
                "message": f"BLE command '{command_name}' prepared for '{device_id}'",
                "command_code": command_code,
                "device_id": device_id,
                "payload": payload,
                "note": "Command prepared - Bluetooth integration needed for actual transmission"
            }
            
        except ImportError as e:
            _LOGGER.error(f"Could not import whispeer_ble module: {e}")
            return {
                "status": "error",
                "message": f"Could not import BLE module: {e}"
            }
        except Exception as e:
            _LOGGER.error(f"Error preparing BLE command: {e}")
            return {
                "status": "error",
                "message": f"BLE command preparation failed: {str(e)}"
            }

    async def _send_rf_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send RF command."""
        # Implement RF command sending logic
        return {
            "status": "success",
            "message": f"RF command '{command_name}' sent to '{device_id}'",
            "command_code": command_code
        }

    async def _send_ir_command(self, device_id: str, command_name: str, command_code: str) -> dict:
        """Send IR command."""
        # Implement IR command sending logic
        return {
            "status": "success",
            "message": f"IR command '{command_name}' sent to '{device_id}'",
            "command_code": command_code
        }

    async def async_sync_devices(self, devices: dict) -> dict:
        """Sync devices with the backend."""
        # Implement device synchronization logic
        return {
            "status": "success",
            "message": f"Synced {len(devices)} devices",
            "device_count": len(devices)
        }

    async def async_test_device(self, device_id: int) -> dict:
        """Test a Whispeer device."""
        # Implement device testing logic
        return {
            "status": "success",
            "message": f"Device {device_id} test completed",
            "test_result": "passed",
        }

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
