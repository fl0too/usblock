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
    removable: bool = True

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


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def _windows_serial_for_drive_letter(letter: str) -> Optional[str]:
    letter = letter.rstrip(":\\/")
    # Preferred: modern Storage cmdlets join drive letter -> disk -> serial.
    ps = (
        f"$ErrorActionPreference='SilentlyContinue';"
        f"(Get-Partition -DriveLetter {letter} | Get-Disk)."
        f"SerialNumber"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps]).strip()
    if out:
        return out
    # Older systems: WMI association chain.
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
    removable = "removable" in (part.opts or "") or True  # best-effort
    serial: Optional[str] = None

    if sys.platform.startswith("win"):
        letter = mp
        serial = _windows_serial_for_drive_letter(letter)
        if not serial:
            serial = _windows_volume_serial(letter)
    elif sys.platform == "darwin":
        serial = _macos_serial_for_mount(mp)
    else:  # linux and friends
        serial = _linux_serial_for_device(device)

    return DriveInfo(
        mountpoint=mp,
        device=device,
        serial=serial,
        label=os.path.basename(mp.rstrip("/\\")) or mp,
        removable=bool(removable),
    )


def list_removable_drives() -> list[DriveInfo]:
    """Enumerate mounted drives with their serials (for the --list command)."""
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
    for d in list_removable_drives():
        tag = d.serial or "(serial unavailable — will use device path, weaker)"
        print(f"  {d.mountpoint:<28} device={d.device:<20} serial={tag}")
    print("\nUse the serial above as the key when protecting content.")
