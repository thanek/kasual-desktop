"""AudioOutputs adapter over ``pactl`` (PulseAudio / PipeWire).

Like GNOME, an output is a sound card's output port, whichever card profile
it needs, plus every sink that belongs to no card (e.g. AirPlay). Switching to a
port outside the card's active profile switches the profile first.
"""

import json
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from domain.audio.output import AudioOutput, AudioOutputs

logger = logging.getLogger(__name__)

_UNPLUGGED = "not available"
_ASCII_ONLY_JSON_ENV = {**os.environ, "LC_ALL": "C"}
_SINK_APPEARS_WITHIN_S = 2.0
_SINK_POLL_S = 0.1

Work = Callable[[], None]


def _on_daemon_thread(work: Work) -> None:
    threading.Thread(target=work, daemon=True, name="audio-output-switch").start()


@dataclass(frozen=True)
class _Route:
    output: AudioOutput
    sink: str | None = None
    card: str | None = None
    port: str | None = None
    profile_to_switch_to: str | None = None


class PactlAudioOutputs(AudioOutputs):
    def __init__(self, run_in_background: Callable[[Work], None] = _on_daemon_thread) -> None:
        self._run_in_background = run_in_background

    def available(self) -> list[AudioOutput]:
        try:
            cards, sinks = _pactl_list("cards"), _pactl_list("sinks")
        except Exception as exc:
            logger.warning("Cannot list audio outputs: %s", exc)
            return []
        active = _active_id(cards, sinks)
        return [route.output for route in _routes(cards, sinks)
                if route.output.connected or route.output.id == active]

    def active(self) -> str | None:
        try:
            return _active_id(_pactl_list("cards"), _pactl_list("sinks"))
        except Exception as exc:
            logger.warning("Cannot read the active audio output: %s", exc)
            return None

    def activate(self, output_id: str) -> None:
        self._run_in_background(lambda: self._switch_to(output_id))

    def _switch_to(self, output_id: str) -> None:
        try:
            route = next((route for route in _routes(_pactl_list("cards"), _pactl_list("sinks"))
                          if route.output.id == output_id), None)
            if route is None:
                logger.warning("Audio output %s is gone", output_id)
            elif route.card is None:
                _pactl("set-default-sink", route.sink)
            else:
                _switch_to_card_port(route)
        except Exception as exc:
            logger.error("Cannot switch the audio output: %s", exc)


def _switch_to_card_port(route: _Route) -> None:
    if route.profile_to_switch_to is not None:
        _pactl("set-card-profile", route.card, route.profile_to_switch_to)
    sink = _wait_for_sink_of(route.card, route.port)
    _pactl("set-sink-port", sink, route.port)
    _pactl("set-default-sink", sink)


def _wait_for_sink_of(card: str, port: str) -> str:
    deadline = time.monotonic() + _SINK_APPEARS_WITHIN_S
    while True:
        sink = next((sink["name"] for sink in _pactl_list("sinks")
                     if _card_of(sink) == card
                     and any(p.get("name") == port for p in sink.get("ports", []))), None)
        if sink is not None:
            return sink
        if time.monotonic() > deadline:
            raise TimeoutError(f"no sink appeared for {card} {port}")
        time.sleep(_SINK_POLL_S)


def _routes(cards: list[dict], sinks: list[dict]) -> list[_Route]:
    card_names = {card["name"] for card in cards}
    return [
        *(route for card in cards for route in _card_routes(card)),
        *(_sink_route(sink) for sink in sinks if _card_of(sink) not in card_names),
    ]


def _card_routes(card: dict) -> list[_Route]:
    routes = []
    for name, port in card.get("ports", {}).items():
        profiles = _usable_profiles(card, port)
        if not _is_output_port(name) or not profiles:
            continue
        needs_switch = card.get("active_profile") not in profiles
        routes.append(_Route(
            AudioOutput(_port_id(card["name"], name), _port_label(card, port),
                        connected=port.get("availability") != _UNPLUGGED),
            card=card["name"], port=name,
            profile_to_switch_to=profiles[0] if needs_switch else None,
        ))
    return routes


def _usable_profiles(card: dict, port: dict) -> list[str]:
    profiles = card.get("profiles", {})
    usable = [name for name in port.get("profiles", [])
              if profiles.get(name, {}).get("available") and profiles[name].get("sinks")]
    return sorted(usable, key=lambda name: profiles[name].get("priority", 0), reverse=True)


def _is_output_port(name: str) -> bool:
    return name.startswith("[Out]") or "output" in name


def _port_label(card: dict, port: dict) -> str:
    device = (port.get("properties", {}).get("device.product.name")
              or card.get("properties", {}).get("device.description")
              or card["name"])
    return f"{port.get('description') or ''} – {device}".strip(" –")


def _sink_route(sink: dict) -> _Route:
    return _Route(AudioOutput(sink["name"], sink.get("description") or sink["name"]),
                  sink=sink["name"])


def _active_id(cards: list[dict], sinks: list[dict]) -> str | None:
    default = _pactl_output("get-default-sink").strip()
    sink = next((sink for sink in sinks if sink["name"] == default), None)
    if sink is None:
        return None
    card = _card_of(sink)
    if card in {card["name"] for card in cards} and sink.get("active_port"):
        return _port_id(card, sink["active_port"])
    return sink["name"]


def _card_of(sink: dict) -> str | None:
    return sink.get("properties", {}).get("device.name")


def _port_id(card: str, port: str) -> str:
    return f"{card}:{port}"


def _pactl_list(kind: str) -> list[dict]:
    return json.loads(subprocess.check_output(
        ["pactl", "-f", "json", "list", kind],
        text=True, stderr=subprocess.DEVNULL, env=_ASCII_ONLY_JSON_ENV,
    ))


def _pactl_output(*args: str) -> str:
    return subprocess.check_output(["pactl", *args], text=True, stderr=subprocess.DEVNULL)


def _pactl(*args: str) -> None:
    subprocess.run(["pactl", *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
