"""Filesystem-level safety and source provenance for the shared manual launcher."""

import json
import subprocess
import sys
from typing import ClassVar

import pytest

from scripts.dev import manual_environment as manual


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "manual source"
    root.mkdir()
    for command in (
        ["git", "init", "-q", str(root)],
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        ["git", "-C", str(root), "config", "user.name", "Test"],
    ):
        subprocess.run(command, check=True, capture_output=True)  # noqa: S603
    (root / "pyproject.toml").write_text(
        "# 手測環境\n[project]\ndependencies = []\n", encoding="utf-8"
    )
    (root / "poetry.lock").write_text("package = []\n")
    (root / ".gitignore").write_text("build/\n")
    (root / "run.py").write_text("pass\n")
    manual.git(root, "add", ".")
    manual.git(root, "commit", "-qm", "baseline")
    return root


def test_exact_source_rejects_wrong_sha_and_dirty_files(source):
    sha = manual.git(source, "rev-parse", "HEAD")
    assert manual.verify_source(source, sha) == sha
    with pytest.raises(RuntimeError, match="SHA"):
        manual.verify_source(source, "0" * 40)
    (source / "run.py").write_text("changed\n")
    with pytest.raises(RuntimeError, match="modified"):
        manual.verify_source(source, sha)


def test_prepare_rejects_incompatible_lock_without_switching(source):
    previous = manual.git(source, "rev-parse", "HEAD")
    (source / "pyproject.toml").write_text(
        '[project]\ndependencies = ["xbrainlab-missing-test-package==1"]\n'
    )
    manual.git(source, "add", "pyproject.toml")
    manual.git(source, "commit", "-qm", "new dependency")
    target = manual.git(source, "rev-parse", "HEAD")
    manual.git(source, "checkout", "--detach", previous)
    with pytest.raises(RuntimeError, match="environment"):
        manual.prepare(source, target)
    assert manual.git(source, "rev-parse", "HEAD") == previous


def test_shared_lease_blocks_concurrent_launch_prepare_or_cleanup(source):
    with manual.manual_lock(source), pytest.raises(RuntimeError, match="in use"):  # noqa: SIM117 - failure must arise acquiring the second lease.
        with manual.manual_lock(source):
            pytest.fail("second owner admitted")
    with manual.manual_lock(source):
        pass


def test_cleanup_preview_acceptance_and_retained_evidence(source):
    sha = manual.git(source, "rev-parse", "HEAD")
    run = manual.create_run(source, sha)
    weights = run / "work" / "output" / "model.pth"
    weights.parent.mkdir()
    weights.write_bytes(b"generated model")
    log = run / "logs" / "app.log"
    log.parent.mkdir()
    log.write_text("diagnostic evidence")
    kept = source / "research.pth"
    kept.write_bytes(b"keep")
    assert manual.clean_run(source, sha, apply=False, accepted=False) == len(
        b"generated model"
    )
    assert weights.exists()
    with pytest.raises(RuntimeError, match="acceptance"):
        manual.clean_run(source, sha, apply=True, accepted=False)
    manual.clean_run(source, sha, apply=True, accepted=True)
    assert not weights.parent.exists()
    assert log.read_text() == "diagnostic evidence"
    assert kept.read_bytes() == b"keep"
    assert json.loads((run / "source.json").read_text())["sha"] == sha


def test_unowned_or_symlinked_output_cannot_be_cleaned(source, tmp_path):
    sha = manual.git(source, "rev-parse", "HEAD")
    run = manual.create_run(source, sha)
    outside = tmp_path / "research"
    outside.mkdir()
    (outside / "keep.pth").write_bytes(b"keep")
    try:
        (run / "work" / "output").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(RuntimeError, match="link"):
        manual.clean_run(source, sha, apply=True, accepted=True)
    assert (outside / "keep.pth").read_bytes() == b"keep"


def test_run_identity_is_required_and_cannot_be_replaced(source):
    sha = manual.git(source, "rev-parse", "HEAD")
    run = manual.create_run(source, sha)
    (run / "source.json").write_text(json.dumps({"sha": "0" * 40}))
    with pytest.raises(RuntimeError, match="identity"):
        manual.clean_run(source, sha, apply=True, accepted=True)
    with pytest.raises(RuntimeError, match="identity"):
        manual.create_run(source, sha)


@pytest.mark.parametrize("sha", ["", "../data", "a" * 39, "a" * 41])
def test_invalid_source_cannot_address_cleanup_tree(source, sha):
    with pytest.raises(ValueError, match="SHA"):
        manual.clean_run(source, sha, apply=True, accepted=True)


def test_prepare_second_source_reuses_environment_without_installing(source):
    previous = manual.git(source, "rev-parse", "HEAD")
    (source / "run.py").write_text("pass  # next candidate\n")
    manual.git(source, "add", "run.py")
    manual.git(source, "commit", "-qm", "next")
    target = manual.git(source, "rev-parse", "HEAD")
    manual.prepare(source, previous)
    manual.prepare(source, target)
    assert manual.verify_source(source, target) == target
    assert not (source / ".venv").exists()


def test_source_symlink_is_rejected_before_mutation(source, tmp_path):
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(RuntimeError, match="link"):
        manual.prepare(alias, manual.git(source, "rev-parse", "HEAD"))


def test_live_python_process_blocks_prepare_and_cleanup(source):
    sha = manual.git(source, "rev-parse", "HEAD")
    manual.create_run(source, sha)
    process = subprocess.Popen(  # noqa: S603 - owned waiting fixture process.
        [
            sys.executable,
            "-c",
            "import sys; print('ready', flush=True); sys.stdin.read()",
        ],
        cwd=source,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="in use"):
            manual.prepare(source, sha)
        with pytest.raises(RuntimeError, match="in use"):
            manual.clean_run(source, sha, apply=True, accepted=True)
    finally:
        process.communicate(timeout=10)
    manual.prepare(source, sha)


def test_installed_dependency_must_match_locked_version(source):
    (source / "pyproject.toml").write_text('[project]\ndependencies = ["pytest"]\n')
    (source / "poetry.lock").write_text(
        '[[package]]\nname = "pytest"\nversion = "0.0.1"\n'
    )
    manual.git(source, "add", ".")
    manual.git(source, "commit", "-qm", "incompatible lock")
    with pytest.raises(RuntimeError, match="not the candidate lock"):
        manual.verify_environment(source, manual.git(source, "rev-parse", "HEAD"))


def test_runtime_paths_isolate_manual_data_and_share_only_models(tmp_path):
    from XBrainLab import platform_paths

    run = tmp_path / "manual run"
    cache = tmp_path / "shared models"
    environment = manual.runtime_environment(run, cache)
    for resolver in (
        platform_paths.user_config_dir,
        platform_paths.user_data_dir,
        platform_paths.user_cache_dir,
        platform_paths.user_log_dir,
    ):
        assert resolver(environ=environment, system_name="Windows").is_relative_to(run)
    assert platform_paths.user_model_cache_dir(environ=environment) == cache / "models"
    assert environment["XBRAINLAB_RAG_CACHE_DIR"] == str(cache / "rag")
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert not run.exists()  # Preflight path selection creates no dataset/settings.


@pytest.mark.parametrize("same_user", [False, True])
def test_process_inspection_ignores_known_other_users_but_fails_closed_for_own(
    source, monkeypatch, same_user
):
    import psutil

    class InaccessibleProcess:
        pid = -1
        info: ClassVar[dict[str, str]] = {
            "name": "python",
            "username": psutil.Process().username() if same_user else "other-account",
        }

        def cwd(self):
            raise psutil.AccessDenied(self.pid)

    monkeypatch.setattr(psutil, "process_iter", lambda fields: [InaccessibleProcess()])
    if same_user:
        with pytest.raises(RuntimeError, match="Cannot verify"):
            manual._assert_idle(source)
    else:
        manual._assert_idle(source)
