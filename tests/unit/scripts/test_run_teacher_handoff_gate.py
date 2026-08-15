from __future__ import annotations

import pytest

from scripts.dev import run_teacher_handoff_gate as gate


def test_teacher_fixture_verification_uses_canonical_data_root(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_dir = tmp_path / "datasets" / "public-fixtures"
    observed_paths = []
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
        for index in range(10)
    ]
    monkeypatch.setattr(gate, "resolve_public_fixture_dir", lambda: public_dir)
    monkeypatch.setattr(gate, "fixture_groups_for_profile", lambda _profile: groups)
    monkeypatch.setattr(
        gate,
        "fixture_profile_size_bytes",
        lambda _groups: gate.TEACHER_FIXTURE_PROFILE_SIZE_BYTES,
    )

    def fixture_is_valid(path, *_args):
        observed_paths.append(path)
        return True

    monkeypatch.setattr(gate, "fixture_file_is_valid", fixture_is_valid)

    assert gate.verify_teacher_fixture_profile()["ok"] is True
    assert observed_paths
    assert all(path.is_relative_to(public_dir) for path in observed_paths)


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


def test_source_dirty_paths_excludes_only_root_settings(
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
                "?? build/dev-artifacts/ui/current.png",
                "?? tests/unit/test_current.py",
            )
        ),
    )

    assert gate._source_dirty_paths() == [
        ".vscode/settings.json",
        "XBrainLab/backend/service.py",
        "build/dev-artifacts/ui/current.png",
        "tests/unit/test_current.py",
    ]


def test_git_output_preserves_first_porcelain_status_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = " M .vscode/settings.json\n?? build/dev-artifacts/ui/current.png\n"

    monkeypatch.setattr(gate.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(gate.subprocess, "run", lambda *_args, **_kwargs: Completed())

    assert gate._git_output("status", "--short").startswith(" M .vscode/settings.json")
