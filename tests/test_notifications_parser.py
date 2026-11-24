"""Tests for the pure dbus-monitor parser behind the freedesktop notification adapter.

The brittle text parsing is isolated from the QProcess plumbing precisely so it
can be exercised without a live bus.
"""

from infrastructure.linux.notifications.notifications import (
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
    def test_flushes_all_fully_streamed_blocks(self):
        found, leftover = parse_notify_blocks(_SAMPLE)
        # Both blocks have fully streamed (each ends with its trailing int32), so
        # both are emitted — the final one is NOT stranded waiting for a follower.
        # The noise signal is ignored.
        assert [a.app_name for a in found] == ["Spotify", "KMail"]
        assert found[0].summary == "Now Playing"
        assert found[0].app_icon == "spotify"
        assert found[1].body == "From Alice"
        assert "KMail" not in leftover

    def test_holds_a_trailing_block_still_streaming(self):
        # The final block is cut off before its trailing int32 arrives, so it is
        # held back (emitting it now would drop the fields still to come).
        partial = _SAMPLE[: _SAMPLE.rindex("int32 -1")]
        found, leftover = parse_notify_blocks(partial)
        assert [a.app_name for a in found] == ["Spotify"]
        assert "KMail" in leftover

    def test_held_tail_flushes_once_it_completes(self):
        partial = _SAMPLE[: _SAMPLE.rindex("int32 -1")]
        _, leftover = parse_notify_blocks(partial)
        # The remaining lines (the trailing int32) complete the held KMail block.
        found, tail = parse_notify_blocks(leftover + "int32 -1\n")
        assert [a.app_name for a in found] == ["KMail"]
        assert found[0].body == "From Alice"
        assert tail == ""

    def test_no_header_yet_keeps_everything(self):
        chunk = '   string "partial"\n'
        found, leftover = parse_notify_blocks(chunk)
        assert found == []
        assert leftover == chunk

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


_RELAYED_BY_GNOME_SHELL = """\
method call time=1.0 sender=:1.9 -> destination=:1.25 serial=9 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "notify-send"
   uint32 0
   string ""
   string "Once"
   string "only"
   array [
   ]
   array [
      dict entry(
         string "urgency"
         variant             byte 2
      )
   ]
   int32 -1
method call time=1.1 sender=:1.25 -> destination=:1.15 serial=586 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "notify-send"
   uint32 0
   string ""
   string "Once"
   string "only"
   array [
   ]
   array [
      dict entry(
         string "x-shell-sender-pid"
         variant             uint32 382852
      )
      dict entry(
         string "x-shell-sender"
         variant             string ":1.9"
      )
   ]
   int32 -1
"""


class TestGnomeShellRelay:
    def test_a_relayed_notification_counts_once(self):
        found, leftover = parse_notify_blocks(_RELAYED_BY_GNOME_SHELL)
        assert [a.summary for a in found] == ["Once"]
        assert leftover == ""

    def test_the_relay_is_dropped_when_streamed_line_by_line(self):
        summaries, buffer = [], ""
        for line in _RELAYED_BY_GNOME_SHELL.splitlines(keepends=True):
            found, buffer = parse_notify_blocks(buffer + line)
            summaries += [a.summary for a in found]
        assert summaries == ["Once"]
