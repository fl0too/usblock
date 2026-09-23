#!/usr/bin/env python3
"""Launcher for the usblock secure viewer.

Put this file (or the built executable) on the USB stick next to the
`protected/` folder. Double-click it, or run:  python run_viewer.py
"""
import os
import sys

# Allow running straight from the USB even if the package isn't installed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from usblock.viewer import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
