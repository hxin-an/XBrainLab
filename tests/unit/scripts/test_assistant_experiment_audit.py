"""Offline audit uses the selected source and preserves original evidence."""

# ruff: noqa: S603, S607 -- disposable fixture Git/Python processes, no shell.

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.dev.assistant_experiment_audit import evidence_digest, replay_rows

ROOT = Path(__file__).resolve().parents[3]


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run = Path(self.temporary.name)
        (self.run / "raw").mkdir()
        (self.run / "inputs").mkdir()
        (self.run / "raw/result.json").write_text("{}")
        self.case = {"case_id": "DEV-A01-01-V0"}
        self.result = {
            "trace": {"case_id": self.case["case_id"]},
            "decision_timed_out": False,
            "scores": {"correct": False},
            "input_audit": {"passed": True},
        }
        self.detail = {
            "issues": [],
            "request": {"case": self.case, "fixture": {}},
            "result": self.result,
        }

    def test_valid_wrong_answer_is_replayed_not_repaired(self):
        calls = []

        def scorer(case, trace, **kwargs):
            calls.append((case, trace, kwargs))
            return {"correct": False}

        before = evidence_digest(self.run)
        result = replay_rows(
            [{"id": "case"}],
            lambda row: self.detail,
            scorer,
            lambda *a, **k: {"passed": True},
            {"max_format_recovery_attempts": 1},
        )
        self.assertEqual(result, {"checked": 1, "issues": []})
        self.assertEqual(calls[0][2]["max_format_recovery_attempts"], 1)
        self.assertEqual(evidence_digest(self.run), before)

    def test_scoring_input_and_capture_failures_remain_separate(self):
        self.detail["issues"] = ["capture_hash_mismatch"]
        result = replay_rows(
            [{"id": "case"}],
            lambda row: self.detail,
            lambda *a, **k: {"correct": True},
            lambda *a, **k: {"passed": False},
            {},
        )
        self.assertEqual(
            result["issues"][0]["issues"],
            [
                "capture_hash_mismatch",
                "score_replay_mismatch",
                "input_audit_replay_mismatch",
            ],
        )

    def test_corrupt_evidence_cannot_be_reported_as_an_incorrect_model_answer(self):
        self.detail["result"] = {}
        result = replay_rows(
            [{"id": "case"}],
            lambda row: self.detail,
            lambda *a, **k: self.fail("No scorer for missing evidence"),
            lambda *a, **k: {},
            {},
        )
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["issues"][0]["issues"], ["missing_request_or_result"])

    def test_inventory_detects_changes_and_does_not_follow_external_models(self):
        outside = self.run / "external"
        outside.mkdir()
        (outside / "weight").write_bytes(b"weight")
        try:
            (self.run / "raw/models").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink unavailable")
        before = evidence_digest(self.run)
        (outside / "weight").write_bytes(b"changed shared weight")
        self.assertEqual(evidence_digest(self.run), before)
        (self.run / "raw/result.json").write_text('{"changed":true}')
        self.assertNotEqual(evidence_digest(self.run), before)

    def test_real_subprocess_imports_selected_scorer_not_coordinator(self):
        source = self.run / "候選 source"
        modules = source / "scripts/dev"
        modules.mkdir(parents=True)
        (source / "scripts/__init__.py").touch()
        (modules / "__init__.py").touch()
        (modules / "assistant_pilot_case.py").write_text(
            "def bootstrap_case_checkout(): pass\n"
            'def audit_initial_input(*a, **k): return {"passed":True}\n'
        )
        (modules / "assistant_pilot_scoring.py").write_text(
            'def score_case_decisions(*a, **k): return {"frozen_candidate":True}\n'
        )
        (modules / "assistant_pilot_presentation.py").write_text(
            'def _details(root, row, **kwargs): return row["detail"]\n'
        )
        (modules / "active_checkout.py").write_text(
            "def assert_active_checkout_import(source): pass\n"
        )
        (modules / "run_assistant_pilot.py").write_text(
            'def environment_identity(): return {"fixture":True}\n'
        )

        def git(*args):
            return subprocess.check_output(["git", "-C", str(source), *args], text=True)

        git("init", "-q")
        git("add", ".")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "isolated scorer",
        )
        head = git("rev-parse", "HEAD").strip()
        self.result["scores"] = {"frozen_candidate": True}
        payload = {
            "source_head": head,
            "raw": str(self.run / "raw"),
            "rows": [{"id": "case", "detail": self.detail}],
            "experiment": {},
        }
        command = [
            sys.executable,
            str(ROOT / "scripts/dev/assistant_experiment_audit.py"),
            "--worker-source",
            str(source),
        ]
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=20,
            env=environment,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["source_head"], head)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["checked"], 1)
        payload["source_head"] = "0" * 40
        process = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=20,
            env=environment,
            check=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Replay candidate source differs", process.stderr)


if __name__ == "__main__":
    unittest.main()
