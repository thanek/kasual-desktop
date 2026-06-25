"""Tests for the pure dbus-monitor parser behind the KDE notification adapter.

The brittle text parsing is isolated from the QProcess plumbing precisely so it
can be exercised without a live bus.
"""

from infrastructure.kde.notifications.notifications import (
    parse_notify_blocks, _parse_notify_args,
)

# A realistic dbus-monitor capture (the EXACT wire format: headers are
# "method call" / "signal" with a space, not "method_call"). Captured live from
# `dbus-monitor --session "interface='...Notifications',member='Notify'"`.
_SAMPLE = """\
signal time=1.0 sender=org.freedesktop.DBus -> destination=:1.2 serial=2 path=/org/freedesktop/DBus; interface=org.freedesktop.DBus; member=NameAcquired
   string ":1.2"
method call time=2.0 sender=:1.55 -> destination=:1.4 serial=42 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "Spotify"
   uint32 0
   string "spotify"
   string "Now Playing"
   string "Song - Artist"
   array [
      string "default"
      string "Open"
   ]
   array [
      dict entry(
         string "urgency"
         variant             byte 1
      )
      dict entry(
         string "sender-pid"
         variant             int64 316429
      )
   ]
   int32 -1
method call time=3.0 sender=:1.55 -> destination=:1.4 serial=43 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "KMail"
   uint32 0
   string "kmail"
   string "New mail"
   string "From Alice"
   array [
   ]
   array [
   ]
   int32 -1
"""


class TestParseNotifyArgs:
    def test_picks_positional_strings_skipping_arrays(self):
        lines = [
            '   string "Spotify"',
            "   uint32 0",
            '   string "spotify"',
            '   string "Now Playing"',
            '   string "Song - Artist"',
            "   array [",
            '      string "default"',
            '      string "Open"',
            "   ]",
            "   int32 -1",
        ]
        args = _parse_notify_args(lines)
        assert args is not None
        assert args.app_name == "Spotify"
        assert args.app_icon == "spotify"
        assert args.summary == "Now Playing"
        assert args.body == "Song - Artist"

    def test_too_few_args_returns_none(self):
        assert _parse_notify_args(['   string "X"']) is None


class TestParseNotifyBlocks:
    def test_returns_completed_blocks_and_holds_the_tail(self):
        found, leftover = parse_notify_blocks(_SAMPLE)
        # Spotify is complete; the trailing KMail block is held until the next
        # header proves it finished. The noise signal is ignored.
        assert [a.app_name for a in found] == ["Spotify"]
        assert found[0].summary == "Now Playing"
        assert found[0].app_icon == "spotify"
        assert "KMail" in leftover

    def test_no_header_yet_keeps_everything(self):
        chunk = '   string "partial"\n'
        found, leftover = parse_notify_blocks(chunk)
        assert found == []
        assert leftover == chunk

    def test_tail_completes_on_next_chunk(self):
        _, leftover = parse_notify_blocks(_SAMPLE)
        # Feeding another header finalizes the held KMail block.
        more = leftover + "signal time=9.0 sender=x -> destination=y serial=99 path=/p; interface=i; member=M\n"
        found, _ = parse_notify_blocks(more)
        assert [a.app_name for a in found] == ["KMail"]
        assert found[0].body == "From Alice"

    def test_ignores_non_notify_method_calls(self):
        text = (
            "method call time=1.0 sender=:1.1 -> destination=:1.2 serial=1 "
            "path=/x; interface=org.freedesktop.Notifications; member=GetCapabilities\n"
            '   string "noise"\n'
            "method call time=2.0 sender=:1.1 -> destination=:1.2 serial=2 "
            "path=/x; interface=org.freedesktop.Notifications; member=Notify\n"
            "signal time=3.0 sender=x -> destination=y serial=3 path=/p; interface=i; member=M\n"
        )
        found, _ = parse_notify_blocks(text)
        assert found == []   # the GetCapabilities call is not a Notify
