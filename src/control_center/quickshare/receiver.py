"""Quick Share receiver process (uses the optional ``pyquickshare`` package).

Started and supervised by the tray. It exits when the visibility becomes
``Closed``, when the auto-disable timer expires, or when the settings that
require re-advertising (name, folder, visibility) change.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import shutil
import signal
import sys
from pathlib import Path
from typing import Any

from .config import load_config, save_config

log = logging.getLogger("tuxcontrol.quickshare")
CONFIRM_TIMEOUT_SECONDS = 60
RESTART_KEYS = ("visibility", "device_name", "download_dir", "auto_disable_minutes")


def unique_destination(folder: Path, name: str) -> Path:
    """Return a non-existing path inside ``folder`` for a sender-supplied name."""
    base = Path(name.replace("\\", "/")).name
    if base in {"", ".", ".."}:
        base = "received-file"
    candidate = folder / base
    stem, suffix = candidate.stem, candidate.suffix
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def _install_safe_writer(download_dir: Path) -> None:
    """pyquickshare writes to a relative ``downloads/<remote name>``; redirect it safely."""
    import aiofile

    original = aiofile.async_open

    def safe_open(path: Any, *args: Any, **kwargs: Any):
        text = str(path)
        if text.startswith("downloads/"):
            path = unique_destination(download_dir, text[len("downloads/"):])
        return original(path, *args, **kwargs)

    aiofile.async_open = safe_open


async def _confirm(request: Any) -> bool:
    name = getattr(request.header, "file_name", "") or "files"
    text = (
        f"A nearby device wants to send “{name}”.\n"
        f"Verification code: {request.pin}\n\nAccept this transfer?"
    )
    if shutil.which("zenity"):
        command = ["zenity", "--question", "--no-markup", "--title=TuxControl Quick Share", f"--text={text}"]
    elif shutil.which("kdialog"):
        command = ["kdialog", "--title", "TuxControl Quick Share", "--yesno", text]
    else:
        log.warning("No dialog tool (zenity/kdialog) found; declining the transfer.")
        return False
    process = await asyncio.create_subprocess_exec(*command)
    try:
        return await asyncio.wait_for(process.wait(), CONFIRM_TIMEOUT_SECONDS) == 0
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        return False


def _notify(message: str) -> None:
    if shutil.which("notify-send"):
        import subprocess

        subprocess.Popen(["notify-send", "-a", "TuxControl", "Quick Share", message])


async def _handle(request: Any, cfg: dict[str, Any]) -> None:
    try:
        if cfg["ask_before_accept"] and not await _confirm(request):
            await request.reject()
            log.info("Declined an incoming transfer")
            return
        results = await request.accept()
        log.info("Transfer completed: %s", results)
        _notify(f"Received {len(results)} item(s) in {cfg['download_dir']}")
    except Exception:
        log.exception("Quick Share transfer failed")


async def _watch(start_cfg: dict[str, Any]) -> None:
    """Return when the receiver should stop."""
    loop = asyncio.get_running_loop()
    minutes = int(start_cfg["auto_disable_minutes"])
    deadline = loop.time() + minutes * 60 if minutes else None
    while True:
        await asyncio.sleep(2)
        current = load_config()
        if deadline is not None and loop.time() >= deadline:
            current["visibility"] = "Closed"
            save_config(current)
            log.info("Auto-disable timer expired; visibility closed")
            return
        if any(current[key] != start_cfg[key] for key in RESTART_KEYS):
            return


async def receive_forever() -> int:
    cfg = load_config()
    if cfg["visibility"] == "Closed":
        return 0
    try:
        import pyquickshare
    except ImportError:
        log.error("pyquickshare is not installed. Run tuxcontrol-quickshare-tray to install it.")
        return 2

    download_dir = Path(cfg["download_dir"])
    download_dir.mkdir(parents=True, exist_ok=True)
    _install_safe_writer(download_dir)
    # The library advertises a hardcoded name; use the configured one instead.
    importlib.import_module("pyquickshare.receive").NAME = cfg["device_name"]

    tasks: set[asyncio.Task] = set()

    async def serve() -> None:
        async for request in pyquickshare.receive(endpoint_id=pyquickshare.generate_endpoint_id()):
            task = asyncio.create_task(_handle(request, cfg))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    server = asyncio.create_task(serve())
    watcher = asyncio.create_task(_watch(cfg))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, watcher.cancel)
    code = 0
    try:
        done, _ = await asyncio.wait({server, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if server in done and server.exception():
            log.error("Quick Share receiver stopped: %s", server.exception())
            code = 1
    except asyncio.CancelledError:
        pass
    finally:
        server.cancel()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(server, *tasks, return_exceptions=True)
    return code


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(asyncio.run(receive_forever()))


if __name__ == "__main__":
    main()
