"""Contract tests for the real-data handoff validation helper."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from scripts.dev import run_real_data_handoff_gate as gate


def test_gate_requires_distinct_dataset_sources_not_derived_formats() -> None:
    families = gate.source_families()

    assert "graz-2a" in families
    assert "mne-bids-tiny" in families
    assert "physionet-eegmmidb" in families
    assert "bbci-competition-iii" in families
    assert "sccn-eeglab" in families
    assert len(families) >= 6
    assert all("mini-real" not in family for family in families)


def test_gate_contains_continuous_interpretation_and_bids_handoffs() -> None:
    slices = {gate_slice.name: gate_slice for gate_slice in gate.GATE_SLICES}

    graz = slices["graz-external-label-continuous-handoff"]
    assert graz.stages == (
        "data-interpretation",
        "external-label-apply",
        "epoch-materialization",
        "dataset-generation",
        "training-readiness",
        "tiny-training",
    )

    bids = slices["public-bids-continuous-handoff"]
    assert bids.stages == (
        "bids-folder-import",
        "events-tsv-apply",
        "epoch-materialization",
        "dataset-generation-readiness",
    )

    physionet = slices["physionet-internal-event-continuous-handoff"]
    assert physionet.stages == (
        "data-interpretation",
        "internal-event-review",
        "epoch-materialization",
        "dataset-generation",
        "training-readiness",
        "tiny-training",
    )


def test_gate_keeps_outer_label_source_lifecycle_as_a_blocking_slice() -> None:
    lifecycle = next(
        gate_slice
        for gate_slice in gate.GATE_SLICES
        if gate_slice.name == "label-source-remove-readd-lifecycle"
    )

    assert "outer-async-rescan" in lifecycle.stages
    assert "test_outer_async_review_remove_then_readd" in lifecycle.pytest_target


def test_pytest_command_is_local_only_and_targets_each_slice_once() -> None:
    command = gate.pytest_command()
    targets = command[command.index("faulthandler_timeout=180") + 1 :]

    assert command[:3] == [sys.executable, "-m", "pytest"]
    assert targets == [item.pytest_target for item in gate.GATE_SLICES]
    assert len(targets) == len(set(targets))
    assert all("fetch" not in target and "download" not in target for target in targets)


def test_main_runs_fixed_manifest_from_repo_root(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def _run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(gate.subprocess, "run", _run)
    monkeypatch.setenv("QT_QPA_PLATFORM", "minimal")
    monkeypatch.delenv("MPLBACKEND", raising=False)

    assert gate.main() == 7
    assert captured["command"] == gate.pytest_command()
    assert captured["cwd"] == gate.ROOT
    assert captured["check"] is False
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["QT_QPA_PLATFORM"] == "minimal"
    assert environment["MPLBACKEND"] == "Agg"
