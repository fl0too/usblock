#!/usr/bin/env python3
"""Unified command dispatcher used by the usblock.sh / usblock.bat launchers.

    usblock view            open the content in the terminal  (default)
    usblock gui             open the graphical viewer
    usblock list            list drives and their serials
    usblock protect ...     encrypt files onto a drive (see: usblock protect -h)
    usblock test            run the self-test

You normally invoke this through ./usblock.sh or usblock.bat, not directly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

USAGE = __doc__


def main(argv: list[str]) -> int:
    args = list(argv)
    # Bare invocation, or a leading option, means "view in terminal".
    if not args or args[0].startswith("-"):
        from usblock.viewer import main as vmain
        return vmain(["--terminal"] + args)

    cmd, rest = args[0].lower(), args[1:]

    if cmd in ("view", "open", "terminal"):
        from usblock.viewer import main as vmain
        return vmain(["--terminal"] + rest)
    if cmd == "gui":
        from usblock.viewer import main as vmain
        return vmain(["--gui"] + rest)
    if cmd == "list":
        from usblock.protect import main as pmain
        return pmain(["--list"])
    if cmd in ("protect", "lock", "add"):
        from usblock.protect import main as pmain
        return pmain(rest)
    if cmd == "test":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.call([sys.executable, os.path.join(here, "tests", "test_roundtrip.py")])
    if cmd in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    print(f"Unknown command: {cmd}\n", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
