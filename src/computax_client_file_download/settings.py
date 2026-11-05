"""Load and save the app's only persisted setting: the CompuTax folder path."""

import json
import os
import sys
from pathlib import Path

APP_DIR_NAME = "computax-downloader"
ROOT_KEY = "computax_root"


def config_dir() -> Path:
    """Return the per-user settings folder for the current operating system."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def default_settings_file() -> Path:
    """Return the path of settings.json inside the per-user settings folder."""
    return config_dir() / "settings.json"


def load_root(settings_file: Path) -> str | None:
    """Return the saved CompuTax path, or None if nothing usable is saved."""
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    root = data.get(ROOT_KEY) if isinstance(data, dict) else None
    return root if isinstance(root, str) and root else None


def save_root(settings_file: Path, root: str) -> None:
    """Atomically write the CompuTax path to the settings file."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_file.with_suffix(".tmp")
    tmp.write_text(json.dumps({ROOT_KEY: root}, indent=2), encoding="utf-8")
    os.replace(tmp, settings_file)
