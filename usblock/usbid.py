"""Cross-platform detection of a USB drive's unique hardware serial number.

The serial (a.k.a. "product code") is stable across reformats on most
devices because it is baked into the flash controller, unlike a volume
serial which changes when the drive is reformatted. We prefer the hardware
serial and only fall back to a volume identifier when it cannot be read.

Nothing here modifies the drive; every call is read-only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class DriveInfo:
    mountpoint: str          # e.g. "E:\\" or "/media/user/STICK"
    device: str              # e.g. "\\\\.\\PHYSICALDRIVE2" or "/dev/sdb1"
    serial: Optional[str]    # hardware serial if we could read it
    label: str = ""
    removable: Optional[bool] = None   # True = USB/removable, False = internal, None = unknown

    @property
    def kind(self) -> str:
        if self.removable is True:
            return "USB / removable"
        if self.removable is False:
            return "internal disk"
        return "unknown type"

    @property
    def key_id(self) -> str:
        """The stable string used as key material. Prefer hardware serial."""
        if self.serial:
            return self.serial.strip()
        # Fall back to the device path so something is always returned; the
        # caller is warned separately that this is weaker.
        return f"nodev:{self.device}"


def _run(cmd: list[str], timeout: int = 15) -> str:
    """Run a command read-only and return stdout, or '' on any failure."""
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


# --------------------------------------------------------------------------
# Linux
# --------------------------------------------------------------------------
def _linux_serial_for_device(device: str) -> Optional[str]:
    # lsblk resolves a partition (/dev/sdb1) to its parent disk's serial.
    out = _run(["lsblk", "-no", "SERIAL", device])
    for line in out.splitlines():
        line = line.strip()
        if line:
            return line
    # Fallback: udevadm.
    out = _run(["udevadm", "info", "--query=property", "--name", device])
    m = re.search(r"ID_SERIAL_SHORT=(.+)", out) or re.search(r"ID_SERIAL=(.+)", out)
    if m:
        return m.group(1).strip()
    return None


def _linux_is_removable(device: str) -> Optional[bool]:
    name = os.path.basename(os.path.realpath(device))
    sys_dir = os.path.join("/sys/class/block", name)
    if not os.path.exists(sys_dir):
        return None
    real = os.path.realpath(sys_dir)
    if os.path.exists(os.path.join(real, "partition")):
        real = os.path.dirname(real)  # partition -> its parent disk
    if "/usb" in real:
        return True
    try:
        with open(os.path.join(real, "removable"), encoding="ascii") as fh:
            return fh.read().strip() == "1"
    except OSError:
        return None


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
# MSFT_Disk BusType values that mean "plugged-in stick/card" (names and codes).
_WIN_REMOVABLE_BUSES = {"USB", "SD", "MMC", "7", "12", "13"}
_WIN_UNKNOWN_BUSES = {"", "UNKNOWN", "0"}


def _windows_disk_props(letter: str) -> tuple[Optional[str], Optional[str]]:
    """(serial, bus type) for a drive letter via the Storage cmdlets, in one call."""
    letter = letter.rstrip(":\\/")
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        f"$d=Get-Partition -DriveLetter {letter} | Get-Disk;"
        "if($d){ [string]$d.SerialNumber + '|' + [string]$d.BusType }"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps]).strip()
    line = out.splitlines()[0] if out else ""
    if "|" not in line:
        return None, None
    serial, bus = line.split("|", 1)
    return (serial.strip() or None), (bus.strip() or None)


def _windows_serial_wmi(letter: str) -> Optional[str]:
    """Older systems without the Storage cmdlets: WMI association chain."""
    letter = letter.rstrip(":\\/")
    ps2 = (
        f"$ErrorActionPreference='SilentlyContinue';"
        f"$d=Get-WmiObject Win32_DiskDrive;"
        f"foreach($x in $d){{"
        f" $parts=Get-WmiObject -Query \"ASSOCIATORS OF {{Win32_DiskDrive.DeviceID='$($x.DeviceID)'}} WHERE AssocClass=Win32_DiskDriveToDiskPartition\";"
        f" foreach($p in $parts){{"
        f"  $logs=Get-WmiObject -Query \"ASSOCIATORS OF {{Win32_DiskPartition.DeviceID='$($p.DeviceID)'}} WHERE AssocClass=Win32_LogicalDiskToPartition\";"
        f"  foreach($l in $logs){{ if($l.DeviceID -eq '{letter}:'){{ Write-Output $x.SerialNumber }} }}"
        f" }} }}"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps2]).strip()
    if out:
        return out.splitlines()[0].strip()
    return None


def _windows_volume_serial(letter: str) -> Optional[str]:
    letter = letter.rstrip(":\\/")
    out = _run(["cmd", "/c", "vol", f"{letter}:"])
    m = re.search(r"([0-9A-Fa-f]{4}-[0-9A-Fa-f]{4})", out)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# macOS
# --------------------------------------------------------------------------
def _macos_serial_for_mount(mountpoint: str) -> Optional[str]:
    out = _run(["diskutil", "info", mountpoint])
    # Try a few keys; hardware serial is best, UUID is the fallback.
    for key in ("Disk / Partition UUID", "Volume UUID"):
        m = re.search(rf"{re.escape(key)}:\s*(.+)", out)
        if m:
            uuid = m.group(1).strip()
            # Attempt to upgrade to a real USB serial via system_profiler.
            usb = _run(["system_profiler", "SPUSBDataType"])
            sm = re.search(r"Serial Number:\s*(.+)", usb)
            if sm:
                return sm.group(1).strip()
            return uuid
    return None


def _macos_is_removable(mountpoint: str) -> Optional[bool]:
    out = _run(["diskutil", "info", mountpoint])
    if not out:
        return None
    if (re.search(r"Protocol:\s*USB", out)
            or re.search(r"Removable Media:\s*Removable", out)
            or re.search(r"Device Location:\s*External", out)):
        return True
    if (re.search(r"Device Location:\s*Internal", out)
            or re.search(r"Removable Media:\s*Fixed", out)):
        return False
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def _mountpoint_of_path(path: str):
    """Return the psutil partition whose mountpoint contains `path`."""
    import psutil

    path = os.path.abspath(path)
    best = None
    best_len = -1
    for part in psutil.disk_partitions(all=False):
        mp = part.mountpoint
        try:
            common = os.path.commonpath([os.path.abspath(mp), path])
        except ValueError:
            continue
        if common == os.path.abspath(mp) and len(mp) > best_len:
            best, best_len = part, len(mp)
    return best


def get_drive_info(path: str) -> DriveInfo:
    """Return DriveInfo (including hardware serial) for the drive holding `path`.

    `path` may be the mount root or any file/dir inside the drive.
    """
    import psutil

    part = _mountpoint_of_path(path)
    if part is None:
        raise RuntimeError(f"Could not find a mounted drive for path: {path!r}")

    mp = part.mountpoint
    device = part.device
    serial: Optional[str] = None
    removable: Optional[bool] = None

    if sys.platform.startswith("win"):
        serial, bus = _windows_disk_props(mp)
        if not serial:
            serial = _windows_serial_wmi(mp)
        if not serial:
            serial = _windows_volume_serial(mp)
        # psutil reports the Windows drive type in opts ("fixed", "removable").
        opts = (part.opts or "").lower()
        bus_u = (bus or "").upper()
        if "removable" in opts or bus_u in _WIN_REMOVABLE_BUSES:
            removable = True
        elif bus_u not in _WIN_UNKNOWN_BUSES or "fixed" in opts:
            removable = False
    elif sys.platform == "darwin":
        serial = _macos_serial_for_mount(mp)
        removable = _macos_is_removable(mp)
    else:  # linux and friends
        serial = _linux_serial_for_device(device)
        removable = _linux_is_removable(device)

    return DriveInfo(
        mountpoint=mp,
        device=device,
        serial=serial,
        label=os.path.basename(mp.rstrip("/\\")) or mp,
        removable=removable,
    )


def list_drives() -> list[DriveInfo]:
    """Enumerate mounted drives with their serials and USB/internal type."""
    import psutil

    infos: list[DriveInfo] = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        mp = part.mountpoint
        if mp in seen:
            continue
        seen.add(mp)
        try:
            infos.append(get_drive_info(mp))
        except RuntimeError:
            continue
    return infos


if __name__ == "__main__":
    print("Mounted drives and their hardware serials:\n")
    for d in list_drives():
        tag = d.serial or "(serial unavailable — will use device path, weaker)"
        print(f"  {d.mountpoint:<28} {d.kind:<16} device={d.device:<20} serial={tag}")
    print("\nUse the serial above as the key when protecting content.")
