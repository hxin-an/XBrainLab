"""Frozen hierarchical scope, real Git snapshots and shell; no model inference."""

# ruff: noqa: S603, S607 -- fixed local fixture shell/Git processes.

from __future__ import annotations

import importlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from pathlib import Path

from tests.unit.scripts import test_assistant_experiment_package as package_tests

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.name == "posix", "Linux package shell/Git integration")
class ExperimentBatchTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("scripts.dev.assistant_experiment_batch")
        self.fixture = package_tests.ExperimentPackageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.source = self.fixture.root, self.fixture.source
        shutil.copyfile(
            ROOT / "scripts/dev/assistant_experiment_batch.py",
            self.source / "scripts/dev/assistant_experiment_batch.py",
        )
        self.fixture.git(self.source, "add", ".")
        self.fixture.git(self.source, "commit", "-qm", "batch dispatcher")
        self.head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = self.head
        self.fixture.save_config()
        self.study = self.root / "研究 study"

    def round(self, relative):
        output = self.study / relative
        self.fixture.api.create_package(
            self.fixture.bank,
            self.fixture.config,
            output,
            coordinator_root=self.source,
        )
        return output

    def batch(self, output, children, **kwargs):
        return self.api.create_batch(
            output, children, coordinator_root=self.source, **kwargs
        )

    def launch(self, batch, *arguments):
        return subprocess.run(
            ["sh", str(batch / "run.sh"), *arguments],
            cwd=self.root,
            env=dict(os.environ, XBL_PYTHON=sys.executable),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_hierarchy_freezes_order_and_ignores_unselected_directories(self):
        first, second = (
            self.round("development/round01"),
            self.round("development/round02"),
        )
        self.round("development/not-selected")
        development = self.batch(self.study / "development", [second, first])
        self.batch(self.study, [development])
        self.assertEqual(self.api.verify_batch(self.study), [second, first])
        self.assertFalse((self.study / "batches").exists())

    def test_blocked_test_prevents_any_development_run(self):
        first = self.round("development/round01")
        development = self.batch(self.study / "development", [first])
        test = self.batch(self.study / "test", [], blocked_reason="TEST remains sealed")
        self.batch(self.study, [development, test])
        result = self.launch(self.study)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TEST remains sealed", result.stderr)
        self.assertFalse((first / "runs").exists())
        self.assertFalse((self.study / "batches").exists())

    def test_missing_or_changed_child_fails_before_any_run(self):
        first, second = self.round("round01"), self.round("round02")
        self.batch(self.study, [first, second])
        for damage in ("missing", "changed"):
            with self.subTest(damage=damage):
                manifest = second / "manifest.json"
                original = manifest.read_bytes()
                if damage == "missing":
                    manifest.unlink()
                else:
                    manifest.write_bytes(original + b"\n")
                result = self.launch(self.study)
                manifest.write_bytes(original)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((first / "runs").exists())

    def test_duplicate_escape_and_symlink_selection_are_rejected(self):
        first = self.round("round01")
        for children in ([first, first], [self.root]):
            with self.subTest(children=children), self.assertRaises(ValueError):
                self.batch(self.study, children)
        link = self.study / "linked"
        link.symlink_to(first, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.batch(self.study, [link])
        self.assertFalse((self.study / "batch.json").exists())

    def test_recursive_duplicate_selection_is_rejected(self):
        first = self.round("development/round01")
        development = self.batch(self.study / "development", [first])
        with self.assertRaises(ValueError):
            self.batch(self.study, [development, first])
        self.assertFalse((self.study / "batch.json").exists())

    def test_help_and_moved_frozen_source_do_not_write_runtime(self):
        first = self.round("round01")
        self.batch(self.study, [first])
        moved = self.root / "搬移 new study"
        self.study.rename(moved)
        self.source.rename(self.root / "source-unavailable")
        result = self.launch(moved, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check-environment", result.stdout)
        self.assertFalse((moved / "batches").exists())
        self.assertFalse((moved / "round01/runs").exists())
        self.assertEqual(self.api.verify_batch(moved), [moved / "round01"])

    def test_old_leaf_without_safe_environment_entry_is_rejected(self):
        first = ExperimentBatchTests.round(self, "round01")
        self.batch(self.study, [first])
        result = self.launch(self.study)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("v4", result.stderr)
        self.assertFalse((first / "runs").exists())


@unittest.skipUnless(os.name == "posix", "Linux shared batch integration")
class RunnableBatchTests(ExperimentBatchTests):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory(prefix="batch-shared-env-")
        cls.addClassCleanup(cls.environment.cleanup)
        venv.EnvBuilder(with_pip=False).create(cls.environment.name)
        cls.python = Path(cls.environment.name) / "bin/python"

    def setUp(self):
        super().setUp()
        scripts = self.source / "scripts/dev"
        for name in (
            "assistant_experiment_shared.py",
            "assistant_experiment_portable.py",
        ):
            shutil.copyfile(ROOT / "scripts/dev" / name, scripts / name)
        (scripts / "run_assistant_dev.py").write_text(
            "import json, os, pathlib, signal, sys, time\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--output') + 1])\n"
            "name = out.parent.parent.name\n"
            "if name == 'round-empty': sys.exit(0)\n"
            "out.mkdir(parents=True, exist_ok=False)\n"
            "(out / 'called.json').write_text(json.dumps({'pid': os.getpid()}))\n"
            "if name == 'round-multiple': out.with_name(out.name + '-other').mkdir()\n"
            "if name == 'round-failed': sys.exit(7)\n"
            "if name == 'round-wait':\n"
            " def stop(number, frame):\n"
            "  (out / 'terminated').write_text(str(number))\n"
            "  sys.exit(128 + number)\n"
            " signal.signal(signal.SIGTERM, stop)\n"
            " signal.signal(signal.SIGINT, stop)\n"
            " (out / 'waiting').touch()\n"
            " while True: time.sleep(0.05)\n",
            encoding="utf-8",
        )
        self.fixture.git(self.source, "add", ".")
        self.fixture.git(self.source, "commit", "-qm", "shared batch fixture")
        self.head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = self.head
        self.fixture.save_config()
        for relative in ("shared/model", "shared/embedding"):
            (self.root / relative).mkdir(parents=True)

    def round(self, relative):
        output = self.study / relative
        self.fixture.api.create_package(
            self.fixture.bank,
            self.fixture.config,
            output,
            coordinator_root=self.source,
            shared_python=self.python,
        )
        return output

    def test_sequential_success_keeps_old_runs_and_indexes_each_new_run(self):
        first, second = self.round("round01"), self.round("round02")
        unselected = self.round("unselected")
        self.batch(self.study, [second, first])
        for _ in range(2):
            result = self.launch(self.study)
            self.assertEqual(result.returncode, 0, result.stderr)
        indexes = list((self.study / "batches").glob("*/index.md"))
        self.assertEqual(len(indexes), 2)
        for index in indexes:
            text = index.read_text()
            self.assertLess(text.index("round02`"), text.index("round01`"))
            self.assertEqual(text.count("completed"), 2)
            self.assertEqual(text.count("/runs/"), 2)
        for leaf in (first, second):
            self.assertEqual(len(list((leaf / "runs").glob("*/called.json"))), 2)
        self.assertFalse((unselected / "runs").exists())

    def test_preflight_checks_every_environment_before_any_inference(self):
        first = self.round("round01")
        missing = self.root / "different-model"
        missing.mkdir()
        self.fixture.values["models"][0]["model_cache"] = str(missing)
        self.fixture.save_config()
        second = self.round("round02")
        self.batch(self.study, [first, second])
        missing.rmdir()
        result = self.launch(self.study)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((first / "runs").exists())
        self.assertFalse((second / "runs").exists())

    def test_environment_check_does_not_create_results(self):
        first = self.round("round01")
        self.batch(self.study, [first])
        result = self.launch(self.study, "--check-environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((first / "runs").exists())
        self.assertFalse((self.study / "batches").exists())

    def test_unwritable_later_runs_directory_stops_before_first_leaf(self):
        first, second = self.round("round01"), self.round("round02")
        self.batch(self.study, [first, second])
        outputs = second / "runs"
        outputs.mkdir(mode=0o500)
        try:
            result = self.launch(self.study)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((first / "runs").exists())
        finally:
            outputs.chmod(0o700)

    def test_failure_stops_later_leaf_and_retains_failed_run_index(self):
        failed, untouched = self.round("round-failed"), self.round("round02")
        self.batch(self.study, [failed, untouched])
        result = self.launch(self.study)
        self.assertEqual(result.returncode, 7, result.stderr)
        index = next((self.study / "batches").glob("*/index.md")).read_text()
        self.assertIn("failed (exit 7)", index)
        self.assertIn("round02`: unattempted", index)
        self.assertIn("round-failed/runs/", index)
        self.assertFalse((untouched / "runs").exists())

    def test_zero_exit_without_actual_run_is_failure(self):
        empty = self.round("round-empty")
        self.batch(self.study, [empty])
        result = self.launch(self.study)
        self.assertEqual(result.returncode, 2, result.stderr)
        index = next((self.study / "batches").glob("*/index.md")).read_text()
        self.assertIn("failed (exit 2)", index)
        self.assertNotIn("completed", index)

    def test_multiple_new_outputs_are_ambiguous_and_stop_next_leaf(self):
        ambiguous, untouched = self.round("round-multiple"), self.round("round02")
        self.batch(self.study, [ambiguous, untouched])
        result = self.launch(self.study)
        self.assertEqual(result.returncode, 2, result.stderr)
        index = next((self.study / "batches").glob("*/index.md")).read_text()
        self.assertIn("ambiguous new outputs, attribution unknown", index)
        self.assertNotIn("completed", index)
        self.assertFalse((untouched / "runs").exists())

    def _assert_parent_signal(self, number):
        waiting, untouched = self.round("round-wait"), self.round("round02")
        self.batch(self.study, [waiting, untouched])
        process = subprocess.Popen(
            [str(self.study / "run.sh")],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            while not list((waiting / "runs").glob("*/waiting")):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail("Frozen expensive-runner fixture did not start")
                time.sleep(0.05)
            process.send_signal(number)
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 128 + number, error)
            self.assertEqual(len(list((waiting / "runs").glob("*/terminated"))), 1)
            self.assertFalse((untouched / "runs").exists())
            index = next((self.study / "batches").glob("*/index.md")).read_text()
            self.assertIn(f"failed (exit {128 + number})", index)
            self.assertIn("round02`: unattempted", index)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_parent_only_termination_reaches_child_and_stops_next_leaf(self):
        self._assert_parent_signal(signal.SIGTERM)

    def test_parent_only_interrupt_reaches_child_and_stops_next_leaf(self):
        self._assert_parent_signal(signal.SIGINT)


if __name__ == "__main__":
    unittest.main()
