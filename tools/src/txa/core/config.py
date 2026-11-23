"""User-level settings and local folders.

Resolution order for every setting: ``TXA_<KEY>`` env var > ``config.json`` >
value baked into the build > built-in default.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from txa import constants

_DEFAULTS = {
    "upstream": lambda: constants.UPSTREAM_REPO,
    "client_id": lambda: constants.GITHUB_CLIENT_ID,
    "namespace": lambda: constants.DEFAULT_NAMESPACE,
    "api": lambda: constants.API_BASE,
    "lang": lambda: "en",
}


def lang() -> str:
    """Active UI language ('en' or 'vi'), configured by install.ps1, `txapm lang`, or TXA_LANG."""
    if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("TXA_TEST_LANG"):
        return "en"
    raw = (os.environ.get("TXA_TEST_LANG") or os.environ.get("TXA_LANG") or load_config().get("lang") or "en").strip().lower()
    return "vi" if raw.startswith("vi") else "en"


def set_lang(code: str) -> str:
    norm = "vi" if code.strip().lower().startswith("vi") else "en"
    cfg = load_config()
    cfg["lang"] = norm
    save_config(cfg)
    _sync_lang_env(norm)
    return norm


def _sync_lang_env(norm: str) -> None:
    """install.ps1 stores the chosen language in the User variable TXA_LANG, and a variable beats config.json. Without
    updating it, `txapm lang vi` would be ignored for good. Only touch it when it already exists (or is set for this run)."""
    if "TXA_LANG" in os.environ:
        os.environ["TXA_LANG"] = norm
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                winreg.QueryValueEx(key, "TXA_LANG")
            except FileNotFoundError:
                return
            winreg.SetValueEx(key, "TXA_LANG", 0, winreg.REG_SZ, norm)
    except OSError:
        pass  # config.json is still written; the next install.ps1 run or `setx TXA_LANG` fixes the variable


def txa_home() -> Path:
    if os.environ.get("TXA_HOME"):
        return Path(os.environ["TXA_HOME"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TXA"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "txa"


def temp_root() -> Path:
    """%TEMP%\\txa - where installers are downloaded before verification."""
    path = Path(tempfile.gettempdir()) / "txa"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return txa_home() / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text("utf-8-sig"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", "utf-8")


def get(key: str) -> str:
    if key not in _DEFAULTS:
        raise KeyError(f"unknown setting '{key}' (known: {', '.join(sorted(_DEFAULTS))})")
    return os.environ.get(f"TXA_{key.upper()}") or load_config().get(key) or _DEFAULTS[key]()


def api_base() -> str:
    explicit = get("api")
    if explicit:
        return explicit.rstrip("/")
    owner, repo = get("upstream").split("/", 1)
    return f"https://{owner.lower()}.github.io/{repo}/{constants.API_NAMESPACE}"


def keys() -> list[str]:
    return sorted(_DEFAULTS)


# --------------------------------------------------------------------------- sources

OFFICIAL_SOURCE = "txa"


def sources() -> list[dict]:
    """Configured package sources in priority order; the official `txa` source is always first."""
    cfg = load_config()
    official = {"name": OFFICIAL_SOURCE, "url": api_base(), "enabled": not cfg.get("txa_disabled"), "official": True}
    return [official, *[{"enabled": True, **item} for item in cfg.get("sources", [])]]


def save_custom_sources(items: list[dict], official_enabled: bool = True) -> None:
    cfg = load_config()
    cfg["sources"] = [{k: v for k, v in item.items() if k != "official"} for item in items if not item.get("official")]
    if official_enabled:
        cfg.pop("txa_disabled", None)
    else:
        cfg["txa_disabled"] = True
    save_config(cfg)
