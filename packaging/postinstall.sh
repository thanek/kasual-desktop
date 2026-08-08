#!/bin/sh
# Post-install hook shared by the .deb, .rpm and Arch packages.
# Reloads udev so the freshly installed 99-kasual-desktop.rules takes effect
# immediately — controllers plugged in after install (and already-plugged ones
# once retriggered) become readable by the active user without a reboot.
#
# Both subsystems the rule grants: gamepads are `input`, /dev/uinput is `misc`.
# A uinput module already loaded before the rule landed keeps the permissions it
# was created with until its node is retriggered.
#
# Mirrors the postinst shipped by Sunshine (LizardByte) for /dev/uinput/uhid.
# No-op when udevadm is absent (non-systemd hosts keep the rule file; a reboot
# or manual `udevadm trigger` applies it later).

set -u

if command -v udevadm >/dev/null 2>&1; then
	udevadm control --reload-rules 2>/dev/null || true
	udevadm trigger --subsystem-match=input --subsystem-match=misc 2>/dev/null || true
else
	echo "kasual-desktop: udevadm not found; udev rule installed but not reloaded." >&2
	echo "kasual-desktop: reboot, or run 'udevadm control --reload-rules && udevadm trigger' once available." >&2
fi

if [ -d /usr/share/gnome-shell/extensions/kasual-helper@consoledesktop.org ]; then
	echo "kasual-desktop: on GNOME, log out and back in, then run:"
	echo "kasual-desktop:   gnome-extensions enable kasual-helper@consoledesktop.org"
fi

exit 0