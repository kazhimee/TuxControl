"""Quick Share sender worker (uses the optional ``pyquickshare`` package).

Protocol, one JSON object per line.
  stdout: {"event": "device", "id", "name", "kind"}
          {"event": "sending", "file"} | {"event": "done", "file"} | {"event": "error", "message"}
          {"event": "finished"}
  stdin:  {"send": "<device id>"}
Usage: python -m control_center.quickshare.sender FILE [FILE...]
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any

DISCOVERY_SECONDS = 120


def emit(**event: Any) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


class _ErrorCapture(logging.Handler):
    """pyquickshare reports most failures through logging instead of exceptions."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def local_addresses() -> set[str]:
    try:
        import ifaddr

        return {
            ip.ip for adapter in ifaddr.get_adapters() for ip in adapter.ips if isinstance(ip.ip, str)
        }
    except Exception:
        return set()


def parse_endpoint_info(raw: bytes) -> tuple[str, str] | None:
    """Decode an mDNS ``n`` record: flags, 16 random bytes, name length, name.

    Flags are version(3 bits) | hidden(1) | device type(3) | reserved(1).
    pyquickshare reads the hidden bit from the wrong position and treats every
    device as hidden, so it is decoded here instead.
    """
    from pyquickshare.common import from_url64

    try:
        data = from_url64(raw.decode("ascii"))
    except Exception:
        return None
    if len(data) < 18 or data[0] & 0x10:
        return None
    length = data[17]
    name = data[18:18 + length].decode("utf-8", errors="replace").strip()
    if not name:
        return None
    kinds = {1: "phone", 2: "tablet", 3: "laptop"}
    return name, kinds.get((data[0] >> 1) & 0b111, "unknown")


def describe(service: Any) -> tuple[str, str] | None:
    """Return (display name, device kind) for a visible device, else None."""
    raw = service.properties.get(b"n")
    return parse_endpoint_info(raw) if raw else None


def patch_library_parser() -> None:
    """Make pyquickshare.send_to accept devices that are visible to everyone."""
    from pyquickshare import send

    def fixed(raw: bytes):
        info = parse_endpoint_info(raw)
        name, kind = info if info else (None, "unknown")
        kind_type = {"phone": send.Type.phone, "tablet": send.Type.tablet, "laptop": send.Type.laptop}.get(
            kind, send.Type.unknown
        )
        return send.DeviceMetadata(info is not None, kind_type, name, {})

    send._parse_n = fixed


async def _read_commands(queue: asyncio.Queue[str]) -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            await queue.put("")
            return
        try:
            target = json.loads(line).get("send")
        except (ValueError, AttributeError):
            continue
        if isinstance(target, str):
            await queue.put(target)


async def run(files: list[Path]) -> int:
    import pyquickshare

    patch_library_parser()
    # Reverse DNS lookups of LAN addresses can stall for many seconds and are not needed.
    socket.gethostbyaddr = lambda address: (address, [], [address])  # type: ignore[assignment]
    own = local_addresses()
    devices: dict[str, Any] = {}
    commands: asyncio.Queue[str] = asyncio.Queue()
    reader = asyncio.create_task(_read_commands(commands))
    discovery = await pyquickshare.discover_services()

    async def collect() -> None:
        while True:
            device = await discovery.__anext__()
            info = describe(device.service_info)
            if info is None:
                continue
            addresses = {socket.inet_ntoa(a) for a in device.service_info.addresses}
            if addresses & own:
                continue
            # A phone often registers several services; list it once, keeping the newest record.
            key = f"{info[0]}|{','.join(sorted(addresses))}"
            if key not in devices:
                emit(event="device", id=key, name=info[0], kind=info[1])
            devices[key] = device

    collector = asyncio.create_task(collect())
    code = 0
    try:
        try:
            target = await asyncio.wait_for(commands.get(), DISCOVERY_SECONDS)
        except asyncio.TimeoutError:
            emit(event="error", message="No device was chosen in time.")
            return 1
        if target not in devices:
            emit(event="error", message="That device is no longer available.")
            return 1
        collector.cancel()
        capture = _ErrorCapture()
        logging.getLogger("pyquickshare").addHandler(capture)
        for path in files:
            emit(event="sending", file=path.name)
            capture.messages.clear()
            try:
                await pyquickshare.send_to(devices[target], file=str(path))
            except Exception as error:
                emit(event="error", message=f"{path.name}: {error}")
                code = 1
                continue
            if capture.messages:
                emit(event="error", message=f"{path.name}: {capture.messages[-1]}")
                code = 1
            else:
                emit(event="done", file=path.name)
    finally:
        reader.cancel()
        collector.cancel()
        emit(event="finished")
    return code


def main() -> None:
    files = [Path(arg).expanduser() for arg in sys.argv[1:]]
    bad = [f for f in files if not f.is_file()]
    if not files or bad:
        emit(event="error", message="Not a readable file: " + (str(bad[0]) if bad else "no files given"))
        sys.exit(2)
    try:
        import pyquickshare  # noqa: F401
    except ImportError:
        emit(event="error", message="pyquickshare is not installed. Start the Quick Share tray once to install it.")
        sys.exit(2)
    sys.exit(asyncio.run(run(files)))


if __name__ == "__main__":
    main()
