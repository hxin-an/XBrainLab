from __future__ import annotations

from scripts.dev.run_public_cross_source_training_smoke import (
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

    monkeypatch.setattr(
        "scripts.dev.run_public_cross_source_training_smoke.run_fixture_smoke",
        fake_run_fixture_smoke,
    )

    snapshot = build_snapshot()

    assert snapshot["summary"]["passed"] == 1
    assert snapshot["summary"]["missing"] == 1
    assert snapshot["summary"]["failed"] == 2


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
            }
        ],
        "summary": {
            "passed": 1,
            "missing": 0,
            "failed": 0,
            "message": "Event-rich public local-only fixtures now provide a repeatable cross-source one-epoch training-smoke protocol.",
        },
    }

    rendered = render_markdown(snapshot)

    assert "# Public Cross-Source Training Smoke" in rendered
    assert "bbci-competition-iii-O3VR.gdf" in rendered
    assert "passed" in rendered
    assert "repeatable cross-source one-epoch training-smoke protocol" in rendered
