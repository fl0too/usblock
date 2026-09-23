"""usblock secure viewer -- the application recipients run.

Responsibilities
  1. Find the manifest on the USB it is launched from (or --drive / auto).
  2. Read the drive's hardware serial, derive the key (+ passphrase if set),
     and verify it. Wrong USB or wrong passphrase => refuse to open anything.
  3. Show the protected PDFs and videos.
       * PDFs are rendered page-by-page in memory (PyMuPDF). No plaintext PDF
         is ever written to disk.
       * Videos are decrypted to a locked-down temp file only while playing,
         then deleted. (This is the weak spot; see README.)
  4. While a known screen-recording process is running, cover the app with an
     opaque warning overlay and hide the content -- i.e. "turn off the screen"
     for this application only. It never touches other apps or the OS.

Run:  python run_viewer.py            (auto-detect the USB it sits on)
      python run_viewer.py --drive E:\\
      python run_viewer.py --headless  (no GUI; list + integrity check only)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from base64 import b64decode

from . import MANIFEST_NAME, PROTECTED_DIRNAME
from . import crypto, detect_recording
from .usbid import get_drive_info


# --------------------------------------------------------------------------
# Manifest / key handling (GUI-independent so it can be unit-tested headless)
# --------------------------------------------------------------------------
class Vault:
    def __init__(self, drive_path: str, passphrase: str = ""):
        self.info = get_drive_info(drive_path)
        self.protected_dir = os.path.join(self.info.mountpoint, PROTECTED_DIRNAME)
        manifest_path = os.path.join(self.protected_dir, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(
                f"No protected content found on {self.info.mountpoint} "
                f"(missing {PROTECTED_DIRNAME}/{MANIFEST_NAME})."
            )
        with open(manifest_path, "r", encoding="utf-8") as fh:
            self.manifest = json.load(fh)

        salt = b64decode(self.manifest["kdf"]["salt_b64"])
        self.key = crypto.derive_key(self.info.key_id, passphrase, salt)
        self.unlocked = crypto.check_verify_token(self.key, self.manifest["verify_token"])

    @property
    def requires_passphrase(self) -> bool:
        return bool(self.manifest.get("requires_passphrase"))

    @property
    def files(self) -> list[dict]:
        return self.manifest.get("files", [])

    def decrypt_file(self, entry: dict) -> bytes:
        if not self.unlocked:
            raise crypto.WrongKeyError("vault is locked")
        with open(os.path.join(self.protected_dir, entry["enc"]), "rb") as fh:
            blob = fh.read()
        return crypto.decrypt(self.key, blob, associated=entry["name"].encode("utf-8"))


def _auto_drive() -> str:
    """Guess the drive we are running from: the mount root of this file."""
    here = os.path.abspath(sys.argv[0] if sys.argv and sys.argv[0] else __file__)
    return here


# --------------------------------------------------------------------------
# Headless mode (no display) -- integrity check + listing
# --------------------------------------------------------------------------
def run_headless(vault: Vault) -> int:
    print(f"Drive:  {vault.info.mountpoint}")
    print(f"Serial: {vault.info.serial or '(none; using device path)'}")
    print(f"Unlocked: {vault.unlocked}")
    if not vault.unlocked:
        print("This USB (or passphrase) does not match. Content stays locked.")
        return 3
    print("\nProtected files:")
    for e in vault.files:
        try:
            data = vault.decrypt_file(e)
            ok = f"OK ({len(data):,} bytes)"
        except crypto.WrongKeyError as exc:
            ok = f"FAILED: {exc}"
        print(f"  [{e['type']:>5}] {e['name']:<40} {ok}")
    return 0


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
def run_gui(drive_path: str, passphrase_arg: str) -> int:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, simpledialog

    root = tk.Tk()
    root.title("usblock secure viewer")
    root.geometry("900x640")

    # --- build / unlock the vault, prompting for a passphrase if needed ----
    def build_vault(pw: str) -> Vault | None:
        try:
            v = Vault(drive_path, pw)
        except FileNotFoundError as exc:
            messagebox.showerror("No content", str(exc))
            root.destroy()
            return None
        return v

    vault = build_vault(passphrase_arg)
    if vault is None:
        return 1
    if not vault.unlocked and vault.requires_passphrase:
        for _ in range(3):
            pw = simpledialog.askstring(
                "Passphrase", "Enter the passphrase for this content:", show="*"
            )
            if pw is None:
                root.destroy()
                return 1
            vault = build_vault(pw)
            if vault and vault.unlocked:
                break
    if not vault.unlocked:
        messagebox.showerror(
            "Locked",
            "This content is bound to a different USB drive, or the passphrase "
            "is wrong.\n\nPlug in the correct USB stick and try again.",
        )
        root.destroy()
        return 3

    # --- anti-recording overlay -------------------------------------------
    overlay = {"win": None}

    def show_overlay(reason: str):
        if overlay["win"] is not None:
            return
        ov = tk.Toplevel(root)
        ov.attributes("-topmost", True)
        try:
            ov.attributes("-fullscreen", True)
        except tk.TclError:
            ov.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
        ov.configure(bg="#111111")
        ov.protocol("WM_DELETE_WINDOW", lambda: None)  # can't close it away
        msg = tk.Label(
            ov,
            text="⛔  Screen recording detected\n\n"
                 "Protected content is hidden while a recorder is running.\n"
                 f"({reason})\n\n"
                 "Close the recording software to continue viewing.",
            fg="#ff5555",
            bg="#111111",
            font=("Helvetica", 20, "bold"),
            justify="center",
        )
        msg.pack(expand=True)
        root.withdraw()  # hide the real content window behind the overlay
        overlay["win"] = ov

    def hide_overlay():
        if overlay["win"] is not None:
            overlay["win"].destroy()
            overlay["win"] = None
            root.deiconify()

    def watchdog():
        hits = detect_recording.scan(strict=True)
        if hits:
            reason = ", ".join(sorted({h.name for h in hits}))
            show_overlay(reason)
        else:
            hide_overlay()
        root.after(1500, watchdog)  # poll on the main (GUI) thread -- thread-safe

    # --- content pane ------------------------------------------------------
    top = tk.Frame(root)
    top.pack(fill="x", padx=8, pady=6)
    tk.Label(
        top,
        text=f"Unlocked from {vault.info.mountpoint}  •  "
             f"{len(vault.files)} protected item(s)",
        font=("Helvetica", 11, "bold"),
    ).pack(side="left")

    body = tk.Frame(root)
    body.pack(fill="both", expand=True, padx=8, pady=6)

    listbox = tk.Listbox(body, width=40)
    listbox.pack(side="left", fill="y")
    for e in vault.files:
        listbox.insert("end", f"[{e['type']}] {e['name']}")

    viewer_area = tk.Frame(body, bg="#222")
    viewer_area.pack(side="left", fill="both", expand=True, padx=(8, 0))

    state = {"pdf": None, "page": 0, "imgs": [], "tmp": None}

    def clear_viewer():
        for w in viewer_area.winfo_children():
            w.destroy()

    def open_pdf(entry: dict, data: bytes):
        try:
            import fitz  # PyMuPDF
        except ImportError:
            clear_viewer()
            tk.Label(
                viewer_area,
                text="PyMuPDF is not installed, so PDFs can't be rendered\n"
                     "in-memory. Install it with:  pip install PyMuPDF",
                fg="white", bg="#222", justify="center",
            ).pack(expand=True)
            return

        doc = fitz.open(stream=data, filetype="pdf")
        state.update(pdf=doc, page=0, imgs=[])
        clear_viewer()

        nav = tk.Frame(viewer_area, bg="#222")
        nav.pack(fill="x")
        page_lbl = tk.Label(nav, bg="#222", fg="white")
        canvas = tk.Canvas(viewer_area, bg="#333", highlightthickness=0)
        vbar = tk.Scrollbar(viewer_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        def render():
            page = doc.load_page(state["page"])
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            png = pix.tobytes("png")
            img = tk.PhotoImage(data=png)
            state["imgs"] = [img]  # keep a ref so tk doesn't GC it
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=img)
            canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
            page_lbl.config(text=f"Page {state['page']+1} / {doc.page_count}")

        def go(delta):
            state["page"] = max(0, min(doc.page_count - 1, state["page"] + delta))
            render()

        tk.Button(nav, text="◀ Prev", command=lambda: go(-1)).pack(side="left")
        tk.Button(nav, text="Next ▶", command=lambda: go(1)).pack(side="left")
        page_lbl.pack(side="left", padx=10)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        render()

    def open_video(entry: dict, data: bytes):
        # Honest limitation: playing arbitrary video formats reliably means
        # handing bytes to a real player, which needs a file path. We write a
        # locked-down temp file, play it, and delete it on close.
        clear_viewer()
        tk.Label(
            viewer_area,
            text=f"Opening “{entry['name']}” in your system video player…\n\n"
                 "NOTE: video is briefly decrypted to a temporary file while it\n"
                 "plays, then deleted. This is weaker than PDF viewing.\n"
                 "Close the player, then pick another item.",
            fg="white", bg="#222", justify="center",
        ).pack(expand=True)

        # Clean up any previous temp video.
        if state["tmp"] and os.path.exists(state["tmp"]):
            try:
                os.remove(state["tmp"])
            except OSError:
                pass

        fd, path = tempfile.mkstemp(
            suffix=os.path.splitext(entry["name"])[1] or ".mp4", prefix="usblock_"
        )
        os.write(fd, data)
        os.close(fd)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        state["tmp"] = path

        def launch_and_cleanup():
            import subprocess
            import time
            try:
                if sys.platform.startswith("win"):
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.run(["open", "-W", path], check=False)
                else:
                    subprocess.run(["xdg-open", path], check=False)
            finally:
                # Give the player a moment to load, then remove the file.
                time.sleep(8)
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

        threading.Thread(target=launch_and_cleanup, daemon=True).start()

    def on_select(_evt=None):
        sel = listbox.curselection()
        if not sel:
            return
        entry = vault.files[sel[0]]
        try:
            data = vault.decrypt_file(entry)
        except crypto.WrongKeyError as exc:
            messagebox.showerror("Cannot open", str(exc))
            return
        if entry["type"] == "pdf":
            open_pdf(entry, data)
        elif entry["type"] == "video":
            open_video(entry, data)
        else:
            clear_viewer()
            tk.Label(
                viewer_area,
                text=f"{entry['name']}\n\nType '{entry['type']}' has no built-in "
                     "preview.",
                fg="white", bg="#222", justify="center",
            ).pack(expand=True)

    listbox.bind("<<ListboxSelect>>", on_select)

    def on_close():
        if state["tmp"] and os.path.exists(state["tmp"]):
            try:
                os.remove(state["tmp"])
            except OSError:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    clear_viewer()
    tk.Label(
        viewer_area,
        text="Select an item on the left to view it.",
        fg="white", bg="#222",
    ).pack(expand=True)

    watchdog()  # start the anti-recording poll
    root.mainloop()
    return 0


# --------------------------------------------------------------------------
def _unlock_with_prompt(drive_path: str, passphrase: str):
    """Build a Vault, prompting for a passphrase in the terminal if needed.

    Returns (vault, exit_code). If exit_code is not None the caller should
    return it; otherwise vault is unlocked and ready.
    """
    import getpass

    try:
        vault = Vault(drive_path, passphrase)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return None, 2

    if not vault.unlocked and vault.requires_passphrase:
        for _ in range(3):
            try:
                pw = getpass.getpass("Passphrase for this content: ")
            except (EOFError, KeyboardInterrupt):
                print()
                return None, 1
            vault = Vault(drive_path, pw)
            if vault.unlocked:
                break

    if not vault.unlocked:
        print(
            "Locked: this content is bound to a different USB drive, or the "
            "passphrase is wrong. Plug in the correct USB stick and retry.",
            file=sys.stderr,
        )
        return None, 3
    return vault, None


def run_terminal_mode(drive_path: str, passphrase: str) -> int:
    from .terminal import run_terminal

    vault, code = _unlock_with_prompt(drive_path, passphrase)
    if vault is None:
        return code
    return run_terminal(vault)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_viewer.py",
        description="Open USB-bound protected content.",
    )
    p.add_argument("--drive", help="USB mount point (default: where this app lives)")
    p.add_argument("--passphrase", default="", help="passphrase if the content needs one")
    p.add_argument("--terminal", action="store_true",
                   help="run in the terminal (text menu, no GUI window)")
    p.add_argument("--gui", action="store_true", help="force the graphical viewer")
    p.add_argument("--headless", action="store_true", help="no UI; verify + list only")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    drive_path = args.drive or _auto_drive()

    if args.headless:
        try:
            vault = Vault(drive_path, args.passphrase)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 2
        return run_headless(vault)

    if args.terminal:
        return run_terminal_mode(drive_path, args.passphrase)

    # Default: try the GUI, but fall back to the terminal viewer if there is
    # no display or tkinter is unavailable (unless --gui forces it).
    try:
        import tkinter  # noqa: F401
        has_display = sys.platform.startswith("win") or sys.platform == "darwin" \
            or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    except ImportError:
        has_display = False

    if not args.gui and not has_display:
        print("No graphical display detected — using the terminal viewer.\n")
        return run_terminal_mode(drive_path, args.passphrase)

    try:
        return run_gui(drive_path, args.passphrase)
    except Exception as exc:  # noqa: BLE001 - surface any GUI/import failure clearly
        print(f"Graphical viewer unavailable ({exc}); falling back to terminal.\n",
              file=sys.stderr)
        return run_terminal_mode(drive_path, args.passphrase)


if __name__ == "__main__":
    raise SystemExit(main())
