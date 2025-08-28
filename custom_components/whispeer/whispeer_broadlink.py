#!/usr/bin/env python3
"""
Whispeer Broadlink Command Emitter
Home Assistant focused IR/RF controller using Broadlink devices.

Supports learning and sending IR/RF commands through Broadlink devices like RM4 Pro/Mini.
"""

import sys
import time
import json
import os
import argparse
import broadlink
import socket

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

def save_devices(devices):
    """Save devices to devices.json file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        devices_file = os.path.join(script_dir, "devices.json")
        
        with open(devices_file, 'w', encoding='utf-8') as f:
            json.dump(devices, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error saving devices.json: {e}")
        return False

def discover_broadlink_devices(timeout=5):
    """Discover Broadlink devices on the network."""
    print(f"🔍 Searching for Broadlink devices on the network (timeout: {timeout}s)...")
    try:
        devices = broadlink.discover(timeout=timeout)
        found_devices = []
        
        for device in devices:
            device_info = {
                'ip': device.host[0],
                'port': device.host[1],
                'mac': device.mac.hex(),
                'type': hex(device.devtype),
                'model': getattr(device, 'model', 'Unknown'),
                'manufacturer': getattr(device, 'manufacturer', 'Broadlink')
            }
            found_devices.append(device_info)
            
        return found_devices
    except Exception as e:
        print(f"❌ Error discovering devices: {e}")
        return []

def connect_to_device(ip, mac=None, device_type=None):
    """Connect to a specific Broadlink device."""
    try:
        if mac and device_type:
            # Fast connection with known parameters
            mac_bytes = bytes.fromhex(mac.replace(':', ''))
            device = broadlink.gendevice(int(device_type, 16), (ip, 80), mac_bytes)
        else:
            # Discover and find the specific device
            devices = broadlink.discover(timeout=5)
            device = None
            for dev in devices:
                if dev.host[0] == ip:
                    device = dev
                    break
            
            if not device:
                print(f"❌ Device with IP {ip} not found")
                return None
        
        # Authenticate
        if device.auth():
            print(f"✅ Connected and authenticated to device at {ip}")
            return device
        else:
            print(f"❌ Authentication failed for device at {ip}")
            return None
            
    except Exception as e:
        print(f"❌ Error connecting to device: {e}")
        return None

def learn_ir_command(device, timeout=30):
    """Learn an IR command from the device."""
    try:
        print("📡 Starting IR learning mode...")
        device.enter_learning()
        print(f"👆 Point your remote at the device and press the button (timeout: {timeout}s)")
        
        for i in range(timeout, 0, -1):
            time.sleep(1)
            packet = device.check_data()
            if packet:
                print(f"\n✅ IR command learned successfully!")
                return packet.hex()
            else:
                print(f"{i}...", end="", flush=True)
        
        print(f"\n❌ No IR command detected within {timeout} seconds")
        return None
        
    except Exception as e:
        print(f"❌ Error learning IR command: {e}")
        return None

def learn_rf_command(device, frequency=433.92, timeout=30):
    """Learn an RF command from the device."""
    try:
        print(f"📡 Starting RF learning mode on {frequency} MHz...")
        device.sweep_frequency()
        print(f"👆 Hold the button on your RF remote near the device to detect frequency...")
        
        # Wait for frequency detection
        freq_detected = False
        for i in range(15, 0, -1):
            time.sleep(1)
            freq_found, detected_freq = device.check_frequency()
            if freq_found:
                print(f"\n✅ Frequency detected: {detected_freq} MHz")
                freq_detected = True
                break
            else:
                print(f"{i}...", end="", flush=True)
        
        if not freq_detected:
            print(f"\n⚠️  No frequency detected, using default {frequency} MHz")
            device.find_rf_packet(frequency)
        else:
            device.find_rf_packet()
        
        print("👆 Now press the button briefly to learn the command...")
        
        for i in range(timeout, 0, -1):
            time.sleep(1)
            packet = device.check_data()
            if packet:
                print(f"\n✅ RF command learned successfully!")
                return packet.hex()
            else:
                print(f"{i}...", end="", flush=True)
        
        print(f"\n❌ No RF command detected within {timeout} seconds")
        return None
        
    except Exception as e:
        print(f"❌ Error learning RF command: {e}")
        return None

def send_command(device, command_data):
    """Send an IR/RF command through the device."""
    try:
        command_bytes = bytes.fromhex(command_data)
        device.send_data(command_bytes)
        print("✅ Command sent successfully")
        return True
    except Exception as e:
        print(f"❌ Error sending command: {e}")
        return False

def emit_command(device_name, command_names, device_ip=None):
    """
    Emit one or more known commands for a registered device.
    
    Args:
        device_name: Name of the device (must exist in devices.json)
        command_names: List of command names (must exist for the device)
        device_ip: IP address of the Broadlink device. If None, use first available.
    
    Returns:
        bool: True if all commands successful, False otherwise
    """
    devices_config = load_devices()
    
    if not devices_config:
        print("❌ No devices loaded from devices.json")
        return False
    
    if device_name not in devices_config:
        print(f"❌ Device '{device_name}' not found in devices.json")
        print("Available devices:")
        for name in devices_config.keys():
            print(f"  - {name}")
        return False
    
    device_config = devices_config[device_name]
    
    # Validate all commands exist before executing any
    for command_name in command_names:
        if command_name not in device_config.get("commands", {}):
            print(f"❌ Command '{command_name}' not found for device '{device_name}'")
            print("Available commands:")
            for cmd in device_config.get("commands", {}).keys():
                print(f"  - {cmd}")
            return False
    
    # Connect to Broadlink device
    if not device_ip:
        broadlink_config = device_config.get("broadlink", {})
        device_ip = broadlink_config.get("ip")
        if not device_ip:
            print("❌ No Broadlink device IP specified")
            return False
    
    mac = device_config.get("broadlink", {}).get("mac")
    device_type = device_config.get("broadlink", {}).get("type")
    
    device = connect_to_device(device_ip, mac, device_type)
    if not device:
        return False
    
    # Execute all commands
    success_count = 0
    for command_name in command_names:
        command_data = device_config["commands"][command_name]
        
        print(f"📱 Sending command '{command_name}' to device '{device_name}'")
        
        if send_command(device, command_data):
            success_count += 1
            print(f"✅ Command '{command_name}' executed successfully")
            time.sleep(0.5)  # Small delay between commands
        else:
            print(f"❌ Command '{command_name}' failed")
    
    if success_count == len(command_names):
        print(f"✅ All {success_count} commands executed successfully")
        return True
    else:
        print(f"⚠️  {success_count} out of {len(command_names)} commands executed successfully")
        return False

def learn_command(device_name, command_name, command_type="ir", device_ip=None, frequency=433.92):
    """
    Learn a new command and save it to devices.json.
    
    Args:
        device_name: Name of the device to add command to
        command_name: Name for the new command
        command_type: Type of command ("ir" or "rf")
        device_ip: IP address of the Broadlink device
        frequency: RF frequency in MHz (for RF commands)
    
    Returns:
        bool: True if command learned and saved successfully
    """
    devices_config = load_devices()
    
    # Initialize device config if it doesn't exist
    if device_name not in devices_config:
        devices_config[device_name] = {
            "uuid": f"broadlink_{device_name}",
            "commands": {},
            "broadlink": {}
        }
    
    # Connect to Broadlink device
    if not device_ip:
        # Try to discover if no IP provided
        discovered = discover_broadlink_devices()
        if not discovered:
            print("❌ No Broadlink devices found and no IP provided")
            return False
        device_ip = discovered[0]['ip']
        print(f"ℹ️  Using discovered device at {device_ip}")
    
    device = connect_to_device(device_ip)
    if not device:
        return False
    
    # Update device config with Broadlink info
    devices_config[device_name]["broadlink"] = {
        "ip": device_ip,
        "mac": device.mac.hex(),
        "type": hex(device.devtype)
    }
    
    # Learn the command
    print(f"🎓 Learning {command_type.upper()} command '{command_name}' for device '{device_name}'")
    
    if command_type.lower() == "ir":
        command_data = learn_ir_command(device)
    elif command_type.lower() == "rf":
        command_data = learn_rf_command(device, frequency)
    else:
        print(f"❌ Invalid command type: {command_type}. Use 'ir' or 'rf'")
        return False
    
    if not command_data:
        print("❌ Failed to learn command")
        return False
    
    # Save the command
    devices_config[device_name]["commands"][command_name] = command_data
    
    if save_devices(devices_config):
        print(f"✅ Command '{command_name}' learned and saved successfully")
        print(f"📊 Command data: {command_data}")
        return True
    else:
        print("❌ Failed to save command to devices.json")
        return False

def send_raw(command_data, device_ip):
    """Send a raw command to a Broadlink device."""
    device = connect_to_device(device_ip)
    if not device:
        return False
    
    print(f"📡 Sending raw command to device at {device_ip}")
    print(f"📊 Data: {command_data}")
    
    return send_command(device, command_data)

def list_devices():
    """List all available devices and their commands."""
    devices_config = load_devices()
    
    if not devices_config:
        print("❌ No devices found in devices.json")
        return
    
    print("📱 Available devices:")
    print("=" * 50)
    
    for device_name, device_info in devices_config.items():
        print(f"\n🔹 {device_name}")
        print(f"   UUID: {device_info.get('uuid', 'Unknown')}")
        print(f"   Commands: {len(device_info.get('commands', {}))}")
        
        broadlink_info = device_info.get('broadlink', {})
        if broadlink_info:
            print(f"   Broadlink IP: {broadlink_info.get('ip', 'Unknown')}")
            print(f"   Broadlink MAC: {broadlink_info.get('mac', 'Unknown')}")
            print(f"   Broadlink Type: {broadlink_info.get('type', 'Unknown')}")
        
        if device_info.get('commands'):
            print("   Available commands:")
            for cmd_name in device_info['commands'].keys():
                print(f"     - {cmd_name}")

def list_broadlink_devices():
    """List all available Broadlink devices on the network."""
    devices = discover_broadlink_devices(timeout=10)
    
    print("🔷 Available Broadlink devices:")
    print("=" * 50)
    
    if not devices:
        print("❌ No Broadlink devices found on the network")
        return
    
    for i, device in enumerate(devices, 1):
        print(f"\n{i}. {device['model']} ({device['manufacturer']})")
        print(f"   IP: {device['ip']}:{device['port']}")
        print(f"   MAC: {device['mac']}")
        print(f"   Type: {device['type']}")

def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Whispeer Broadlink Command Emitter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send a known command
  python3 whispeer_broadlink.py emit_command tv_living_room power_on
  
  # Send multiple commands
  python3 whispeer_broadlink.py emit_command tv_living_room power_on volume_up volume_up
  
  # Learn a new IR command
  python3 whispeer_broadlink.py learn_command tv_living_room power_off ir --ip 192.168.1.10
  
  # Learn a new RF command
  python3 whispeer_broadlink.py learn_command garage_door open rf --ip 192.168.1.10 --frequency 433.92
  
  # Send a raw command
  python3 whispeer_broadlink.py send_raw "2600500000012693..." --ip 192.168.1.10
  
  # List available devices
  python3 whispeer_broadlink.py list_devices
  
  # Discover Broadlink devices
  python3 whispeer_broadlink.py list_broadlink_devices
        """
    )
    
    subparsers = parser.add_subparsers(dest='mode', help='Operation mode')
    
    # emit_command subcommand
    cmd_parser = subparsers.add_parser('emit_command', help='Emit a known command')
    cmd_parser.add_argument('device_name', help='Device name (from devices.json)')
    cmd_parser.add_argument('command_names', nargs='+', help='Command name(s)')
    cmd_parser.add_argument('--ip', help='Broadlink device IP address')
    
    # learn_command subcommand
    learn_parser = subparsers.add_parser('learn_command', help='Learn a new command')
    learn_parser.add_argument('device_name', help='Device name')
    learn_parser.add_argument('command_name', help='Command name')
    learn_parser.add_argument('command_type', choices=['ir', 'rf'], help='Command type (ir or rf)')
    learn_parser.add_argument('--ip', required=True, help='Broadlink device IP address')
    learn_parser.add_argument('--frequency', type=float, default=433.92, help='RF frequency in MHz (default: 433.92)')
    
    # send_raw subcommand
    raw_parser = subparsers.add_parser('send_raw', help='Send a raw command')
    raw_parser.add_argument('command_data', help='Hex command data')
    raw_parser.add_argument('--ip', required=True, help='Broadlink device IP address')
    
    # list_devices subcommand
    subparsers.add_parser('list_devices', help='List available devices')
    
    # list_broadlink_devices subcommand
    subparsers.add_parser('list_broadlink_devices', help='List available Broadlink devices')
    
    args = parser.parse_args()
    
    if not args.mode:
        parser.print_help()
        sys.exit(1)
    
    # Execute based on mode
    if args.mode == 'emit_command':
        success = emit_command(args.device_name, args.command_names, args.ip)
        sys.exit(0 if success else 1)
    
    elif args.mode == 'learn_command':
        success = learn_command(args.device_name, args.command_name, args.command_type, args.ip, args.frequency)
        sys.exit(0 if success else 1)
    
    elif args.mode == 'send_raw':
        success = send_raw(args.command_data, args.ip)
        sys.exit(0 if success else 1)
    
    elif args.mode == 'list_devices':
        list_devices()
    
    elif args.mode == 'list_broadlink_devices':
        list_broadlink_devices()
    
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
