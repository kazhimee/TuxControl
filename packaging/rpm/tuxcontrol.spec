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
Source0:        tuxcontrol-%{version}.tar.gz

%description
TuxControl is an open-source GTK 4 application for managing GNOME applications,
services, themes, and shell extensions.

%prep
%setup -q -n tuxcontrol-%{version}

%build

%install
install -d %{buildroot}%{_libdir}/tuxcontrol/control_center
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/licenses/tuxcontrol
install -m 0644 control_center/*.py %{buildroot}%{_libdir}/tuxcontrol/control_center/
install -m 0644 org.tuxcontrol.App.desktop \
  %{buildroot}%{_datadir}/applications/org.tuxcontrol.App.desktop
install -m 0644 LICENSE %{buildroot}%{_datadir}/licenses/tuxcontrol/LICENSE
cat > %{buildroot}%{_bindir}/tuxcontrol <<'LAUNCHER'
#!/bin/sh
export PYTHONPATH="%{_libdir}/tuxcontrol${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m control_center.app "$@"
LAUNCHER
chmod 0755 %{buildroot}%{_bindir}/tuxcontrol

%files
%{_bindir}/tuxcontrol
%{_libdir}/tuxcontrol/control_center/
%{_datadir}/applications/org.tuxcontrol.App.desktop
%{_datadir}/licenses/tuxcontrol/LICENSE
