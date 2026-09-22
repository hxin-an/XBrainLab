"""Full DEV selection and immutable replacement preserve the research denominator."""

import json
from collections import Counter
from copy import deepcopy

import pytest

from scripts.dev import assistant_pilot_bank as bank_reader
from scripts.dev import run_assistant_pilot as runner


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
        reports.append(raw)
        target.mkdir()
        (target / "index.html").write_text("partial")
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
    assert "preserved failure" in (output / "index.html").read_text()
    assert len(list((output / "launches").glob("*-end.json"))) == 1


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
        target.mkdir()
        (target / "presentation-audit.json").write_text(json.dumps(audit))
        return {"complete_selected_schedule": True}

    monkeypatch.setattr(reporter, "write_report", report)
    assert (
        entry.run_attempt(
            {"source": {"head": "a" * 40}}, {}, tmp_path, resume=False, report_only=True
        )
        == expected
    )


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
    with pytest.raises(ValueError, match="Retained DEV"):
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
