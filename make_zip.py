#!/usr/bin/env python3
"""Bundle everything a user needs into usblock_dist.zip.

The zip contains the source, launchers, requirements, and docs -- the whole
kit to drop onto a USB stick (or to install and run from). It deliberately
excludes the venv, caches, and any already-encrypted content.
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "usblock_dist.zip")

INCLUDE_FILES = [
    "run_viewer.py",
    "protect.py",
    "build_exe.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
]
INCLUDE_DIRS = ["usblock", "tests"]
SKIP = {"__pycache__"}


def main() -> int:
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in INCLUDE_FILES:
            p = os.path.join(ROOT, f)
            if os.path.exists(p):
                z.write(p, arcname=os.path.join("usblock", f))
        for d in INCLUDE_DIRS:
            base = os.path.join(ROOT, d)
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [x for x in dirnames if x not in SKIP]
                for fn in filenames:
                    if fn.endswith(".pyc"):
                        continue
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, ROOT)
                    z.write(full, arcname=os.path.join("usblock", rel))
    size = os.path.getsize(OUT)
    print(f"Wrote {OUT} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
