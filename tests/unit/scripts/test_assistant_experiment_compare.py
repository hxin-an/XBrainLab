"""Saved manifest/journal/report/capture integration; no model or scorer execution."""

# Fixed Git commands operate only on the disposable test fixture repository.
# ruff: noqa: S603, S607, RUF001 -- assertions include Chinese report punctuation.

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.dev.assistant_experiment_audit import evidence_digest
from scripts.dev.assistant_experiment_config import (
    MODELS,
    build_jobs,
    experiment_identity,
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value).encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_test_full_schedule_reaches_report_validation_not_old_valid_limit(tmp_path):
    from scripts.dev.assistant_experiment_compare import _load

    jobs = [
        {
            "id": f"job-{i}",
            "condition": "phi4-full",
            "case_id": f"TEST-{i}",
            "repeat": 0,
        }
        for i in range(1584)
    ]
    save(tmp_path / "raw/manifest.json", {"jobs": jobs})
    (tmp_path / "raw/journal.jsonl").write_text("")
    result = _load(tmp_path)
    assert any("No saved report" in str(issue) for issue in result["issues"])


def fixture(
    root,
    observations,
    *,
    candidate=1,
    head="a" * 40,
    scorer="v6",
    alias="phi4",
    source_root="/frozen",
):
    """The on-disk layout emitted by run_assistant_dev and write_report."""
    config = {
        "schema": "xbrainlab.assistant_experiment_config.v1",
        "split": "DEV",
        "purpose": "engineering-smoke",
        "budget_seconds": 60,
        "embedding_cache": "cache",
        "resource_inventory": "resources.json",
        "case_ids": [f"DEV-A01-{i:02}-V0" for i in range(len(observations))],
        "models": [
            {
                "alias": alias,
                "candidate_index": candidate,
                "source": {"head": head, "root": str(source_root)},
                "model_cache": "cache",
            }
        ],
    }
    experiment = experiment_identity(config)
    jobs = build_jobs({"case_ids": config["case_ids"]}, config)
    rows, journal = [], []
    for index, (job, observation) in enumerate(zip(jobs, observations, strict=True)):
        job["decision"] = "Action"
        row = {
            **job,
            "artifact_id": job["id"],
            "evidence_status": "missing",
            "decision_valid": False,
            "issues": [],
        }
        rows.append(row)
        if observation is None:
            continue
        case = {
            "case_id": job["case_id"],
            "split": "DEV",
            "decision": "Action",
            "input": "Set sampling frequency",
            "expected_tool": "resample",
            "expected_parameters": {"sfreq": 64},
            "expected_workflow_stage": "preprocess",
        }
        request = {**job, "case": case, "experiment": experiment}
        request_sha = save(root / "raw/cases" / (job["id"] + ".request.json"), request)
        generations, captures, attempts = [], [], []
        for sequence, (tool, parameters, correct) in enumerate(observation, 1):
            raw = json.dumps({"tool_name": tool, "parameters": parameters})
            base = (
                root
                / "raw/conditions"
                / job["id"].split("__DEV-A")[0]
                / "prompts"
                / f"session-{index}"
                / str(sequence)
            )
            base.mkdir(parents=True)
            prompt = f"Actual rendered input {index}/{sequence}"
            (base / "prompt.txt").write_text(prompt)
            (base / "raw-output.txt").write_text(raw)
            metadata = {
                "session_id": f"session-{index}",
                "sequence": sequence,
                "status": "completed",
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }
            save(base / "metadata.json", metadata)
            generations.append({"raw_response": raw, "terminal": "finished"})
            captures.append({"metadata": metadata})
            attempts.append(
                {
                    "observed_tool": tool,
                    "correct": correct,
                    "reason": "matched" if correct else "decision_mismatch",
                    "explanation": {
                        "observed": {"tool": tool, "parameters": parameters}
                    },
                }
            )
        result = {
            "case": case,
            "case_id": case["case_id"],
            "status": "recorded",
            "cleanup_ok": True,
            "trace": {"generations": generations},
            "condition_evidence": {"artifact_id": job["id"].split("__DEV-A")[0]},
            "input_audit": {"issues": []},
            "capture_audit": {"issues": [], "captures": captures},
            "decision_seconds": index + 1,
            "scores": {
                "scorer_schema": "xbrainlab.assistant_decision_scores." + scorer,
                "response_contract": "assistant_tool_response.v1",
                "parameter_scope": "single_turn_complete_parameters",
                "max_format_recovery_attempts": 1,
                "measurement_valid": True,
                "measurement_issues": [],
                "execution_status": "completed",
                "attempt_decisions": attempts,
                "first_decision_correct": observation[0][2],
                "final_decision_correct": observation[-1][2],
            },
        }
        result_sha = save(root / "raw/cases" / job["id"] / "result.json", result)
        row.update(
            evidence_status="verified",
            decision_valid=True,
            request_sha256=request_sha,
            result_sha256=result_sha,
            first=observation[0][2],
            final=observation[-1][2],
            timings={"decision": index + 1},
            case_recorded=True,
        )
        journal.extend(
            [
                {"event": "case_start", "id": job["id"], "request_sha256": request_sha},
                {"event": "case_end", "id": job["id"], "result_sha256": result_sha},
            ]
        )
    manifest = {
        "schema": "xbrainlab.assistant_pilot_run.v2",
        "source": {"head": head, "dirty": []},
        "experiment": experiment,
        "config": config,
        "environment": {"python": "3.11"},
        "models": {MODELS[alias]: {"revision": "frozen"}},
        "bank_sha256": "b" * 64,
        "corpus_sha256": "c" * 64,
        "embedding_sha256": "d" * 64,
        "resource_inventory_sha256": "f" * 64,
        "jobs": jobs,
    }
    manifest_sha = save(root / "raw/manifest.json", manifest)
    journal.append({"event": "session_end", "cleanup_certified": True})
    journal_bytes = "".join(json.dumps(item) + "\n" for item in journal).encode()
    (root / "raw/journal.jsonl").write_bytes(journal_bytes)
    report = {
        "schema": "xbrainlab.assistant_experiment_report.v4",
        "manifest_sha256": manifest_sha,
        "journal_sha256": hashlib.sha256(journal_bytes).hexdigest(),
        "cases": rows,
        "complete_selected_schedule": all(item is not None for item in observations),
        "partial": any(item is None for item in observations),
        "session_cleanup_certified": True,
    }
    save(root / "reports/20260929/report.json", report)
    return root


def amend(run, *, manifest_change=None, case_change=None, result_change=None):
    """Publish coherent saved fixtures so tests isolate semantics, not hash errors."""
    report_path = run / "reports/20260929/report.json"
    report = json.loads(report_path.read_text())
    manifest = json.loads((run / "raw/manifest.json").read_text())
    records = [
        json.loads(line)
        for line in (run / "raw/journal.jsonl").read_text().splitlines()
    ]
    if manifest_change:
        manifest_change(manifest)
    if case_change or result_change:
        row = report["cases"][0]
        request_path = run / "raw/cases" / (row["id"] + ".request.json")
        result_path = run / "raw/cases" / row["id"] / "result.json"
        request = json.loads(request_path.read_text())
        result = json.loads(result_path.read_text())
        if case_change:
            case_change(request["case"])
            result["case"] = request["case"]
        if result_change:
            result_change(result)
        row["request_sha256"] = save(request_path, request)
        row["result_sha256"] = save(result_path, result)
        for record in records:
            for field in ("request_sha256", "result_sha256"):
                if field in record and record["id"] == row["id"]:
                    record[field] = row[field]
    journal_bytes = "".join(json.dumps(record) + "\n" for record in records).encode()
    (run / "raw/journal.jsonl").write_bytes(journal_bytes)
    report["manifest_sha256"] = save(run / "raw/manifest.json", manifest)
    report["journal_sha256"] = hashlib.sha256(journal_bytes).hexdigest()
    save(report_path, report)


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        from scripts.dev import assistant_experiment_compare

        self.api = assistant_experiment_compare

    def test_self_comparison_preserves_hashes_and_separates_phases(self):
        run = fixture(
            self.root / "a",
            [[("resample", {"sfreq": 32}, False), ("resample", {"sfreq": 64}, True)]],
        )
        before = evidence_digest(run)
        actual = self.api.compare_runs(run, run)
        self.assertEqual(actual["classification"], "same_config_reproduction")
        self.assertEqual(actual["summary"]["first"]["correctness"]["both_wrong"], 1)
        self.assertEqual(actual["summary"]["final"]["correctness"]["both_right"], 1)
        self.assertEqual(actual["summary"]["final"]["tool_parameters_equal"]["rate"], 1)
        self.assertEqual(evidence_digest(run), before)
        self.assertTrue(actual["original_evidence_unchanged"])

    def test_candidate_alignment_changes_and_latency(self):
        a = fixture(
            self.root / "a",
            [[("resample", {"sfreq": 32}, False)], [("resample", {"sfreq": 64}, True)]],
        )
        b = fixture(
            self.root / "b",
            [[("resample", {"sfreq": 64}, True)], [("filter", {}, False)]],
            candidate=2,
        )
        actual = self.api.compare_runs(a, b)
        self.assertEqual(actual["classification"], "candidate_comparison")
        counts = actual["summary"]["final"]["correctness"]
        self.assertEqual((counts["improved"], counts["regressed"]), (1, 1))
        self.assertEqual(actual["summary"]["final"]["tool_equal"]["numerator"], 1)
        self.assertEqual(actual["timing"]["paired_delta_b_minus_a"]["p95"], 0)
        self.assertEqual(actual["timing"]["a"]["p95"], 1.95)
        self.assertIn(
            "Actual rendered input", actual["cases"][0]["a"]["captures"][0]["prompt"]
        )

    def test_non_action_message_and_json_key_order_do_not_change_decision(self):
        a = fixture(
            self.root / "a",
            [
                [("respond_to_user", {"message": "one"}, False)],
                [("filter", {"low": 1, "high": 40}, False)],
            ],
        )
        b = fixture(
            self.root / "b",
            [
                [("respond_to_user", {"message": "two"}, False)],
                [("filter", {"high": 40, "low": 1}, False)],
            ],
        )
        result = self.api.compare_runs(a, b)
        self.assertEqual(
            result["summary"]["final"]["tool_parameters_equal"]["numerator"], 2
        )
        self.assertEqual(result["summary"]["final"]["correctness"]["both_wrong"], 2)

    def test_missing_rows_remain_in_union_denominator(self):
        a = fixture(self.root / "a", [None, [("resample", {}, False)]])
        b = fixture(self.root / "b", [None])
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["planned_union"], 2)
        self.assertEqual(result["summary"]["final"]["tool_equal"]["denominator"], 0)
        self.assertEqual(result["summary"]["final"]["tool_equal"]["unavailable"], 2)
        self.assertIsNone(result["summary"]["final"]["tool_equal"]["rate"])

    def test_corrupt_capture_and_duplicate_rows_are_visible(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, False)]])
        next((a / "raw").rglob("raw-output.txt")).write_text("corrupt")
        report_path = b / "reports/20260929/report.json"
        report = json.loads(report_path.read_text())
        report["cases"].append(report["cases"][0])
        save(report_path, report)
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 1)
        self.assertTrue(result["runs"][1]["issues"])
        self.assertTrue(result["cases"][0]["a"]["issues"])

    def test_scorer_change_disables_correctness_only(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, True)]], scorer="v7")
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["classification"], "incompatible_or_unknown")
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 1)
        self.assertEqual(result["summary"]["final"]["tool_equal"]["numerator"], 1)

    def test_oracle_change_does_not_become_improvement(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, True)]])
        amend(
            b, case_change=lambda case: case.update(expected_parameters={"sfreq": 32})
        )
        result = self.api.compare_runs(a, b)
        self.assertEqual(
            result["cases"][0]["correctness_reason"], "case_or_oracle_changed"
        )
        self.assertEqual(result["summary"]["final"]["correctness"]["improved"], 0)

    def test_source_bank_environment_differences_are_explicit(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, False)]], head="e" * 40)
        amend(
            b,
            manifest_change=lambda manifest: manifest.update(
                bank_sha256="f" * 64, environment={"python": "3.12"}
            ),
        )
        result = self.api.compare_runs(a, b)
        self.assertTrue(
            {"source", "config", "bank_sha256", "environment"}
            <= {item["field"] for item in result["differences"]}
        )
        self.assertEqual(
            result["cases"][0]["correctness_reason"], "scorer_source_changed_or_unknown"
        )

    def test_missing_report_retains_planned_inventory(self):
        run = fixture(self.root / "a", [None, None])
        (run / "reports/20260929/report.json").unlink()
        result = self.api.compare_runs(run, run)
        self.assertEqual(result["planned_union"], 2)
        self.assertEqual(result["classification"], "incompatible_or_unknown")
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 2)

    def test_malformed_saved_decisions_are_unavailable(self):
        run = fixture(
            self.root / "a", [[("resample", {}, False)], [("resample", {}, False)]]
        )
        amend(run, result_change=lambda result: result.update(scores=[]))
        result = self.api.compare_runs(run, run)
        self.assertEqual(result["summary"]["final"]["tool_equal"]["unavailable"], 1)
        self.assertEqual(result["summary"]["final"]["correctness"]["both_wrong"], 1)

    def test_dirty_source_does_not_certify_scorer_identity(self):
        run = fixture(self.root / "a", [[("resample", {}, False)]])
        amend(
            run,
            manifest_change=lambda manifest: manifest["source"].update(
                dirty=["scorer.py"]
            ),
        )
        result = self.api.compare_runs(run, run)
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 1)

    def test_unknown_environment_never_claims_reproduction(self):
        run = fixture(self.root / "a", [[("resample", {}, False)]])
        amend(run, manifest_change=lambda manifest: manifest.pop("environment"))
        result = self.api.compare_runs(run, run)
        self.assertEqual(result["classification"], "incompatible_or_unknown")

    def test_numeric_json_normalization_and_per_condition_timing(self):
        a = fixture(self.root / "a", [[("resample", {"sfreq": 64}, True)], None])
        b = fixture(self.root / "b", [[("resample", {"sfreq": 64.0}, True)], None])
        result = self.api.compare_runs(a, b)
        self.assertEqual(
            result["summary"]["final"]["tool_parameters_equal"]["numerator"], 1
        )
        timing = result["by_model_repeat"]["phi4-rag-on/repeat-0"]["timing"]
        self.assertEqual(timing["a"]["excluded"], 1)
        self.assertEqual(sum(timing["a"]["exclusions"].values()), 1)

    def test_recovery_budget_change_does_not_regrade_saved_scores(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, False)]])
        amend(
            b,
            result_change=lambda result: result["scores"].update(
                max_format_recovery_attempts=0
            ),
        )
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["summary"]["first"]["correctness"]["both_wrong"], 1)
        self.assertEqual(result["classification"], "candidate_comparison")

    def test_different_models_never_align_even_with_identical_case_ids(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        b = fixture(self.root / "b", [[("resample", {}, False)]], alias="granite4")
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["planned_union"], 2)
        self.assertEqual(result["summary"]["first"]["correctness"]["unavailable"], 2)
        self.assertEqual(len(result["by_model_repeat"]), 2)

    def test_frozen_git_dependencies_allow_prompt_changes_but_detect_parser_change(
        self,
    ):
        source = self.root / "source"
        source.mkdir()
        names = [
            "scripts/dev/assistant_pilot_scoring.py",
            "XBrainLab/backend/schema.py",
            "XBrainLab/llm/tools/schema.py",
            "XBrainLab/llm/agent/decision_contract.py",
            "XBrainLab/llm/agent/parser.py",
            "XBrainLab/llm/agent/prompt_policy.py",
            "XBrainLab/llm/agent/verifier.py",
        ]
        for name in names:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# frozen fixture\n")

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(source), *args], text=True, timeout=15
            ).strip()

        git("init", "-q")

        def commit(message):
            git("add", ".")
            git(
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                message,
            )
            return git("rev-parse", "HEAD")

        first = commit("frozen scorer")
        (source / "prompt.txt").write_text("changed candidate input")
        second = commit("prompt only")
        a = fixture(
            self.root / "a", [[("resample", {}, False)]], head=first, source_root=source
        )
        b = fixture(
            self.root / "b", [[("resample", {}, True)]], head=second, source_root=source
        )
        result = self.api.compare_runs(a, b)
        self.assertEqual(result["summary"]["final"]["correctness"]["improved"], 1)
        (source / "XBrainLab/llm/agent/parser.py").write_text("# different parser\n")
        third = commit("parser changed")
        c = fixture(
            self.root / "c", [[("resample", {}, True)]], head=third, source_root=source
        )
        result = self.api.compare_runs(a, c)
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 1)

        # A whole-package copy retains historical absolute paths verbatim. Its
        # local Git objects must still establish scorer equivalence after move.
        package = self.root / "experiment"
        for head in (first, second, third):
            destination = package / "snapshot/sources" / head
            shutil.copytree(source, destination)
            subprocess.check_call(
                ["git", "-C", str(destination), "checkout", "-q", "--detach", head],
                timeout=15,
            )
        original = [evidence_digest(run) for run in (a, b, c)]
        locations = (
            "results/reference/baseline",
            "results/runs/new",
            "results/runs/changed",
        )
        for run, relative in zip((a, b, c), locations, strict=True):
            shutil.copytree(run, package / relative)
        moved = self.root / "搬移 experiment with spaces"
        package.rename(moved)
        source.rename(self.root / "original-source-unavailable")
        relocated = [moved / relative for relative in locations]
        self.assertEqual([evidence_digest(run) for run in relocated], original)
        result = self.api.compare_runs(*relocated[:2])
        self.assertEqual(result["summary"]["final"]["correctness"]["improved"], 1)
        self.assertTrue(result["cases"][0]["a"]["scoring_source"]["dependency_tree"])
        result = self.api.compare_runs(relocated[0], relocated[2])
        self.assertEqual(result["summary"]["final"]["correctness"]["unavailable"], 1)
        self.assertEqual([evidence_digest(run) for run in relocated], original)
        self.assertEqual([evidence_digest(run) for run in (a, b, c)], original)

    def test_output_never_overwrites_or_nests_inside_original(self):
        a = fixture(self.root / "a", [[("resample", {}, False)]])
        for output in (a, a / "new", self.root):
            with self.assertRaises((ValueError, FileExistsError)):
                self.api.write_comparison(a, a, output)
        output = self.root / "comparison"
        self.api.write_comparison(a, a, output)
        self.assertTrue((output / "comparison.json").is_file())
        self.assertIn(
            "same_config_reproduction", (output / "comparison.md").read_text()
        )

    def test_readable_report_separates_agreement_and_links_existing_evidence(self):
        run = fixture(self.root / "a", [[("resample", {}, False)]])
        output = self.root / "comparison"
        before = evidence_digest(run)
        result = self.api.write_comparison(run, run, output)
        text = (output / "comparison.md").read_text()
        self.assertIn("逐題正誤判定一致", text)
        self.assertIn("| 最終正確（可比案例） | 0 | 0 |", text)
        self.assertIn("1/1（100.0%）", text)
        self.assertIn("一致率不是答對率", text)
        self.assertNotIn("```json", text)
        self.assertNotIn("DEV-A01-00-V0", text)
        self.assertFalse((output / "cases.md").exists())
        self.assertIn("](../a/reports/20260929/report.json)", text)
        self.assertIn("[完整比較資料與原始輸入／輸出](comparison.json)", text)
        self.assertEqual(evidence_digest(run), before)
        self.assertEqual(
            json.loads((output / "comparison.json").read_text()),
            {k: v for k, v in result.items() if k != "output"},
        )

    def test_readable_report_flags_changed_parameters_even_if_both_wrong(self):
        a = fixture(self.root / "a", [[("resample", {"sfreq": 32}, False)]])
        b = fixture(self.root / "b", [[("resample", {"sfreq": 16}, False)]])
        output = self.root / "comparison"
        self.api.write_comparison(a, b, output)
        text = (output / "comparison.md").read_text()
        self.assertIn("存在逐題決策或判分差異", text)
        self.assertIn("0/1（0.0%）", text)

    def test_readable_report_does_not_certify_missing_evidence(self):
        a = fixture(self.root / "a", [[("resample", {}, False)], None])
        output = self.root / "comparison"
        self.api.write_comparison(a, a, output)
        text = (output / "comparison.md").read_text()
        self.assertIn("不能確認完整重跑一致", text)
        self.assertIn("不可比較", text)
        self.assertIn("排除 1", text)

    def test_readable_report_handles_unknown_source_metadata(self):
        b = fixture(self.root / "b", [[("resample", {}, False)]])
        for index, source in enumerate(({}, "malformed")):
            with self.subTest(source=source):
                a = fixture(self.root / f"a-{index}", [[("resample", {}, False)]])
                amend(a, manifest_change=lambda m, value=source: m.update(source=value))
                output = self.root / f"comparison-{index}"
                before = evidence_digest(a)
                self.api.write_comparison(a, b, output)
                text = (output / "comparison.md").read_text()
                self.assertIn("未提供有效版本", text)
                self.assertFalse((output / "cases.md").exists())
                self.assertEqual(evidence_digest(a), before)


if __name__ == "__main__":
    unittest.main()
