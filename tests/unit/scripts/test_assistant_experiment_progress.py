"""Progress is a read-only view, never the experiment's success authority."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.dev import assistant_experiment_batch as batch
from scripts.dev import assistant_experiment_progress as progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.jobs = [
            {"id": f"{model}-{i}", "condition": model}
            for model in ("model-a", "model-b")
            for i in range(2)
        ]

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def manifest(self):
        self.write("prepared-manifest.json", {"jobs": self.jobs})

    def condition(self, model, count, status="running"):
        return self.write(
            f"raw/conditions/{model}/result.json",
            {
                "status": status,
                "results": [
                    {"id": f"{model}-{i}", "status": "recorded", "cleanup_ok": True}
                    for i in range(count)
                ],
            },
        )

    def test_startup_model_transition_and_report_without_mutation(self):
        self.assertIn("Preparing", progress.describe(self.root))
        self.manifest()
        self.assertIn("0/4", progress.describe(self.root))
        self.condition("model-a", 0)
        self.assertIn("Loading model / first case", progress.describe(self.root))
        self.condition("model-a", 1)
        self.assertIn("model-a 1/2", progress.describe(self.root))
        self.condition("model-a", 2, "recorded")
        self.condition("model-b", 1)
        self.assertIn("model-b 1/2", progress.describe(self.root))
        self.assertIn("3/4", progress.describe(self.root))
        self.condition("model-b", 2, "recorded")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertIn("Finalizing / report", progress.describe(self.root))
        self.assertEqual(
            before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        )

    def test_failed_measurement_is_not_recorded_success(self):
        self.manifest()
        path = self.condition("model-a", 1, "measurement_failed")
        value = json.loads(path.read_text())
        value["results"].append({"id": "model-a-1", "status": "measurement_failed"})
        path.write_text(json.dumps(value))
        line = progress.describe(self.root)
        self.assertIn("1/4 recorded", line)
        self.assertIn("measurement_failed", line)

    def test_partial_write_is_unavailable_not_zero_progress(self):
        self.manifest()
        path = self.condition("model-a", 1)
        path.write_text('{"status":')
        self.assertIn("temporarily unavailable", progress.describe(self.root))

    @unittest.skipUnless(os.name == "posix", "Linux launcher")
    def test_progress_updates_while_child_is_running(self):
        self.manifest()
        path = self.condition("model-a", 0)
        child = (
            "import json, pathlib, time; time.sleep(0.2); "
            f"p=pathlib.Path({str(path)!r}); d=json.loads(p.read_text()); "
            "d['results']=[{'id':'model-a-0','status':'recorded','cleanup_ok':True}]; "
            "p.write_text(json.dumps(d)); time.sleep(5.2)"
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = batch._invoke(
                [sys.executable, "-c", child],
                dict(os.environ),
                self.root,
                progress_root=self.root,
            )
        self.assertEqual(code, 0)
        lines = output.getvalue().splitlines()
        self.assertIn("0/4", lines[0])
        self.assertTrue(
            any("1/4" in line and "Runner exit" not in line for line in lines)
        )

    @unittest.skipUnless(os.name == "posix", "Linux launcher")
    def test_closed_progress_output_does_not_abandon_child(self):
        class ClosedOutput:
            def write(self, _value):
                raise BrokenPipeError

        marker = self.root / "finished"
        with contextlib.redirect_stdout(ClosedOutput()):
            code = batch._invoke(
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).touch()",
                ],
                dict(os.environ),
                self.root,
                progress_root=self.root,
            )
        self.assertEqual(code, 0)
        self.assertTrue(marker.is_file())

    @unittest.skipUnless(os.name == "posix", "Linux launcher")
    def test_real_child_emits_progress_and_keeps_failure_exit(self):
        self.manifest()
        self.condition("model-a", 1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = batch._invoke(
                [sys.executable, "-c", "raise SystemExit(7)"],
                dict(os.environ),
                self.root,
                progress_root=self.root,
            )
        self.assertEqual(code, 7)
        self.assertIn("model-a 1/2", output.getvalue())
        self.assertIn("Elapsed", output.getvalue())
        self.assertIn("exit 7", output.getvalue())
