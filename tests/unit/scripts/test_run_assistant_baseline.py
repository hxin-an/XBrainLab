"""B0 entry preserves frozen identity and evidence without duplicating scoring."""

import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dev import run_assistant_baseline as entry


def test_report_identity_rejects_partial_jobs_models_and_embedding():
    conditions = {"m-on": ("m", True), "n-off": ("n", False)}
    frozen = dict.fromkeys(
        (
            "schema",
            "source",
            "bank_sha256",
            "selection",
            "config",
            "corpus_sha256",
            "seed",
            "repeat",
            "budget_seconds",
            "child_timeout_seconds",
            "condition_timeout_seconds",
        ),
        "fixed",
    )
    frozen.update(
        models={"m": {"spec": 1}, "n": {"spec": 2}},
        embedding_sha256="pinned",
        jobs=[{"condition": c, "id": f"{c}-{i}"} for c in conditions for i in range(2)],
    )
    entry.verify_run_identity(frozen, frozen, conditions)
    for mutate in (
        lambda m: m.update(jobs=m["jobs"][:1]),
        lambda m: m.update(embedding_sha256=None),
        lambda m: m["models"].pop("n"),
        lambda m: m.update(source="foreign"),
        lambda m: m.update(jobs=list(reversed(m["jobs"]))),
    ):
        altered = deepcopy(frozen)
        mutate(altered)
        with pytest.raises(ValueError):
            entry.verify_run_identity(altered, frozen, conditions)
    subset = deepcopy(frozen)
    subset.update(
        models={"n": frozen["models"]["n"]},
        jobs=frozen["jobs"][2:],
        embedding_sha256=None,
    )
    entry.verify_run_identity(subset, frozen, conditions)


def test_layout_rejects_archive_source_overlap_and_long_windows_paths(tmp_path):
    archive, checkout = tmp_path / "archive", tmp_path / "source"
    for output in (archive / "new", checkout / "raw", tmp_path):
        with pytest.raises(ValueError, match="overlap"):
            entry.validate_layout(archive, checkout, output, windows=False)
    entry.validate_layout(archive, checkout, tmp_path / "result 空白", windows=False)
    with pytest.raises(ValueError, match="short"):
        entry.validate_layout(archive, checkout, tmp_path / ("x" * 90), windows=True)


def test_existing_output_requires_explicit_resume_and_retained_inputs(tmp_path):
    archive = tmp_path / "archive"
    (archive / "experiment").mkdir(parents=True)
    for name in entry.INPUT_FILES:
        (archive / "experiment" / name).write_bytes(name.encode())
    output = tmp_path / "result"
    entry.prepare_output(archive, output, resume=False)
    original = (output / "inputs" / entry.INPUT_FILES[0]).read_bytes()
    with pytest.raises(FileExistsError):
        entry.prepare_output(archive, output, resume=False)
    assert (output / "inputs" / entry.INPUT_FILES[0]).read_bytes() == original
    entry.prepare_output(archive, output, resume=True)
    (output / "inputs" / entry.INPUT_FILES[0]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="input"):
        entry.prepare_output(archive, output, resume=True)


def test_environment_drift_cannot_become_a_baseline_run():
    frozen = {
        "python": "p",
        "machine": "x",
        "gpus": ["g"],
        "packages": [["torch", "v"]],
    }
    entry.verify_environment(frozen, frozen)
    for field, value in (("packages", []), ("python", "q"), ("gpus", ["other"])):
        with pytest.raises(ValueError, match="environment"):
            entry.verify_environment({**frozen, field: value}, frozen)


def test_frozen_import_rejects_already_loaded_product_before_chdir(
    tmp_path, monkeypatch
):
    # The test's own scripts import must not accidentally satisfy the rejection.
    for name in list(sys.modules):
        if name in {"scripts", "XBrainLab"} or name.startswith(
            ("scripts.", "XBrainLab.")
        ):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "XBrainLab", SimpleNamespace(__file__="foreign"))
    previous = Path.cwd()
    with pytest.raises(ValueError, match="already imported"):
        entry.load_frozen(tmp_path)
    assert Path.cwd() == previous


def test_real_git_restore_is_reused_but_never_resets_dirty_source(
    tmp_path, monkeypatch
):
    original = tmp_path / "source repo"
    original.mkdir()

    def git(*args):
        return subprocess.check_output(  # noqa: S603 - local temporary Git fixture
            [shutil.which("git"), "-C", str(original), *args],
            text=True,
            encoding="utf-8",
        ).strip()

    git("init", "-q")
    (original / "example.txt").write_bytes(b"original\nsecond line\n")
    git("config", "core.autocrlf", "false")
    git("add", "example.txt")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    sha = git("rev-parse", "HEAD")
    monkeypatch.setattr(entry, "SOURCE", sha)
    bundle = tmp_path / "source.bundle"
    git("bundle", "create", str(bundle), "HEAD")
    checkout = tmp_path / "restored 空白"
    entry.ensure_checkout(bundle, checkout, entry.digest(bundle))
    assert (checkout / "example.txt").read_bytes() == b"original\nsecond line\n"
    entry.ensure_checkout(bundle, checkout, entry.digest(bundle))
    (checkout / "example.txt").write_text("user change")
    with pytest.raises(ValueError, match="clean"):
        entry.ensure_checkout(bundle, checkout, entry.digest(bundle))
    assert (checkout / "example.txt").read_text() == "user change"
    monkeypatch.setattr(entry, "SOURCE", "0" * 40)
    with pytest.raises(ValueError, match="not frozen"):
        entry.ensure_checkout(bundle, checkout, entry.digest(bundle))
    assert (checkout / "example.txt").read_text() == "user change"


def test_archive_hash_failure_prevents_use(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text("original")
    monkeypatch.setattr(entry, "MANIFEST_SHA", hashlib.sha256(b"expected").hexdigest())
    with pytest.raises(ValueError, match="manifest"):
        entry.verify_archive(tmp_path)


def test_missing_or_changed_model_fails_content_check(tmp_path):
    weight = tmp_path / "weight.bin"
    weight.write_bytes(b"original")
    resources = {
        "models": {
            "m": {
                "snapshot": {
                    "root": str(tmp_path),
                    "files": [
                        {
                            "path": "weight.bin",
                            "bytes": 8,
                            "sha256": entry.digest(weight),
                        }
                    ],
                }
            }
        }
    }
    manifest = {"models": {"m": {}}, "embedding_sha256": None}
    assert entry.verify_resources(resources, manifest)["files_content_hashed"] == 1
    weight.write_bytes(b"modified")
    with pytest.raises(ValueError, match="content differs"):
        entry.verify_resources(resources, manifest)
    weight.unlink()
    with pytest.raises(FileNotFoundError):
        entry.verify_resources(resources, manifest)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows entry contract")
def test_second_entry_rejected_before_reading_archive(tmp_path, monkeypatch):
    from filelock import FileLock, Timeout

    lock = tmp_path / "entry.lock"
    monkeypatch.setattr(entry, "LOCK", lock)
    monkeypatch.setattr(entry, "validate_layout", lambda *a, **k: None)
    monkeypatch.setattr(
        entry,
        "verify_archive",
        lambda *a: pytest.fail("Lock must precede archive/source access"),
    )
    with FileLock(lock), pytest.raises(Timeout):
        entry.main(["--check", "--checkout", str(tmp_path / "different-source")])


@pytest.mark.parametrize("exit_code,complete", [(0, True), (7, False), (0, False)])
def test_attempt_reports_success_or_failure_without_overwriting(
    tmp_path, exit_code, complete
):
    root = tmp_path / "results"
    root.mkdir()

    def execute(manifest, bank, output, *, resume):
        assert not resume
        output.mkdir()
        (output / "manifest.json").write_text(json.dumps(manifest))
        return exit_code

    def write_report(raw, output):
        assert (raw / "manifest.json").is_file()
        output.mkdir()
        (output / "index.html").write_text("report")
        (output / "presentation-audit.json").write_text(
            json.dumps({"complete": complete, "issues": {}})
        )
        return {"complete_selected_schedule": complete, "pilot_complete": complete}

    runner, reporter = (
        SimpleNamespace(execute=execute),
        SimpleNamespace(write_report=write_report),
    )
    result = entry.run_attempt(
        runner, reporter, {"source": "fixture"}, {}, root, resume=False
    )
    assert result == (exit_code or (0 if complete else 1))
    assert (root / "index.html").is_file()
    assert "report" in (root / "index.html").read_text()
    assert len(list((root / "reports").glob("*/index.html"))) == 1
    receipt = json.loads(next((root / "launches").glob("*-end.json")).read_text())
    assert receipt["runner_exit_code"] == exit_code


def test_resume_calls_existing_runner_and_keeps_both_report_attempts(tmp_path):
    root = tmp_path / "results"
    root.mkdir()
    seen = []

    def execute(manifest, bank, output, *, resume):
        seen.append(resume)
        output.mkdir(exist_ok=True)
        (output / "manifest.json").write_text("{}")
        return 0

    def write_report(raw, output):
        output.mkdir()
        (output / "index.html").write_text(str(len(seen)))
        (output / "presentation-audit.json").write_text('{"complete":true,"issues":{}}')
        return {"complete_selected_schedule": True}

    runner, reporter = (
        SimpleNamespace(execute=execute),
        SimpleNamespace(write_report=write_report),
    )
    entry.run_attempt(runner, reporter, {}, {}, root, resume=False)
    first = next((root / "reports").glob("*/index.html"))
    entry.run_attempt(runner, reporter, {}, {}, root, resume=True)
    assert seen == [False, True]
    assert first.read_text() == "1"
    assert len(list((root / "reports").glob("*/index.html"))) == 2


def test_interrupt_preserves_partial_and_nonzero_status(tmp_path):
    def execute(*args, **kwargs):
        raise KeyboardInterrupt

    def report(*args):
        pytest.fail("No raw manifest exists; do not invent a report")

    assert (
        entry.run_attempt(
            SimpleNamespace(execute=execute),
            SimpleNamespace(write_report=report),
            {},
            {},
            tmp_path,
            resume=False,
        )
        == 130
    )
    assert "130" in (tmp_path / "README.md").read_text()
