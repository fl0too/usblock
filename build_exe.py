#!/usr/bin/env python3
"""Build a standalone executable of the viewer with PyInstaller.

Run this on the OS you want the .exe/.app/binary for -- PyInstaller does not
cross-compile. On Windows you get SecureViewer.exe; on macOS a binary; on
Linux an ELF binary. Copy the result onto the USB next to the protected/
folder.

    pip install pyinstaller PyMuPDF
    python build_exe.py

Output lands in ./dist/.
"""
import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "SecureViewer",
        "--noconsole",              # no console window on Windows/macOS
        # PyMuPDF + tkinter are picked up automatically; add hidden imports
        # here if a plugin is missed on your platform.
        "run_viewer.py",
    ]
    print("Running:", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print("PyInstaller not found. Install it: pip install pyinstaller")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
