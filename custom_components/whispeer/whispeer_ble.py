#!/usr/bin/env python3
"""
Whispeer BLE Command Emitter
Linux/Home Assistant focused BLE advertiser using BlueZ (hcitool/hciconfig) with a simple
simulation fallback when tools or hardware are unavailable.

Removed multi-platform / bleak abstraction to keep the script lean for target deployment.
"""

import subprocess
import sys
import time
import shutil
import json
import os
import argparse
import re

def load_devices():
    """Load devices from devices.json file."""
    try:
        # Try to find devices.json in the same directory as this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        devices_file = os.path.join(script_dir, "devices.json")
        
        if not os.path.exists(devices_file):
            # If not found, try relative path
            devices_file = "devices.json"
        
        with open(devices_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ devices.json file not found. Please ensure it exists in the script directory.")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing devices.json: {e}")
        return {}
    except Exception as e:
        print(f"❌ Error loading devices.json: {e}")
        return {}

def get_available_interfaces():
    """Get list of available Bluetooth interfaces."""
    interfaces = []
    
    # Linux detection (primary target platform)
    try:
        # Try hciconfig first (Linux)
        result = subprocess.run(['hciconfig'], capture_output=True, text=True)
        if result.returncode == 0:
            # Parse hciconfig output
            lines = result.stdout.split('\n')
            for line in lines:
                if line.startswith('hci'):
                    interface = line.split(':')[0]
                    # Check if interface is UP
                    if 'UP RUNNING' in line:
                        status = 'UP'
                    elif 'DOWN' in line:
                        status = 'DOWN'
                    else:
                        status = 'UNKNOWN'
                    
                    interfaces.append({
                        'name': interface,
                        'status': status,
                        'type': 'bluetooth',
                        'platform': 'linux'
                    })
    except FileNotFoundError:
        pass
    
    # If no interfaces found with hciconfig, try bluetoothctl (modern Linux)
    if not interfaces:
        try:
            result = subprocess.run(['bluetoothctl', 'list'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'Controller' in line:
                        # Extract controller info
                        parts = line.split()
                        if len(parts) >= 2:
                            mac_addr = parts[1]
                            name = ' '.join(parts[2:]) if len(parts) > 2 else 'Unknown'
                            interfaces.append({
                                'name': f'hci{len(interfaces)}',  # Assume sequential naming
                                'mac': mac_addr,
                                'description': name,
                                'status': 'AVAILABLE',
                                'type': 'bluetooth',
                                'platform': 'linux'
                            })
        except FileNotFoundError:
            pass
    
    # If no interfaces found, provide a default simulation interface
    if not interfaces:
        interfaces.append({
            'name': 'sim0',
            'description': 'Simulation Interface (no hardware)',
            'status': 'SIMULATION',
            'type': 'simulation'
        })
    
    return interfaces

def check_bluetooth_availability():
    """Check if Bluetooth tools are available in the current environment."""
    # Check for Linux BLE tools
    hcitool_available = shutil.which("hcitool") is not None
    hciconfig_available = shutil.which("hciconfig") is not None
    bluetoothctl_available = shutil.which("bluetoothctl") is not None
    
    # Primary availability (Linux native tools)
    linux_available = hcitool_available and hciconfig_available
    
    return {
        "hcitool": hcitool_available,
        "hciconfig": hciconfig_available,
        "bluetoothctl": bluetoothctl_available,
        "available": linux_available,
        "modern": bluetoothctl_available,
    }

def hex_str_to_list(hexstr):
    """Convert hex string to list of hex bytes."""
    return [hexstr[i:i+2].upper() for i in range(0, len(hexstr), 2)]

def build_adv_payload(data_hex):
    """Build BLE advertisement payload."""
    flags = ["02", "01", "06"]
    # Hardcoded UUID for now - F0 08
    uuid = "F0 08"
    service_data = ["16"] + uuid.split() + hex_str_to_list(data_hex)
    service_len = f"{len(service_data):02X}"
    full_payload = flags + [service_len] + service_data
    length_byte = f"{len(full_payload):02X}"
    return [length_byte] + full_payload

def run_cmd(cmd):
    """Execute command with error handling."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(f"Output: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        raise

def emit_signal(data_hex, interface=None):
    """
    Emit a raw BLE signal.
    
    Args:
        data_hex: Hex data to send
        interface: Bluetooth interface to use (e.g., "hci0"). If None, use first available.
    
    Returns:
        bool: True if successful, False otherwise
    """
    bt_status = check_bluetooth_availability()

    # Linux implementation using hcitool (only supported hardware path now)
    if bt_status["available"]:
        if interface is None:
            interfaces = get_available_interfaces()
            if not interfaces:
                print("❌ No Bluetooth interfaces available")
                return False
            interface = interfaces[0]['name']
            print(f"ℹ️  Using interface: {interface}")
        
        payload = build_adv_payload(data_hex)
        base_cmd = ["hcitool", "-i", interface, "cmd"]
        
        print(f"📡 Emitting signal on {interface}")
        print(f"📊 Data: {data_hex}")
        print(f"📦 Payload: {' '.join(payload)}")
        
        try:
            run_cmd(base_cmd + ["0x08", "0x000A", "00"])      # Disable advertising
            run_cmd(base_cmd + ["0x08", "0x0008"] + payload)  # Set new payload
            run_cmd(base_cmd + ["0x08", "0x000A", "01"])      # Enable advertising

            time.sleep(0.4)  # Small pause for reliability
            print(f"✅ Signal emitted successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to emit signal: {e}")
            return False
    
    # Basic simulation fallback
    payload = build_adv_payload(data_hex)
    print("⚠️  Bluetooth tools not available - running in basic simulation mode")
    print(f"🔄 SIMULATION: Would emit signal")
    print(f"📊 Data: {data_hex}")
    print(f"📦 Payload: {' '.join(payload)}")
    print(f"✅ Signal simulated successfully")
    return True

def emit_command(device_name, command_names, interface=None):
    """
    Emit one or more known commands for a registered device.
    
    Args:
        device_name: Name of the device (must exist in devices.json)
        command_names: List of command names (must exist for the device)
        interface: Bluetooth interface to use. If None, use first available.
    
    Returns:
        bool: True if all commands successful, False otherwise
    """
    devices = load_devices()
    
    if not devices:
        print("❌ No devices loaded from devices.json")
        return False
    
    if device_name not in devices:
        print(f"❌ Device '{device_name}' not found in devices.json")
        print("Available devices:")
        for name in devices.keys():
            print(f"  - {name}")
        return False
    
    device = devices[device_name]
    
    # Validate all commands exist before executing any
    for command_name in command_names:
        if command_name not in device.get("commands", {}):
            print(f"❌ Command '{command_name}' not found for device '{device_name}'")
            print("Available commands:")
            for cmd in device.get("commands", {}).keys():
                print(f"  - {cmd}")
            return False
    
    # Execute all commands
    success_count = 0
    for command_name in command_names:
        data_hex = device["commands"][command_name]
        
        print(f"📱 Sending command '{command_name}' to device '{device_name}'")
        
        if emit_signal(data_hex, interface):
            success_count += 1
            print(f"✅ Command '{command_name}' executed successfully")
        else:
            print(f"❌ Command '{command_name}' failed")
    
    if success_count == len(command_names):
        print(f"✅ All {success_count} commands executed successfully")
        return True
    else:
        print(f"⚠️  {success_count} out of {len(command_names)} commands executed successfully")
        return False

def list_devices():
    """List all available devices and their commands."""
    devices = load_devices()
    
    if not devices:
        print("❌ No devices found in devices.json")
        return
    
    print("📱 Available devices:")
    print("=" * 50)
    
    for device_name, device_info in devices.items():
        print(f"\n🔹 {device_name}")
        print(f"   UUID: {device_info.get('uuid', 'Unknown')}")
        print(f"   Commands: {len(device_info.get('commands', {}))}")
        
        if device_info.get('commands'):
            print("   Available commands:")
            for cmd_name in device_info['commands'].keys():
                print(f"     - {cmd_name}")

def list_interfaces():
    """List all available Bluetooth interfaces."""
    interfaces = get_available_interfaces()
    
    print("🔷 Available Bluetooth interfaces:")
    print("=" * 50)
    
    if not interfaces:
        print("❌ No Bluetooth interfaces found")
        return
    
    for i, interface in enumerate(interfaces, 1):
        print(f"\n{i}. {interface['name']}")
        print(f"   Status: {interface['status']}")
        print(f"   Type: {interface['type']}")
        if 'description' in interface:
            print(f"   Description: {interface['description']}")
        
        if 'platform' in interface:
            print(f"   Platform: {interface['platform']}")
        
        if 'details' in interface:
            details = interface['details']
            if 'address' in details and details['address'] != 'Unknown':
                print(f"   Address: {details['address']}")
            if 'firmware' in details and details['firmware'] != 'Unknown':
                print(f"   Firmware: {details['firmware']}")
            if 'chipset' in details and details['chipset'] != 'Unknown':
                print(f"   Chipset: {details['chipset']}")
            if 'state' in details and details['state'] != 'Unknown':
                print(f"   State: {details['state']}")
        if 'mac' in interface:
            print(f"   MAC: {interface['mac']}")
        

def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Whispeer BLE Command Emitter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Emit a single known command
  python3 whispeer_ble.py emit_command ventilador_oficina light_on
  
  # Emit multiple commands
  python3 whispeer_ble.py emit_command ventilador_oficina light_on fan_speed_3 beep_on
  
  # Emit a raw signal
  python3 whispeer_ble.py emit_signal "100005c701c70fcd3c404b93b840d19185c8d1457459a1eb"
  
  # List available devices
  python3 whispeer_ble.py list_devices
  
  # List available interfaces
  python3 whispeer_ble.py list_interfaces
  
  # Specify interface
  python3 whispeer_ble.py emit_command ventilador_oficina light_on --interface hci1
        """
    )
    
    subparsers = parser.add_subparsers(dest='mode', help='Operation mode')
    
    # emit_command subcommand
    cmd_parser = subparsers.add_parser('emit_command', help='Emit a known command')
    cmd_parser.add_argument('device_name', help='Device name (from devices.json)')
    cmd_parser.add_argument('command_names', nargs='+', help='Command name(s) - can specify multiple commands')
    cmd_parser.add_argument('--interface', '-i', help='Bluetooth interface to use (e.g., hci0)')
    
    # emit_signal subcommand
    signal_parser = subparsers.add_parser('emit_signal', help='Emit a raw signal')
    signal_parser.add_argument('data', help='Hex data to send')
    signal_parser.add_argument('--interface', '-i', help='Bluetooth interface to use (e.g., hci0)')
    
    # list_devices subcommand
    subparsers.add_parser('list_devices', help='List available devices')
    
    # list_interfaces subcommand
    subparsers.add_parser('list_interfaces', help='List available Bluetooth interfaces')
    
    
    args = parser.parse_args()
    
    # Handle legacy command line format (backwards compatibility)
    if not args.mode and len(sys.argv) >= 3:
        # Legacy format: python3 whispeer_ble.py <device_name> <command_1> [<command_2> ...]
        device_name = sys.argv[1]
        command_names = sys.argv[2:]  # All remaining arguments are command names
        
        print("ℹ️  Using legacy command format. Consider using: emit_command subcommand")
        success = emit_command(device_name, command_names, None)
        sys.exit(0 if success else 1)
    
    if not args.mode:
        parser.print_help()
        sys.exit(1)
    
    # Execute based on mode
    if args.mode == 'emit_command':
        success = emit_command(args.device_name, args.command_names, args.interface)
        sys.exit(0 if success else 1)
    
    elif args.mode == 'emit_signal':
        success = emit_signal(args.data, args.interface)
        sys.exit(0 if success else 1)
    
    elif args.mode == 'list_devices':
        list_devices()
    
    elif args.mode == 'list_interfaces':
        list_interfaces()
    
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
