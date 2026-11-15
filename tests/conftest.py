"""Shared test setup.

The daemon's AI switches live in ``~/.jarvis/settings.json`` and are read at call
time, so without this fixture the suite would pass or fail depending on how the
developer left the real HUD switches. Tests pin the defaults ON here; any test
that exercises a switch overrides the same env var with ``monkeypatch.setenv``.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ai_switches_on(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SETTING_GEMINI_ENABLED", "1")
    # Local / Cloud is a persisted user choice too. Pin the suite to the shipped
    # default so a developer who left the HUD on LOCAL does not turn the cloud
    # chain tests into local-model tests (and vice versa).
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "cloud")
