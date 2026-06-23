"""Tests for WhichAppDiscovery (shutil.which-backed availability)."""

from infrastructure.kde.app_discovery import WhichAppDiscovery


def test_available_command_is_found(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.kde.app_discovery.shutil.which",
        lambda cmd: "/usr/bin/steam" if cmd == "steam" else None,
    )
    discovery = WhichAppDiscovery()
    assert discovery.is_available("steam") is True


def test_unknown_command_is_not_found(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.kde.app_discovery.shutil.which", lambda cmd: None
    )
    assert WhichAppDiscovery().is_available("definitely-not-installed") is False
