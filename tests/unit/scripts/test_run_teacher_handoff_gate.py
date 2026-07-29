from __future__ import annotations

import pytest

from scripts.dev import run_teacher_handoff_gate as gate


@pytest.mark.parametrize(
    ("group_count", "size_bytes", "expected_ok"),
    (
        (10, 277_106_963, True),
        (9, 277_106_963, False),
        (10, 277_106_962, False),
    ),
)
def test_teacher_fixture_verification_has_an_independent_fixed_denominator(
    monkeypatch: pytest.MonkeyPatch,
    group_count: int,
    size_bytes: int,
    expected_ok: bool,
) -> None:
    groups = [
        {
            "name": f"group-{index}",
            "files": [
                {
                    "filename": f"group-{index}/fixture.edf",
                    "sha256": "a" * 64,
                    "size_bytes": 1,
                }
            ],
        }
        for index in range(group_count)
    ]
    monkeypatch.setattr(gate, "fixture_groups_for_profile", lambda _profile: groups)
    monkeypatch.setattr(gate, "fixture_profile_size_bytes", lambda _groups: size_bytes)
    monkeypatch.setattr(gate, "fixture_file_is_valid", lambda *_args: True)

    result = gate.verify_teacher_fixture_profile()

    assert result["ok"] is expected_ok


def test_source_dirty_paths_excludes_only_protected_settings_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gate,
        "_git_output",
        lambda *_args: "\n".join(
            (
                " M settings.json",
                " M .vscode/settings.json",
                " M XBrainLab/backend/service.py",
                "?? artifacts/ui/current.png",
                "?? tests/unit/test_current.py",
            )
        ),
    )

    assert gate._source_dirty_paths() == [
        "XBrainLab/backend/service.py",
        "tests/unit/test_current.py",
    ]


def test_git_output_preserves_first_porcelain_status_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = " M .vscode/settings.json\n?? artifacts/ui/current.png\n"

    monkeypatch.setattr(gate.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(gate.subprocess, "run", lambda *_args, **_kwargs: Completed())

    assert gate._git_output("status", "--short").startswith(" M .vscode/settings.json")
