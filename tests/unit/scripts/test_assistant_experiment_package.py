"""Real Git snapshots and generated shell entry; no models or research execution."""

# ruff: noqa: S603, S607 -- fixed fixture Git/Python/shell processes, no external input.

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.name == "posix", "Linux package shell/Git integration")
class ExperimentPackageTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("scripts.dev.assistant_experiment_package")
        self.temporary = tempfile.TemporaryDirectory(prefix="experiment-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "editable-source"
        self.source.mkdir()
        scripts = self.source / "scripts" / "dev"
        scripts.mkdir(parents=True)
        for name in (
            "assistant_experiment_package.py",
            "assistant_experiment_config.py",
        ):
            shutil.copyfile(ROOT / "scripts" / "dev" / name, scripts / name)
        # Only the expensive runner boundary is substituted. Git, filesystem,
        # generated shell, process cwd, Python import and argv are real.
        (scripts / "run_assistant_dev.py").write_text(
            "import json, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--output') + 1])\n"
            "out.mkdir(parents=True, exist_ok=True)\n"
            "(out / 'called.json').write_text(json.dumps({'args': args, 'cwd': str(pathlib.Path.cwd()), 'prefix': sys.prefix}))\n",
            encoding="utf-8",
        )
        (scripts / "assistant_experiment_audit.py").write_text(
            "import json, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--run') + 1])\n"
            "(out / 'audit-called.json').write_text(json.dumps({'args': args}))\n",
            encoding="utf-8",
        )
        (self.source / "pyproject.toml").write_text("# fixture project\n")
        (self.source / "poetry.lock").write_text("# fixture lock\n")
        (self.source / ".gitignore").write_text("__pycache__/\nprivate/\n")
        (self.source / "settings.json").write_text('{"committed": true}\n')
        self.git(self.source, "init", "-q")
        self.git(self.source, "config", "user.email", "fixture@example.invalid")
        self.git(self.source, "config", "user.name", "Fixture")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "fixture")
        self.head = self.git(self.source, "rev-parse", "HEAD").strip()
        self.bank = self.root / "bank.xlsx"
        self.bank.write_bytes(b"opaque bank bytes: runner owns XLSX validation")
        self.config = self.root / "config.json"
        (self.root / "resource-copy.json").write_text('{"resources": []}\n')
        self.values = {
            "schema": "xbrainlab.assistant_experiment_config.v1",
            "split": "DEV",
            "purpose": "engineering-smoke",
            "case_ids": ["DEV-A01-01-V0"],
            "budget_seconds": 60,
            "embedding_cache": "shared/embedding",
            "resource_inventory": "resource-copy.json",
            "models": [
                {
                    "alias": "granite4",
                    "candidate_index": 2,
                    "source": {"root": str(self.source), "head": self.head},
                    "model_cache": "shared/model",
                }
            ],
        }
        self.save_config()
        self.output = self.root / "packages" / "封存 experiment"

    @staticmethod
    def git(root, *args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, timeout=20
        )

    def save_config(self):
        self.config.write_text(json.dumps(self.values), encoding="utf-8")

    def create(self):
        self.api.create_package(
            self.bank, self.config, self.output, coordinator_root=self.source
        )

    def launch(self, *args):
        environment = dict(os.environ, XBL_PYTHON=sys.executable)
        return subprocess.run(
            ["bash", str(self.output / "run.sh"), *args],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def retained_run(self, name="retained", source_package=None):
        run = self.output / "runs" / name
        shutil.copytree((source_package or self.output) / "inputs", run / "inputs")
        return run

    def test_independent_snapshot_and_no_private_copy(self):
        private = self.source / "private"
        private.mkdir()
        (private / "secret").write_text("not part of the source")
        self.create()
        snapshot = self.output / "sources" / self.head
        self.assertEqual(self.git(snapshot, "rev-parse", "HEAD").strip(), self.head)
        self.assertTrue((snapshot / ".git").is_dir())
        self.assertFalse((snapshot / ".git/objects/info/alternates").exists())
        self.assertFalse((snapshot / "private").exists())
        sealed = json.loads((self.output / "inputs/config.json").read_text())
        self.assertEqual(
            sealed["models"][0]["source"]["root"], f"../sources/{self.head}"
        )
        self.assertEqual(json.loads(self.config.read_text()), self.values)
        self.assertEqual(
            (self.output / "inputs/bank.xlsx").read_bytes(), self.bank.read_bytes()
        )
        self.source.rename(self.root / "unavailable-source")
        self.api.verify_package(self.output)

    def test_moved_package_launches_from_outside_cwd(self):
        self.create()
        moved = self.root / "搬移 new parent" / "package 空白"
        moved.parent.mkdir()
        self.output.rename(moved)
        self.output = moved
        self.source.rename(self.root / "unavailable-source")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = list((self.output / "runs").glob("*/called.json"))
        self.assertEqual(len(calls), 1)
        called = json.loads(calls[0].read_text())
        self.assertEqual(called["args"][0], "run")
        self.assertEqual(Path(called["cwd"]), self.output / "sources" / self.head)
        self.assertEqual(
            Path(called["args"][called["args"].index("--config") + 1]),
            self.output / "inputs/config.json",
        )

    def test_resume_and_model_free_report_forward_to_original_run(self):
        self.create()
        run = self.retained_run()
        # There are deliberately no model or embedding directories.
        result = self.launch("--report-only", "retained")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads((run / "called.json").read_text())["args"],
            ["report", "--output", str(run)],
        )
        result = self.launch("--resume", str(run), "--replace-invalid")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads((run / "called.json").read_text())["args"],
            ["resume", "--output", str(run), "--replace-invalid"],
        )

    def test_audit_is_model_free_and_delegates_to_existing_audit_owner(self):
        self.create()
        run = self.retained_run()
        result = self.launch("--audit", "retained")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads((run / "audit-called.json").read_text())["args"],
            ["--package", str(self.output), "--run", str(run)],
        )
        self.assertFalse((run / "called.json").exists())

    def test_foreign_run_with_same_source_but_different_config_refused(self):
        self.create()
        foreign = self.output
        self.values["models"][0]["candidate_index"] = 3
        self.save_config()
        self.output = foreign.with_name("different-config-package")
        self.create()
        self.assertEqual(
            self.api.verify_package(foreign)["sources"],
            self.api.verify_package(self.output)["sources"],
        )
        for action in ("--resume", "--report-only", "--audit"):
            with self.subTest(action=action):
                run = self.retained_run(action.removeprefix("--"), foreign)
                before = {
                    path.name: path.read_bytes() for path in (run / "inputs").iterdir()
                }
                result = self.launch(action, run.name)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    "Retained run inputs differ from sealed package", result.stderr
                )
                self.assertFalse((run / "called.json").exists())
                self.assertFalse((run / "audit-called.json").exists())
                self.assertEqual(
                    before,
                    {
                        path.name: path.read_bytes()
                        for path in (run / "inputs").iterdir()
                    },
                )

    def test_each_retained_input_must_match_sealed_package_before_dispatch(self):
        self.create()
        for filename in ("bank.xlsx", "config.json", "resources.json"):
            for missing in (False, True):
                with self.subTest(filename=filename, missing=missing):
                    run = self.retained_run(f"{filename}-{missing}")
                    target = run / "inputs" / filename
                    if missing:
                        target.unlink()
                    else:
                        target.write_bytes(target.read_bytes() + b"changed")
                    result = self.launch("--report-only", run.name)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((run / "called.json").exists())

    def test_sealed_file_mutation_refused_before_runner(self):
        for relative in (
            "inputs/bank.xlsx",
            "inputs/config.json",
            "run.sh",
            f"sources/{self.head}/poetry.lock",
        ):
            with self.subTest(relative=relative):
                if self.output.exists():
                    self.output = self.output.with_name(self.output.name + "-next")
                self.create()
                path = self.output / relative
                path.write_bytes(path.read_bytes() + b"\nchanged")
                result = self.launch("--report-only", "retained")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list(self.output.glob("runs/*/called.json")))

    def test_missing_source_refused_before_runner(self):
        self.create()
        snapshot = self.output / "sources" / self.head
        snapshot.rename(self.output / "sources" / "missing")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "runs").exists())

    def test_dirty_or_mismatched_source_does_not_publish_package(self):
        (self.source / "poetry.lock").write_text("dirty")
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse((self.output / "run.sh").exists())

    def test_existing_output_preserved(self):
        self.output.mkdir(parents=True)
        sentinel = self.output / "sentinel"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_ambiguous_or_foreign_run_selection_refused(self):
        self.create()
        for args in (
            ("--replace-invalid",),
            ("--resume", "a", "--report-only", "b"),
            ("--audit", "a", "--report-only", "b"),
            ("--audit", "a", "--replace-invalid"),
            ("--resume", str(self.root)),
        ):
            result = self.launch(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(self.output.glob("runs/*/called.json")))

    def test_distinct_candidate_and_coordinator_heads_are_all_sealed(self):
        candidate = self.root / "other-source"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-local", str(self.source), str(candidate)],
            check=True,
            timeout=20,
        )
        self.git(candidate, "config", "user.email", "fixture@example.invalid")
        self.git(candidate, "config", "user.name", "Fixture")
        (candidate / "candidate.txt").write_text("different model candidate source")
        self.git(candidate, "add", "candidate.txt")
        self.git(candidate, "commit", "-qm", "candidate")
        other_head = self.git(candidate, "rev-parse", "HEAD").strip()
        self.values["models"].append(
            {
                "alias": "phi4",
                "candidate_index": 4,
                "source": {"root": str(candidate), "head": other_head},
                "model_cache": "shared/phi4",
            }
        )
        self.save_config()
        self.create()
        manifest = self.api.verify_package(self.output)
        self.assertEqual(set(manifest["sources"]), {self.head, other_head})
        self.assertEqual(manifest["coordinator"], self.head)
        for head in (self.head, other_head):
            self.assertEqual(
                self.git(self.output / "sources" / head, "rev-parse", "HEAD").strip(),
                head,
            )

    def test_resource_inventory_is_sealed_without_requiring_resources(self):
        inventory = self.root / "resource-copy.json"
        inventory.write_text('{"resources": []}\n')
        self.values["resource_inventory"] = inventory.name
        self.save_config()
        self.create()
        self.assertEqual(
            (self.output / "inputs/resources.json").read_bytes(), inventory.read_bytes()
        )
        self.assertEqual(
            json.loads((self.output / "inputs/config.json").read_text())[
                "resource_inventory"
            ],
            "resources.json",
        )
        self.assertIn(
            "inputs/resources.json", self.api.verify_package(self.output)["files"]
        )
        (self.output / "inputs/resources.json").write_text("changed")
        with self.assertRaises(ValueError):
            self.api.verify_package(self.output)

    def test_relative_resource_binding_is_rebased_once(self):
        self.create()
        sealed = json.loads((self.output / "inputs/config.json").read_text())
        self.assertEqual(
            (self.output / "inputs" / sealed["embedding_cache"]).resolve(),
            self.root / "shared/embedding",
        )
        self.assertEqual(
            (self.output / "inputs" / sealed["models"][0]["model_cache"]).resolve(),
            self.root / "shared/model",
        )

    def test_source_settings_are_not_modified_or_read_from_local_edits(self):
        settings = self.source / "settings.json"
        self.create()
        original = settings.read_bytes()
        self.assertEqual(
            (self.output / "sources" / self.head / "settings.json").read_bytes(),
            original,
        )
        settings.write_text('{"local": "not exported"}\n')
        self.output = self.output.with_name("second-package")
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(settings.read_text(), '{"local": "not exported"}\n')
        self.assertFalse(self.output.exists())

    def test_create_cli_uses_its_own_coordinator_checkout(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.dev.assistant_experiment_package",
                "create",
                "--bank",
                str(self.bank),
                "--config",
                str(self.config),
                "--output",
                str(self.output),
            ],
            cwd=self.source,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.api.verify_package(self.output)["coordinator"], self.head)

    def test_missing_python_binding_is_explicit(self):
        self.create()
        environment = dict(os.environ)
        environment.pop("XBL_PYTHON", None)
        completed = subprocess.run(
            ["bash", str(self.output / "run.sh")],
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("XBL_PYTHON", completed.stderr)
        self.assertFalse((self.output / "runs").exists())

    def test_plain_launcher_uses_unsealed_local_environment_binding(self):
        self.create()
        binding = self.output / "environment/python"
        binding.symlink_to(sys.executable)
        self.assertNotIn(
            "environment/python", self.api.verify_package(self.output)["files"]
        )
        environment = dict(os.environ)
        environment.pop("XBL_PYTHON", None)
        completed = subprocess.run(
            [str(self.output / "run.sh")],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(list(self.output.glob("runs/*/called.json"))), 1)

    def test_local_binding_keeps_real_virtual_environment(self):
        environment_root = self.root / "locked environment"
        venv.EnvBuilder(with_pip=False).create(environment_root)
        self.create()
        (self.output / "environment/python").symlink_to(environment_root / "bin/python")
        environment = dict(os.environ)
        environment.pop("XBL_PYTHON", None)
        completed = subprocess.run(
            [str(self.output / "run.sh")],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = next(self.output.glob("runs/*/called.json"))
        self.assertEqual(
            json.loads(receipt.read_text())["prefix"], str(environment_root)
        )


if __name__ == "__main__":
    unittest.main()
