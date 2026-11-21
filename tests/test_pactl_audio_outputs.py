"""Reading and switching audio outputs through ``pactl``, the way GNOME lists them."""

import json
import subprocess
from unittest.mock import patch

from domain.audio.output import AudioOutput
from infrastructure.linux.audio.outputs import PactlAudioOutputs

GPU = "alsa_card.pci-gpu"
USB = "alsa_card.usb-audio"

_CARDS = [
    {"name": GPU, "active_profile": "output:hdmi-stereo",
     "properties": {"device.description": "GB203 High Definition Audio Controller"},
     "ports": {
         "hdmi-output-0": {"description": "HDMI/DisplayPort", "availability": "available",
                           "properties": {"device.product.name": "DELL U2717D"},
                           "profiles": ["output:hdmi-stereo"]},
         "hdmi-output-1": {"description": "HDMI / DisplayPort 2", "availability": "available",
                           "properties": {"device.product.name": "SAMSUNG"},
                           "profiles": ["output:hdmi-surround-extra1",
                                        "output:hdmi-stereo-extra1"]},
         "hdmi-output-2": {"description": "HDMI / DisplayPort 3",
                           "availability": "not available", "properties": {},
                           "profiles": ["output:hdmi-stereo-extra2"]},
     },
     "profiles": {
         "output:hdmi-stereo": {"sinks": 1, "available": True, "priority": 5900},
         "output:hdmi-stereo-extra1": {"sinks": 1, "available": True, "priority": 5700},
         "output:hdmi-surround-extra1": {"sinks": 1, "available": True, "priority": 600},
         "output:hdmi-stereo-extra2": {"sinks": 1, "available": False, "priority": 5700},
     }},
    {"name": USB, "active_profile": "HiFi",
     "properties": {"device.description": "USB Audio"},
     "ports": {
         "[Out] Speaker": {"description": "Speakers", "availability": "available",
                           "properties": {}, "profiles": ["HiFi"]},
         "[Out] Headphones": {"description": "Front Headphones",
                              "availability": "not available", "properties": {},
                              "profiles": ["HiFi"]},
         "[In] Mic": {"description": "Microphone", "availability": "available",
                      "properties": {}, "profiles": ["HiFi"]},
     },
     "profiles": {"HiFi": {"sinks": 3, "sources": 2, "available": True, "priority": 9000}}},
]

_GPU_SINK = {"name": "alsa_output.gpu.hdmi-stereo", "active_port": "hdmi-output-0",
             "properties": {"device.name": GPU},
             "ports": [{"name": "hdmi-output-0"}]}
_SAMSUNG_SINK = {"name": "alsa_output.gpu.hdmi-stereo-extra1", "active_port": "hdmi-output-1",
                 "properties": {"device.name": GPU},
                 "ports": [{"name": "hdmi-output-1"}]}
_SPEAKER_SINK = {"name": "alsa_output.usb.speaker", "active_port": "[Out] Speaker",
                 "properties": {"device.name": USB},
                 "ports": [{"name": "[Out] Speaker"}]}
_SONOS_SINK = {"name": "raop_sink.sonos", "description": "Sonos", "properties": {}, "ports": []}


class FakePactl:
    def __init__(self, sinks, default_sink, sinks_after_profile_switch=None,
                 cards=_CARDS, texts=None):
        self.sinks = sinks
        self.default_sink = default_sink
        self.sinks_after_profile_switch = sinks_after_profile_switch
        self.cards = cards
        self.texts = texts or {}
        self.commands = []

    def check_output(self, argv, env=None, **_):
        if argv[1:] == ["-f", "json", "list", "cards"]:
            return json.dumps(self.cards)
        if argv[1:] == ["-f", "json", "list", "sinks"]:
            return json.dumps(self.sinks)
        if argv[1:] == ["get-default-sink"]:
            return self.default_sink + "\n"
        if argv[1] == "list":
            assert env["LC_ALL"] == "C"
            if argv[2] not in self.texts:
                raise subprocess.CalledProcessError(1, argv)
            return self.texts[argv[2]]
        raise AssertionError(argv)

    def run(self, argv, **_):
        self.commands.append(argv[1:])
        if argv[1] == "set-card-profile" and self.sinks_after_profile_switch:
            self.sinks = self.sinks_after_profile_switch


ONBOARD = "alsa_card.pci-0000_00_03.0"

_NULL_CARDS = [
    {"name": ONBOARD, "active_profile": "output:analog-stereo",
     "properties": {"device.description": "(null)"},
     "ports": {
         "analog-output-lineout": {"description": "(null)", "availability": "availability unknown",
                                   "properties": {"device.product.name": "(null)"},
                                   "profiles": ["output:analog-stereo"]},
         "analog-output-headphones": {"description": "(null)",
                                      "availability": "availability unknown",
                                      "properties": {}, "profiles": ["output:analog-stereo"]},
     },
     "profiles": {"output:analog-stereo": {"sinks": 1, "available": True, "priority": 6500}}},
]

_NULL_SINKS = [
    {"name": "alsa_output.pci-0000_00_03.0.analog-stereo", "description": "(null)",
     "active_port": "analog-output-lineout", "properties": {"device.name": ONBOARD},
     "ports": [{"name": "analog-output-lineout", "description": "(null)"}]},
    {"name": "raop_sink.glosnik", "description": "(null)", "properties": {}, "ports": []},
]

_TEXT_CARDS = """Card #44
\tName: alsa_card.pci-0000_00_03.0
\tDriver: alsa
\tProperties:
\t\tdevice.product.name = "82801FB High Definition Audio Controller"
\t\tdevice.description = "Wbudowany dźwięk"
\tProfiles:
\t\toutput:analog-stereo: Wyjście Analogowe stereo (sinks: 1, sources: 0, priority: 6500, available: yes)
\tActive Profile: output:analog-stereo
\tPorts:
\t\tanalog-output-lineout: Wyjście liniowe (tył) (type: Line, priority: 9000, availability unknown)
\t\t\tProperties:
\t\t\t\tport.type = "line"
\t\t\tPart of profile(s): output:analog-stereo
"""

_TEXT_SINKS = """Sink #51
\tState: SUSPENDED
\tName: alsa_output.pci-0000_00_03.0.analog-stereo
\tDescription: Wbudowany dźwięk Analogowe stereo
\tVolume: front-left: 32768 /  50% / -18.06 dB,   front-right: 32768 /  50% / -18.06 dB
\t        balance 0.00
\tPorts:
\t\tanalog-output-lineout: Wyjście liniowe (tył) (type: Line, priority: 9000, availability unknown)
\tActive Port: analog-output-lineout

Sink #55
\tName: raop_sink.glosnik
\tDescription: Głośnik w salonie
\tProperties:
\t\tdevice.description = "Głośnik w salonie"
"""


def _polish_pactl(texts):
    return FakePactl(_NULL_SINKS, _NULL_SINKS[0]["name"], cards=_NULL_CARDS, texts=texts)


def _with(pactl, use):
    with patch("infrastructure.linux.audio.outputs.subprocess.check_output",
               side_effect=pactl.check_output), \
         patch("infrastructure.linux.audio.outputs.subprocess.run", side_effect=pactl.run):
        return use(PactlAudioOutputs(run_in_background=lambda work: work()))


def _everyday_pactl():
    return FakePactl([_GPU_SINK, _SPEAKER_SINK, _SONOS_SINK], _SPEAKER_SINK["name"])


class TestAvailable:
    def test_lists_card_ports_by_their_device_then_cardless_sinks(self):
        assert _with(_everyday_pactl(), lambda o: o.available()) == [
            AudioOutput(f"{GPU}:hdmi-output-0", "HDMI/DisplayPort – DELL U2717D"),
            AudioOutput(f"{GPU}:hdmi-output-1", "HDMI / DisplayPort 2 – SAMSUNG"),
            AudioOutput(f"{USB}:[Out] Speaker", "Speakers – USB Audio"),
            AudioOutput("raop_sink.sonos", "Sonos"),
        ]

    def test_names_mangled_to_null_by_pactl_json_come_from_its_text_listing(self):
        pactl = _polish_pactl({"cards": _TEXT_CARDS, "sinks": _TEXT_SINKS})
        assert _with(pactl, lambda o: o.available()) == [
            AudioOutput(f"{ONBOARD}:analog-output-lineout", "Wyjście liniowe (tył) – Wbudowany dźwięk"),
            AudioOutput(f"{ONBOARD}:analog-output-headphones", "analog-output-headphones – Wbudowany dźwięk"),
            AudioOutput("raop_sink.glosnik", "Głośnik w salonie"),
        ]

    def test_names_missing_from_the_text_listing_fall_back_to_identifiers(self):
        pactl = _polish_pactl({"cards": "", "sinks": ""})
        assert _with(pactl, lambda o: o.available()) == [
            AudioOutput(f"{ONBOARD}:analog-output-lineout", f"analog-output-lineout – {ONBOARD}"),
            AudioOutput(f"{ONBOARD}:analog-output-headphones", f"analog-output-headphones – {ONBOARD}"),
            AudioOutput("raop_sink.glosnik", "raop_sink.glosnik"),
        ]

    def test_a_failing_text_listing_still_lists_and_switches_the_outputs(self):
        pactl = _polish_pactl({})
        assert [output.id for output in _with(pactl, lambda o: o.available())] == [
            f"{ONBOARD}:analog-output-lineout",
            f"{ONBOARD}:analog-output-headphones",
            "raop_sink.glosnik",
        ]
        _with(pactl, lambda o: o.activate("raop_sink.glosnik"))
        assert pactl.commands == [["set-default-sink", "raop_sink.glosnik"]]

    def test_offers_nothing_when_pactl_is_missing(self):
        with patch("infrastructure.linux.audio.outputs.subprocess.check_output",
                   side_effect=FileNotFoundError("pactl")):
            assert PactlAudioOutputs().available() == []


class TestActive:
    def test_is_the_default_sinks_card_port(self):
        assert _with(_everyday_pactl(), lambda o: o.active()) == f"{USB}:[Out] Speaker"

    def test_is_the_sink_itself_when_it_has_no_card(self):
        pactl = FakePactl([_GPU_SINK, _SONOS_SINK], "raop_sink.sonos")
        assert _with(pactl, lambda o: o.active()) == "raop_sink.sonos"


class TestActivate:
    def test_a_port_of_the_active_profile_becomes_the_default(self):
        pactl = _everyday_pactl()
        _with(pactl, lambda o: o.activate(f"{GPU}:hdmi-output-0"))
        assert pactl.commands == [
            ["set-sink-port", _GPU_SINK["name"], "hdmi-output-0"],
            ["set-default-sink", _GPU_SINK["name"]],
        ]

    def test_a_port_outside_the_active_profile_switches_to_its_best_profile_first(self):
        pactl = FakePactl([_GPU_SINK, _SPEAKER_SINK], _SPEAKER_SINK["name"],
                          sinks_after_profile_switch=[_SAMSUNG_SINK, _SPEAKER_SINK])
        _with(pactl, lambda o: o.activate(f"{GPU}:hdmi-output-1"))
        assert pactl.commands == [
            ["set-card-profile", GPU, "output:hdmi-stereo-extra1"],
            ["set-sink-port", _SAMSUNG_SINK["name"], "hdmi-output-1"],
            ["set-default-sink", _SAMSUNG_SINK["name"]],
        ]

    def test_a_cardless_sink_simply_becomes_the_default(self):
        pactl = _everyday_pactl()
        _with(pactl, lambda o: o.activate("raop_sink.sonos"))
        assert pactl.commands == [["set-default-sink", "raop_sink.sonos"]]
