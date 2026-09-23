#!/usr/bin/env bash
# usblock launcher for macOS / Linux.
#   ./usblock.sh                 open content in the terminal
#   ./usblock.sh list            show drives + serials
#   ./usblock.sh protect ...     encrypt files onto a drive
#
# On first run it sets up a private Python environment automatically, so you
# never have to touch pip or python yourself. Re-runs are instant.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$DIR"

PYBIN="${PYTHON:-}"
if [ -z "$PYBIN" ]; then
    if command -v python3 >/dev/null 2>&1; then PYBIN=python3
    elif command -v python  >/dev/null 2>&1; then PYBIN=python
    else
        echo "Python 3 is required but was not found on PATH." >&2
        exit 1
    fi
fi

VENV="$DIR/.venv"
VENV_PY="$VENV/bin/python"

need_setup=0
if [ -x "$VENV_PY" ]; then
    # venv exists; make sure the core deps import.
    "$VENV_PY" -c "import cryptography, psutil" >/dev/null 2>&1 || need_setup=1
else
    need_setup=1
fi

if [ "$need_setup" -eq 1 ]; then
    echo "First-time setup: creating a private environment (one-off)…"
    if "$PYBIN" -m venv "$VENV" 2>/dev/null; then
        "$VENV_PY" -m pip install --quiet --upgrade pip || true
        "$VENV_PY" -m pip install --quiet -r "$DIR/requirements.txt"
        RUN_PY="$VENV_PY"
    else
        echo "Could not create a venv (read-only drive?). Trying system Python…" >&2
        RUN_PY="$PYBIN"
    fi
else
    RUN_PY="$VENV_PY"
fi

exec "$RUN_PY" "$DIR/usblock_cli.py" "$@"
