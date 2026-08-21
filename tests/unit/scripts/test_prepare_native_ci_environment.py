from __future__ import annotations

from scripts.dev import prepare_native_ci_environment as prepare


def test_build_isolated_environment_creates_every_required_root(tmp_path) -> None:
    root = tmp_path / "Native 測試"

    environment = prepare.build_isolated_environment(root)

    assert set(environment) == set(prepare.REQUIRED_ISOLATED_ENV)
    assert all(path.startswith(str(root.resolve())) for path in environment.values())


def test_github_environment_writer_is_deterministic(tmp_path) -> None:
    output = tmp_path / "github-env"

    prepare.write_github_environment(output, {"B": "second", "A": "first"})

    assert output.read_text(encoding="utf-8") == "A=first\nB=second\n"
