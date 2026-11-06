"""StatusNotifier/AppIndicator tray for TuxControl Quick Share.

Needs ``pystray`` and ``Pillow``; the receiver additionally needs
``pyquickshare``. ``tuxcontrol-quickshare-tray`` installs them on request.
"""
from __future__ import annotations

import fcntl
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import VISIBILITIES, load_config, save_config

try:
    import pystray
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Quick Share tray dependencies are missing. Start it with tuxcontrol-quickshare-tray.") from exc

_HERE = Path(__file__).resolve()
# Source checkout: <root>/src/control_center/quickshare; installed/portable: <lib>/control_center/quickshare.
ROOT = next(
    (p for p in (_HERE.parents[2], _HERE.parents[3]) if (p / "tuxcenter.png").is_file()),
    _HERE.parents[2],
)
ICON = ROOT / "tuxcenter.png"
PKG_PARENT = _HERE.parents[2]
POLL_SECONDS = 2
CRASH_BACKOFF_SECONDS = 15

_stop = threading.Event()
_receiver: subprocess.Popen | None = None
_state = {"text": "Starting…"}
_icon: "pystray.Icon | None" = None


def _acquire_single_instance():
    """Hold an exclusive lock for the life of the process; return None if another tray owns it."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/tuxcontrol-{os.getuid()}")
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = open(runtime / "tuxcontrol-quickshare-tray.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _env() -> dict[str, str]:
    env = {**os.environ}
    env["PYTHONPATH"] = str(PKG_PARENT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _system_python() -> str:
    """GTK/PyGObject lives in the system Python, not necessarily in this venv."""
    for candidate in ("/usr/bin/python3", shutil.which("python3"), sys.executable):
        if candidate and Path(candidate).exists():
            return candidate
    return sys.executable


def _spawn_gui(module: str) -> None:
    subprocess.Popen([_system_python(), "-m", module], env=_env(), start_new_session=True)


def _refresh_menu() -> None:
    if _icon is not None:
        _icon.update_menu()


def _stop_receiver() -> None:
    global _receiver
    proc, _receiver = _receiver, None
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _supervise() -> None:
    """Keep the receiver process in line with the saved configuration."""
    global _receiver
    retry_at = 0.0
    while not _stop.is_set():
        cfg = load_config()
        alive = _receiver is not None and _receiver.poll() is None
        previous = _state["text"]
        if cfg["visibility"] == "Closed":
            if alive:
                _stop_receiver()
            _receiver = None
            _state["text"] = "Not visible (closed)"
        elif alive:
            scope = "nearby devices" if cfg["visibility"] == "LAN" else "everyone"
            _state["text"] = f"Visible to {scope} as {cfg['device_name']}"
        else:
            code = _receiver.returncode if _receiver else 0
            if code == 2:
                _state["text"] = "pyquickshare missing: rerun tuxcontrol-quickshare-tray"
            elif code != 0 and time.monotonic() < retry_at:
                _state["text"] = "Receiver failed; retrying shortly"
            else:
                retry_at = time.monotonic() + CRASH_BACKOFF_SECONDS if code != 0 else 0.0
                _receiver = subprocess.Popen(
                    [sys.executable, "-m", "control_center.quickshare.receiver"], env=_env()
                )
                _state["text"] = "Starting receiver…"
        if _state["text"] != previous:
            _refresh_menu()
        _stop.wait(POLL_SECONDS)
    _stop_receiver()


def _set_visibility(value: str) -> None:
    cfg = load_config()
    cfg["visibility"] = value
    save_config(cfg)
    _refresh_menu()


def _quit(icon, _item) -> None:
    _stop.set()
    icon.stop()


def main() -> None:
    global _icon
    lock = _acquire_single_instance()
    if lock is None:
        print("TuxControl Quick Share is already running.", file=sys.stderr)
        raise SystemExit(0)
    if not ICON.is_file():
        raise SystemExit(f"Icon not found: {ICON}")
    image = Image.open(ICON).convert("RGBA")

    def radio(value: str):
        return pystray.MenuItem(
            value,
            lambda _icon, _item: _set_visibility(value),
            checked=lambda _item: load_config()["visibility"] == value,
            radio=True,
        )

    menu = pystray.Menu(
        pystray.MenuItem("Open TuxControl", lambda *_: _spawn_gui("control_center.app"), default=True),
        pystray.MenuItem("Send files…", lambda *_: _spawn_gui("control_center.quickshare.send_window")),
        pystray.MenuItem("Visibility", pystray.Menu(*(radio(v) for v in VISIBILITIES))),
        pystray.MenuItem(lambda _item: _state["text"], None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings", lambda *_: _spawn_gui("control_center.quickshare.settings")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
    _icon = pystray.Icon("tuxcontrol-quickshare", image, "TuxControl Quick Share", menu)
    threading.Thread(target=_supervise, daemon=True).start()
    # Without this, a SIGTERM would leave the receiver process orphaned.
    signal.signal(signal.SIGTERM, lambda *_: _icon.stop())
    try:
        _icon.run()
    finally:
        _stop.set()
        _stop_receiver()


if __name__ == "__main__":
    main()
