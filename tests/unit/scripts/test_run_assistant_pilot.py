"""Pilot parent scheduling, immutable identity and durable execution boundaries."""

import json
import os
import sys

import pytest

from scripts.dev import run_assistant_pilot as runner


def test_conditions_and_phase_order_are_fixed():
    conditions = runner.select_conditions("all")
    assert len(conditions) == 10
    selection = {
        "phase_one_case_ids": ["DEV-A", "DEV-C"],
        "phase_two_case_ids": ["DEV-N"],
    }
    jobs = runner.build_jobs(selection, conditions)
    assert len(jobs) == 30
    assert all(job["phase"] == 1 for job in jobs[:20])
    assert all(job["phase"] == 2 for job in jobs[20:])
    assert len({job["id"] for job in jobs}) == 30
    assert runner.select_conditions("phi4-rag-off,granite4-rag-on") == [
        "granite4-rag-on",
        "phi4-rag-off",
    ]
    with pytest.raises(ValueError):
        runner.select_conditions("missing")
    with pytest.raises(ValueError):
        runner.select_conditions("phi4-rag-off,phi4-rag-off")


def test_unfinished_child_budget_is_reserved_not_user_idle():
    records = [
        {"event": "session_start", "session": "s", "elapsed_seconds": 2},
        {
            "event": "case_start",
            "session": "s",
            "elapsed_seconds": 3,
            "id": "a",
            "timeout_seconds": 450,
        },
    ]
    assert runner.consumed_seconds(records) == 453
    records.append(
        {
            "event": "case_end",
            "session": "s",
            "elapsed_seconds": 20,
            "id": "a",
            "status": "failed",
        }
    )
    records.append({"event": "session_end", "session": "s", "elapsed_seconds": 21})
    records.extend(
        [
            {"event": "session_start", "session": "next", "elapsed_seconds": 1},
            {"event": "session_end", "session": "next", "elapsed_seconds": 4},
        ]
    )
    assert runner.consumed_seconds(records) == 25


@pytest.fixture
def run_inputs(tmp_path, monkeypatch):
    source = {"head": "a" * 40, "dirty": []}
    environment = {"python": "fixture"}
    monkeypatch.setattr(runner, "source_identity", lambda: source)
    monkeypatch.setattr(runner, "environment_identity", lambda: environment)
    condition = "phi4-rag-off"
    bank = {
        "cases": [{"case_id": "DEV-A", "split": "DEV", "fixture_id": "fx"}],
        "fixtures": {"fx": {"conditions": {"stage": "empty"}}},
    }
    manifest = {
        "schema": runner.SCHEMA,
        "source": source,
        "environment": environment,
        "config": {"model_caches": {runner.CONDITIONS[condition][0]: str(tmp_path)}},
        "jobs": runner.build_jobs(
            {"phase_one_case_ids": ["DEV-A"], "phase_two_case_ids": []}, [condition]
        ),
        "budget_seconds": 14400,
    }
    return manifest, bank, tmp_path / "run"


def test_real_child_failure_is_preserved_and_not_resent_on_resume(
    run_inputs, tmp_path, monkeypatch
):
    manifest, bank, output = run_inputs
    child = tmp_path / "child.py"
    child.write_text(
        "import json,pathlib,sys\np=pathlib.Path(sys.argv[2]);p.mkdir()\n"
        "(p/'result.json').write_text(json.dumps({'status':'measurement_failed','cleanup_ok':True}))\n"
        "print('evidence')\nsys.exit(7)\n"
    )
    monkeypatch.setattr(
        runner,
        "_case_command",
        lambda request, destination: [
            sys.executable,
            str(child),
            str(request),
            str(destination),
        ],
    )
    assert runner.execute(manifest, bank, output) != 0
    records = runner.read_journal(output)
    ends = [record for record in records if record["event"] == "case_end"]
    assert len(ends) == 1
    assert ends[0]["returncode"] == 7
    assert ends[0]["status"] == "failed"
    assert (
        output / "cases" / (manifest["jobs"][0]["id"] + ".request.stdout.log")
    ).read_text().strip() == "evidence"
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: pytest.fail("resent completed failure")
    )
    assert runner.execute(manifest, bank, output, resume=True) != 0


def test_dirty_or_changed_identity_never_starts_child(run_inputs, monkeypatch):
    manifest, bank, output = run_inputs
    monkeypatch.setattr(
        runner, "source_identity", lambda: {"head": "b" * 40, "dirty": []}
    )
    with pytest.raises(ValueError, match="identity"):
        runner.execute(manifest, bank, output)
    assert not output.exists()


def test_resume_manifest_mismatch_preserves_existing_files(run_inputs):
    manifest, bank, output = run_inputs
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps({**manifest, "budget_seconds": 9}))
    with pytest.raises(ValueError, match="manifest"):
        runner.execute(manifest, bank, output, resume=True)
    assert json.loads((output / "manifest.json").read_text())["budget_seconds"] == 9


def test_truncated_journal_fails_closed(tmp_path):
    (tmp_path / "journal.jsonl").write_text('{"event":')
    with pytest.raises(ValueError):
        runner.read_journal(tmp_path)


def _child_result(tmp_path, monkeypatch, result):
    child = tmp_path / "child.py"
    child.write_text(
        "import json,pathlib,sys\np=pathlib.Path(sys.argv[2]);p.mkdir()\n"
        f"(p/'result.json').write_text({json.dumps(json.dumps(result))})\n"
    )
    monkeypatch.setattr(
        runner,
        "_case_command",
        lambda request, destination: [
            sys.executable,
            str(child),
            str(request),
            str(destination),
        ],
    )


def test_uncertified_cleanup_refuses_resume(run_inputs, tmp_path, monkeypatch):
    manifest, bank, output = run_inputs
    _child_result(tmp_path, monkeypatch, {"status": "recorded", "cleanup_ok": False})
    assert runner.execute(manifest, bank, output) == 1
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: pytest.fail("unsafe resume")
    )
    with pytest.raises(ValueError, match="cleanup"):
        runner.execute(manifest, bank, output, resume=True)


def test_recorded_wrong_answer_is_measurement_not_engineering_failure(
    run_inputs, tmp_path, monkeypatch
):
    manifest, bank, output = run_inputs
    bank["cases"].append({**bank["cases"][0], "case_id": "DEV-B"})
    manifest["jobs"] = runner.build_jobs(
        {"phase_one_case_ids": ["DEV-A"], "phase_two_case_ids": ["DEV-B"]},
        ["phi4-rag-off"],
    )
    _child_result(
        tmp_path,
        monkeypatch,
        {"status": "recorded", "cleanup_ok": True, "correct": False},
    )
    assert runner.execute(manifest, bank, output) == 0
    ends = [
        record
        for record in runner.read_journal(output)
        if record["event"] == "case_end"
    ]
    assert [record["id"] for record in ends] == [job["id"] for job in manifest["jobs"]]
    assert all(record["status"] == "recorded" for record in ends)


def test_resumed_budget_prevents_starting_a_case_without_full_timeout(
    run_inputs, monkeypatch
):
    manifest, bank, output = run_inputs
    output.mkdir()
    runner._write_new(output / "manifest.json", manifest)
    runner._append(
        output,
        {
            "event": "session_end",
            "session": "old",
            "elapsed_seconds": 14000,
            "cleanup_certified": True,
        },
    )
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: pytest.fail("budget overspend")
    )
    assert runner.execute(manifest, bank, output, resume=True) == 2
    assert not any(
        record["event"] == "case_start" for record in runner.read_journal(output)
    )


def test_unresolved_started_case_is_not_resent_even_with_session_end(
    run_inputs, monkeypatch
):
    manifest, bank, output = run_inputs
    output.mkdir()
    runner._write_new(output / "manifest.json", manifest)
    runner._append(
        output,
        {
            "event": "case_start",
            "session": "old",
            "elapsed_seconds": 1,
            "id": manifest["jobs"][0]["id"],
            "timeout_seconds": 450,
        },
    )
    runner._append(
        output,
        {
            "event": "session_end",
            "session": "old",
            "elapsed_seconds": 2,
            "cleanup_certified": True,
        },
    )
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: pytest.fail("resent unresolved case")
    )
    with pytest.raises(ValueError, match="never be resent"):
        runner.execute(manifest, bank, output, resume=True)


def test_source_identity_ignores_only_daily_settings(monkeypatch):
    def git(*args):
        if args[0] == "diff":
            return "settings.json\0"
        if args[0] == "ls-files":
            return "scripts/dev/new.py\0build/log.txt\0settings.json\0"
        return "a" * 40

    monkeypatch.setattr(runner, "_git", git)
    assert runner.source_identity() == {
        "head": "a" * 40,
        "dirty": ["scripts/dev/new.py"],
    }


def test_model_configuration_hash_detects_template_change(tmp_path):
    model = "microsoft/Phi-4-mini-instruct"
    spec = runner.research_model_spec(model)
    snapshot = (
        tmp_path / f"models--{model.replace('/', '--')}" / "snapshots" / spec.revision
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    (snapshot / "tokenizer_config.json").write_text('{"chat_template":"one"}')
    before = runner._model_configuration(model, str(tmp_path))
    (snapshot / "tokenizer_config.json").write_text('{"chat_template":"two"}')
    assert runner._model_configuration(model, str(tmp_path)) != before


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf"), "10"])
def test_corrupt_elapsed_time_cannot_buy_more_budget(seconds):
    with pytest.raises(ValueError, match="elapsed"):
        runner.consumed_seconds(
            [{"event": "session_end", "session": "s", "elapsed_seconds": seconds}]
        )


def test_parent_timeout_records_and_reaps_only_its_child(tmp_path, monkeypatch):
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(120)\n")
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: [runner._python_executable(), str(child)]
    )
    owned = []
    returncode, timed_out = runner._run_child(
        tmp_path / "case.request.json",
        tmp_path / "case",
        0.1,
        on_started=owned.append,
    )
    assert len(owned) == 1 and owned[0] > 0
    assert timed_out is True and returncode != 0
    assert (tmp_path / "case.request.stdout.log").is_file()


def test_child_launch_pid_and_virtual_environment_are_exact(tmp_path, monkeypatch):
    child = tmp_path / "child.py"
    child.write_text(
        "import os,sys,json\n"
        "print(json.dumps(dict(pid=os.getpid(),prefix=sys.prefix,executable=sys.executable)))\n"
    )
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: [runner._python_executable(), str(child)]
    )
    owned = []
    code, timed_out = runner._run_child(
        tmp_path / "identity.request.json",
        tmp_path / "case",
        20,
        on_started=owned.append,
    )
    observed = json.loads((tmp_path / "identity.request.stdout.log").read_text())
    assert code == 0 and timed_out is False
    assert observed == {
        "pid": owned[0],
        "prefix": sys.prefix,
        "executable": sys.executable,
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows view of an explicit WSL gitfile")
def test_windows_git_location_uses_exact_gitfile_without_rewriting(
    tmp_path, monkeypatch
):
    root = tmp_path / "checkout"
    root.mkdir()
    gitdir = tmp_path / "worktree-data"
    gitdir.mkdir()
    posix = f"/mnt/{gitdir.drive[0].lower()}/{gitdir.as_posix()[3:]}"
    content = f"gitdir: {posix}\n"
    (root / ".git").write_text(content)
    monkeypatch.setattr(runner, "ROOT", root)
    assert runner._git_location() == [
        f"--git-dir={gitdir.resolve()}",
        f"--work-tree={root}",
    ]
    assert (root / ".git").read_text() == content
