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


def _guided_protect() -> None:
    """Interactive 'protect files onto a USB' flow for double-click users."""
    import getpass
    import shlex

    from usblock.protect import cmd_list, cmd_protect

    print("\nDetected drives (use one of these as the target):\n")
    cmd_list()
    drive = input(
        "\nWhich drive should the content be locked to?\n"
        "  (e.g. E:\\ on Windows, or /media/you/STICK): "
    ).strip().strip('"').strip("'")
    if not drive:
        print("  Cancelled — no drive entered.")
        return

    pw = getpass.getpass(
        "Passphrase (leave blank for none — but a passphrase is recommended): "
    )
    raw = input(
        "Files to protect — drag them into this window, or type paths\n"
        "  separated by spaces: "
    ).strip()
    # posix=False keeps Windows backslash paths intact and respects quotes.
    try:
        files = shlex.split(raw, posix=(os.name != "nt"))
    except ValueError:
        files = raw.split()
    files = [f.strip().strip('"').strip("'") for f in files if f.strip()]
    if not files:
        print("  Cancelled — no files given.")
        return
    cmd_protect(drive, pw, files)
    input("\nDone. Press Enter to return to the menu… ")


def interactive_menu() -> int:
    """Shown when the launcher is double-clicked with no command."""
    while True:
        print()
        print("=========== usblock ===========")
        print("  1) Open protected content on this USB")
        print("  2) Protect files onto a USB (encrypt + lock to that stick)")
        print("  3) List drives and their serials")
        print("  4) Help")
        print("  q) Quit")
        try:
            choice = input("Choose 1-4 or q: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("q", "quit", "exit"):
            return 0
        if choice == "1":
            from usblock.viewer import main as vmain
            vmain(["--terminal"])
        elif choice == "2":
            _guided_protect()
        elif choice == "3":
            from usblock.protect import main as pmain
            pmain(["--list"])
            input("\nPress Enter to return to the menu… ")
        elif choice in ("4", "h", "help"):
            print(USAGE)
        else:
            print("  ? Not a valid choice.")


def main(argv: list[str]) -> int:
    args = list(argv)
    # Bare invocation (e.g. a double-click) -> friendly menu.
    if not args:
        return interactive_menu()
    # A leading option means "view in terminal" with those options.
    if args[0].startswith("-"):
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
