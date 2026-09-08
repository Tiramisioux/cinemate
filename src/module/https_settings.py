"""Shared settings["system"]["https"] defaults, plus self-signed cert issuing.

Split out the same way module.web_api_settings is, so main.py can read the
block and mint a certificate without importing flask.

Why this is off by default, and why it is not simply "better":

  * A camera is reached at cinepi.local or, on the hotspot, at 10.42.0.1.
    Neither can ever hold a publicly-trusted certificate -- no CA will issue
    for an mDNS name or a private address -- so HTTPS here always means a
    self-signed certificate and a full-page browser interstitial on first
    visit (and on every visit in a private window, and repeatedly on iOS).
  * cinepi-raw's MJPEG preview is plain HTTP on port 8000 and cannot speak
    TLS. A secure page may not load an insecure subresource, so turning this
    on without more would black out the live preview. main.routes handles
    that by proxying the stream same-origin when, and only when, the page was
    served over TLS -- see _stream_url_for_request().

Turn it on when you need a secure context: the RAW pane's "download to a
folder" uses the File System Access API, which browsers refuse to expose on
a plain-HTTP origin.
"""
from __future__ import annotations

import datetime
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HTTPS_SETTINGS = {
    "enabled": False,
    # Relative paths resolve against the repo root, like sensors.database_file.
    "cert_file": "resources/certs/cinemate.crt",
    "key_file": "resources/certs/cinemate.key",
    # Days a freshly minted self-signed certificate is good for. It is
    # re-issued automatically once it expires.
    "valid_days": 3650,
}


def https_settings(settings):
    """Merge settings["system"]["https"] over the documented defaults."""
    cfg = ((settings or {}).get("system", {}) or {}).get("https", {}) or {}
    merged = dict(DEFAULT_HTTPS_SETTINGS)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_HTTPS_SETTINGS})
    return merged


def _repo_root() -> Path:
    # src/module/https_settings.py -> repo root
    return Path(__file__).resolve().parents[2]


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else _repo_root() / path


def _certificate_is_usable(cert: Path) -> bool:
    """True if *cert* exists and has not expired.

    Checked with openssl rather than parsed here: a certificate that expired
    while the camera sat on a shelf would otherwise fail at bind time, which
    is the worst possible moment to find out.
    """
    if not cert.is_file():
        return False
    openssl = shutil.which("openssl")
    if not openssl:
        return True  # cannot check; assume the operator knows
    result = subprocess.run(
        [openssl, "x509", "-checkend", "0", "-noout", "-in", str(cert)],
        capture_output=True,
    )
    if result.returncode != 0:
        logger.warning("TLS certificate %s has expired; re-issuing", cert)
        return False
    return True


def ensure_certificate(cfg: dict) -> tuple[Path, Path] | None:
    """Return (cert, key), minting a self-signed pair if needed.

    Returns None if a certificate cannot be produced, so the caller can fall
    back to plain HTTP rather than failing to serve at all -- a camera that
    does not answer on :5000 is worse than one that answers insecurely.
    """
    cert = resolve_path(cfg["cert_file"])
    key = resolve_path(cfg["key_file"])

    if _certificate_is_usable(cert) and key.is_file():
        return cert, key

    openssl = shutil.which("openssl")
    if not openssl:
        logger.error(
            "https.enabled is true but openssl is not installed, so no "
            "certificate can be issued. Serving plain HTTP instead."
        )
        return None

    try:
        cert.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert),
                "-days", str(int(cfg.get("valid_days") or 3650)),
                "-subj", "/CN=cinepi.local/O=CineMate",
                # The names a camera is actually reached by. Without these a
                # modern browser rejects the certificate outright rather than
                # merely warning, because CN alone has not been honoured for
                # years.
                "-addext",
                "subjectAltName=DNS:cinepi.local,DNS:localhost,"
                "IP:127.0.0.1,IP:10.42.0.1",
            ],
            capture_output=True,
            check=True,
        )
        key.chmod(0o600)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        logger.error(
            "Could not issue a TLS certificate (%s); serving plain HTTP. %s",
            exc, detail.decode("utf-8", "replace").strip(),
        )
        return None

    logger.info(
        "Issued a self-signed TLS certificate valid until %s: %s",
        (datetime.date.today()
         + datetime.timedelta(days=int(cfg.get("valid_days") or 3650))).isoformat(),
        cert,
    )
    return cert, key


def ssl_context_for(settings) -> tuple[Path, Path] | None:
    """The ssl_context to hand socketio.run(), or None for plain HTTP."""
    cfg = https_settings(settings)
    if not cfg.get("enabled"):
        return None
    return ensure_certificate(cfg)
