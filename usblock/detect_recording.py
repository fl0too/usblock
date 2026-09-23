"""Detect running screen-recording / screen-capture software.

This is a *best-effort deterrent*. It matches running process names against
a list of well-known recorders. It cannot catch everything: a renamed
binary, a hardware capture card, an HDMI splitter, a phone camera pointed at
the screen, or a kernel/driver-level grabber will all slip past. Treat a
positive as "hide the content" and a negative as "no *known* recorder seen",
never as a guarantee that nothing is capturing.

We deliberately do NOT try to kill other processes or interfere with the
operating system. The only action taken (in the viewer) is to hide this
application's own window.
"""

from __future__ import annotations

from dataclasses import dataclass

# Substrings matched case-insensitively against process names. Grouped only
# for readability; matching is flat.
KNOWN_RECORDERS = {
    # Cross-platform / streaming
    "obs", "obs64", "obs32", "streamlabs", "xsplit", "wondershare",
    # Windows
    "bandicam", "camtasia", "camrec", "snagit", "snagiteditor", "sharex",
    "action", "mirillis", "flashback", "fbrecorder", "screenpresso",
    "icecream screen", "screenrec", "activepresenter", "debut", "screencast",
    "movavi", "screencap",
    # macOS
    "screencapture",           # the built-in `screencapture` CLI
    "quicktime player",        # screen recording via QuickTime
    "screenflow", "capto", "kap", "cleanshot", "gifox", "screenflick",
    # Linux
    "simplescreenrecorder", "kazam", "vokoscreen", "vokoscreenng",
    "recordmydesktop", "gtk-recordmydesktop", "peek", "green-recorder",
    "obs-studio", "wf-recorder", "gpu-screen-recorder", "kooha",
    # Generic capture backends often used for recording
    "ffmpeg", "gstreamer", "gst-launch", "vlc",   # vlc/ffmpeg can capture screen
}

# These are noisy (also used for totally innocent things). Only report them
# when strict=False so the caller can choose sensitivity.
SOFT_MATCHES = {"ffmpeg", "gstreamer", "gst-launch", "vlc"}


@dataclass
class Detection:
    pid: int
    name: str
    matched: str


def scan(strict: bool = True) -> list[Detection]:
    """Return a list of detected recorder processes.

    strict=True  -> ignore the noisy soft matches (ffmpeg/vlc/gstreamer).
    strict=False -> include them too (more false positives).
    """
    import psutil

    hits: list[Detection] = []
    candidates = KNOWN_RECORDERS - (SOFT_MATCHES if strict else set())

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not name:
            continue
        for needle in candidates:
            if needle in name:
                hits.append(Detection(pid=proc.info["pid"], name=name, matched=needle))
                break
    return hits


def is_recording(strict: bool = True) -> bool:
    return bool(scan(strict=strict))


if __name__ == "__main__":
    found = scan(strict=False)
    if found:
        print("Possible screen recorders running:")
        for d in found:
            print(f"  pid={d.pid:<7} {d.name}  (matched '{d.matched}')")
    else:
        print("No known screen-recording processes detected.")
