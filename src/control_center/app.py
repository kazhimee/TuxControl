"""GTK 4 user interface for TuxControl."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, Gtk

from control_center import backends, themes


class ControlCenter(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.tuxcontrol.App")
        self.connect("activate", self.on_activate)
        self.window: Gtk.ApplicationWindow | None = None
        self.status_label: Gtk.Label | None = None
        self.app_list: Gtk.ListBox | None = None
        self.service_list: Gtk.ListBox | None = None
        self.service_scope_selector: Gtk.DropDown | None = None
        self.service_scope = "user"
        self.theme_list: Gtk.ListBox | None = None
        self.extension_list: Gtk.ListBox | None = None
        self.extension_catalog_list: Gtk.ListBox | None = None
        self.extension_search_entry: Gtk.SearchEntry | None = None
        self.theme_store_window: Gtk.Window | None = None
        self.extension_store_window: Gtk.Window | None = None
        self.theme_store_stack: Gtk.Stack | None = None
        self.extension_store_stack: Gtk.Stack | None = None
        self.theme_store_source: Gtk.DropDown | None = None
        self.theme_store_category: Gtk.DropDown | None = None
        self.theme_store_search: Gtk.SearchEntry | None = None
        self.theme_store_results: Gtk.ListBox | None = None
        self.extension_uuid_entry: Gtk.Entry | None = None
        self.theme_search_timeout = 0
        self.extension_search_timeout = 0
        self.theme_search_serial = 0
        self.extension_search_serial = 0
        self.app_search: Gtk.SearchEntry | None = None
        self.apps: list[Gio.AppInfo] = []
        self.flatpak_ids: set[str] = set()

    def on_activate(self, _application: Gtk.Application) -> None:
        if self.window:
            self.window.present()
            return

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("TuxControl")
        self.window.set_default_size(980, 720)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.set_child(root)

        header = Gtk.HeaderBar()
        self.window.set_titlebar(header)
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_transition_duration(140)
        switcher = Gtk.StackSwitcher(stack=stack)
        header.set_title_widget(switcher)
        root.append(stack)

        for name, title, builder in (
            ("overview", "Overview", self.build_overview),
            ("applications", "Applications", self.build_applications),
            ("services", "Services", self.build_services),
            ("themes", "Themes", self.build_themes),
            ("extensions", "Extensions", self.build_extensions),
        ):
            stack.add_titled(builder(), name, title)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(6)
        footer.set_margin_bottom(6)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        self.status_label.set_ellipsize(3)
        footer.append(self.status_label)
        root.append(footer)

        self.window.present()
        self.refresh_apps()
        self.refresh_services()
        self.refresh_themes()
        self.refresh_extensions()

    def page(self, title: str, description: str) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(22)
        page.set_margin_bottom(18)
        page.set_margin_start(22)
        page.set_margin_end(22)
        heading = Gtk.Label(label=title)
        heading.add_css_class("title-1")
        heading.set_xalign(0)
        page.append(heading)
        summary = Gtk.Label(label=description)
        summary.set_wrap(True)
        summary.set_xalign(0)
        summary.add_css_class("dim-label")
        page.append(summary)
        return page

    def list_scroller(self, listing: Gtk.ListBox) -> Gtk.ScrolledWindow:
        listing.set_selection_mode(Gtk.SelectionMode.NONE)
        listing.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(listing)
        return scroll

    @staticmethod
    def themed_icon(name: str, size: int = 32) -> Gtk.Image:
        image = Gtk.Image.new_from_icon_name(name)
        image.set_pixel_size(size)
        return image

    @staticmethod
    def theme_icon_name(category: str) -> str:
        normalized = category.casefold()
        if "icon" in normalized or "cursor" in normalized:
            return "preferences-desktop-icons"
        if "plasma" in normalized or "kde" in normalized:
            return "preferences-desktop-theme-global"
        return "preferences-desktop-theme"

    def show_store_details(
        self,
        stack: Gtk.Stack | None,
        title: str,
        icon_name: str,
        fields: list[tuple[str, str]],
    ) -> None:
        if not stack:
            return
        old_details = stack.get_child_by_name("details")
        if old_details:
            stack.remove(old_details)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_margin_top(18)
        page.set_margin_bottom(18)
        page.set_margin_start(18)
        page.set_margin_end(18)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        back = Gtk.Button(label="← Back to results")
        back.connect("clicked", lambda *_: stack.set_visible_child_name("catalog"))
        toolbar.append(back)
        heading = Gtk.Label(label="Details")
        heading.add_css_class("title-2")
        heading.set_xalign(0)
        heading.set_hexpand(True)
        toolbar.append(heading)
        page.append(toolbar)

        identity = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        identity.set_margin_top(10)
        identity.append(self.themed_icon(icon_name, 56))
        item_title = Gtk.Label(label=title)
        item_title.add_css_class("title-1")
        item_title.set_xalign(0)
        item_title.set_wrap(True)
        item_title.set_hexpand(True)
        identity.append(item_title)
        page.append(identity)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for key, value in fields:
            if not value:
                continue
            field_title = Gtk.Label(label=key)
            field_title.add_css_class("heading")
            field_title.set_xalign(0)
            body.append(field_title)
            field_value = Gtk.Label(label=value)
            field_value.set_xalign(0)
            field_value.set_wrap(True)
            body.append(field_value)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(body)
        page.append(scroller)
        stack.add_named(page, "details")
        stack.set_visible_child_name("details")

    def show_theme_details(self, item: themes.StoreTheme) -> None:
        self.show_store_details(
            self.theme_store_stack,
            item.name,
            self.theme_icon_name(item.category),
            [
                ("Category", item.category),
                ("Author", item.author),
                ("Version", item.version),
                ("Downloads", str(item.downloads)),
                ("Summary", item.summary),
                ("Description", item.description),
                ("Package file", item.download_name),
                ("Store page", item.detail_url),
            ],
        )

    def show_extension_details(self, item: backends.ExtensionCatalogItem) -> None:
        self.show_store_details(
            self.extension_store_stack,
            item.name,
            "application-x-addon",
            [
                ("Creator", item.creator),
                ("Extension UUID", item.uuid),
                ("Downloads", str(item.downloads)),
                ("Description", item.description),
                ("GNOME Extensions page", item.details_url),
            ],
        )

    def build_overview(self) -> Gtk.Widget:
        page = self.page(
            "TuxControl",
            "A focused control panel for applications, user and system services, themes, and GNOME Shell extensions.",
        )
        support_notice = Gtk.Label(
            label="GNOME is currently supported. KDE Plasma support is not available yet."
        )
        support_notice.set_xalign(0)
        support_notice.add_css_class("warning")
        page.append(support_notice)
        info = backends.detect_desktop()
        manager = backends.available_package_manager() or "not detected"
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.set_margin_top(12)
        card.set_margin_bottom(6)
        card.set_margin_start(6)
        card.set_margin_end(6)
        for label, value in (
            ("Desktop environment", info.desktop),
            ("Distribution", info.distribution),
            ("System package manager", manager),
        ):
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
            key = Gtk.Label(label=label)
            key.set_xalign(0)
            key.set_hexpand(True)
            value_label = Gtk.Label(label=value)
            value_label.set_xalign(1)
            line.append(key)
            line.append(value_label)
            card.append(line)
        page.append(card)
        note = Gtk.Label(
            label=(
                "System package changes request authorization through PolicyKit (pkexec). "
                "System-wide service changes request administrator authorization. Review each confirmation "
                "before applying a change."
            )
        )
        note.set_wrap(True)
        note.set_xalign(0)
        note.add_css_class("dim-label")
        page.append(note)
        return page

    def build_applications(self) -> Gtk.Widget:
        page = self.page(
            "Applications",
            "Launch installed desktop applications, remove supported packages, or install an application by package name or Flatpak ID.",
        )
        self.app_search = Gtk.SearchEntry()
        self.app_search.set_placeholder_text("Filter installed applications")
        self.app_search.connect("search-changed", lambda *_: self.populate_apps())
        page.append(self.app_search)

        package_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.package_entry = Gtk.Entry()
        self.package_entry.set_hexpand(True)
        self.package_entry.set_placeholder_text("Package name (system package manager)")
        install_package = Gtk.Button(label="Install package")
        install_package.connect("clicked", lambda *_: self.install_package())
        package_box.append(self.package_entry)
        package_box.append(install_package)
        page.append(package_box)

        flatpak_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.flatpak_entry = Gtk.Entry()
        self.flatpak_entry.set_hexpand(True)
        self.flatpak_entry.set_placeholder_text("Flatpak application ID, e.g. org.gnome.Calculator")
        install_flatpak = Gtk.Button(label="Install from Flathub")
        install_flatpak.connect("clicked", lambda *_: self.install_flatpak())
        flatpak_box.append(self.flatpak_entry)
        flatpak_box.append(install_flatpak)
        page.append(flatpak_box)

        self.app_list = Gtk.ListBox()
        page.append(self.list_scroller(self.app_list))
        return page

    def build_services(self) -> Gtk.Widget:
        page = self.page(
            "Services",
            "Manage services in your user session or system-wide. System-wide changes request administrator authorization through PolicyKit.",
        )
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        model = Gtk.StringList.new(["User session", "System-wide"])
        self.service_scope_selector = Gtk.DropDown(model=model)
        self.service_scope_selector.connect("notify::selected", self.on_service_scope_changed)
        controls.append(self.service_scope_selector)
        refresh = Gtk.Button(label="Refresh services")
        refresh.connect("clicked", lambda *_: self.refresh_services())
        controls.append(refresh)
        page.append(controls)
        self.service_list = Gtk.ListBox()
        page.append(self.list_scroller(self.service_list))
        return page

    def build_themes(self) -> Gtk.Widget:
        page = self.page(
            "Themes",
            "Browse GNOME-Look.org and Pling, install GTK, icon, or Plasma themes directly, see active themes, apply them, or remove user-installed themes.",
        )
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        store = Gtk.Button(label="Browse GNOME-Look / Pling…")
        store.connect("clicked", lambda *_: self.open_theme_store())
        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh_themes())
        controls.append(store)
        controls.append(refresh)
        page.append(controls)
        self.theme_list = Gtk.ListBox()
        page.append(self.list_scroller(self.theme_list))
        return page

    def build_extensions(self) -> Gtk.Widget:
        page = self.page(
            "GNOME extensions",
            "See installed and active GNOME Shell extensions, or browse compatible extensions.gnome.org releases in a separate window.",
        )
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        browse = Gtk.Button(label="Browse and install extensions…")
        browse.connect("clicked", lambda *_: self.open_extension_store())
        controls.append(browse)
        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh_extensions())
        controls.append(refresh)
        page.append(controls)
        installed_title = Gtk.Label(label="Installed extensions")
        installed_title.set_xalign(0)
        installed_title.add_css_class("title-3")
        page.append(installed_title)

        self.extension_list = Gtk.ListBox()
        page.append(self.list_scroller(self.extension_list))
        return page

    def open_theme_store(self) -> None:
        if self.theme_store_window:
            self.theme_store_window.present()
            return
        popup = Gtk.Window(application=self, title="TuxControl — Theme stores")
        popup.set_transient_for(self.window)
        popup.set_modal(False)
        popup.set_default_size(820, 620)
        popup.connect("close-request", lambda *_: self.clear_theme_store_window())

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(18)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)
        heading = Gtk.Label(label="Browse themes")
        heading.add_css_class("title-1")
        heading.set_xalign(0)
        content.append(heading)
        summary = Gtk.Label(
            label="Search the public OCS catalog. TuxControl downloads and installs compatible theme archives into your user theme folder."
        )
        summary.set_wrap(True)
        summary.set_xalign(0)
        summary.add_css_class("dim-label")
        content.append(summary)

        selectors = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.theme_store_category = Gtk.DropDown(
            model=Gtk.StringList.new(
                ["Any theme", "GTK / GNOME", "Icons / cursors", "KDE Plasma"]
            )
        )
        self.theme_store_category.connect(
            "notify::selected", lambda *_: self.schedule_theme_search()
        )
        selectors.append(self.theme_store_category)
        self.theme_store_source = Gtk.DropDown(
            model=Gtk.StringList.new(["GNOME-Look.org", "Pling"])
        )
        self.theme_store_source.connect(
            "notify::selected", lambda *_: self.schedule_theme_search()
        )
        selectors.append(self.theme_store_source)
        self.theme_store_search = Gtk.SearchEntry()
        self.theme_store_search.set_hexpand(True)
        self.theme_store_search.set_placeholder_text("Search themes")
        self.theme_store_search.connect(
            "search-changed", lambda *_: self.schedule_theme_search()
        )
        selectors.append(self.theme_store_search)
        search = Gtk.Button(label="Search")
        search.connect("clicked", lambda *_: self.search_theme_store())
        selectors.append(search)
        content.append(selectors)

        self.theme_store_results = Gtk.ListBox()
        self.theme_store_results.set_selection_mode(Gtk.SelectionMode.NONE)
        self.theme_store_results.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.theme_store_results)
        content.append(scroll)
        self.theme_store_window = popup
        stack = Gtk.Stack()
        stack.add_named(content, "catalog")
        popup.set_child(stack)
        self.theme_store_stack = stack
        popup.present()
        GLib.idle_add(self.search_theme_store)

    def clear_theme_store_window(self) -> bool:
        if self.theme_search_timeout:
            GLib.source_remove(self.theme_search_timeout)
            self.theme_search_timeout = 0
        self.theme_search_serial += 1
        self.theme_store_window = None
        self.theme_store_source = None
        self.theme_store_category = None
        self.theme_store_search = None
        self.theme_store_results = None
        self.theme_store_stack = None
        return False

    def schedule_theme_search(self) -> None:
        self.theme_search_serial += 1
        if self.theme_search_timeout:
            GLib.source_remove(self.theme_search_timeout)
        self.theme_search_timeout = GLib.timeout_add(350, self.run_scheduled_theme_search)

    def run_scheduled_theme_search(self) -> bool:
        self.theme_search_timeout = 0
        self.search_theme_store()
        return GLib.SOURCE_REMOVE

    def search_theme_store(self) -> None:
        if not self.theme_store_results or not self.theme_store_source:
            return
        query = self.theme_store_search.get_text() if self.theme_store_search else ""
        source = "gnome-look" if self.theme_store_source.get_selected() == 0 else "pling"
        serial = self.theme_search_serial = self.theme_search_serial + 1
        self.clear_list(self.theme_store_results)

        def render(items: list[themes.StoreTheme]) -> None:
            if not self.theme_store_results or serial != self.theme_search_serial:
                return
            selected_category = (
                self.theme_store_category.get_selected()
                if self.theme_store_category
                else 0
            )
            keywords = {
                1: ("gtk", "gnome", "gtk3", "gtk4"),
                2: ("icon", "cursor", "cursors"),
                3: ("plasma", "kde", "look and feel", "global theme"),
            }.get(selected_category, ())
            if keywords:
                items = [
                    item
                    for item in items
                    if any(
                        word in f"{item.name} {item.category}".casefold()
                        for word in keywords
                    )
                ]
            self.clear_list(self.theme_store_results)
            if not items:
                self.theme_store_results.append(
                    self.info_row("No matching themes found. Try another query or category.")
                )
                return
            for item in items:
                row = Gtk.ListBoxRow()
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                line.set_margin_top(8)
                line.set_margin_bottom(8)
                line.set_margin_start(10)
                line.set_margin_end(10)
                details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                details.set_hexpand(True)
                theme_icon = Gtk.Image.new_from_icon_name(
                    self.theme_icon_name(item.category)
                )
                theme_icon.set_pixel_size(36)
                line.append(theme_icon)
                title = Gtk.Label(label=item.name)
                title.set_xalign(0)
                title.set_ellipsize(3)
                title.add_css_class("heading")
                category = Gtk.Label(label=f"{item.category}  ·  {item.summary}")
                category.set_xalign(0)
                category.set_wrap(True)
                category.set_ellipsize(3)
                category.add_css_class("dim-label")
                details.append(title)
                details.append(category)
                line.append(details)
                details_button = Gtk.Button(label="Details")
                details_button.connect(
                    "clicked",
                    lambda _button, selected=item: self.show_theme_details(selected),
                )
                line.append(details_button)
                install = Gtk.Button(label="Install")
                install.add_css_class("suggested-action")
                install.connect(
                    "clicked",
                    lambda _button, selected=item: self.install_store_theme(selected),
                )
                line.append(install)
                row.set_child(line)
                self.theme_store_results.append(row)

        self.run_worker(
            f"Searching {source} for “{query}”",
            lambda: themes.search_store_themes(source, query),
            render,
        )

    def install_store_theme(self, item: themes.StoreTheme) -> None:
        self.confirm(
            f"Download and install “{item.name}” from the theme store?",
            lambda: self.run_worker(
                f"Installing theme {item.name}",
                lambda: themes.download_and_install_store_theme(item),
                lambda _result: self.refresh_themes(),
            ),
        )

    def open_extension_store(self) -> None:
        if backends.detect_desktop().desktop != "GNOME":
            self.show_error("GNOME Shell extensions are only available in a GNOME session.")
            return
        if self.extension_store_window:
            self.extension_store_window.present()
            return
        popup = Gtk.Window(application=self, title="TuxControl — GNOME Extensions")
        popup.set_transient_for(self.window)
        popup.set_modal(False)
        popup.set_default_size(760, 600)
        popup.connect("close-request", lambda *_: self.clear_extension_store_window())

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_top(18)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)
        heading = Gtk.Label(label="GNOME extension catalog")
        heading.add_css_class("title-1")
        heading.set_xalign(0)
        content.append(heading)
        search_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.extension_search_entry = Gtk.SearchEntry()
        self.extension_search_entry.set_hexpand(True)
        self.extension_search_entry.set_placeholder_text("Search compatible GNOME extensions")
        self.extension_search_entry.connect(
            "search-changed", lambda *_: self.schedule_extension_search()
        )
        search_line.append(self.extension_search_entry)
        search = Gtk.Button(label="Search")
        search.connect("clicked", lambda *_: self.search_extension_catalog())
        search_line.append(search)
        content.append(search_line)
        self.extension_catalog_list = Gtk.ListBox()
        self.extension_catalog_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.extension_catalog_list.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(self.extension_catalog_list)
        content.append(scroll)
        manual_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.extension_uuid_entry = Gtk.Entry()
        self.extension_uuid_entry.set_hexpand(True)
        self.extension_uuid_entry.set_placeholder_text("Or install by extension UUID")
        manual_line.append(self.extension_uuid_entry)
        install = Gtk.Button(label="Install UUID")
        install.connect("clicked", lambda *_: self.install_extension())
        manual_line.append(install)
        content.append(manual_line)
        self.extension_store_window = popup
        stack = Gtk.Stack()
        stack.add_named(content, "catalog")
        popup.set_child(stack)
        self.extension_store_stack = stack
        popup.present()
        GLib.idle_add(self.search_extension_catalog)

    def clear_extension_store_window(self) -> bool:
        if self.extension_search_timeout:
            GLib.source_remove(self.extension_search_timeout)
            self.extension_search_timeout = 0
        self.extension_search_serial += 1
        self.extension_store_window = None
        self.extension_search_entry = None
        self.extension_catalog_list = None
        self.extension_uuid_entry = None
        self.extension_store_stack = None
        return False

    def schedule_extension_search(self) -> None:
        self.extension_search_serial += 1
        if self.extension_search_timeout:
            GLib.source_remove(self.extension_search_timeout)
        self.extension_search_timeout = GLib.timeout_add(
            350, self.run_scheduled_extension_search
        )

    def run_scheduled_extension_search(self) -> bool:
        self.extension_search_timeout = 0
        self.search_extension_catalog()
        return GLib.SOURCE_REMOVE

    def set_status(self, text: str) -> None:
        if self.status_label:
            self.status_label.set_text(text)

    def show_error(self, message: str) -> None:
        self.set_status(message)
        if not self.window:
            return
        popup = Gtk.Window(application=self, title="TuxControl — Operation failed")
        popup.set_transient_for(self.window)
        popup.set_modal(True)
        popup.set_default_size(440, 180)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(20)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)
        title = Gtk.Label(label="Operation failed")
        title.add_css_class("title-2")
        title.set_xalign(0)
        content.append(title)
        detail = Gtk.Label(label=message)
        detail.set_wrap(True)
        detail.set_xalign(0)
        content.append(detail)
        close = Gtk.Button(label="Close")
        close.set_halign(Gtk.Align.END)
        close.connect("clicked", lambda *_: popup.destroy())
        content.append(close)
        popup.set_child(content)
        popup.present()

    def confirm(self, message: str, callback) -> None:
        assert self.window is not None
        popup = Gtk.Window(application=self, title="TuxControl — Confirm change")
        popup.set_transient_for(self.window)
        popup.set_modal(True)
        popup.set_default_size(460, 200)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(20)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)
        title = Gtk.Label(label="Confirm change")
        title.add_css_class("title-2")
        title.set_xalign(0)
        content.append(title)
        detail = Gtk.Label(label=message)
        detail.set_wrap(True)
        detail.set_xalign(0)
        content.append(detail)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: popup.destroy())
        continue_button = Gtk.Button(label="Continue")
        continue_button.add_css_class("suggested-action")

        def accept(*_args) -> None:
            popup.destroy()
            callback()

        continue_button.connect("clicked", accept)
        buttons.append(cancel)
        buttons.append(continue_button)
        content.append(buttons)
        popup.set_child(content)
        popup.present()

    def run_worker(self, description: str, operation, success=None) -> None:
        self.set_status(description)

        def work() -> None:
            try:
                result = operation()
            except Exception as error:
                GLib.idle_add(self.show_error, str(error))
                return

            def complete() -> bool:
                self.set_status(f"{description} — complete")
                if success:
                    success(result)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(complete)

        threading.Thread(target=work, daemon=True).start()

    def refresh_apps(self) -> None:
        self.apps = Gio.AppInfo.get_all()
        try:
            self.flatpak_ids = {app_id for app_id, _name in backends.installed_flatpaks()}
        except Exception as error:
            self.show_error(str(error))
            self.flatpak_ids = set()
        self.populate_apps()

    def populate_apps(self) -> None:
        if not self.app_list:
            return
        child = self.app_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.app_list.remove(child)
            child = next_child
        query = self.app_search.get_text().casefold() if self.app_search else ""
        app_infos = sorted(
            (app for app in self.apps if app.get_name()),
            key=lambda app: (app.get_name() or "").casefold(),
        )
        added = 0
        for app in app_infos:
            name = app.get_name() or "Unnamed application"
            app_id = app.get_id() or ""
            if query and query not in name.casefold() and query not in app_id.casefold():
                continue
            row = Gtk.ListBoxRow()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            line.set_margin_top(7)
            line.set_margin_bottom(7)
            line.set_margin_start(9)
            line.set_margin_end(9)
            label = Gtk.Label(label=name)
            label.set_xalign(0)
            label.set_hexpand(True)
            label.set_ellipsize(3)
            icon = app.get_icon()
            if icon:
                app_icon = Gtk.Image.new_from_gicon(icon)
                app_icon.set_pixel_size(36)
                line.append(app_icon)
            else:
                line.append(self.themed_icon("application-x-executable", 36))
            line.append(label)
            launch = Gtk.Button(label="Launch")
            launch.connect("clicked", lambda _button, selected=app: self.launch_app(selected))
            line.append(launch)
            is_flatpak = app_id.removesuffix(".desktop") in self.flatpak_ids
            remove = Gtk.Button(label="Remove")
            remove.set_sensitive(is_flatpak or bool(backends.available_package_manager()))
            remove.set_tooltip_text(
                "Remove using Flatpak or the detected system package owner."
                if is_flatpak
                else "Package ownership is checked when you select Remove."
            )
            remove.connect(
                "clicked",
                lambda _button, selected=app, flatpak=is_flatpak: self.remove_app(selected, flatpak),
            )
            line.append(remove)
            row.set_child(line)
            self.app_list.append(row)
            added += 1
        if added == 0:
            self.app_list.append(self.info_row("No matching applications found."))

    def launch_app(self, app: Gio.AppInfo) -> None:
        try:
            app.launch([], None)
        except GLib.Error as error:
            self.show_error(str(error))

    def remove_app(self, app: Gio.AppInfo, is_flatpak: bool) -> None:
        app_id = (app.get_id() or "").removesuffix(".desktop")
        package = None if is_flatpak else backends.desktop_app_package(app.get_filename() or "")
        if is_flatpak:
            self.confirm(f"Uninstall Flatpak application {app_id} from your user account?", lambda: self.run_worker(
                f"Removing {app_id}", lambda: backends.remove_flatpak(app_id), lambda _result: self.refresh_apps()
            ))
        elif package:
            self.confirm(f"Remove system package “{package}”? PolicyKit will request administrator authorization.", lambda: self.run_worker(
                f"Removing {package}", lambda: backends.change_system_package(package, "remove"), lambda _result: self.refresh_apps()
            ))
        else:
            self.show_error("Could not identify the package that owns this application launcher.")

    def install_package(self) -> None:
        package = self.package_entry.get_text().strip()
        try:
            backends.validate_package_name(package)
        except ValueError as error:
            self.show_error(str(error))
            return
        self.confirm(f"Install system package “{package}”? PolicyKit will request administrator authorization.", lambda: self.run_worker(
            f"Installing {package}", lambda: backends.change_system_package(package, "install"), lambda _result: self.refresh_apps()
        ))

    def install_flatpak(self) -> None:
        app_id = self.flatpak_entry.get_text().strip()
        try:
            backends.validate_flatpak_app_id(app_id)
        except ValueError as error:
            self.show_error(str(error))
            return
        self.confirm(f"Install Flatpak application “{app_id}” from Flathub into your user account?", lambda: self.run_worker(
            f"Installing {app_id}", lambda: backends.install_flatpak(app_id), lambda _result: self.refresh_apps()
        ))

    def refresh_services(self) -> None:
        if not self.service_list:
            return
        self.clear_list(self.service_list)
        try:
            services = (
                backends.list_system_services()
                if self.service_scope == "system"
                else backends.list_user_services()
            )
        except Exception as error:
            self.show_error(str(error))
            return
        if not services:
            self.service_list.append(self.info_row(f"No {self.service_scope} services found."))
            return
        for service in services:
            row = Gtk.ListBoxRow()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.set_margin_top(6)
            line.set_margin_bottom(6)
            line.set_margin_start(9)
            line.set_margin_end(9)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.set_hexpand(True)
            line.append(self.themed_icon(
                "preferences-system" if service.scope == "system" else "preferences-desktop-services",
                32,
            ))
            title = Gtk.Label(label=service.name)
            title.set_xalign(0)
            enablement = (
                "enabled"
                if service.enabled
                else "disabled"
                if service.enableable
                else "not configurable"
            )
            subtitle = Gtk.Label(label=f"{service.description} · {'active' if service.active else 'inactive'} · {enablement} · {service.scope}")
            subtitle.set_xalign(0)
            subtitle.set_ellipsize(3)
            subtitle.add_css_class("dim-label")
            text.append(title)
            text.append(subtitle)
            line.append(text)
            action = "stop" if service.active else "start"
            toggle = Gtk.Button(label=action.title())
            toggle.connect("clicked", lambda _button, item=service, act=action: self.change_service(item.name, act))
            line.append(toggle)
            enable_action = "disable" if service.enabled else "enable"
            enable = Gtk.Button(label=enable_action.title())
            enable.set_sensitive(service.enableable)
            if not service.enableable:
                enable.set_tooltip_text("This unit does not support enable/disable operations.")
            enable.connect("clicked", lambda _button, item=service, act=enable_action: self.change_service(item.name, act))
            line.append(enable)
            row.set_child(line)
            self.service_list.append(row)

    def change_service(self, name: str, action: str) -> None:
        scope = self.service_scope
        prompt = f"{action.title()} {scope} service “{name}”?"
        if scope == "system":
            prompt += " PolicyKit will request administrator authorization."
        self.confirm(prompt, lambda: self.run_worker(
            f"{action.title()} {name}",
            lambda: backends.manage_service(name, action, scope),
            lambda _result: self.refresh_services(),
        ))

    def on_service_scope_changed(self, selector: Gtk.DropDown, _property) -> None:
        self.service_scope = "system" if selector.get_selected() == 1 else "user"
        self.refresh_services()

    def refresh_themes(self) -> None:
        if not self.theme_list:
            return
        self.clear_list(self.theme_list)
        theme_items = themes.list_themes()
        active_themes = themes.active_theme_names(backends.detect_desktop().desktop)
        if not theme_items:
            self.theme_list.append(self.info_row("No themes were found in the standard theme folders."))
            return
        for item in theme_items:
            row = Gtk.ListBoxRow()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.set_margin_top(6)
            line.set_margin_bottom(6)
            line.set_margin_start(9)
            line.set_margin_end(9)
            active = (item.kind, item.name) in active_themes
            status = "ACTIVE" if active else "installed"
            label = Gtk.Label(label=f"{item.name}  ·  {item.kind}  ·  {status}  ·  {item.path}")
            label.set_xalign(0)
            label.set_hexpand(True)
            label.set_ellipsize(3)
            line.append(self.themed_icon(self.theme_icon_name(item.kind), 36))
            line.append(label)
            apply_label = {
                "plasma": "Apply Plasma theme",
                "gtk": "Apply GTK theme",
            }.get(item.kind, "Not applicable")
            apply = Gtk.Button(label=apply_label)
            apply.set_sensitive(item.kind in {"gtk", "plasma"} and item.path.exists())
            apply.connect("clicked", lambda _button, selected=item: self.apply_theme(selected))
            line.append(apply)
            remove = Gtk.Button(label="Remove")
            remove.set_sensitive(item.user_owned)
            remove.connect("clicked", lambda _button, selected=item.path: self.remove_theme(selected))
            line.append(remove)
            row.set_child(line)
            self.theme_list.append(row)

    def apply_theme(self, theme: themes.Theme) -> None:
        info = backends.detect_desktop()
        if theme.kind == "plasma" and info.desktop == "KDE Plasma":
            command = ["plasma-apply-desktoptheme", theme.name]
        elif theme.kind == "gtk" and info.desktop == "GNOME":
            command = ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", theme.name]
        elif theme.kind == "gtk" and info.desktop == "KDE Plasma":
            command = ["plasma-apply-gtktheme", theme.name]
        else:
            self.show_error("This theme type cannot be applied by the current desktop session.")
            return
        self.confirm(f"Apply theme “{theme.name}” for your desktop account?", lambda: self.run_worker(
            f"Applying theme {theme.name}", lambda: backends.run_command(command, timeout=60)
        ))

    def remove_theme(self, path: Path) -> None:
        self.confirm(f"Permanently remove user theme folder “{path.name}”?", lambda: self.run_worker(
            f"Removing theme {path.name}",
            lambda: themes.remove_user_theme(path),
            lambda _result: self.refresh_themes(),
        ))

    def refresh_extensions(self) -> None:
        if not self.extension_list:
            return
        self.clear_list(self.extension_list)
        if backends.detect_desktop().desktop != "GNOME":
            self.extension_list.append(self.info_row("GNOME Shell extensions are available only in a GNOME session."))
            return
        try:
            extensions = backends.list_gnome_extensions()
        except Exception as error:
            self.show_error(str(error))
            return
        if not extensions:
            self.extension_list.append(self.info_row("No GNOME Shell extensions are installed."))
            return
        for extension in extensions:
            row = Gtk.ListBoxRow()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.set_margin_top(6)
            line.set_margin_bottom(6)
            line.set_margin_start(9)
            line.set_margin_end(9)
            state = (
                "Active"
                if extension.active
                else "Enabled, not active"
                if extension.enabled
                else "Disabled"
            )
            label = Gtk.Label(label=f"{extension.name}  ·  {state}\n{extension.uuid}")
            label.set_xalign(0)
            label.set_hexpand(True)
            label.set_wrap(True)
            line.append(self.themed_icon("application-x-addon", 36))
            line.append(label)
            toggle = Gtk.Button(label="Turn off" if extension.enabled else "Turn on")
            toggle.connect(
                "clicked",
                lambda _button, item=extension, enabled=extension.enabled:
                self.toggle_extension(item.uuid, not enabled),
            )
            line.append(toggle)
            remove = Gtk.Button(label="Uninstall")
            remove.connect("clicked", lambda _button, item=extension.uuid: self.remove_extension(item))
            line.append(remove)
            row.set_child(line)
            self.extension_list.append(row)

    def search_extension_catalog(self) -> None:
        query = self.extension_search_entry.get_text() if self.extension_search_entry else ""
        listing = self.extension_catalog_list
        if not listing:
            return
        serial = self.extension_search_serial = self.extension_search_serial + 1
        self.clear_list(listing)
        if backends.detect_desktop().desktop != "GNOME":
            listing.append(
                self.info_row("The GNOME extension catalog is available only in a GNOME session.")
            )
            return

        def display(results: list[backends.ExtensionCatalogItem]) -> None:
            current_listing = self.extension_catalog_list
            if not current_listing or serial != self.extension_search_serial:
                return
            try:
                installed = {
                    extension.uuid for extension in backends.list_gnome_extensions()
                }
            except Exception as error:
                self.show_error(str(error))
                return
            self.clear_list(current_listing)
            visible = [item for item in results if item.uuid not in installed]
            if not visible:
                current_listing.append(
                    self.info_row("No new compatible extensions matched. Try a different search.")
                )
                return
            for item in visible:
                row = Gtk.ListBoxRow()
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                line.set_margin_top(6)
                line.set_margin_bottom(6)
                line.set_margin_start(9)
                line.set_margin_end(9)
                details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                details.set_hexpand(True)
                icon = Gtk.Image.new_from_icon_name("application-x-addon")
                icon.set_pixel_size(36)
                line.append(icon)
                title = Gtk.Label(label=item.name)
                title.set_xalign(0)
                title.set_ellipsize(3)
                description = Gtk.Label(label=item.description or item.uuid)
                description.set_xalign(0)
                description.set_wrap(True)
                description.set_ellipsize(3)
                description.add_css_class("dim-label")
                details.append(title)
                details.append(description)
                line.append(details)
                detail_button = Gtk.Button(label="Details")
                detail_button.connect(
                    "clicked",
                    lambda _button, selected=item: self.show_extension_details(selected),
                )
                line.append(detail_button)
                install = Gtk.Button(label="Install")
                install.connect(
                    "clicked",
                    lambda _button, selected=item: self.install_extension_by_uuid(
                        selected.uuid, selected.name
                    ),
                )
                line.append(install)
                row.set_child(line)
                current_listing.append(row)

        self.run_worker(
            f"{'Loading compatible extensions' if not query else f'Searching extensions for “{query}”'}",
            lambda: backends.search_gnome_extensions(query),
            display,
        )

    def toggle_extension(self, uuid: str, enabled: bool) -> None:
        action = "Enable" if enabled else "Disable"
        self.confirm(f"{action} GNOME Shell extension “{uuid}”?", lambda: self.run_worker(
            f"{action} extension", lambda: backends.set_gnome_extension(uuid, enabled),
            lambda _result: self.refresh_extensions(),
        ))

    def remove_extension(self, uuid: str) -> None:
        self.confirm(f"Uninstall GNOME Shell extension “{uuid}” from your account?", lambda: self.run_worker(
            f"Uninstalling extension {uuid}",
            lambda: backends.uninstall_gnome_extension(uuid),
            lambda _result: self.refresh_extensions(),
        ))

    def install_extension(self) -> None:
        uuid = self.extension_uuid_entry.get_text().strip() if self.extension_uuid_entry else ""
        try:
            backends.validate_extension_uuid(uuid)
        except ValueError as error:
            self.show_error(str(error))
            return
        self.install_extension_by_uuid(uuid, uuid)

    def install_extension_by_uuid(self, uuid: str, name: str) -> None:
        def installed(_result) -> None:
            self.refresh_extensions()
            if self.extension_search_entry:
                self.search_extension_catalog()

        self.confirm(
            f"Download and install GNOME extension “{name}” from extensions.gnome.org?",
            lambda: self.run_worker(
                f"Installing {name}",
                lambda: backends.install_gnome_extension(uuid),
                installed,
            ),
        )

    @staticmethod
    def clear_list(listing: Gtk.ListBox) -> None:
        child = listing.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            listing.remove(child)
            child = next_child

    @staticmethod
    def info_row(message: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=message)
        label.set_xalign(0)
        label.set_margin_top(12)
        label.set_margin_bottom(12)
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_wrap(True)
        row.set_child(label)
        return row


def main() -> int:
    application = ControlCenter()
    return application.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
