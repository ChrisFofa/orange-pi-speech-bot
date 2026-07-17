"""
device_utils.py

Reusable device identification helpers for Big Bang special event packages.

Purpose
-------
The Orange Pi needs a stable device identifier so Supabase can decide:

- whether this device is registered,
- whether this device can unlock a special event,
- whether this device is allowed to receive AI credentials.

The preferred identifier is a real network MAC address.

This module tries:
    1. Linux network interfaces in /sys/class/net
    2. Python uuid.getnode()
    3. A generated fallback machine identifier

Future developers should usually copy this file unchanged.
"""

from __future__ import annotations

import hashlib
import os
import socket
import uuid
from pathlib import Path
from typing import Optional


def _is_valid_mac(mac: str) -> bool:
    """
    Return True if a string looks like a usable MAC address.
    """
    if not mac:
        return False

    mac = mac.strip().lower()

    if mac in {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}:
        return False

    parts = mac.split(":")

    if len(parts) != 6:
        return False

    for part in parts:
        if len(part) != 2:
            return False

        try:
            int(part, 16)
        except ValueError:
            return False

    return True


def _read_mac_from_linux_sysfs() -> Optional[str]:
    """
    Try to read MAC addresses from Linux network interfaces.

    On Orange Pi / Debian / Ubuntu, network devices usually appear here:

        /sys/class/net/<interface>/address

    We skip loopback and prefer common wired/wireless interfaces.
    """
    net_dir = Path("/sys/class/net")

    if not net_dir.exists():
        return None

    preferred_prefixes = ("wlan", "wl", "eth", "en")

    interfaces = []
    for item in net_dir.iterdir():
        if not item.is_dir() and not item.is_symlink():
            continue

        name = item.name

        if name == "lo":
            continue

        interfaces.append(name)

    # Sort preferred interfaces first.
    # Sort: wlan first, then others alphabetically
    def _iface_sort_key(name):
        if name.startswith(('wlan', 'wl')):
            return (0, name)
        return (1, name)
    interfaces.sort(key=_iface_sort_key)

    for interface_name in interfaces:
        address_file = net_dir / interface_name / "address"

        try:
            mac = address_file.read_text(encoding="utf-8").strip().lower()
        except Exception:
            continue

        if _is_valid_mac(mac):
            return mac

    return None


def _read_mac_from_uuid_getnode() -> Optional[str]:
    """
    Try to get a MAC address using Python's uuid.getnode().

    Note:
        uuid.getnode() may return a random multicast address on some systems
        if it cannot find a hardware MAC. We still use it as a fallback.
    """
    try:
        node = uuid.getnode()
    except Exception:
        return None

    mac = ":".join(f"{(node >> shift) & 0xff:02x}" for shift in range(40, -1, -8))

    if _is_valid_mac(mac):
        return mac

    return None


def get_device_mac() -> str:
    """
    Return the best available MAC address.

    This is the main function other files should use.
    """
    mac = _read_mac_from_linux_sysfs()

    if mac:
        return mac

    mac = _read_mac_from_uuid_getnode()

    if mac:
        return mac

    # Last resort: generate a stable-ish fallback from hostname and home path.
    # This should not normally happen on an Orange Pi.
    fallback_source = f"{socket.gethostname()}::{Path.home()}::{os.name}"
    digest = hashlib.sha256(fallback_source.encode("utf-8")).hexdigest()

    return "fallback-" + digest[:16]


def get_device_label() -> str:
    """
    Return a human-friendly label useful for logs or Supabase calls.
    """
    hostname = socket.gethostname() or "unknown-host"
    mac = get_device_mac()

    return f"{hostname}-{mac}"