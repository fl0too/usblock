# usblock — hardware-bound secure viewer for USB content

`usblock` lets you put PDFs and videos on a USB stick so that they can **only
be opened while that specific USB stick is plugged in**. The content is
encrypted with a key derived from the drive's **hardware serial number** (its
"product code"), so copying the encrypted files to another drive or a hard
disk leaves them unreadable. The bundled viewer also **hides its own window
while a known screen-recording program is running**.

This is the pattern software vendors use for training materials on a USB
dongle. It is a **deterrent against casual copying and recording — not
unbreakable protection.** Please read the *Threat model & limitations* section
below before relying on it.

---

## What's in the box

| File | Purpose |
|------|---------|
| `usblock.sh` / `usblock.bat` | **Run this.** Terminal launchers — auto-set-up on first run, then dispatch every command. You never type `python`. |
| `usblock_cli.py` | The command dispatcher the launchers call (`view` / `gui` / `list` / `protect` / `test`). |
| `protect.py` | Encrypt your files and bind them to a chosen USB drive. |
| `run_viewer.py` | The viewer recipients run to read the content ("the executable"). |
| `build_exe.py` | Turn the viewer into a standalone `.exe`/binary with PyInstaller. |
| `usblock/` | The library: USB serial detection, crypto, recorder detection, GUI + terminal viewer. |
| `tests/` | End-to-end self-test (`./usblock.sh test`). |
| `requirements.txt` | Python dependencies. |

---

## Run it from the terminal (no `python` typing)

The launcher scripts do everything. On first run they quietly create a private
environment and install dependencies; after that they're instant.

```bash
# macOS / Linux
./usblock.sh                       # open the content in a text menu (terminal)
./usblock.sh list                  # show drives + serials
./usblock.sh protect --drive /media/you/STICK --passphrase "secret" --add a.pdf b.mp4
./usblock.sh gui                   # graphical viewer instead of the terminal one
```

```bat
REM Windows (cmd or PowerShell, or just double-click usblock.bat)
usblock.bat                        :: terminal viewer
usblock.bat list
usblock.bat protect --drive E:\ --passphrase "secret" --add a.pdf b.mp4
```

Python still does the cryptography and USB-serial work under the hood — it just
runs behind the launcher, so you interact only with the terminal. The terminal
viewer shows a numbered menu; type a number to open an item. **While a screen
recorder is running the menu is replaced by a warning and opening is refused**
until you close the recorder — the terminal equivalent of blanking the screen.

The rest of this README uses the underlying `python …` commands, which still
work if you prefer them.

---

## Install

Python 3.9+ required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`cryptography` and `psutil` are required. `PyMuPDF` is strongly recommended so
PDFs render **in memory** (no plaintext PDF ever hits the disk). Without it,
PDFs simply won't preview.

---

## 1. Find your USB's serial

```bash
python protect.py --list
```

You'll see each mounted drive and its hardware serial. If a drive shows
`(no hardware serial …)`, the OS couldn't read one and the tool will fall back
to the device path — weaker and less portable, so prefer a stick that reports
a real serial.

## 2. Protect your files onto the stick

```bash
# Windows
python protect.py --drive E:\ --passphrase "a strong secret" --add lesson1.pdf intro.mp4

# macOS / Linux
python protect.py --drive /media/you/STICK --passphrase "a strong secret" \
    --add lesson1.pdf intro.mp4 handbook.pdf
```

This creates on the stick:

```
E:\protected\manifest.json     # salt, KDF params, verify token, file list
E:\protected\lesson1.pdf.enc   # AES-256-GCM encrypted
E:\protected\intro.mp4.enc
```

Your original files are left untouched. **Use `--passphrase`** for anything
you actually care about (see limitations).

## 3. Ship the viewer with it

Copy `run_viewer.py` and the `usblock/` folder onto the stick next to
`protected/`, **or** build a one-file executable so recipients don't need
Python:

```bash
pip install pyinstaller PyMuPDF
python build_exe.py          # -> dist/SecureViewer(.exe) — copy it onto the stick
```

## 4. Open the content

```bash
./usblock.sh                         # terminal viewer, auto-detects the USB
./usblock.sh gui                     # graphical viewer
# or, directly:
python run_viewer.py --terminal      # text menu, no GUI window
python run_viewer.py                 # GUI (falls back to terminal if no display)
python run_viewer.py --drive E:\     # point it at a specific drive
python run_viewer.py --headless      # verify + list only, no interaction
```

The viewer reads the stick's serial, derives the key (prompting for the
passphrase if one was set), and unlocks. **Plug the wrong stick in and it stays
locked.**

---

## The anti-screen-recording feature

While the viewer is open it polls (every ~1.5 s) for well-known screen
recorders (OBS, Camtasia, Bandicam, ShareX, QuickTime screen capture,
SimpleScreenRecorder, and many more — see `usblock/detect_recording.py`). When
one is detected it **covers the app with an opaque full-screen warning and
hides the content**, restoring it once the recorder is closed.

"Turn off the screen" here means **blanking this application's own window** —
the standard, non-destructive DRM behaviour used by streaming and banking
apps. `usblock` never turns off your monitor, never kills other programs, and
never touches the operating system.

---

## Threat model & limitations (read this)

`usblock` raises the effort required to copy or record your content. It does
**not** make that impossible, and you should not treat it as if it does:

- **The serial is readable by anyone holding the stick.** Binding to the serial
  stops "copy the files to a different drive and open them"; it does **not**
  stop someone who has the physical stick. Always add a `--passphrase` for real
  confidentiality — then the key depends on a secret, not just the hardware.
- **Decrypted content exists in RAM while you view it**, and can in principle be
  extracted by someone with sufficient access to the machine. PDFs are rendered
  in memory; **videos are briefly written to a locked-down temp file** while the
  system player runs, then deleted — that temp file is the weakest link.
- **Screen-recording detection is process-name based.** A renamed recorder, a
  driver/kernel-level grabber, an HDMI capture card, or simply a phone camera
  pointed at the screen will not be caught. Analog capture always wins.
- **A serial can be spoofed** on some controllers, and encrypted blobs can be
  copied freely (they're just useless without the key).

In short: good against honest users and casual copying; not a match for a
determined, technical adversary with local access. Size your expectations
accordingly.

## Please use it lawfully

Only protect and distribute content **you own or are licensed to distribute**,
and use the anti-recording feature to protect your own material — not to evade
legitimate monitoring, accessibility tooling, or security software on machines
you don't control. You are responsible for how you use this.

## Run the tests

```bash
python tests/test_roundtrip.py     # or: python -m pytest -q
```
