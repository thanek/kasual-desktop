"""Presentation vocabulary for notifications — how a timestamp reads.

Pure, Qt-free. Turns a notification's arrival time into a short, localized
"how long ago" label, in coarse buckets (just now / N min / N h / a date).
Lives in the domain because it is the wording of the feature, not an adapter —
its only outward need is translation, taken through the `support.i18n` port
(the `translate(context, text)` calls double as extraction markers, exactly as
`domain.system.action_view` does).
"""

from datetime import datetime

from support.i18n import translate

_MINUTE = 60
_HOUR   = 60 * _MINUTE
_DAY    = 24 * _HOUR


def relative_age(timestamp: datetime, now: datetime) -> str:
    """A short, localized "time ago" label for *timestamp* relative to *now*."""
    seconds = int((now - timestamp).total_seconds())
    if seconds < _MINUTE:
        return translate("Kasual Desktop", "just now")
    if seconds < _HOUR:
        return translate("Kasual Desktop", "{0} min ago").format(seconds // _MINUTE)
    if seconds < _DAY:
        return translate("Kasual Desktop", "{0} h ago").format(seconds // _HOUR)
    # Older than a day: fall back to the calendar date (locale-neutral ISO).
    return timestamp.strftime("%Y-%m-%d")
