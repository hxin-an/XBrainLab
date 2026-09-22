"""Full DEV selection and immutable replacement preserve the research denominator."""

import json
import subprocess
from collections import Counter
from copy import deepcopy

import pytest

from scripts.dev import assistant_pilot_bank as bank_reader
from scripts.dev import run_assistant_pilot as runner


def fixture_git(root, *arguments):
    return subprocess.check_output(  # noqa: S603 - fixed test commands in an owned temporary Git fixture
        [runner._executable("git"), "-C", str(root), *arguments], text=True, timeout=15
    ).strip()


def experiment_config(tmp_path, split="VALID"):
    return {
        "schema": "xbrainlab.assistant_experiment_config.v1",
        "split": split,
        "purpose": "research",
        "models": [
            {
                "alias": alias,
                "candidate_index": candidate,
                "source": {"head": str(candidate) * 40, "root": str(tmp_path)},
                "model_cache": str(tmp_path),
            }
            for alias, candidate in (("granite4", 1), ("phi4", 5))
        ],
        "embedding_cache": str(tmp_path),
        "resource_inventory": "resources.json",
        "budget_seconds": 3600,
    }


def valid_rows():
    from tests.unit.scripts.test_assistant_pilot_bank import _rows

    rows = _rows()
    human, truth, fixture = (
        rows["VALID"].pop(),
        rows["ground_truth"].pop(),
        rows["情境定義"].pop(),
    )
    for category, families, decision in (
        ("A", 18, "Action"),
        ("C", 6, "Clarification"),
        ("N", 9, "No-call"),
    ):
        for number in range(1, families + 1):
            family = f"VALID-{category}{number:02}-01"
            fx = "FX-" + family
            rows["情境定義"].append({**fixture, "fixture_id": fx, "family_id": family})
            for repeat in range(3):
                case_id = f"{family}-V{repeat}"
                rows["VALID"].append(
                    {**human, "題號": case_id, "Family": family, "情境編號": fx}
                )
                rows["ground_truth"].append(
                    {
                        **truth,
                        "case_id": case_id,
                        "family_id": family,
                        "fixture_id": fx,
                        "decision": decision,
                        "expected_tool": "import_eeg_data"
                        if decision == "Action"
                        else "respond_to_user",
                        "expected_parameters_json": "{}"
                        if decision == "Action"
                        else "N/A: message is free text; use parameter_rule",
                    }
                )
    return rows


def test_configured_valid_selection_reads_real_bank_and_keeps_three_repeats(tmp_path):
    from scripts.dev import assistant_experiment_config as protocol
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook

    config = experiment_config(tmp_path)
    bank = bank_reader.load_bank(_workbook(tmp_path, valid_rows()))
    experiment = protocol.experiment_identity(config)
    selection = protocol.build_selection(bank, config)
    jobs = protocol.build_jobs(selection, config)
    assert experiment["repeats"] == [0, 1, 2]
    assert experiment["seed"] == 0
    assert len(jobs) == len({job["id"] for job in jobs}) == 594
    assert len({job["case_id"] for job in jobs}) == 99
    assert {job["candidate_index"] for job in jobs} == {1, 5}
    assert all(job["split"] == "VALID" for job in jobs)
    assert len(runner.condition_batches(jobs)) == 6
    assert all(job["source_head"] == str(job["candidate_index"]) * 40 for job in jobs)


def test_incomplete_research_bank_cannot_be_silently_used_as_smoke(tmp_path):
    from scripts.dev import assistant_experiment_config as protocol
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook

    bank = bank_reader.load_bank(_workbook(tmp_path))
    with pytest.raises(ValueError, match="population"):
        protocol.build_selection(bank, experiment_config(tmp_path))


@pytest.mark.parametrize(
    "change",
    ["sixth", "zero", "bool", "test", "seed", "repeat", "duplicate", "unknown"],
)
def test_experiment_config_rejects_unapproved_identity(tmp_path, change):
    from scripts.dev import assistant_experiment_config as protocol

    config = experiment_config(tmp_path)
    if change in {"sixth", "zero", "bool"}:
        config["models"][0]["candidate_index"] = {"sixth": 6, "zero": 0, "bool": True}[
            change
        ]
    elif change == "test":
        config["split"] = "TEST"
    elif change == "duplicate":
        config["models"].append(deepcopy(config["models"][0]))
    else:
        config[change] = 99
    with pytest.raises(ValueError):
        protocol.experiment_identity(config)


def test_experiment_smoke_selection_is_explicit_and_never_crosses_split(tmp_path):
    from scripts.dev import assistant_experiment_config as protocol
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook

    config = experiment_config(tmp_path, "DEV")
    config["purpose"] = "engineering-smoke"
    config["case_ids"] = ["DEV-A01-01-V0"]
    bank = bank_reader.load_bank(_workbook(tmp_path))
    assert protocol.build_selection(bank, config)["case_ids"] == config["case_ids"]
    assert protocol.experiment_identity(config)["repeats"] == [0]
    config["case_ids"] = ["VALID-A01-01-V0"]
    with pytest.raises(ValueError):
        protocol.build_selection(bank, config)


def test_new_config_preparation_resolves_paths_without_editing_input(
    tmp_path, monkeypatch
):
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook

    config = experiment_config(tmp_path, "DEV")
    config.update(purpose="engineering-smoke", case_ids=["DEV-A01-01-V0"])
    for model in config["models"]:
        model["source"]["root"] = "."
        model["model_cache"] = "."
    config["embedding_cache"] = "."
    resources = []
    for repo, revision in [
        (
            runner._MODELS[item["alias"]],
            runner.research_model_spec(runner._MODELS[item["alias"]]).revision,
        )
        for item in config["models"]
    ] + [(runner.RAGConfig.EMBEDDING_MODEL, runner.RAGConfig.EMBEDDING_REVISION)]:
        snapshot = (
            tmp_path / ("models--" + repo.replace("/", "--")) / "snapshots" / revision
        )
        snapshot.mkdir(parents=True)
        weight = snapshot / "model.safetensors"
        weight.write_bytes(b"synthetic weight payload")
        resources.append(
            {
                "repo": repo,
                "revision": revision,
                "files": {
                    weight.name: {
                        "bytes": weight.stat().st_size,
                        "sha256": runner.hashlib.sha256(
                            weight.read_bytes()
                        ).hexdigest(),
                    }
                },
            }
        )
    inventory = tmp_path / "resources.json"
    inventory.write_text(json.dumps({"resources": resources}))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(runner, "_verify_candidate_source", lambda *_: None)
    monkeypatch.setattr(
        runner, "source_identity", lambda: {"head": "f" * 40, "dirty": []}
    )
    monkeypatch.setattr(
        runner, "environment_identity", lambda: {"platform": "synthetic-linux"}
    )
    monkeypatch.setattr(
        runner, "_model_configuration", lambda *_: {"config.json": "c" * 64}
    )
    monkeypatch.setattr(runner.RAGConfig, "embedding_cache_ready", lambda _: True)
    monkeypatch.setattr(runner, "_identity", lambda _: ("e" * 64, {}))
    manifest, _bank = runner.prepare_manifest(
        _workbook(tmp_path), None, path, [], dev_initial=True
    )
    assert manifest["config"] == config
    assert path.read_bytes() == original
    assert manifest["environment"]["platform"] == "synthetic-linux"
    assert manifest["runtime_config"]["embedding_cache"] == str(tmp_path)
    assert {job["source_root"] for job in manifest["jobs"]} == {str(tmp_path)}
    assert manifest["budget_seconds"] == 3600
    assert manifest["resource_inventory"] == {"resources": resources}
    assert (
        manifest["resource_inventory_sha256"]
        == runner.hashlib.sha256(inventory.read_bytes()).hexdigest()
    )
    original_size = weight.stat().st_size
    weight.write_bytes(b"tampered weight payload!")
    assert weight.stat().st_size == original_size
    with pytest.raises(ValueError, match="resource"):
        runner.prepare_manifest(
            tmp_path / "bank.xlsx", None, path, [], dev_initial=True
        )
    weight.unlink()
    with pytest.raises(ValueError, match="resource"):
        runner.prepare_manifest(
            tmp_path / "bank.xlsx", None, path, [], dev_initial=True
        )


def test_candidate_source_missing_protocol_is_refused_even_at_exact_clean_head(
    tmp_path,
):
    fixture_git(tmp_path, "init")
    fixture_git(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "Fixture",
    )
    head = fixture_git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="protocol"):
        runner._verify_candidate_source(tmp_path, head)


def test_linux_gpu_lock_is_shared_across_package_roots():
    from scripts.dev import run_assistant_dev as entry

    assert (
        entry.gpu_lock_path(platform="posix", uid=42).as_posix()
        == "/tmp/xbrainlab-assistant-gpu-42.lock"
    )
    assert entry.gpu_lock_path(platform="nt") == entry.LOCK


def test_candidate_dependency_lock_mismatch_is_rejected_before_child(tmp_path):
    helper = tmp_path / "scripts" / "dev" / "assistant_experiment_config.py"
    helper.parent.mkdir(parents=True)
    helper.write_text('PROTOCOL = "xbrainlab.assistant_experiment.v1"\n')
    (tmp_path / "poetry.lock").write_text("different locked environment\n")
    fixture_git(tmp_path, "init")
    fixture_git(tmp_path, "add", ".")
    fixture_git(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Fixture",
    )
    head = fixture_git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="dependency lock"):
        runner._verify_candidate_source(tmp_path, head)


def test_candidate_same_lock_changed_model_factory_is_refused(tmp_path):
    helper = tmp_path / "scripts" / "dev" / "assistant_experiment_config.py"
    helper.parent.mkdir(parents=True)
    helper.write_text('PROTOCOL = "xbrainlab.assistant_experiment.v1"\n')
    (tmp_path / "poetry.lock").write_bytes((runner.ROOT / "poetry.lock").read_bytes())
    (helper.parent / "assistant_pilot_models.py").write_text(
        "# changed generation policy\n"
    )
    fixture_git(tmp_path, "init")
    fixture_git(tmp_path, "add", ".")
    fixture_git(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Fixture",
    )
    head = fixture_git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match=r"policy.*assistant_pilot_models"):
        runner._verify_candidate_source(tmp_path, head)


def full_bank():
    cases = []
    for prefix, groups, families, decision in (
        ("A", 18, 2, "Action"),
        ("C", 6, 2, "Clarification"),
        ("N", 3, 6, "No-call"),
    ):
        for group in range(1, groups + 1):
            for family in range(1, families + 1):
                family_id = f"DEV-{prefix}{group:02}-{family:02}"
                cases.extend(
                    {
                        "case_id": f"{family_id}-V{variant}",
                        "family_id": family_id,
                        "split": "DEV",
                        "decision": decision,
                        "input": "Reviewed input",
                        "expected_tool": f"tool{group}"
                        if prefix == "A"
                        else "respond_to_user",
                    }
                    for variant in range(4)
                )
    return {
        "schema": bank_reader.SCHEMA,
        "source": {"sha256": "a" * 64},
        "cases": cases,
    }


def test_full_dev_selection_includes_every_variant_in_stable_order():
    bank = full_bank()
    selection = bank_reader.build_dev_selection(bank)
    assert len(selection["case_ids"]) == len(set(selection["case_ids"])) == 264
    assert selection["counts"] == {"Action": 144, "Clarification": 48, "No-call": 72}
    bank["cases"].reverse()
    assert bank_reader.build_dev_selection(bank) == selection
    assert selection["case_ids"] == sorted(selection["case_ids"])
    assert Counter(case["decision"] for case in bank["cases"]) == selection["counts"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_decision", "test"])
def test_full_dev_selection_rejects_changed_population(change):
    bank = full_bank()
    if change == "missing":
        bank["cases"].pop()
    elif change == "duplicate":
        bank["cases"].append(deepcopy(bank["cases"][0]))
    elif change == "wrong_decision":
        bank["cases"][0]["decision"] = "No-call"
    else:
        bank["cases"][0]["split"] = "TEST"
    with pytest.raises(ValueError):
        bank_reader.build_dev_selection(bank)


def test_dev_conditions_are_only_approved_models_with_rag_on():
    from scripts.dev.run_assistant_dev import select_models

    assert select_models("all") == [
        key for key in runner.CONDITIONS if key.endswith("-on")
    ]
    assert select_models("phi4,granite4") == ["granite4-rag-on", "phi4-rag-on"]
    for value in ("phi4-rag-off", "phi4,phi4", "unknown"):
        with pytest.raises(ValueError):
            select_models(value)


def test_direct_entry_sets_offscreen_offline_and_checkout_before_bootstrap(
    tmp_path, monkeypatch
):
    from scripts.dev import assistant_pilot_case
    from scripts.dev import run_assistant_dev as entry

    for key in (
        "QT_QPA_PLATFORM",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "PYTHONPATH",
    ):
        monkeypatch.setenv(key, "inherited-wrong-value")
    bootstrapped = []
    original = assistant_pilot_case.bootstrap_case_checkout

    def bootstrap():
        assert entry.os.environ["QT_QPA_PLATFORM"] == "offscreen"
        assert entry.os.environ["HF_HUB_OFFLINE"] == "1"
        assert entry.os.environ["TRANSFORMERS_OFFLINE"] == "1"
        assert entry.os.environ["PYTHONPATH"] == str(runner.ROOT)
        original()
        assert entry.sys.path[0] == str(runner.ROOT)
        bootstrapped.append(True)

    monkeypatch.setattr(assistant_pilot_case, "bootstrap_case_checkout", bootstrap)
    monkeypatch.setattr(
        runner,
        "prepare_manifest",
        lambda *_a, **_k: ({"experiment": runner.DEV_EXPERIMENT}, {}),
    )
    target = tmp_path / "manifest.json"
    assert (
        entry.main(
            [
                "prepare",
                "--bank",
                "supplied.xlsx",
                "--config",
                "supplied.json",
                "--manifest-output",
                str(target),
            ]
        )
        == 0
    )
    assert bootstrapped == [True]
    assert json.loads(target.read_text())["experiment"]["qt_platform"] == "offscreen"


def test_entry_preserves_fixed_inputs_and_refuses_overwrite(tmp_path):
    from scripts.dev import run_assistant_dev as entry

    bank = tmp_path / "source.xlsx"
    config = tmp_path / "config.json"
    bank.write_bytes(b"reviewed workbook")
    config.write_text('{"model_caches": {}}')
    output = tmp_path / "output"
    manifest = {
        "selection": {"case_ids": ["DEV-A"]},
        "bank_sha256": entry.digest(bank),
        "config": {"model_caches": {}},
    }
    entry.prepare_output(output, bank, config, manifest)
    assert (output / "inputs" / "bank.xlsx").read_bytes() == bank.read_bytes()
    assert (output / "inputs" / "config.json").read_bytes() == config.read_bytes()
    with pytest.raises(FileExistsError):
        entry.prepare_output(output, bank, config, {})


def test_entry_rejects_input_changed_after_manifest_preparation(tmp_path):
    from scripts.dev import run_assistant_dev as entry

    bank, config = tmp_path / "source.xlsx", tmp_path / "config.json"
    bank.write_bytes(b"changed after preparation")
    config.write_text("{}")
    with pytest.raises(ValueError, match="changed during preparation"):
        entry.prepare_output(
            tmp_path / "run",
            bank,
            config,
            {"bank_sha256": "0" * 64, "config": {}, "selection": {}},
        )


def test_source_bank_without_review_status_is_copied_byte_for_byte(tmp_path):
    from scripts.dev import run_assistant_dev as entry
    from tests.unit.scripts.test_assistant_pilot_bank import _workbook

    source = _workbook(tmp_path)
    original = source.read_bytes()
    bank = bank_reader.load_bank(source)
    assert all(
        "review_status" not in c["metadata"]["ground_truth"] for c in bank["cases"]
    )
    config = tmp_path / "config.json"
    config.write_text("{}")
    manifest = {
        "bank_sha256": entry.digest(source),
        "config": {},
        "selection": {
            "source_sha256": entry.digest(source),
            "case_ids": ["DEV-A01-01-V0"],
        },
    }
    output = tmp_path / "run"
    entry.prepare_output(output, source, config, manifest)
    saved = output / "inputs" / "bank.xlsx"
    assert saved.read_bytes() == original == source.read_bytes()
    assert (
        entry.digest(saved)
        == manifest["bank_sha256"]
        == manifest["selection"]["source_sha256"]
    )
    assert bank_reader.load_bank(saved)["cases"] == bank["cases"]


def test_failed_entry_attempt_still_builds_partial_report_and_navigation(
    tmp_path, monkeypatch
):
    from scripts.dev import assistant_pilot_report as reporter
    from scripts.dev import run_assistant_dev as entry

    output = tmp_path / "output"
    output.mkdir()
    (output / "raw").mkdir()
    (output / "raw" / "manifest.json").write_text("{}")

    def fail(*_args, **_kwargs):
        raise ValueError("preserved failure")

    reports = []

    def report(raw, target):
        from scripts.dev.assistant_pilot_presentation import render_page

        reports.append(raw)
        target.mkdir()
        (target / "index.html").write_text(render_page("Partial", "partial"))
        (target / "presentation-audit.json").write_text(
            '{"complete": false, "issues": []}'
        )
        return {"complete_selected_schedule": False}

    monkeypatch.setattr(runner, "execute", fail)
    monkeypatch.setattr(reporter, "write_report", report)
    assert (
        entry.run_attempt({"source": {"head": "a" * 40}}, {}, output, resume=False) == 1
    )
    assert reports == [output / "raw"]
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "Results incomplete" in page
    assert "<details>" not in page
    launch = next((output / "launches").glob("*-end.json"))
    assert "preserved failure" in json.loads(launch.read_text())["error"]
    assert len(list((output / "launches").glob("*-end.json"))) == 1


def test_report_without_raw_manifest_explains_incomplete_entry(tmp_path):
    from scripts.dev import run_assistant_dev as entry

    assert (
        entry.run_attempt(
            {"source": {"head": "a" * 40}}, {}, tmp_path, resume=False, report_only=True
        )
        == 1
    )
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Results incomplete" in page
    assert "execution details are saved in launches/" in page
    assert "Evaluation complete" not in page


@pytest.mark.parametrize(
    "audit, expected",
    [
        (
            {
                "complete": False,
                "selected_complete": True,
                "issues": {"superseded:case": ["capture_missing"]},
            },
            0,
        ),
        ({"complete": True, "issues": []}, 1),
        (
            {
                "complete": False,
                "selected_complete": False,
                "issues": {"selected:case": ["capture_missing"]},
            },
            1,
        ),
    ],
)
def test_report_only_never_submits_cases(tmp_path, monkeypatch, audit, expected):
    from scripts.dev import assistant_pilot_report as reporter
    from scripts.dev import run_assistant_dev as entry

    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "manifest.json").write_text("{}")
    monkeypatch.setattr(
        runner, "execute", lambda *_a, **_k: pytest.fail("report executed cases")
    )

    def report(_raw, target):
        from scripts.dev.assistant_pilot_presentation import render_page

        target.mkdir()
        (target / "index.html").write_text(
            render_page("Selected", "<h1>Selected</h1>"),
            encoding="utf-8",
        )
        (target / "presentation-audit.json").write_text(json.dumps(audit))
        return {"complete_selected_schedule": True}

    monkeypatch.setattr(reporter, "write_report", report)
    assert (
        entry.run_attempt(
            {"source": {"head": "a" * 40}}, {}, tmp_path, resume=False, report_only=True
        )
        == expected
    )
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert ("Results incomplete" in page) is bool(expected)
    assert "Evaluation complete" not in page


@pytest.mark.parametrize("changed", ["prepared", "bank", "config", "selection"])
def test_report_entry_rejects_changed_retained_identity(tmp_path, monkeypatch, changed):
    from scripts.dev import run_assistant_dev as entry

    bank, config = tmp_path / "bank.xlsx", tmp_path / "config.json"
    bank.write_bytes(b"fixed workbook")
    config.write_text("{}")
    manifest = {
        "experiment": dict(runner.DEV_EXPERIMENT),
        "bank_sha256": entry.digest(bank),
        "config": {},
        "selection": {"case_ids": ["DEV-A"]},
        "source": {"head": "a" * 40},
    }
    output = tmp_path / "run"
    entry.prepare_output(output, bank, config, manifest)
    (output / "raw").mkdir()
    (output / "raw" / "manifest.json").write_text(json.dumps(manifest))
    targets = {
        "prepared": output / "prepared-manifest.json",
        "bank": output / "inputs" / "bank.xlsx",
        "config": output / "inputs" / "config.json",
        "selection": output / "inputs" / "selection.json",
    }
    targets[changed].write_text('{"changed": true}')
    monkeypatch.setattr(
        entry,
        "run_attempt",
        lambda *_a, **_k: pytest.fail("Changed input reached reporting"),
    )
    with pytest.raises(ValueError, match="Retained experiment"):
        entry.main(["report", "--output", str(output)])


@pytest.mark.parametrize(
    "changed", [None, "source", "bank_sha256", "config", "environment"]
)
def test_expected_manifest_binds_launch_before_output_or_execution(
    tmp_path, monkeypatch, changed
):
    from scripts.dev import assistant_pilot_case
    from scripts.dev import run_assistant_dev as entry

    manifest = {
        "source": {"head": "a" * 40},
        "bank_sha256": "b" * 64,
        "config": {"model_caches": {}},
        "environment": {"python": "pinned"},
    }
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps(manifest))
    actual = deepcopy(manifest)
    if changed:
        actual[changed] = {
            "source": {"head": "c" * 40},
            "bank_sha256": "c" * 64,
            "config": {
                "model_caches": {"microsoft/Phi-4-mini-instruct": "D:/changed-cache"}
            },
            "environment": {"python": "changed"},
        }[changed]
    monkeypatch.setattr(assistant_pilot_case, "bootstrap_case_checkout", lambda: None)
    monkeypatch.setattr(runner, "prepare_manifest", lambda *_a, **_k: (actual, {}))
    monkeypatch.setattr(entry, "LOCK", tmp_path / "gpu.lock")
    calls = []
    monkeypatch.setattr(entry, "prepare_output", lambda *_a: calls.append("output"))
    monkeypatch.setattr(
        entry, "run_attempt", lambda *_a, **_k: calls.append("execute") or 0
    )
    output = tmp_path / "run"
    argv = [
        "run",
        "--bank",
        "bank.xlsx",
        "--config",
        "config.json",
        "--output",
        str(output),
        "--expected-manifest",
        str(expected),
    ]
    if changed:
        with pytest.raises(ValueError, match="expected manifest"):
            entry.main(argv)
        assert calls == []
        assert not output.exists()
    else:
        assert entry.main(argv) == 0
        assert calls == ["output", "execute"]


@pytest.mark.parametrize("action", ["prepare", "resume", "report"])
def test_expected_manifest_is_run_only(action, monkeypatch, capsys):
    from scripts.dev import run_assistant_dev as entry

    monkeypatch.setattr(
        runner,
        "prepare_manifest",
        lambda *_a, **_k: pytest.fail("invalid mode reached preparation"),
    )
    with pytest.raises(SystemExit) as exc:
        entry.main([action, "--expected-manifest", "expected.json"])
    assert exc.value.code == 2
    assert "--expected-manifest requires run" in capsys.readouterr().err
