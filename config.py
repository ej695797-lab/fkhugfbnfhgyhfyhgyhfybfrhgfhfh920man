import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _force_utf8_console() -> None:
    """
    Windows consoles default to a legacy code page (cp1252), which raises
    UnicodeEncodeError on any non-ASCII output such as player display names.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_console()


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "OGYeeps")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
# Render (and most PaaS) inject PORT; it must win over SERVER_PORT so the
# platform's proxy can reach us.
SERVER_PORT = int(os.getenv("PORT") or os.getenv("SERVER_PORT", "8000"))
SEED_DB = _flag("SEED_DB", "0")
RELOAD = _flag("RELOAD", "0")


def _writable_log_dir() -> Path:
    """
    Prefer ./logs, but fall back to the system temp dir when the working
    directory is read-only (Render, Docker, most PaaS filesystems).
    """
    preferred = BASE_DIR / "logs"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "yeeps-logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


LOG_DIR = _writable_log_dir()

# HTTPS. Generate a certificate first with: python make_cert.py
USE_SSL = _flag("USE_SSL", "0")
CERT_FILE = Path(os.getenv("SSL_CERTFILE", BASE_DIR / "certs" / "server.crt"))
KEY_FILE = Path(os.getenv("SSL_KEYFILE", BASE_DIR / "certs" / "server.key"))