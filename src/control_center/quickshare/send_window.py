"""GTK 4 window for sending files to nearby Quick Share devices.

The protocol runs in ``sender.py`` inside the private virtualenv created by the
tray launcher; this window only talks to it over a JSON-lines pipe.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

PKG_PARENT = Path(__file__).resolve().parents[2]
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
VENV_PYTHON = DATA_HOME / "tuxcontrol" / "venv" / "bin" / "python"
ICONS = {"phone": "phone-symbolic", "tablet": "tablet-symbolic", "laptop": "computer-symbolic"}


class SendWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application, files: list[Path]) -> None:
        super().__init__(application=application, title="Send with Quick Share")
        self.set_default_size(460, 520)
        self.files = files
        self.process: subprocess.Popen | None = None
        self.sending = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        self.set_child(box)

        title = Gtk.Label(label="Send with Quick Share", xalign=0)
        title.add_css_class("title-2")
        box.append(title)
        self.files_label = Gtk.Label(xalign=0, wrap=True)
        box.append(self.files_label)
        pick = Gtk.Button(label="Choose files…", halign=Gtk.Align.START)
        pick.connect("clicked", self.choose_files)
        box.append(pick)

        hint = Gtk.Label(
            label="On the phone open Quick Share, unlock the screen and set it to receive from Everyone. "
            "Nearby devices appear below.",
            xalign=0, wrap=True,
        )
        hint.add_css_class("dim-label")
        box.append(hint)

        self.devices = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.devices.add_css_class("boxed-list")
        self.placeholder = Gtk.Label(label="Searching for nearby devices…", margin_top=16, margin_bottom=16)
        self.devices.set_placeholder(self.placeholder)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self.devices)
        box.append(scroller)

        self.status = Gtk.Label(label="", xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        box.append(self.status)
        self.close_button = Gtk.Button(label="Close", halign=Gtk.Align.END)
        self.close_button.connect("clicked", lambda *_: self.close())
        box.append(self.close_button)

        self.connect("close-request", self.on_close)
        self.update_files_label()
        if files:
            self.start_worker()

    def update_files_label(self) -> None:
        if not self.files:
            self.files_label.set_text("No files selected.")
        elif len(self.files) == 1:
            self.files_label.set_text(self.files[0].name)
        else:
            self.files_label.set_text(f"{len(self.files)} files: " + ", ".join(f.name for f in self.files[:3]) + ("…" if len(self.files) > 3 else ""))

    def choose_files(self, _button: Gtk.Button) -> None:
        if self.sending:
            return
        dialog = Gtk.FileDialog(title="Choose files to send")

        def done(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                chosen = source.open_multiple_finish(result)
            except GLib.Error:
                return
            paths = [Path(chosen.get_item(i).get_path()) for i in range(chosen.get_n_items())]
            if paths:
                self.stop_worker()
                self.clear_devices()
                self.files = paths
                self.update_files_label()
                self.start_worker()

        dialog.open_multiple(self, None, done)

    def clear_devices(self) -> None:
        while (row := self.devices.get_first_child()) is not None:
            self.devices.remove(row)

    def start_worker(self) -> None:
        if not VENV_PYTHON.is_file():
            self.status.set_text("Quick Share components are not installed yet. Start the Quick Share tray once to install them.")
            return
        env = {**os.environ, "PYTHONPATH": str(PKG_PARENT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")}
        self.process = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "control_center.quickshare.sender", *map(str, self.files)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env,
        )
        self.status.set_text("Looking for devices…")
        threading.Thread(target=self.read_events, args=(self.process,), daemon=True).start()

    def stop_worker(self) -> None:
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()

    def read_events(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            GLib.idle_add(self.handle_event, process, event)
        process.wait()
        GLib.idle_add(self.worker_exited, process)

    def handle_event(self, process: subprocess.Popen, event: dict) -> bool:
        if process is not self.process:
            return GLib.SOURCE_REMOVE
        kind = event.get("event")
        if kind == "device":
            self.add_device(event["id"], event["name"], event.get("kind", ""))
        elif kind == "sending":
            self.status.set_text(f"Sending {event['file']}…")
        elif kind == "done":
            self.status.set_text(f"Sent {event['file']}. Accept it on the phone if asked.")
        elif kind == "error":
            self.status.set_text(event.get("message", "Sending failed."))
        return GLib.SOURCE_REMOVE

    def worker_exited(self, process: subprocess.Popen) -> bool:
        if process is self.process:
            self.sending = False
            self.process = None
            self.devices.set_sensitive(True)
            if process.returncode == 0:
                self.status.set_text("All files were sent.")
            elif not self.status.get_text():
                self.status.set_text("Quick Share stopped unexpectedly.")
        return GLib.SOURCE_REMOVE

    def add_device(self, device_id: str, name: str, kind: str) -> None:
        self.placeholder.set_text("")
        row = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
        row.append(Gtk.Image.new_from_icon_name(ICONS.get(kind, "network-wireless-symbolic")))
        label = Gtk.Label(label=name, xalign=0, hexpand=True)
        label.set_ellipsize(3)
        row.append(label)
        send = Gtk.Button(label="Send")
        send.add_css_class("suggested-action")
        send.connect("clicked", lambda *_: self.send_to(device_id, name))
        row.append(send)
        self.devices.append(row)

    def send_to(self, device_id: str, name: str) -> None:
        process = self.process
        if not process or self.sending or process.stdin is None:
            return
        self.sending = True
        self.devices.set_sensitive(False)
        self.status.set_text(f"Connecting to {name}…")
        try:
            process.stdin.write(json.dumps({"send": device_id}) + "\n")
            process.stdin.flush()
        except OSError:
            self.status.set_text("Quick Share stopped unexpectedly.")

    def on_close(self, *_args) -> bool:
        self.stop_worker()
        return False


def main(argv: list[str] | None = None) -> int:
    files = [Path(a).expanduser().resolve() for a in (sys.argv[1:] if argv is None else argv)]
    files = [f for f in files if f.is_file()]
    app = Gtk.Application(application_id="org.tuxcontrol.QuickShareSend", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda application: SendWindow(application, files).present())
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
