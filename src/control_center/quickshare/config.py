"""Persistent Quick Share preferences shared by the tray, settings, and receiver."""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "tuxcontrol"
CONFIG_FILE = CONFIG_DIR / "quickshare.json"
VISIBILITIES = ("LAN", "Everyone", "Closed")
AUTO_DISABLE_CHOICES = (0, 5, 10, 30, 60)

DEFAULTS: dict[str, Any] = {
    "device_name": socket.gethostname(),
    "visibility": "LAN",
    "auto_disable_minutes": 0,
    "download_dir": str(Path.home() / "Downloads"),
    "ask_before_accept": True,
}


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    clean = DEFAULTS.copy()
    clean.update({k: v for k, v in data.items() if k in DEFAULTS})
    if clean["visibility"] not in VISIBILITIES:
        clean["visibility"] = DEFAULTS["visibility"]
    if clean["auto_disable_minutes"] not in AUTO_DISABLE_CHOICES:
        clean["auto_disable_minutes"] = 0
    name = str(clean["device_name"]).strip()[:64]
    clean["device_name"] = name or DEFAULTS["device_name"]
    folder = str(clean["download_dir"]).strip()
    clean["download_dir"] = str(Path(folder).expanduser()) if folder else DEFAULTS["download_dir"]
    clean["ask_before_accept"] = bool(clean["ask_before_accept"])
    return clean


def load_config() -> dict[str, Any]:
    try:
        stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    return _sanitize(stored if isinstance(stored, dict) else {})


def save_config(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_sanitize(data), indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)
