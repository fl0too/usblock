"""Packaging tool: encrypt PDFs/videos and bind them to a USB drive.

Usage examples
--------------
List drives and their serials (so you know what you're binding to):

    python -m usblock.protect --list

Protect files onto a USB mounted at E:\\ (Windows) or /media/you/STICK:

    python -m usblock.protect --drive E:\\ --passphrase "optional secret" \\
        --add lesson1.pdf intro.mp4 handbook.pdf

This writes:
    <drive>/protected/manifest.json   (salt, verify token, file list)
    <drive>/protected/<name>.enc      (one AES-256-GCM blob per file)

The original files are left untouched. Copy run_viewer.py (or the built
executable) onto the drive so recipients can open the content.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone

from base64 import b64encode

from . import MANIFEST_NAME, PROTECTED_DIRNAME, __version__
from . import crypto
from .usbid import get_drive_info, list_drives


def _classify(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime:
        if mime == "application/pdf":
            return "pdf"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("image/"):
            return "image"
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}:
        return "video"
    return "other"


def cmd_list() -> int:
    drives = list_drives()
    if not drives:
        print("No mounted drives found.")
        return 1
    print("Mounted drives (lock your content to the one marked USB / removable):\n")
    for d in drives:
        tag = d.serial or "(no hardware serial — device path will be used, weaker)"
        print(f"  {d.mountpoint:<24} {d.kind:<16} serial = {tag}")
    return 0


def cmd_protect(drive_path: str, passphrase: str, files: list[str]) -> int:
    info = get_drive_info(drive_path)
    if info.removable is False:
        print(
            f"WARNING: {info.mountpoint} looks like an internal disk, not a USB "
            "stick. The protected files will be written there and bound to it.\n",
            file=sys.stderr,
        )
    if not info.serial:
        print(
            "WARNING: could not read a hardware serial for this drive. Falling "
            "back to the device path, which is less stable and less unique.\n"
            f"         key id = {info.key_id}\n",
            file=sys.stderr,
        )
    print(f"Binding to drive {info.mountpoint}  (key id: {info.key_id})")

    salt = crypto.new_salt()
    key = crypto.derive_key(info.key_id, passphrase, salt)

    out_dir = os.path.join(info.mountpoint, PROTECTED_DIRNAME)
    os.makedirs(out_dir, exist_ok=True)

    entries = []
    for src in files:
        if not os.path.isfile(src):
            print(f"  skip (not a file): {src}", file=sys.stderr)
            continue
        with open(src, "rb") as fh:
            plaintext = fh.read()
        base = os.path.basename(src)
        # Authenticate the filename+type so it can't be swapped.
        associated = base.encode("utf-8")
        blob = crypto.encrypt(key, plaintext, associated=associated)
        enc_name = base + ".enc"
        with open(os.path.join(out_dir, enc_name), "wb") as fh:
            fh.write(blob)
        entries.append(
            {
                "name": base,
                "enc": enc_name,
                "type": _classify(src),
                "size": len(plaintext),
            }
        )
        print(f"  encrypted {base}  ({len(plaintext):,} bytes) -> {enc_name}")

    if not entries:
        print("Nothing was encrypted.", file=sys.stderr)
        return 1

    manifest = {
        "usblock_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(),
        "kdf": {
            "algo": "PBKDF2-HMAC-SHA256",
            "iterations": crypto.KDF_ITERATIONS,
            "salt_b64": b64encode(salt).decode("ascii"),
        },
        "cipher": "AES-256-GCM",
        "verify_token": crypto.make_verify_token(key),
        # Store only a short fingerprint of the key id, never the id itself,
        # so the manifest doesn't leak which serial unlocks it.
        "key_hint": info.key_id[:2] + "…" if info.key_id else "",
        "requires_passphrase": bool(passphrase),
        "files": entries,
    }
    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\nDone. Wrote {len(entries)} file(s) + manifest to {out_dir}")
    print("Copy run_viewer.py (or the built executable) onto the drive so the")
    print("recipient can open the content on this same USB stick.")
    if not passphrase:
        print(
            "\nNote: no passphrase was set, so anyone holding THIS physical "
            "USB can open the files. Add --passphrase for real confidentiality."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m usblock.protect",
        description="Encrypt PDFs/videos and bind them to a specific USB drive.",
    )
    p.add_argument("--list", action="store_true", help="list drives + serials and exit")
    p.add_argument("--drive", help="mount point / drive root of the target USB")
    p.add_argument("--passphrase", default="", help="optional extra secret (recommended)")
    p.add_argument("--add", nargs="+", default=[], help="files to protect")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        return cmd_list()
    if not args.drive or not args.add:
        print("error: --drive and --add are required (or use --list)", file=sys.stderr)
        return 2
    return cmd_protect(args.drive, args.passphrase, args.add)


if __name__ == "__main__":
    raise SystemExit(main())
