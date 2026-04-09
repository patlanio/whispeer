"""BLE advertisement emitter using hcitool.

Provides adapter discovery (via ``hciconfig``) and raw BLE advertisement
emission (via ``hcitool``).  Both tools must be present on the system for
BLE support to be available.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Pre-check tool availability once at import time.
_HCITOOL = shutil.which("hcitool")
_HCICONFIG = shutil.which("hciconfig")
CAN_EMIT = _HCITOOL is not None and _HCICONFIG is not None


def get_ble_adapters() -> list[dict[str, Any]]:
    """Return local BLE adapters parsed from ``hciconfig``.

    Returns an empty list when ``hcitool`` or ``hciconfig`` are absent
    (BLE is blocked entirely).
    """
    if not CAN_EMIT:
        _LOGGER.warning(
            "hcitool/hciconfig not found — BLE support disabled"
        )
        return []

    try:
        result = subprocess.run(
            [_HCICONFIG],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        _LOGGER.error("Failed to run hciconfig: %s", exc)
        return []

    adapters: list[dict[str, Any]] = []
    # hciconfig output: blocks separated by blank lines.
    # First line:  "hci0:   Type: Primary  Bus: USB"
    # Second line: "        BD Address: AA:BB:CC:DD:EE:FF  ACL MTU: ..."
    # Third+ lines: flags like "UP RUNNING" or "DOWN"
    current_name = ""
    current_mac = ""
    current_status = "DOWN"

    for line in result.stdout.splitlines():
        m_header = re.match(r"^(hci\d+):", line)
        if m_header:
            # Flush previous adapter.
            if current_name:
                adapters.append({
                    "hci_name": current_name,
                    "mac": current_mac,
                    "status": current_status,
                    "can_emit": True,
                })
            current_name = m_header.group(1)
            current_mac = ""
            current_status = "DOWN"
            if "UP RUNNING" in line:
                current_status = "UP"
            elif "DOWN" in line:
                current_status = "DOWN"
            continue

        if current_name:
            m_mac = re.search(
                r"BD Address:\s*([0-9A-Fa-f:]{17})", line
            )
            if m_mac:
                current_mac = m_mac.group(1).upper()
            if "UP RUNNING" in line:
                current_status = "UP"

    # Flush last adapter.
    if current_name:
        adapters.append({
            "hci_name": current_name,
            "mac": current_mac,
            "status": current_status,
            "can_emit": True,
        })

    return adapters


def _hex_str_to_bytes(hexstr: str) -> list[str]:
    """Convert a flat hex string to a list of uppercase two-char hex bytes."""
    hexstr = hexstr.replace(" ", "").replace(":", "")
    return [hexstr[i : i + 2].upper() for i in range(0, len(hexstr), 2)]


def _int_to_le16(value: int) -> list[str]:
    """Return a 16-bit integer as two little-endian hex bytes."""
    return [f"{value & 0xFF:02X}", f"{(value >> 8) & 0xFF:02X}"]


def build_adv_payload_manufacturer(
    mfr_id: int, data_hex: str
) -> list[str]:
    """Build an HCI LE advertising payload with AD type 0xFF (manufacturer)."""
    data_bytes = _hex_str_to_bytes(data_hex)
    # AD structure: length, type=0xFF, mfr_id (2 LE), data
    ad_content = ["FF"] + _int_to_le16(mfr_id) + data_bytes
    ad_len = f"{len(ad_content):02X}"
    return [ad_len] + ad_content


def build_adv_payload_service_16(
    uuid16: int, data_hex: str
) -> list[str]:
    """Build an HCI LE advertising payload with AD type 0x16 (service data)."""
    data_bytes = _hex_str_to_bytes(data_hex)
    ad_content = ["16"] + _int_to_le16(uuid16) + data_bytes
    ad_len = f"{len(ad_content):02X}"
    return [ad_len] + ad_content


def _build_hci_payload(ad_type: str, field_id, data_hex: str) -> list[str]:
    """Build full HCI LE Set Advertising Data payload bytes.

    Wraps the AD structure with mandatory Flags (02 01 06) and a leading
    total-length byte.
    """
    flags = ["02", "01", "06"]

    if ad_type == "manufacturer":
        ad_struct = build_adv_payload_manufacturer(int(field_id), data_hex)
    elif ad_type == "service":
        ad_struct = build_adv_payload_service_16(int(field_id, 16) if isinstance(field_id, str) else int(field_id), data_hex)
    else:
        raise ValueError(f"Unknown ad_type: {ad_type}")

    body = flags + ad_struct
    length_byte = f"{len(body):02X}"
    return [length_byte] + body


def _run_hcitool(adapter: str, *ogf_ocf_args: str) -> None:
    """Run a single ``hcitool -i <adapter> cmd`` invocation."""
    cmd = [_HCITOOL, "-i", adapter, "cmd"] + list(ogf_ocf_args)
    _LOGGER.debug("hcitool cmd: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, timeout=5)


def emit_ble(
    adapter: str,
    ad_type: str,
    field_id: int | str,
    data_hex: str,
) -> bool:
    """Emit a BLE advertisement on *adapter* using ``hcitool``.

    Returns ``True`` on success, ``False`` on failure.
    """
    if not CAN_EMIT:
        _LOGGER.error("hcitool not available — cannot emit BLE")
        return False

    try:
        payload = _build_hci_payload(ad_type, field_id, data_hex)
    except Exception as exc:
        _LOGGER.error("Failed to build BLE payload: %s", exc)
        return False

    _LOGGER.info(
        "Emitting BLE on %s: ad_type=%s field_id=%s len=%d",
        adapter, ad_type, field_id, len(payload),
    )

    try:
        # Disable advertising
        _run_hcitool(adapter, "0x08", "0x000A", "00")
        # Set advertising data
        _run_hcitool(adapter, "0x08", "0x0008", *payload)
        # Enable advertising
        _run_hcitool(adapter, "0x08", "0x000A", "01")
        _LOGGER.info("BLE advertisement emitted successfully on %s", adapter)
        return True
    except subprocess.CalledProcessError as exc:
        _LOGGER.error("hcitool command failed: %s", exc)
        return False
    except Exception as exc:
        _LOGGER.error("BLE emit error: %s", exc)
        return False
