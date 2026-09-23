"""Terminal (text-menu) viewer -- no GUI window required.

Runs entirely in the terminal: unlock the vault, list the protected items,
pick one by number to open it. While a known screen-recording process is
running, the file menu is replaced by a full-screen warning ("turn off the
screen" for the app in a terminal context) and opening is refused until the
recorder is closed.

Opening a file decrypts it to a locked-down temporary file, hands it to the
system's default application, and deletes it as soon as you're done. This
temp file is the weak spot -- see README's threat model.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from . import crypto, detect_recording


# --------------------------------------------------------------------------
# small terminal helpers
# --------------------------------------------------------------------------
def _enable_ansi() -> bool:
    """Return True if ANSI escapes will render. On Windows, try to turn on the
    console's virtual-terminal processing so escapes aren't printed literally."""
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            return bool(
                kernel32.SetConsoleMode(
                    handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
            )
        except Exception:  # noqa: BLE001
            return False
    return True


_ANSI = _enable_ansi()


def _clear() -> None:
    if _ANSI:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    else:
        os.system("cls" if os.name == "nt" else "clear")


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _ANSI else s


def _red(s: str) -> str:
    return f"\033[1;31m{s}\033[0m" if _ANSI else s


def _open_with_default_app(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def _secure_delete(path: str) -> None:
    try:
        if os.path.exists(path):
            with open(path, "r+b", buffering=0) as fh:
                length = os.fstat(fh.fileno()).st_size
                fh.seek(0)
                fh.write(os.urandom(min(length, 1 << 20)))
                fh.flush()
                os.fsync(fh.fileno())
            os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# the recording "lock screen"
# --------------------------------------------------------------------------
def _recording_gate() -> bool:
    """If a recorder is running, show the warning and wait. Return True if we
    blocked (so the caller should re-render), False if all clear."""
    hits = detect_recording.scan(strict=True)
    if not hits:
        return False
    while hits:
        _clear()
        who = ", ".join(sorted({h.name for h in hits}))
        print(_red("  ############################################"))
        print(_red("  #        SCREEN RECORDING DETECTED         #"))
        print(_red("  ############################################"))
        print()
        print("  Protected content is hidden while a recorder runs.")
        print(f"  Detected: {who}")
        print()
        print("  Close the recording software to continue. (Ctrl+C to quit.)")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            raise
        hits = detect_recording.scan(strict=True)
    return True


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------
def run_terminal(vault) -> int:
    """vault is an unlocked usblock.viewer.Vault."""
    from .viewer import Vault  # noqa: F401  (type hint / clarity only)

    while True:
        # If a recorder appears, the menu vanishes behind the warning.
        if _recording_gate():
            continue

        _clear()
        print(_bold("=== usblock secure viewer (terminal) ==="))
        print(f"Drive : {vault.info.mountpoint}")
        print(f"Serial: {vault.info.serial or '(none; device path)'}")
        print(f"Status: {_bold('UNLOCKED')}   ({len(vault.files)} item(s))")
        print()
        for i, e in enumerate(vault.files, 1):
            size = e.get("size", 0)
            print(f"  {i:>2}. [{e['type']:>5}] {e['name']}  ({size:,} bytes)")
        print()
        print("  Enter a number to open, r to refresh, q to quit.")

        try:
            choice = input("usblock> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("q", "quit", "exit"):
            return 0
        if choice in ("", "r", "refresh"):
            continue
        if not choice.isdigit() or not (1 <= int(choice) <= len(vault.files)):
            print("  ? Not a valid selection.")
            time.sleep(1)
            continue

        entry = vault.files[int(choice) - 1]

        # Re-check right before revealing anything.
        if detect_recording.is_recording(strict=True):
            print(_red("  Refusing to open: a screen recorder is running."))
            time.sleep(1.5)
            continue

        try:
            data = vault.decrypt_file(entry)
        except crypto.WrongKeyError as exc:
            print(_red(f"  Cannot open: {exc}"))
            time.sleep(2)
            continue

        _open_file_in_terminal_session(entry, data)

    # unreachable


def _open_file_in_terminal_session(entry: dict, data: bytes) -> None:
    import tempfile

    suffix = os.path.splitext(entry["name"])[1] or ""
    fd, path = tempfile.mkstemp(prefix="usblock_", suffix=suffix)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    print(f"\n  Opening “{entry['name']}” in your default application…")
    print("  (Decrypted to a temporary file only while you view it.)")
    try:
        _open_with_default_app(path)
    except Exception as exc:  # noqa: BLE001
        print(_red(f"  Could not launch a viewer: {exc}"))
    finally:
        try:
            input("\n  Press Enter when you're done to securely delete the temp copy… ")
        except (EOFError, KeyboardInterrupt):
            print()
        _secure_delete(path)
