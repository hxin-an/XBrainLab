from __future__ import annotations

import json
from pathlib import Path

import scripts.dev.run_public_cross_source_training_smoke as smoke_script
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_EPOCH_ONLY_FIXTURES,
    PUBLIC_TRAINING_FIXTURES,
    SmokeResult,
    build_snapshot,
    render_markdown,
)


def test_build_snapshot_summarizes_runner_results(monkeypatch):
    fixture_names = {fixture["name"] for fixture in PUBLIC_TRAINING_FIXTURES}

    def fake_run_fixture_smoke(fixture):
        name = fixture["name"]
        assert name in fixture_names
        if name == "bbci-gdf":
            return SmokeResult(
                name=name,
                filename=fixture["filename"],
                source_family=fixture["source_family"],
                status="passed",
                dataset_count=1,
                message="ok",
            )
        if name == "sccn-eeglab":
            return SmokeResult(
                name=name,
                filename=fixture["filename"],
                source_family=fixture["source_family"],
                status="missing",
                dataset_count=0,
                message="not downloaded",
            )
        return SmokeResult(
            name=name,
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="failed",
            dataset_count=0,
            message="boom",
        )

    def fake_run_fixture_epoch_smoke(fixture):
        return SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=0,
            message="epoch only ok",
            protocol="epoch-only",
        )

    monkeypatch.setattr(
        "scripts.dev.run_public_cross_source_training_smoke.run_fixture_smoke",
        fake_run_fixture_smoke,
    )
    monkeypatch.setattr(
        "scripts.dev.run_public_cross_source_training_smoke.run_fixture_epoch_smoke",
        fake_run_fixture_epoch_smoke,
    )

    repo_root = Path("/tmp/xbrainlab")
    snapshot = build_snapshot(repo_root)

    assert snapshot["public_data_dir"] == str(
        repo_root / "tests" / "fixtures" / "data" / "public"
    )
    assert snapshot["summary"]["passed"] == 2
    assert snapshot["summary"]["missing"] == 1
    assert snapshot["summary"]["failed"] == 1


def test_render_markdown_includes_summary():
    snapshot = {
        "results": [
            {
                "name": "bbci-gdf",
                "filename": "bbci-competition-iii-O3VR.gdf",
                "source_family": "BBCI",
                "status": "passed",
                "dataset_count": 1,
                "message": "ok",
                "protocol": "training",
            }
        ],
        "summary": {
            "passed": 1,
            "missing": 0,
            "failed": 0,
            "message": "Event-rich public local-only fixtures provide repeatable training smoke where class-balanced splits are viable.",
        },
    }

    rendered = render_markdown(snapshot)

    assert "# Public Cross-Source Training Smoke" in rendered
    assert "bbci-competition-iii-O3VR.gdf" in rendered
    assert "passed" in rendered
    assert "training smoke" in rendered


def test_cnt_fixture_is_epoch_only_for_tiny_event_count():
    training_fixture_names = {fixture["name"] for fixture in PUBLIC_TRAINING_FIXTURES}
    epoch_fixture_by_name = {
        fixture["name"]: fixture for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
    }

    assert "mne-cnt" not in training_fixture_names
    assert epoch_fixture_by_name["mne-cnt"]["filename"] == "scan41_short.cnt"


def test_json_output_keeps_runner_noise_off_stdout(monkeypatch, capsys):
    def fake_build_snapshot():
        print("mne progress that should not corrupt json")
        return {
            "repo_root": "/tmp/xbrainlab",
            "public_data_dir": "/tmp/xbrainlab/tests/fixtures/data/public",
            "results": [],
            "summary": {
                "passed": 0,
                "missing": 0,
                "failed": 0,
                "message": "ok",
            },
        }

    monkeypatch.setattr(smoke_script, "build_snapshot", fake_build_snapshot)
    monkeypatch.setattr(
        "sys.argv",
        ["run_public_cross_source_training_smoke.py", "--format", "json"],
    )

    assert smoke_script.main() == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out)["summary"]["message"] == "ok"
    assert "mne progress" not in captured.out
    assert "mne progress that should not corrupt json" in captured.err
