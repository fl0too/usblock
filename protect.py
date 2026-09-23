#!/usr/bin/env python3
"""Launcher for the usblock packaging tool (see usblock/protect.py).

Examples:
    python protect.py --list
    python protect.py --drive E:\\ --passphrase secret --add a.pdf b.mp4
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from usblock.protect import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
