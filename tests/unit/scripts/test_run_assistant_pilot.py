"""Pilot parent scheduling, immutable identity and durable execution boundaries."""

import json
import os
import sys
from copy import deepcopy

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


def test_condition_batches_load_each_model_rag_condition_once():
    selection = {
        "phase_one_case_ids": ["DEV-A", "DEV-C"],
        "phase_two_case_ids": ["DEV-N"],
    }
    jobs = runner.build_jobs(selection, ["granite4-rag-on", "granite4-rag-off"])
    batches = runner.condition_batches(jobs)
    assert [batch["condition"] for batch in batches] == [
        "granite4-rag-on",
        "granite4-rag-off",
    ]
    assert [[job["case_id"] for job in batch["jobs"]] for batch in batches] == [
        ["DEV-A", "DEV-C", "DEV-N"],
        ["DEV-A", "DEV-C", "DEV-N"],
    ]
    assert all({job["phase"] for job in batch["jobs"]} == {1, 2} for batch in batches)


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
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
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
        "(p/'result.json').write_text(json.dumps({'status':'measurement_failed','cleanup_ok':True,'results':[]}))\n"
        "print('evidence')\nsys.exit(7)\n"
    )
    monkeypatch.setattr(
        runner,
        "_condition_command",
        lambda request, destination, cases_root: [
            sys.executable,
            str(child),
            str(request),
            str(destination),
            str(cases_root),
        ],
    )
    assert runner.execute(manifest, bank, output) != 0
    records = runner.read_journal(output)
    ends = [record for record in records if record["event"] == "case_end"]
    assert ends == []  # An unstarted/unreported case must remain missing evidence.
    condition_end = next(
        record for record in records if record["event"] == "condition_end"
    )
    assert condition_end["returncode"] == 7
    assert condition_end["status"] == "failed"
    assert (
        output / "conditions" / "phi4-rag-off.request.stdout.log"
    ).read_text().strip() == "evidence"
    monkeypatch.setattr(
        runner,
        "_condition_command",
        lambda *_: pytest.fail("resent completed failure"),
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


def test_dev_platform_drift_is_rejected_before_launch(run_inputs, monkeypatch):
    manifest, _bank, _output = run_inputs
    manifest["experiment"] = dict(runner.DEV_EXPERIMENT)
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    with pytest.raises(ValueError, match="Qt platform"):
        runner._assert_identity(manifest)


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
        "import json,pathlib,sys\n"
        "req=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "p=pathlib.Path(sys.argv[2]);p.mkdir()\n"
        "cases=pathlib.Path(sys.argv[3]); rows=[]\n"
        "for job in req['jobs']:\n"
        " d=cases/job['id'];d.mkdir();"
        f"r={result!r};"
        "(d/'result.json').write_text(json.dumps(r));"
        "rows.append({'id':job['id'],'case_id':job['payload']['case']['case_id'],'status':r['status'],'cleanup_ok':r['cleanup_ok']})\n"
        f"summary={result!r};summary['results']=rows;"
        "(p/'result.json').write_text(json.dumps(summary))\n"
    )
    monkeypatch.setattr(
        runner,
        "_condition_command",
        lambda request, destination, cases_root: [
            sys.executable,
            str(child),
            str(request),
            str(destination),
            str(cases_root),
        ],
    )


def test_uncertified_cleanup_refuses_resume(run_inputs, tmp_path, monkeypatch):
    manifest, bank, output = run_inputs
    _child_result(tmp_path, monkeypatch, {"status": "recorded", "cleanup_ok": False})
    assert runner.execute(manifest, bank, output) == 1
    monkeypatch.setattr(
        runner, "_condition_command", lambda *_: pytest.fail("unsafe resume")
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


def test_dev_explicit_replacement_preserves_failure_and_never_resends_valid_case(
    run_inputs, tmp_path, monkeypatch
):
    manifest, bank, output = run_inputs
    manifest["experiment"] = dict(runner.DEV_EXPERIMENT)
    manifest["jobs"][0]["condition"] = "phi4-rag-on"
    manifest["jobs"][0]["id"] = "phi4-rag-on__DEV-A"
    manifest["embedding_sha256"] = "fixture"
    manifest["config"]["embedding_cache"] = str(tmp_path)
    monkeypatch.setattr(
        runner,
        "prepare_rag_cache",
        lambda *a, **k: {"cache_root": str(tmp_path), "embedding_sha256": "fixture"},
    )
    monkeypatch.setattr(runner, "verify_rag_cache", lambda *_: None)
    bank["cases"].append({**bank["cases"][0], "case_id": "DEV-B"})
    manifest["jobs"].append(
        {**manifest["jobs"][0], "id": "phi4-rag-on__DEV-B", "case_id": "DEV-B"}
    )
    calls = []

    def child(request, destination, cases_root, timeout, *, on_started):
        payload = runner._json(request)
        calls.append([job["payload"]["case"]["case_id"] for job in payload["jobs"]])
        destination.mkdir()
        rows = []
        for job in payload["jobs"]:
            directory = cases_root / job["id"]
            directory.mkdir()
            result = {
                "status": "measurement_failed"
                if len(calls) == 1 and job["payload"]["case"]["case_id"] == "DEV-B"
                else "recorded",
                "cleanup_ok": True,
                "correct": False,
            }
            runner._write_new(directory / "result.json", result)
            rows.append({"id": job["id"], **result})
        runner._write_new(
            destination / "result.json",
            {
                "status": "recorded" if len(calls) > 1 else "measurement_failed",
                "cleanup_ok": True,
                "results": rows,
            },
        )
        return (0 if len(calls) > 1 else 1), False

    monkeypatch.setattr(runner, "_run_condition_child", child)
    assert runner.execute(manifest, bank, output) == 1
    original = (output / "cases" / "phi4-rag-on__DEV-B" / "result.json").read_bytes()
    assert runner.execute(manifest, bank, output, resume=True) == 1
    assert len(calls) == 1
    assert (
        runner.execute(manifest, bank, output, resume=True, replace_invalid=True) == 0
    )
    assert calls == [["DEV-A", "DEV-B"], ["DEV-B"]]
    assert (
        output / "cases" / "phi4-rag-on__DEV-B" / "result.json"
    ).read_bytes() == original
    ends = [item for item in runner.read_journal(output) if item["event"] == "case_end"]
    replacement = ends[-1]
    assert replacement["id"] == "phi4-rag-on__DEV-B"
    assert replacement["artifact_id"] == "phi4-rag-on__DEV-B__attempt-2"
    assert replacement["replaces_artifact_id"] == "phi4-rag-on__DEV-B"
    assert (
        runner.execute(manifest, bank, output, resume=True, replace_invalid=True) == 0
    )
    assert len(calls) == 2


def test_dev_resume_cannot_run_while_same_output_is_locked(run_inputs):
    from filelock import FileLock, Timeout

    manifest, bank, output = run_inputs
    manifest["experiment"] = dict(runner.DEV_EXPERIMENT)
    lock = output.with_name(f".{output.name}.dev.lock")
    with FileLock(str(lock), timeout=0), pytest.raises(Timeout):
        runner.execute(manifest, bank, output, resume=True)


def test_configured_valid_runs_real_children_per_repeat_and_never_resends_wrong_valid(
    run_inputs, tmp_path, monkeypatch
):
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook
    from tests.unit.scripts.test_run_assistant_dev import experiment_config, valid_rows

    manifest, bank, output = run_inputs
    config = experiment_config(tmp_path)
    config["models"] = [config["models"][1]]
    manifest["config"] = config
    manifest["runtime_config"] = {
        "model_caches": {runner._MODELS["phi4"]: str(tmp_path)},
        "embedding_cache": str(tmp_path),
        "sources": {"phi4": config["models"][0]["source"]},
    }
    bank = runner.load_bank(_workbook(tmp_path, valid_rows()))
    manifest["experiment"] = runner.experiment_config.experiment_identity(config)
    selection = runner.experiment_config.build_selection(bank, config)
    manifest["selection"] = selection
    manifest["budget_seconds"] = config["budget_seconds"]
    manifest["jobs"] = runner.experiment_config.build_jobs(selection, config)
    decisions = {case["case_id"]: case["decision"] for case in bank["cases"]}
    for job in manifest["jobs"]:
        job["decision"] = decisions[job["case_id"]]
    manifest["embedding_sha256"] = "fixture"
    monkeypatch.setattr(runner, "_verify_candidate_source", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "prepare_rag_cache",
        lambda *a, **k: {"cache_root": str(tmp_path), "embedding_sha256": "fixture"},
    )
    monkeypatch.setattr(runner, "verify_rag_cache", lambda *_: None)
    with monkeypatch.context() as guarded:
        guarded.setattr(
            runner,
            "_run_condition_child",
            lambda *_a, **_k: pytest.fail("invalid derived identity reached a child"),
        )
        for key, value in (
            ("candidate_index", 6),
            ("repeat", 4),
            ("source_root", "wrong-source"),
        ):
            changed = deepcopy(manifest)
            changed["jobs"][0][key] = value
            target = output.with_name("invalid-" + key)
            with pytest.raises(ValueError, match="derived"):
                runner.execute(changed, bank, target)
            assert not target.exists()
        changed = deepcopy(manifest)
        changed["budget_seconds"] = 14400
        with pytest.raises(ValueError, match="derived"):
            runner.execute(changed, bank, output)
    _child_result(
        tmp_path,
        monkeypatch,
        {"status": "recorded", "cleanup_ok": True, "correct": False},
    )
    assert runner.execute(manifest, bank, output) == 0
    requests = sorted((output / "conditions").glob("*.request.json"))
    assert len(requests) == 3
    assert {runner._json(path)["repeat"] for path in requests} == {0, 1, 2}
    for path in requests:
        payload = runner._json(path)
        assert payload["candidate_index"] == 5
        assert payload["source_head"] == "5" * 40
        assert payload["jobs"][0]["payload"]["repeat"] == payload["repeat"]
    original = {str(path): path.read_bytes() for path in output.rglob("result.json")}
    monkeypatch.setattr(
        runner,
        "_condition_command",
        lambda *_: pytest.fail("resent a valid wrong answer"),
    )
    assert (
        runner.execute(manifest, bank, output, resume=True, replace_invalid=True) == 0
    )
    assert {
        str(path): path.read_bytes() for path in output.rglob("result.json")
    } == original


def test_configured_subset_spawns_only_selected_two_model_conditions(
    run_inputs, tmp_path, monkeypatch
):
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook
    from tests.unit.scripts.test_run_assistant_dev import experiment_config

    manifest, _bank, output = run_inputs
    config = experiment_config(tmp_path, "DEV")
    config.update(purpose="engineering-smoke", case_ids=["DEV-A01-01-V0"])
    bank = runner.load_bank(_workbook(tmp_path))  # Public synthetic fixture only.
    selection = runner.experiment_config.build_selection(bank, config)
    manifest.update(
        config=config,
        experiment=runner.experiment_config.experiment_identity(config),
        selection=selection,
        jobs=runner.experiment_config.build_jobs(selection, config),
        budget_seconds=config["budget_seconds"],
        embedding_sha256="fixture",
        runtime_config={
            "model_caches": {
                runner._MODELS[item["alias"]]: str(tmp_path)
                for item in config["models"]
            },
            "embedding_cache": str(tmp_path),
            "sources": {item["alias"]: item["source"] for item in config["models"]},
        },
    )
    decisions = {case["case_id"]: case["decision"] for case in bank["cases"]}
    for job in manifest["jobs"]:
        job["decision"] = decisions[job["case_id"]]
    # Isolate external source/cache/model work, not scheduling or child spawning.
    monkeypatch.setattr(runner, "_verify_candidate_source", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "prepare_rag_cache",
        lambda *_a, **_k: {"cache_root": str(tmp_path), "embedding_sha256": "fixture"},
    )
    _child_result(tmp_path, monkeypatch, {"status": "recorded", "cleanup_ok": True})
    processes = []
    popen = runner.subprocess.Popen

    def observe_spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", observe_spawn)
    assert runner.execute(manifest, bank, output) == 0
    assert len(processes) == 2
    assert all(process.poll() == 0 for process in processes)
    requests = [runner._json(runner.Path(process.args[2])) for process in processes]
    # This oracle is independent of build_jobs/manifest: no third model or RAG-off.
    assert sorted(
        (request["condition"], request["jobs"][0]["payload"]["model_id"])
        for request in requests
    ) == [
        ("granite4-rag-on", "ibm-granite/granite-4.0-micro"),
        ("phi4-rag-on", "microsoft/Phi-4-mini-instruct"),
    ]
    assert all(
        len(request["jobs"]) == 1
        and request["jobs"][0]["payload"]["case"]["case_id"] == "DEV-A01-01-V0"
        and request["jobs"][0]["payload"]["rag_enabled"] is True
        and request["repeat"] == 0
        for request in requests
    )
    records = runner.read_journal(output)
    assert [row["pid"] for row in records if row["event"] == "child_started"] == [
        process.pid for process in processes
    ]
    assert len(list((output / "cases").glob("*/result.json"))) == 2


@pytest.mark.parametrize("valid", [True, False])
def test_dev_attempt_limit_and_changed_original_evidence(run_inputs, valid):
    manifest, _bank, output = run_inputs
    output.mkdir()
    job = manifest["jobs"][0]
    destination = output / "cases" / (job["id"] + "__attempt-2")
    destination.mkdir(parents=True)
    result_path = destination / "result.json"
    runner._write_new(result_path, {"status": "measurement_failed", "cleanup_ok": True})
    records = [
        {
            "event": "case_end",
            "id": job["id"],
            "artifact_id": destination.name,
            "attempt": 2,
            "status": "failed",
            "cleanup_certified": True,
            "result_sha256": runner.hashlib.sha256(result_path.read_bytes()).hexdigest()
            if valid
            else "wrong",
        }
    ]
    if valid:
        assert runner._dev_pending_jobs([job], records, output, True) == ([], True)
    else:
        with pytest.raises(ValueError, match="evidence changed"):
            runner._dev_pending_jobs([job], records, output, True)


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
        runner, "_condition_command", lambda *_: pytest.fail("budget overspend")
    )
    assert runner.execute(manifest, bank, output, resume=True) == 2
    assert not any(
        record["event"] == "case_start" for record in runner.read_journal(output)
    )


def test_unresolved_started_condition_is_not_resent_even_with_session_end(
    run_inputs, monkeypatch
):
    manifest, bank, output = run_inputs
    output.mkdir()
    runner._write_new(output / "manifest.json", manifest)
    runner._append(
        output,
        {
            "event": "condition_start",
            "session": "old",
            "elapsed_seconds": 1,
            "id": "phi4-rag-off",
            "timeout_seconds": runner.CONDITION_TIMEOUT_SECONDS,
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
        runner,
        "_condition_command",
        lambda *_: pytest.fail("resent unresolved condition"),
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


@pytest.mark.parametrize("condition", [False, True], ids=["case", "condition"])
def test_parent_timeout_records_and_reaps_only_its_child(
    tmp_path, monkeypatch, condition
):
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(120)\n")
    monkeypatch.setattr(
        runner,
        "_condition_command" if condition else "_case_command",
        lambda *_: [runner._python_executable(), str(child)],
    )
    processes = []
    real_popen = runner.subprocess.Popen

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    request = tmp_path / "case.request.json"
    request.write_text("{}")
    owned = []
    if condition:
        returncode, timed_out = runner._run_condition_child(
            request,
            tmp_path / "condition",
            tmp_path / "cases",
            0.1,
            on_started=owned.append,
        )
    else:
        returncode, timed_out = runner._run_child(
            request,
            tmp_path / "case",
            0.1,
            on_started=owned.append,
        )
    assert len(owned) == 1 and owned[0] > 0
    assert timed_out is True and returncode != 0
    assert len(processes) == 1 and processes[0].pid == owned[0]
    assert processes[0].poll() == returncode
    assert (tmp_path / "case.request.stdout.log").is_file()


def test_child_process_hides_windows_console_without_changing_other_platforms():
    assert runner._child_creation_flags("nt") == runner._WINDOWS_CREATE_NO_WINDOW
    assert runner._child_creation_flags("posix") == 0


def test_child_launch_pid_and_virtual_environment_are_exact(tmp_path, monkeypatch):
    child = tmp_path / "child.py"
    child.write_text(
        "import os,sys,json\n"
        "print(json.dumps(dict(pid=os.getpid(),prefix=sys.prefix,executable=sys.executable)))\n"
    )
    monkeypatch.setattr(
        runner, "_case_command", lambda *_: [runner._python_executable(), str(child)]
    )
    real_popen = runner.subprocess.Popen
    launch_flags = []

    def spawn(*args, **kwargs):
        launch_flags.append(kwargs.get("creationflags"))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
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
    assert launch_flags == [runner._child_creation_flags()]


@pytest.mark.platform_contract
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
