"""GTK 4 settings window for Quick Share."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from .config import AUTO_DISABLE_CHOICES, VISIBILITIES, load_config, save_config

AUTO_DISABLE_LABELS = ("Never", "5 minutes", "10 minutes", "30 minutes", "1 hour")
VISIBILITY_LABELS = (
    "Nearby devices on my network",
    "Everyone",
    "Closed (not receiving)",
)


def _row(box: Gtk.Box, title: str, widget: Gtk.Widget, hint: str = "") -> None:
    label = Gtk.Label(label=title, xalign=0)
    label.add_css_class("heading")
    box.append(label)
    box.append(widget)
    if hint:
        note = Gtk.Label(label=hint, xalign=0, wrap=True)
        note.add_css_class("dim-label")
        box.append(note)


def build_form(parent: Gtk.Window | None = None) -> Gtk.Box:
    """Build the settings form; reused by the standalone window and the main app."""
    cfg = load_config()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(20)

    visibility = Gtk.DropDown.new_from_strings(list(VISIBILITY_LABELS))
    visibility.set_selected(VISIBILITIES.index(cfg["visibility"]))
    _row(box, "Visibility", visibility)

    name = Gtk.Entry(text=str(cfg["device_name"]), max_length=64)
    _row(box, "Device name", name, "Shown to nearby Android devices.")

    folder = Gtk.Entry(text=str(cfg["download_dir"]), hexpand=True)
    choose = Gtk.Button(label="Browse…")
    folder_line = Gtk.Box(spacing=6)
    folder_line.append(folder)
    folder_line.append(choose)
    _row(box, "Save received files to", folder_line)

    def browse(_button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Choose download folder")

        def done(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                selected = source.select_folder_finish(result)
            except Exception:
                return
            if selected and selected.get_path():
                folder.set_text(selected.get_path())

        dialog.select_folder(parent or choose.get_root(), None, done)

    choose.connect("clicked", browse)

    timeout = Gtk.DropDown.new_from_strings(list(AUTO_DISABLE_LABELS))
    timeout.set_selected(AUTO_DISABLE_CHOICES.index(int(cfg["auto_disable_minutes"])))
    _row(box, "Stop receiving automatically after", timeout)

    ask = Gtk.Switch(active=bool(cfg["ask_before_accept"]), halign=Gtk.Align.START)
    _row(box, "Ask before accepting a transfer", ask, "Recommended. Without it, anyone nearby can send you files.")

    status = Gtk.Label(
        label="Changes apply to the running Quick Share tray within a few seconds.", xalign=0, wrap=True
    )
    status.add_css_class("dim-label")
    box.append(status)

    def save(_button: Gtk.Button) -> None:
        save_config({
            "device_name": name.get_text(),
            "visibility": VISIBILITIES[visibility.get_selected()],
            "auto_disable_minutes": AUTO_DISABLE_CHOICES[timeout.get_selected()],
            "download_dir": folder.get_text(),
            "ask_before_accept": ask.get_active(),
        })
        status.set_text("Settings saved.")

    button = Gtk.Button(label="Save", halign=Gtk.Align.END)
    button.add_css_class("suggested-action")
    button.connect("clicked", save)
    box.append(button)
    return box


def main() -> int:
    app = Gtk.Application(application_id="org.tuxcontrol.QuickShareSettings")

    def activate(application: Gtk.Application) -> None:
        win = Gtk.ApplicationWindow(application=application, title="Quick Share Settings")
        win.set_default_size(460, 520)
        win.set_child(build_form(win))
        win.present()

    app.connect("activate", activate)
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
