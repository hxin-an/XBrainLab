"""Scoped fixtures for local-runtime and downloader process contracts."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def keep_spawned_children_outside_pytest_cov(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep real child startup observable instead of instrumenting the child."""
    for name in tuple(os.environ):
        if name.startswith("COV_CORE_"):
            monkeypatch.delenv(name, raising=False)
