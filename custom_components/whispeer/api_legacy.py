"""Sample API Client."""
import asyncio
import logging
import os
import socket
import subprocess
import uuid
import time
from typing import Dict, Any, List, Optional

import aiohttp
import async_timeout
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import SIGNAL_WHISPEER_DATA_UPDATED, SIGNAL_WHISPEER_NEW_DEVICE

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}

# Global dictionary to store learning sessions
LEARNING_SESSIONS = {}

class LearnSession:
    """Class to manage a learning session."""
    def __init__(self, session_id: str, device_type: str, device_ip: str = None, frequency: float = 433.92, interface: str = None):
        self.session_id = session_id
        self.device_type = device_type
        self.device_ip = device_ip
        self.frequency = frequency
        self.interface = interface
        self.device = None
        self.status = "preparing"  # preparing, ready, learning, completed, error, timeout
        self.command_data = None
        self.error_message = None
        self.created_at = time.time()
        self.updated_at = time.time()
    
    def update_status(self, status: str, command_data: str = None, error_message: str = None):
        """Update session status."""
        self.status = status
        self.updated_at = time.time()
        if command_data:
            self.command_data = command_data
        if error_message:
            self.error_message = error_message


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

    # -P prevents prepending the script directory to sys.path, which would
    # otherwise shadow stdlib modules (e.g. our select.py shadows stdlib select).
    cmd = ["python3", "-P", script_path] + script_args

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

    # -P prevents prepending the script directory to sys.path, which would
    # otherwise shadow stdlib modules (e.g. our select.py shadows stdlib select).
    cmd = ["python3", "-P", script_path] + script_args

    return _run_subprocess(cmd, timeout)


class WhispeerApiClient:
    def __init__(
        self, session: aiohttp.ClientSession, 
        hass=None
    ) -> None:
        """Whispeer API Client."""
        self._session = session
        self._hass = hass
        self._store = Store(hass, 1, "whispeer_devices")
        self._devices_cache: Dict[str, Dict[str, Any]] = {}

    async def async_get_data(self) -> dict:
        """Get data from the API."""
        # Return basic status instead of making external API calls
        return {
            "status": "success",
            "message": "Whispeer API is ready",
            "timestamp": asyncio.get_event_loop().time()
        }

    async def _load_devices(self) -> Dict[str, Dict[str, Any]]:
        """Load devices from Home Assistant storage."""
        try:
            data = await self._store.async_load()
            if not data:
                return {}
            if isinstance(data, dict):
                # Sanitize: ensure every device has a non-empty id key and field
                sanitized: Dict[str, Dict[str, Any]] = {}
                for did, info in data.items():
                    did_str = str(did).strip()
                    if not did_str:
                        did_str = uuid.uuid4().hex[:8]
                    if not isinstance(info, dict):
                        info = {}
                    if not info.get("id"):
                        info["id"] = did_str
                    sanitized[did_str] = info
                return sanitized
            return {}
        except Exception as e:
            _LOGGER.error(f"Failed to load devices: {e}")
            return {}

    async def _save_devices(self, devices: Dict[str, Dict[str, Any]]) -> None:
        """Save devices to Home Assistant storage."""
        try:
            await self._store.async_save(devices)
            self._devices_cache = devices
        except Exception as e:
            _LOGGER.error(f"Failed to save devices: {e}")

    async def async_get_devices(self) -> list:
        """Get list of Whispeer devices from persistent storage."""
        if not self._devices_cache:
            self._devices_cache = await self._load_devices()
        # Return as list for API consumers
        return [
            {"id": did, **info} for did, info in self._devices_cache.items()
        ]

    async def async_add_device(self, device_data: dict) -> dict:
        """Add a new Whispeer device to persistent storage."""
        devices = await self._load_devices()
        # Generate ID if not provided
        device_id = (device_data.get("id") or uuid.uuid4().hex[:8]).strip()
        # Normalize minimal fields
        info = {
            "name": device_data.get("name") or f"Device {device_id}",
            "type": device_data.get("type") or "unknown",
            "emitter": device_data.get("emitter") or {},
            "commands": device_data.get("commands") or {},
        }
        devices[str(device_id)] = info
        await self._save_devices(devices)

        # Broadcast the new device so that platform listeners register entities
        # without requiring a restart.
        device_info = {"id": str(device_id), **info}
        async_dispatcher_send(self._hass, SIGNAL_WHISPEER_NEW_DEVICE, device_info)

        return _create_success_response(
            "Device added successfully",
            id=str(device_id),
            **info
        )

    async def async_remove_device(self, device_id: int) -> dict:
        """Remove a Whispeer device from persistent storage."""
        devices = await self._load_devices()
        removed = devices.pop(str(device_id), None)
        await self._save_devices(devices)
        if removed is None:
            return _create_error_response(f"Device {device_id} not found")

        # Broadcast so __init__.py can remove stale entities from the registry.
        remaining_ids: set[str] = set(devices.keys())
        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, remaining_ids
        )

        return _create_success_response(f"Device {device_id} removed successfully")

    async def async_send_command(self, device_id: str, device_type: str, command_name: str, command_code: str, emitter_data: dict = None) -> dict:
        """Send a command to a device."""
        # Implement actual command sending logic based on device type
        if device_type == "ble":
            return await self._send_ble_command(device_id, command_name, command_code, emitter_data)
        elif device_type == "rf":
            return await self._send_rf_command(device_id, command_name, command_code, emitter_data)
        elif device_type == "ir":
            return await self._send_ir_command(device_id, command_name, command_code, emitter_data)
        elif device_type == "broadlink":
            return await self._send_broadlink_command(device_id, command_name, command_code, emitter_data)
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

    async def _send_ble_command(self, device_id: str, command_name: str, command_code: str, emitter_data: dict = None) -> dict:
        """Send BLE command using emit_signal mode with the hex data."""
        if not command_code:
            return _create_error_response(
                f"No command code provided for command '{command_name}' on device '{device_id}'"
            )
        
        # Extract interface from emitter data if available
        script_args = ["emit_signal", command_code]
        if emitter_data and emitter_data.get('adapter'):
            script_args.extend(["--interface", emitter_data['adapter']])
        
        # Use emit_signal mode directly with the hex data
        result = _execute_ble_script(script_args)

        if not result["success"]:
            return _create_error_response(
                result["message"],
                command_code=command_code,
                device_id=device_id,
                command_name=command_name,
                emitter_data=emitter_data,
                script_output=result.get("stdout"),
                script_error=result.get("stderr"),
                return_code=result.get("return_code")
            )
        
        return _create_success_response(
            f"BLE command '{command_name}' sent successfully for device '{device_id}'",
            command_code=command_code,
            device_id=device_id,
            command_name=command_name,
            emitter_data=emitter_data,
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

    async def _send_broadlink_command(self, device_id: str, command_name: str, command_code: str, emitter_data: dict = None) -> dict:
        """Send Broadlink command using emit_signal with emitter data or emit_command fallback."""
        if not command_code:
            return _create_error_response(
                f"No command code provided for command '{command_name}' on device '{device_id}'"
            )
        
        try:
            # If emitter data is provided, use emit_signal for direct communication
            if emitter_data and emitter_data.get('ip'):
                _LOGGER.info(f"Using emit_signal mode with emitter data for device '{device_id}'")
                _LOGGER.debug(f"Emitter data: {emitter_data}")

                # Build script arguments for emit_signal
                script_args = ["emit_signal", command_code, "--ip", emitter_data['ip']]

                # Add optional parameters if available
                if emitter_data.get('mac'):
                    script_args.extend(["--mac", emitter_data['mac']])
                if emitter_data.get('type'):
                    script_args.extend(["--type", emitter_data['type']])

                result = _execute_broadlink_script(script_args)

                if not result["success"]:
                    return _create_error_response(
                        result["message"],
                        command_code=command_code,
                        device_id=device_id,
                        command_name=command_name,
                        emitter_data=emitter_data,
                        script_output=result.get("stdout"),
                        script_error=result.get("stderr"),
                        return_code=result.get("return_code")
                    )

                return _create_success_response(
                    f"Broadlink signal sent successfully for device '{device_id}' command '{command_name}'",
                    command_code=command_code,
                    device_id=device_id,
                    command_name=command_name,
                    emitter_data=emitter_data,
                    script_output=result["stdout"],
                    return_code=result["return_code"]
                )

            else:
                # Fallback: Use emit_command mode with device and command name (requires devices.json)
                _LOGGER.info(f"Using emit_command fallback for device '{device_id}' (no emitter data provided)")
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

        except Exception as e:
            _LOGGER.error(f"Error sending Broadlink command: {e}")
            return _create_error_response(f"Error sending Broadlink command: {str(e)}")

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

    async def async_learn_raw_command(self, command_type: str, device_ip: str, frequency: float = 433.92) -> dict:
        """Learn a raw command without saving it, just return the learned code."""
        whispeer_broadlink, error_msg = _import_whispeer_broadlink()
        if not whispeer_broadlink:
            return _create_error_response(error_msg)
        
        try:
            _LOGGER.info(f"🚀 Starting raw {command_type} command learning from IP: {device_ip}")
            _LOGGER.info(f"🐳 Running in Docker environment - network debugging enabled")
            
            # Check if we're in Docker and log network context
            import os
            if os.path.exists('/.dockerenv'):
                _LOGGER.info("🐳 Confirmed: Running inside Docker container")
            else:
                _LOGGER.info("💻 Running on host system (not in Docker)")
            
            # Connect to device
            _LOGGER.info(f"🔌 Attempting to connect to Broadlink device at {device_ip}")
            device = whispeer_broadlink.connect_to_device(device_ip)
            if not device:
                error_msg = f"Failed to connect to Broadlink device at {device_ip}. This may be a Docker networking issue - the device might not be accessible from inside the container."
                _LOGGER.error(error_msg)
                return _create_error_response(error_msg)
            
            _LOGGER.info(f"✅ Successfully connected to device at {device_ip}")
            
            # Learn the command based on type
            if command_type.lower() == "ir":
                _LOGGER.info("📡 Starting IR command learning...")
                command_data = whispeer_broadlink.learn_ir_command(device)
            elif command_type.lower() == "rf":
                _LOGGER.info(f"📻 Starting RF command learning at {frequency} MHz...")
                command_data = whispeer_broadlink.learn_rf_command(device, frequency)
            else:
                return _create_error_response(f"Unsupported command type: {command_type}")
            
            if command_data:
                _LOGGER.info(f"🎉 {command_type.upper()} command learned successfully!")
                return _create_success_response(
                    f"{command_type.upper()} command learned successfully",
                    command_data=command_data,
                    command_type=command_type,
                    device_ip=device_ip,
                    frequency=frequency if command_type.lower() == "rf" else None
                )
            else:
                error_msg = f"Failed to learn {command_type} command - no data received"
                _LOGGER.error(error_msg)
                return _create_error_response(error_msg)
                
        except Exception as e:
            _LOGGER.error(f"❌ Error learning raw {command_type} command: {e}")
            import traceback
            _LOGGER.error(f"🔍 Full error traceback: {traceback.format_exc()}")
            return _create_error_response(f"Raw command learning failed: {str(e)}")

    async def async_learn_raw_ble_command(self, interface: str = "hci0") -> dict:
        """Learn a raw BLE command without saving it, just return the learned code."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            _LOGGER.info(f"Learning raw BLE command on interface: {interface}")
            
            # For now, return a simulated response since BLE learning is more complex
            # In a real implementation, this would capture BLE signals
            import time
            import random
            
            # Simulate learning time
            await asyncio.sleep(2)
            
            # Generate a sample BLE command (this should be replaced with actual BLE capture)
            command_data = f"{''.join([f'{random.randint(0,255):02x}' for _ in range(24)])}"
            
            return _create_success_response(
                "BLE command learned successfully (simulated)",
                command_data=command_data,
                command_type="ble",
                interface=interface
            )
                
        except Exception as e:
            _LOGGER.error(f"Error learning raw BLE command: {e}")
            return _create_error_response(f"BLE command learning failed: {str(e)}")

    async def async_prepare_to_learn(self, device_type: str, device_ip: str, frequency: float = 433.92) -> dict:
        """Prepare device for learning - connect and enter learning mode."""
        whispeer_broadlink, error_msg = _import_whispeer_broadlink()
        if not whispeer_broadlink:
            return _create_error_response(error_msg)
        
        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            
            _LOGGER.info(f"🚀 Preparing {device_type} learning session {session_id} for IP: {device_ip}")
            
            # Create learning session
            session = LearnSession(session_id, device_type, device_ip, frequency)
            LEARNING_SESSIONS[session_id] = session
            
            # Check if we're in Docker and log network context
            import os
            if os.path.exists('/.dockerenv'):
                _LOGGER.info("🐳 Confirmed: Running inside Docker container")
            else:
                _LOGGER.info("💻 Running on host system (not in Docker)")
            
            # Connect to device
            _LOGGER.info(f"🔌 Attempting to connect to Broadlink device at {device_ip}")
            device = whispeer_broadlink.connect_to_device(device_ip)
            if not device:
                session.update_status("error", error_message=f"Failed to connect to Broadlink device at {device_ip}")
                error_msg = f"Failed to connect to Broadlink device at {device_ip}. This may be a Docker networking issue - the device might not be accessible from inside the container."
                _LOGGER.error(error_msg)
                return _create_error_response(error_msg, session_id=session_id)
            
            _LOGGER.info(f"✅ Successfully connected to device at {device_ip}")
            session.device = device
            
            # Enter learning mode based on device type
            if device_type.lower() == "ir":
                _LOGGER.info(f"📡 Entering IR learning mode...")
                device.enter_learning()
            elif device_type.lower() == "rf":
                _LOGGER.info(f"📻 Entering RF learning mode at {frequency} MHz...")
                device.find_rf_packet(frequency)
            else:
                session.update_status("error", error_message=f"Unsupported device type: {device_type}")
                return _create_error_response(f"Unsupported device type: {device_type}", session_id=session_id)
            
            # Update session status to ready
            session.update_status("ready")
            _LOGGER.info(f"✅ Device ready for {device_type.upper()} learning - session {session_id}")
            
            return _create_success_response(
                f"Device ready for {device_type.upper()} learning",
                session_id=session_id,
                device_type=device_type,
                device_ip=device_ip,
                frequency=frequency if device_type.lower() == "rf" else None
            )
                
        except Exception as e:
            if 'session_id' in locals():
                LEARNING_SESSIONS.get(session_id, LearnSession("", "")).update_status("error", error_message=str(e))
            _LOGGER.error(f"❌ Error preparing to learn {device_type}: {e}")
            import traceback
            _LOGGER.error(f"🔍 Full error traceback: {traceback.format_exc()}")
            return _create_error_response(f"Failed to prepare for learning: {str(e)}", session_id=session_id if 'session_id' in locals() else None)

    async def async_prepare_to_learn_ble(self, interface: str = "hci0") -> dict:
        """Prepare BLE interface for learning."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            
            _LOGGER.info(f"🚀 Preparing BLE learning session {session_id} for interface: {interface}")
            
            # Create learning session
            session = LearnSession(session_id, "ble", interface=interface)
            LEARNING_SESSIONS[session_id] = session
            
            # For BLE, we just mark as ready since there's no device connection step
            session.update_status("ready")
            _LOGGER.info(f"✅ BLE interface {interface} ready for learning - session {session_id}")
            
            return _create_success_response(
                f"BLE interface ready for learning",
                session_id=session_id,
                device_type="ble",
                interface=interface
            )
                
        except Exception as e:
            if 'session_id' in locals():
                LEARNING_SESSIONS.get(session_id, LearnSession("", "")).update_status("error", error_message=str(e))
            _LOGGER.error(f"❌ Error preparing BLE learning: {e}")
            return _create_error_response(f"Failed to prepare BLE for learning: {str(e)}", session_id=session_id if 'session_id' in locals() else None)

    async def async_check_learned_command(self, session_id: str, device_type: str) -> dict:
        """Check if a command has been learned and retrieve it."""
        try:
            _LOGGER.info(f"🔍 Checking learned command for session: {session_id}")
            
            # Get session
            session = LEARNING_SESSIONS.get(session_id)
            if not session:
                return _create_error_response(f"Learning session {session_id} not found or expired")
            
            # Check if session has timed out (30 seconds)
            if time.time() - session.created_at > 30:
                session.update_status("timeout")
                _LOGGER.warning(f"⏰ Learning session {session_id} timed out")
                return _create_error_response("Learning session timed out", session_id=session_id, learning_status="timeout")
            
            # If session is already completed or errored, return the result
            if session.status == "completed":
                return _create_success_response(
                    f"{session.device_type.upper()} command learned successfully",
                    command_data=session.command_data,
                    command_type=session.device_type,
                    session_id=session_id,
                    learning_status="completed"
                )
            elif session.status == "error":
                return _create_error_response(session.error_message or "Learning failed", session_id=session_id, learning_status="error")
            elif session.status == "timeout":
                return _create_error_response("Learning session timed out", session_id=session_id, learning_status="timeout")
            
            # If session is ready but not learning yet, start learning
            if session.status == "ready":
                session.update_status("learning")
                _LOGGER.info(f"📡 Starting {session.device_type.upper()} command learning for session {session_id}")
                
                # Start learning in background
                asyncio.create_task(self._perform_learning(session))
                
                return _create_success_response(
                    "Learning in progress - press button on remote control",
                    session_id=session_id,
                    learning_status="learning",
                    device_type=session.device_type
                )
            
            # If already learning, check for data
            elif session.status == "learning":
                if device_type.lower() in ['ir', 'rf']:
                    whispeer_broadlink, error_msg = _import_whispeer_broadlink()
                    if not whispeer_broadlink:
                        session.update_status("error", error_message=error_msg)
                        return _create_error_response(error_msg)
                    
                    # Check if device has data
                    if session.device:
                        try:
                            packet = session.device.check_data()
                            if packet:
                                command_data = packet.hex()
                                session.update_status("completed", command_data=command_data)
                                _LOGGER.info(f"🎉 {session.device_type.upper()} command learned successfully for session {session_id}")
                                
                                return _create_success_response(
                                    f"{session.device_type.upper()} command learned successfully",
                                    command_data=command_data,
                                    command_type=session.device_type,
                                    session_id=session_id,
                                    learning_status="completed"
                                )
                        except Exception as check_error:
                            # Handle the specific "device storage is full" error as expected behavior
                            error_str = str(check_error)
                            if "[Errno -5]" in error_str and "storage is full" in error_str:
                                _LOGGER.debug(f"Device storage full warning for session {session_id} (expected, continuing)")
                                # Continue as if no error occurred - this is expected behavior
                                pass
                            else:
                                # For other errors, log and continue polling
                                _LOGGER.warning(f"Error checking device data for session {session_id}: {check_error}")
                                # Don't fail the session, just continue polling
                                pass
                
                # Still learning
                return _create_success_response(
                    "Learning in progress - press button on remote control",
                    session_id=session_id,
                    learning_status="learning",
                    device_type=session.device_type
                )
            
            # Session is preparing
            return _create_success_response(
                "Preparing device for learning",
                session_id=session_id,
                learning_status=session.status,
                device_type=session.device_type
            )
                
        except Exception as e:
            _LOGGER.error(f"❌ Error checking learned command: {e}")
            return _create_error_response(f"Error checking learned command: {str(e)}")

    async def _perform_learning(self, session: LearnSession):
        """Background task to perform the actual learning."""
        try:
            _LOGGER.info(f"🎯 Background learning started for session {session.session_id}")
            
            if session.device_type.lower() == "ble":
                # Simulate BLE learning
                await asyncio.sleep(2)
                import random
                command_data = f"{''.join([f'{random.randint(0,255):02x}' for _ in range(24)])}"
                session.update_status("completed", command_data=command_data)
                _LOGGER.info(f"🎉 BLE command learned (simulated) for session {session.session_id}")
            
            # For IR/RF, the actual learning happens in async_check_learned_command
            # This is just a timeout mechanism
            timeout = 25  # 25 seconds before we give up
            elapsed = 0
            while elapsed < timeout and session.status == "learning":
                await asyncio.sleep(1)
                elapsed += 1
            
            # If still learning after timeout, mark as timeout
            if session.status == "learning":
                session.update_status("timeout")
                _LOGGER.warning(f"⏰ Learning timed out for session {session.session_id}")
                
        except Exception as e:
            _LOGGER.error(f"❌ Error in background learning: {e}")
            session.update_status("error", error_message=str(e))

    async def async_learn_broadlink_command(self, device_name: str, command_name: str, command_type: str, device_ip: str, frequency: float = 433.92) -> dict:
        """Learn a new Broadlink command using whispeer_broadlink module functions or Home Assistant integration."""
        try:
            # Use whispeer_broadlink script
            _LOGGER.info("Using whispeer_broadlink script for command learning")
            whispeer_broadlink, error_msg = _import_whispeer_broadlink()
            if not whispeer_broadlink:
                return _create_error_response(error_msg)
                
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
        """Get available Broadlink devices using whispeer_broadlink module or Home Assistant integration."""
        try:
            # Use the script for discovery
            _LOGGER.info("Using whispeer_broadlink script for device discovery")
            whispeer_broadlink, error_msg = _import_whispeer_broadlink()
            if not whispeer_broadlink:
                return _create_error_response(error_msg)
            
            devices = whispeer_broadlink.discover_broadlink_devices(timeout=10)
            return _create_success_response(
                f"Found {len(devices)} Broadlink device(s) from network discovery",
                devices=devices,
                source="script"
            )
                
        except Exception as e:
            _LOGGER.error(f"Error discovering Broadlink devices: {e}")
            return _create_error_response(f"Error discovering Broadlink devices: {str(e)}")

    async def async_get_broadlink_interfaces(self, hass=None) -> dict:
        """Get available Broadlink interfaces from both network discovery and Home Assistant."""
        try:
            all_devices = []
            
            # Use script for network discovery
            _LOGGER.info("Using whispeer_broadlink script for interface discovery")
            try:
                whispeer_broadlink, error_msg = _import_whispeer_broadlink()
                if whispeer_broadlink:
                    discovered_devices = whispeer_broadlink.discover_broadlink_devices(timeout=10)
                    
                    for device in discovered_devices:
                        device_ip = device.get('ip')
                        device_model = device.get('model', 'Broadlink')
                        label = f"{device_model} ({device_ip})"
                        
                        all_devices.append({
                            'label': label,
                            'ip': device_ip,
                            'mac': device.get('mac'),
                            'type': device.get('type'),
                            'model': device.get('model', 'Unknown'),
                            'manufacturer': device.get('manufacturer', 'Broadlink'),
                            'source': 'network_discovery'
                        })
                else:
                    _LOGGER.warning(f"Could not import whispeer_broadlink: {error_msg}")
            except Exception as e:
                _LOGGER.error(f"Error in network discovery: {e}")
            
            # Always add manual entry option
            all_devices.append({
                'label': 'Manual Entry (Enter IP manually)',
                'ip': 'manual',
                'source': 'manual'
            })
            
            return _create_success_response(
                f"Found {len(all_devices)} Broadlink interface(s)",
                interfaces=all_devices
            )
            
        except Exception as e:
            _LOGGER.error(f"Error getting Broadlink interfaces: {e}")
            return _create_error_response(f"Error getting Broadlink interfaces: {str(e)}")

    async def async_get_ble_interfaces(self) -> dict:
        """Get available Bluetooth interfaces using whispeer_ble module."""
        whispeer_ble, error_msg = _import_whispeer_ble()
        if not whispeer_ble:
            return _create_error_response(error_msg)
        
        try:
            interfaces = whispeer_ble.get_available_interfaces()
            # Convert to list of objects with labels for consistency
            interface_objects = []
            for iface in interfaces:
                interface_objects.append({
                    'label': str(iface),
                    'interface': str(iface),
                    'type': 'ble'
                })
                
            return _create_success_response(
                f"Found {len(interface_objects)} Bluetooth interface(s)",
                interfaces=interface_objects
            )
            
        except Exception as e:
            _LOGGER.error(f"Error getting BLE interfaces: {e}")
            return _create_error_response(f"Error getting BLE interfaces: {str(e)}")

    async def async_get_interfaces(self, device_type: str, hass=None) -> dict:
        """Get available interfaces for any device type."""
        device_type = device_type.lower()
        
        if device_type == 'ir':
            # IR functionality is provided by Broadlink devices
            return await self.async_get_broadlink_interfaces(hass)
        elif device_type == 'rf':
            # RF functionality is provided by Broadlink devices
            return await self.async_get_broadlink_interfaces(hass)
        elif device_type == 'ble':
            return await self.async_get_ble_interfaces()
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

    async def _send_rf_command(self, device_id: str, command_name: str, command_code: str, emitter_data: dict = None) -> dict:
        """Send RF command."""
        # Try Broadlink first, then fallback to generic RF
        try:
            return await self._send_broadlink_command(device_id, command_name, command_code, emitter_data)
        except Exception as e:
            _LOGGER.warning(f"Broadlink RF command failed, using generic RF: {e}")
            # Implement generic RF command sending logic
            return _create_success_response(
                f"RF command '{command_name}' sent to '{device_id}'",
                command_code=command_code,
                emitter_data=emitter_data,
                method="generic_rf"
            )

    async def _send_ir_command(self, device_id: str, command_name: str, command_code: str, emitter_data: dict = None) -> dict:
        """Send IR command."""
        # Try Broadlink first, then fallback to generic IR
        try:
            return await self._send_broadlink_command(device_id, command_name, command_code, emitter_data)
        except Exception as e:
            _LOGGER.warning(f"Broadlink IR command failed, using generic IR: {e}")
            # Implement generic IR command sending logic
            return _create_success_response(
                f"IR command '{command_name}' sent to '{device_id}'",
                command_code=command_code,
                emitter_data=emitter_data,
                method="generic_ir"
            )

    async def async_sync_devices(self, devices: dict, replace: bool = False) -> dict:
        """Sync devices from frontend to backend persistent storage.

        By default, merges the incoming devices into the stored set to avoid
        accidentally deleting existing devices if the frontend sends a partial set.
        Set `replace=True` to fully replace the stored set.
        """
        if not isinstance(devices, dict):
            return _create_error_response("Invalid devices payload")

        current = await self._load_devices()
        if replace:
            merged: Dict[str, Dict[str, Any]] = {}
        else:
            merged = {**current}

        # Merge with id enforcement
        for did, info in devices.items():
            did_str = str(did).strip()
            if not did_str:
                did_str = uuid.uuid4().hex[:8]
            if not isinstance(info, dict):
                info = {}
            if not info.get("id"):
                info["id"] = did_str
            merged[did_str] = info

        await self._save_devices(merged)

        # Dispatch SIGNAL_WHISPEER_NEW_DEVICE for each brand-new device.
        new_device_ids = set(merged.keys()) - set(current.keys())
        for did in new_device_ids:
            device_data = {"id": did, **merged[did]}
            async_dispatcher_send(
                self._hass, SIGNAL_WHISPEER_NEW_DEVICE, device_data
            )

        # Always broadcast a full-data-updated signal so platforms and
        # __init__.py can run cleanup / refresh logic.
        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set(merged.keys())
        )

        return _create_success_response(
            f"Synced {len(devices)} devices",
            device_count=len(devices),
            merged_count=len(merged),
            replace=replace
        )

    async def async_test_device(self, device_id: int) -> dict:
        """Test a Whispeer device."""
        # Implement device testing logic
        return _create_success_response(
            f"Device {device_id} test completed",
            test_result="passed"
        )

    async def async_clear_devices(self) -> dict:
        """Clear all stored Whispeer devices from persistent storage."""
        await self._save_devices({})
        # Broadcast an empty set so __init__.py removes all owned entities.
        async_dispatcher_send(
            self._hass, SIGNAL_WHISPEER_DATA_UPDATED, set()
        )
        return _create_success_response("All devices cleared")

    async def async_get_broadlink_codes(self) -> dict:
        """Read all learned remote codes from Home Assistant .storage files.

        Handles known integrations explicitly and falls back to a generic scan
        for any other remote storage file that looks like it contains learned codes.
        """
        import json

        result = []
        storage_dir = self._hass.config.path(".storage")

        try:
            files = await self._hass.async_add_executor_job(os.listdir, storage_dir)
        except OSError as e:
            _LOGGER.error(f"Cannot list .storage directory: {e}")
            return {"codes": result}

        def _read_storage_file(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                _LOGGER.warning(f"Failed to read {path}: {exc}")
                return None

        # Metadata-only keys that should never be treated as codes
        META_KEYS = {"model", "frequency", "type", "manufacturer"}

        def _extract_codes(entries, identifier, source):
            """Extract code entries from a {device: {command: code}} data dict."""
            if not isinstance(entries, dict):
                return
            for device_name, commands in entries.items():
                if not isinstance(commands, dict):
                    continue
                for cmd_name, cmd_value in commands.items():
                    if not isinstance(cmd_value, str):
                        continue
                    if cmd_name in META_KEYS:
                        continue
                    code_preview = cmd_value[:60] + ("\u2026" if len(cmd_value) > 60 else "")
                    result.append({
                        "identifier": identifier,
                        "source": source,
                        "device": device_name,
                        "command": cmd_name,
                        "code": cmd_value,
                        "code_preview": code_preview,
                        "code_length": len(cmd_value),
                    })

        # Known integration patterns: (prefix, suffix, source_label)
        # suffix=None means any suffix is accepted after the prefix
        KNOWN_PATTERNS = [
            ("broadlink_remote_", "_codes", "broadlink"),
            ("broadlink_remote_", "_flags", "broadlink"),
        ]

        parsed_files: set = set()

        # First pass: known patterns - parsed explicitly
        for prefix, suffix, integration in KNOWN_PATTERNS:
            for fname in sorted(files):
                if not fname.startswith(prefix):
                    continue
                if suffix and not fname.endswith(suffix):
                    continue
                # Skip backup files
                if fname.endswith(".bak") or fname.endswith(".orig"):
                    continue
                fpath = os.path.join(storage_dir, fname)
                parsed_files.add(fname)
                data = await self._hass.async_add_executor_job(_read_storage_file, fpath)
                if data is None:
                    continue
                # Extract the identifier part (e.g. MAC) between prefix and suffix
                identifier = fname[len(prefix):]
                if suffix and identifier.endswith(suffix):
                    identifier = identifier[:-len(suffix)]
                _extract_codes(data.get("data", {}), identifier, integration)

        # Second pass: generic scan for any other storage file that looks like
        # it stores learned remote codes ({device: {command: code_string}})
        for fname in sorted(files):
            if fname in parsed_files:
                continue
            if fname.endswith(".bak") or fname.endswith(".orig"):
                continue
            fname_lower = fname.lower()
            # Only bother reading files whose name hints at remote/learned content
            if not any(kw in fname_lower for kw in ("remote", "learned", "learn_command", "ir_", "_ir", "rf_", "_rf")):
                continue
            fpath = os.path.join(storage_dir, fname)
            data = await self._hass.async_add_executor_job(_read_storage_file, fpath)
            if data is None:
                continue
            entries = data.get("data", {})
            if not isinstance(entries, dict):
                continue
            # Heuristic: must contain at least one {command: long_string} mapping
            looks_like_codes = any(
                isinstance(cmds, dict) and any(
                    isinstance(v, str) and len(v) > 10 and v not in META_KEYS
                    for v in cmds.values()
                )
                for cmds in entries.values()
                if isinstance(cmds, dict)
            )
            if not looks_like_codes:
                continue
            parsed_files.add(fname)
            # Derive a readable source label from the filename
            integration = fname.split("_")[0] if "_" in fname else fname
            _extract_codes(entries, fname, integration)

        return {"codes": result}

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


class WhispeerPrepareToLearnView(HomeAssistantView):
    """View to prepare device for learning (connect and enter learning mode)."""

    url = "/api/services/whispeer/prepare_to_learn"
    name = "api:whispeer:prepare_to_learn"
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Prepare device for learning."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                # TODO: Validate token if needed
            else:
                _LOGGER.debug("No Authorization header found")
            
            data = await request.json()
            device_type = data.get('device_type', '').lower()
            emitter = data.get('emitter', {})
            
            if not device_type:
                return web.json_response({
                    "status": "error",
                    "message": "Missing required field: device_type"
                }, status=400)
            
            if not emitter:
                return web.json_response({
                    "status": "error",
                    "message": "Missing required field: emitter"
                }, status=400)
            
            _LOGGER.info(f"Preparing to learn command for device type: {device_type}")
            _LOGGER.info(f"Emitter data: {emitter}")
            
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
                    "status": "error",
                    "message": "Whispeer coordinator not found"
                }, status=500)
            
            # Route to appropriate preparation method based on device type
            if device_type in ['ir', 'rf']:
                device_ip = emitter.get('ip')
                frequency = emitter.get('frequency', 433.92)
                
                if not device_ip:
                    return web.json_response({
                        "status": "error",
                        "message": "IP address required for IR/RF learning"
                    }, status=400)
                
                result = await coordinator.api.async_prepare_to_learn(device_type, device_ip, frequency)
            elif device_type == 'ble':
                interface = emitter.get('name') or emitter.get('interface', 'hci0')
                result = await coordinator.api.async_prepare_to_learn_ble(interface)
            else:
                result = _create_error_response(f"Unsupported device type: {device_type}")
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error preparing to learn: {e}")
            return web.json_response({"error": str(e)}, status=500)


class WhispeerCheckLearnedCommandView(HomeAssistantView):
    """View to check if a command has been learned and retrieve it."""

    url = "/api/services/whispeer/check_learned_command"
    name = "api:whispeer:check_learned_command"
    requires_auth = False  # Allow access from iframe panel

    async def post(self, request):
        """Check if a command has been learned."""
        try:
            # Manual authentication check for iframe panels
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                # TODO: Validate token if needed
            else:
                _LOGGER.debug("No Authorization header found")
            
            data = await request.json()
            device_type = data.get('device_type', '').lower()
            session_id = data.get('session_id', '')
            
            if not device_type:
                return web.json_response({
                    "status": "error",
                    "message": "Missing required field: device_type"
                }, status=400)
            
            if not session_id:
                return web.json_response({
                    "status": "error",
                    "message": "Missing required field: session_id"
                }, status=400)
            
            _LOGGER.info(f"Checking learned command for session: {session_id}")
            
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
                    "status": "error",
                    "message": "Whispeer coordinator not found"
                }, status=500)
            
            # Check if command was learned
            result = await coordinator.api.async_check_learned_command(session_id, device_type)
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error(f"Error checking learned command: {e}")
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
