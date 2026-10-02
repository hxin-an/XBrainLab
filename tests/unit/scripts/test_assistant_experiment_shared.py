"""Real copy/shell/environment isolation; only model execution is substituted."""

# ruff: noqa: S603, S607 -- bounded disposable shell/Git/venv integration.

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path

from tests.unit.scripts import test_assistant_experiment_package as package_fixture

ROOT = package_fixture.ROOT


@unittest.skipUnless(os.name == "posix", "Shared Linux experiment environment")
class SharedExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory(prefix="shared-readonly-env-")
        cls.addClassCleanup(cls.environment.cleanup)
        venv.EnvBuilder(with_pip=False).create(cls.environment.name)
        cls.python = Path(cls.environment.name) / "bin/python"

    def setUp(self):
        self.fixture = package_fixture.ExperimentPackageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.output = self.fixture.output
        scripts = self.fixture.source / "scripts/dev"
        for name in (
            "assistant_experiment_shared.py",
            "assistant_experiment_portable.py",
        ):
            source = ROOT / "scripts/dev" / name
            if source.exists():
                shutil.copyfile(source, scripts / name)
        (scripts / "run_assistant_dev.py").write_text(
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--output') + 1])\n"
            "out.mkdir(parents=True, exist_ok=False)\n"
            "cache = pathlib.Path(os.environ['XBRAINLAB_CACHE_DIR'])\n"
            "(cache / 'fixture-write').write_text('local only')\n"
            "(out / 'called.json').write_text(json.dumps({'args': args, 'prefix': sys.prefix, 'env': dict(os.environ)}))\n"
        )
        self.fixture.git(self.fixture.source, "add", ".")
        self.fixture.git(self.fixture.source, "commit", "-qm", "shared fixture")
        self.fixture.head = self.fixture.git(
            self.fixture.source, "rev-parse", "HEAD"
        ).strip()
        self.fixture.values["models"][0]["source"]["head"] = self.fixture.head
        for relative in ("shared/model", "shared/embedding"):
            (self.root / relative).mkdir(parents=True)
        self.fixture.save_config()

    def create(self):
        return self.fixture.api.create_package(
            self.fixture.bank,
            self.fixture.config,
            self.output,
            coordinator_root=self.fixture.source,
            shared_python=self.python,
        )

    def launch(self, *args, entry="run.sh", env=None):
        return subprocess.run(
            ["bash", str(self.output / entry), *args],
            env=dict(os.environ, **(env or {})),
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_copy_runs_twice_without_original_source_or_manual_environment(self):
        self.create()
        original = self.output
        self.output = self.root / "recipient space 中文" / "round-01"
        shutil.copytree(original, self.output)
        for directory in (
            original,
            self.root / "shared/model",
            self.root / "shared/embedding",
        ):
            original_mode = directory.stat().st_mode
            directory.chmod(0o555)
            self.addCleanup(directory.chmod, original_mode)
        self.fixture.source.rename(self.root / "source-not-used")
        poison = dict.fromkeys(
            (
                "PYTHONPATH",
                "PYTHONHOME",
                "VIRTUAL_ENV",
                "XBL_PYTHON",
                "XBRAINLAB_CONFIG_DIR",
                "XBRAINLAB_CACHE_DIR",
                "HF_HOME",
            ),
            "/must/not/be/used",
        )
        for _ in range(2):
            result = self.launch(env=poison)
            self.assertEqual(result.returncode, 0, result.stderr)
        runs = list((self.output / "runs").iterdir())
        self.assertEqual(len(runs), 2)
        for run in runs:
            called = json.loads((run / "called.json").read_text())
            self.assertEqual(called["prefix"], self.environment.name)
            for name in (
                "XBRAINLAB_CACHE_DIR",
                "XBRAINLAB_LOG_DIR",
                "HF_HOME",
                "TMPDIR",
            ):
                self.assertTrue(Path(called["env"][name]).is_relative_to(self.output))
            self.assertNotIn("VIRTUAL_ENV", called["env"])
        self.assertFalse((original / "runs").exists())
        self.assertFalse((original / ".runtime").exists())
        self.assertFalse((self.output / "models").exists())
        self.fixture.api.verify_package(self.output)

    def test_check_environment_does_not_create_run_or_install_venv(self):
        self.create()
        readme = (self.output / "README.md").read_text()
        self.assertIn(self.fixture.head, readme)
        self.assertIn("granite4", readme)
        result = self.launch("--check-environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No inference", result.stdout)
        self.assertFalse((self.output / "runs").exists())
        self.assertEqual(
            [p.name for p in (self.output / ".runtime").iterdir()], ["cache"]
        )

    def test_missing_shared_model_stops_check_before_run(self):
        self.create()
        (self.root / "shared/model").rmdir()
        result = self.launch("--check-environment")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("resource", result.stderr.lower())
        self.assertFalse((self.output / "runs").exists())

    def test_adjustment_notes_are_frozen_not_read_from_editable_file(self):
        notes = self.root / "round-notes.md"
        notes.write_text("Granite: baseline, no model-specific prompt changes.")
        self.fixture.api.create_package(
            self.fixture.bank,
            self.fixture.config,
            self.output,
            coordinator_root=self.fixture.source,
            shared_python=self.python,
            notes=notes,
        )
        notes.write_text("Unapproved later edit")
        readme = (self.output / "README.md").read_text()
        self.assertIn("Granite: baseline", readme)
        self.assertNotIn("Unapproved", readme)
        self.fixture.api.verify_package(self.output)

    def test_missing_shared_python_is_not_replaced_by_system_python(self):
        local = self.root / "missing environment"
        venv.EnvBuilder(with_pip=False).create(local)
        self.python = local / "bin/python"
        self.create()
        self.python.unlink()
        result = self.launch("--check-environment")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or not executable", result.stderr)
        self.assertFalse((self.output / "runs").exists())

    def test_changed_shared_python_environment_is_rejected(self):
        local = self.root / "mutable environment"
        venv.EnvBuilder(with_pip=False).create(local)
        self.python = local / "bin/python"
        self.create()
        site = next((local / "lib").glob("python*/site-packages"))
        dist = site / "unexpected-1.0.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text("Name: unexpected\nVersion: 1.0\n")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("environment", result.stderr.lower())
        self.assertFalse((self.output / "runs").exists())

    def test_symlinked_output_cannot_write_to_original(self):
        self.create()
        external = self.root / "other-user-results"
        external.mkdir()
        (self.output / "runs").symlink_to(external, target_is_directory=True)
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_nested_cache_link_cannot_overwrite_outside_file(self):
        self.create()
        self.assertEqual(self.launch("--check-environment").returncode, 0)
        external = self.root / "original-result.txt"
        external.write_text("preserve original")
        (self.output / ".runtime/cache/app/fixture-write").symlink_to(external)
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(external.read_text(), "preserve original")
        self.assertFalse((self.output / "runs").exists())

    def test_tampered_binding_rejected_before_environment_probe(self):
        self.create()
        metadata = self.output / "environment/shared.json"
        value = json.loads(metadata.read_text())
        value["python"] = "/does/not/exist/python"
        metadata.write_text(json.dumps(value))
        result = self.launch("--check-environment")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Sealed package file differs", result.stderr)
        self.assertFalse((self.output / "runs").exists())

    def test_explicit_comparison_output_must_stay_in_copy(self):
        self.create()
        result = self.launch(
            str(self.root),
            str(self.root),
            "--output",
            str(self.root / "external"),
            entry="compare.sh",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "external").exists())


if __name__ == "__main__":
    unittest.main()
