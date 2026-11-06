Name:           tuxcontrol
Version:        %{pkgver}
Release:        1%{?dist}
Summary:        GNOME control center for apps, services, themes, and extensions
License:        GPL-3.0-only
BuildArch:      noarch
Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       gtk4
Requires:       systemd
Recommends:     libayatana-appindicator-gtk3
Recommends:     zenity
Source0:        tuxcontrol-%{version}.tar.gz
AutoReqProv:    no

%description
TuxControl is an open-source GTK 4 application for managing GNOME applications,
services, themes, and shell extensions. It also includes an optional Quick Share
tray for receiving files from nearby Android devices.

%prep
%setup -q -n tuxcontrol-%{version}

%build

%install
cp -a usr %{buildroot}/usr
install -d %{buildroot}%{_datadir}/licenses/tuxcontrol
mv %{buildroot}%{_datadir}/doc/tuxcontrol/copyright %{buildroot}%{_datadir}/licenses/tuxcontrol/LICENSE
rmdir %{buildroot}%{_datadir}/doc/tuxcontrol

%post
/usr/bin/update-desktop-database -q %{_datadir}/applications >/dev/null 2>&1 || :
/usr/bin/gtk-update-icon-cache -q -t %{_datadir}/icons/hicolor >/dev/null 2>&1 || :

%postun
/usr/bin/update-desktop-database -q %{_datadir}/applications >/dev/null 2>&1 || :
/usr/bin/gtk-update-icon-cache -q -t %{_datadir}/icons/hicolor >/dev/null 2>&1 || :

%files
%license %{_datadir}/licenses/tuxcontrol/LICENSE
%{_bindir}/tuxcontrol
%{_bindir}/tuxcontrol-quickshare-send
%{_bindir}/tuxcontrol-quickshare-settings
%{_bindir}/tuxcontrol-quickshare-tray
%{_prefix}/lib/tuxcontrol/
%{_datadir}/applications/org.tuxcontrol.App.desktop
%{_datadir}/applications/org.tuxcontrol.QuickShare.desktop
%{_datadir}/icons/hicolor/256x256/apps/tuxcontrol.png
