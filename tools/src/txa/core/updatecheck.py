"""Tell the user, once in a while, that a newer txapm / txacreate / txacli exists - and how to get it.

The notice goes to stderr after the command finished, only in an interactive terminal, at most one
network lookup every 6 hours (cached), and a slow or offline network never delays or breaks a command.
Disable with TXA_NO_UPDATE_CHECK=1.
"""
from __future__ import annotations

import atexit
import json
import os
import sys
import time
from pathlib import Path

import requests

from txa import __version__
from txa.core import config, semver

CACHE_SECONDS = 6 * 3600
TIMEOUT = 2.0
INSTALL_PS1 = "irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex"
_registered = False


def install_method() -> str:
    """How this copy of TXA was installed: "powershell" (the .exe from install.ps1), "pipx" or "pip"."""
    if getattr(sys, "frozen", False):
        return "powershell"
    prefix = str(Path(sys.prefix)).lower().replace("\\", "/")
    home = os.environ.get("PIPX_HOME", "").lower().replace("\\", "/")
    if "/pipx/" in prefix or (home and prefix.startswith(home)):
        return "pipx"
    return "pip"


def update_command(method: str | None = None) -> str:
    return {"powershell": INSTALL_PS1, "pipx": "pipx upgrade txa"}.get(method or install_method(), "python -m pip install --upgrade txa")


def _cache_file() -> Path:
    return config.txa_home() / "state" / "update-check.json"


def _read_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict) -> None:
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), "utf-8")
    except OSError:
        pass


def _lookup(method: str) -> str | None:
    """Newest published version: the GitHub release for the .exe install, PyPI for pip/pipx."""
    headers = {"User-Agent": f"txa/{__version__}", "Accept": "application/json", "Accept-Encoding": "identity"}
    try:
        if method == "powershell":
            data = requests.get(f"https://api.github.com/repos/{config.get('upstream')}/releases/latest", headers=headers, timeout=TIMEOUT).json()
            return str(data.get("tag_name", "")).lstrip("v") or None
        return requests.get("https://pypi.org/pypi/txa/json", headers=headers, timeout=TIMEOUT).json()["info"]["version"]
    except (requests.RequestException, ValueError, KeyError):
        return None


def newer_version(now: float | None = None, lookup=_lookup) -> str | None:
    """The newer version to announce, or None (up to date, offline, or checked recently without news)."""
    method = install_method()
    cache = _read_cache()
    now = time.time() if now is None else now
    latest = cache.get("latest")
    if not latest or now - float(cache.get("checked", 0)) > CACHE_SECONDS or cache.get("method") != method:
        latest = lookup(method) or latest
        _write_cache({"checked": now, "latest": latest, "method": method})
    if latest and semver.is_valid(latest) and semver.is_valid(__version__) and semver.parse(latest) > semver.parse(__version__):
        return latest
    return None


def message(latest: str, method: str | None = None) -> str:
    from txa.core import winos

    command = update_command(method)
    if winos.ui_language() == "vi":
        return f"! Có bản TXA mới {latest} (đang dùng {__version__}). Cập nhật bằng lệnh:  {command}"
    return f"! A new TXA version {latest} is available (you have {__version__}). Update with:  {command}"


def notify() -> None:
    if os.environ.get("TXA_NO_UPDATE_CHECK") or os.environ.get("CI") or not (sys.stderr.isatty() and sys.stdin.isatty()):
        return
    try:
        latest = newer_version()
        if latest:
            from txa.core import console

            print(console.paint(message(latest), "yellow"), file=sys.stderr)
    except Exception:  # noqa: BLE001 - never let the courtesy notice break a command
        pass


def register() -> None:
    """Call once at the start of an entry point: the notice is printed when the process exits."""
    global _registered
    if not _registered:
        _registered = True
        atexit.register(notify)
