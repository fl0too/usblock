"""usblock - hardware-bound secure viewer for USB-distributed content.

This package binds encrypted PDFs and videos to a specific USB drive using
the drive's hardware serial number as part of the decryption key, and
provides a viewer that hides its own content while a screen-recording
process is running.

It is a *deterrent*, not unbreakable protection. See README.md for the
honest threat model and limitations.
"""

__version__ = "1.0.0"

MANIFEST_NAME = "manifest.json"
PROTECTED_DIRNAME = "protected"
