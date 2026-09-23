"""End-to-end test: crypto round-trip + protect + locked/unlocked viewer.

Runs without a real USB by pointing get_drive_info at a temp directory with a
fake serial. Run:  python -m pytest -q   (or just: python tests/test_roundtrip.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usblock import crypto, protect as protect_mod, usbid, viewer  # noqa: E402
from usblock.usbid import DriveInfo  # noqa: E402


def _patch_drive(monkeypatch, mount, serial):
    info = DriveInfo(mountpoint=mount, device="/dev/fake", serial=serial, label="FAKE")
    monkeypatch.setattr(usbid, "get_drive_info", lambda path: info)
    monkeypatch.setattr(protect_mod, "get_drive_info", lambda path: info)
    monkeypatch.setattr(viewer, "get_drive_info", lambda path: info)


def test_crypto_roundtrip():
    salt = crypto.new_salt()
    key = crypto.derive_key("SERIAL123", "pw", salt)
    blob = crypto.encrypt(key, b"hello world", associated=b"a.pdf")
    assert crypto.decrypt(key, blob, associated=b"a.pdf") == b"hello world"
    # Wrong associated data fails.
    try:
        crypto.decrypt(key, blob, associated=b"b.pdf")
        assert False, "should have raised"
    except crypto.WrongKeyError:
        pass


def test_wrong_key_locked():
    salt = crypto.new_salt()
    good = crypto.derive_key("SERIAL123", "", salt)
    bad = crypto.derive_key("OTHERSERIAL", "", salt)
    token = crypto.make_verify_token(good)
    assert crypto.check_verify_token(good, token) is True
    assert crypto.check_verify_token(bad, token) is False


def test_full_flow(monkeypatch, tmp_path):
    mount = str(tmp_path)
    # A sample PDF-ish and video-ish file.
    src_pdf = tmp_path / "doc.pdf"
    src_pdf.write_bytes(b"%PDF-1.4 fake pdf bytes")
    src_vid = tmp_path / "clip.mp4"
    src_vid.write_bytes(b"\x00\x00\x00\x18ftypmp42 fake video")

    _patch_drive(monkeypatch, mount, "SERIAL-ABC-123")
    rc = protect_mod.cmd_protect(mount, "secretpw", [str(src_pdf), str(src_vid)])
    assert rc == 0
    assert (tmp_path / "protected" / "manifest.json").exists()
    assert (tmp_path / "protected" / "doc.pdf.enc").exists()

    # Correct serial + passphrase -> unlocked, decrypts back to originals.
    v = viewer.Vault(mount, "secretpw")
    assert v.unlocked is True
    names = {e["name"]: e for e in v.files}
    assert v.decrypt_file(names["doc.pdf"]) == b"%PDF-1.4 fake pdf bytes"
    assert names["clip.mp4"]["type"] == "video"

    # Wrong passphrase -> locked.
    v2 = viewer.Vault(mount, "WRONG")
    assert v2.unlocked is False

    # Different USB serial -> locked.
    _patch_drive(monkeypatch, mount, "DIFFERENT-SERIAL")
    v3 = viewer.Vault(mount, "secretpw")
    assert v3.unlocked is False


if __name__ == "__main__":
    # Minimal runner so this works without pytest installed.
    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)
            self._undo.clear()

    import tempfile
    from pathlib import Path

    test_crypto_roundtrip()
    test_wrong_key_locked()
    mp = _MP()
    with tempfile.TemporaryDirectory() as d:
        try:
            test_full_flow(mp, Path(d))
        finally:
            mp.undo()
    print("All tests passed.")
