"""Single experiment snapshot: real Git, shell, copies and offline comparison.

Only expensive model execution is substituted. The frozen runner fixture records
its real arguments/environment and provides deterministic failure/cancellation.
"""

# ruff: noqa: S603 -- fixed disposable shell/Git/venv fixture processes.

from __future__ import annotations

import importlib
import json
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
from unittest.mock import patch

from scripts.dev.assistant_experiment_audit import evidence_digest
from tests.unit.scripts import test_assistant_experiment_compare as compare_tests
from tests.unit.scripts import test_assistant_experiment_package as package_tests

ROOT = Path(__file__).resolve().parents[3]
DEV = "stages/dev"
ROUND = f"{DEV}/round-01"


@unittest.skipUnless(os.name == "posix", "Linux shared experiment integration")
class ExperimentBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory(prefix="central-shared-env-")
        cls.addClassCleanup(cls.environment.cleanup)
        venv.EnvBuilder(with_pip=False).create(cls.environment.name)
        cls.python = Path(cls.environment.name) / "bin/python"

    def setUp(self):
        self.api = importlib.import_module("scripts.dev.assistant_experiment_batch")
        self.fixture = package_tests.ExperimentPackageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.source = self.fixture.root, self.fixture.source
        scripts = self.source / "scripts/dev"
        for name in (
            "assistant_experiment_batch.py",
            "assistant_experiment_progress.py",
            "assistant_experiment_shared.py",
            "assistant_experiment_portable.py",
            "assistant_experiment_compare.py",
            "assistant_experiment_audit.py",
            "assistant_pilot_presentation.py",
        ):
            shutil.copyfile(ROOT / "scripts/dev" / name, scripts / name)
        shutil.copytree(
            ROOT / "scripts/dev/assistant_report_assets",
            scripts / "assistant_report_assets",
        )
        (scripts / "run_assistant_dev.py").write_text(
            "import json, os, pathlib, signal, sys, time\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--output') + 1])\n"
            "config_path = pathlib.Path(args[args.index('--config') + 1])\n"
            "config = json.loads(config_path.read_text())\n"
            "candidate = config['models'][0]['candidate_index']\n"
            "mode = os.environ.get('XBL_FIXTURE_CANDIDATE_' + str(candidate), '')\n"
            "if mode == 'empty': sys.exit(0)\n"
            "out.mkdir(parents=True, exist_ok=False)\n"
            "called = {'candidate': candidate, 'args': args, 'config': config, 'pid': os.getpid(),\n"
            " 'started_ns': time.time_ns(), 'prefix': sys.prefix, 'env': dict(os.environ)}\n"
            "(out / 'called.json').write_text(json.dumps(called))\n"
            "(out / 'prepared-manifest.json').write_text(json.dumps({'config': config}))\n"
            "if mode == 'fail': sys.exit(7)\n"
            "if mode == 'wait':\n"
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
        self.fixture.git(self.source, "commit", "-qm", "central experiment fixture")
        self.head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = self.head
        for relative in ("shared/model", "shared/embedding"):
            (self.root / relative).mkdir(parents=True)
        self.study = self.root / "研究 experiment"

    def selection(self, candidate=1, *, path=None, model=None):
        values = json.loads(json.dumps(self.fixture.values))
        values["models"][0]["candidate_index"] = candidate
        if model is not None:
            values["models"][0]["model_cache"] = str(model)
        config = self.root / f"candidate-{candidate}.json"
        config.write_text(json.dumps(values), encoding="utf-8")
        return {
            "path": path or f"{DEV}/round-{candidate:02}",
            "bank": self.fixture.bank,
            "config": config,
            "notes": f"Fixture candidate {candidate}; no inference.",
        }

    def create(self, selections=None, *, references=()):
        selections = selections or [self.selection()]
        scopes = {
            ".": {"children": [DEV, "stages/val", "stages/test"]},
            DEV: {"children": [item["path"] for item in selections]},
            "stages/val": {"blocked_reason": "VALID is not frozen"},
            "stages/test": {"blocked_reason": "TEST remains sealed"},
        }
        return self.api.create_experiment(
            self.study,
            selections,
            scopes,
            coordinator_root=self.source,
            shared_python=self.python,
            references=list(references),
        )

    def launch(self, scope=DEV, *arguments, entry="run.sh", env=None):
        return subprocess.run(
            [str(self.study / scope / entry), *map(str, arguments)],
            cwd=self.root,
            env=dict(os.environ, **(env or {})),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def calls(self):
        return sorted((self.study / "results/runs").glob("*/called.json"))

    def scope_index(self):
        files = list((self.study / "results/runs").glob("*-scope.json"))
        self.assertEqual(len(files), 1)
        return files[0].read_text()

    def test_central_source_dedup_and_stage_entries_share_one_snapshot(self):
        self.create([self.selection(1), self.selection(2)])
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(manifest["sources"], [self.head])
        sources = self.study / "snapshot/sources"
        self.assertEqual([path.name for path in sources.iterdir()], [self.head])
        self.assertEqual(len(list((self.study / "snapshot/inputs").glob("*.xlsx"))), 1)
        for scope in (".", DEV, ROUND, "stages/val", "stages/test"):
            self.assertTrue((self.study / scope / "run.sh").is_file())
        self.assertFalse(list((self.study / "stages").rglob(".git")))
        self.assertFalse(list(self.study.rglob("batch-source")))
        self.assertTrue((self.study / "compare.sh").is_file())

    def test_append_round_preserves_existing_files_and_runs_both_candidates(self):
        self.create()
        self.assertEqual(self.launch(ROUND).returncode, 0)
        before = {
            path.relative_to(self.study): path.read_bytes()
            for path in self.study.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        (self.source / "candidate-notes.txt").write_text("Second candidate source\n")
        self.fixture.git(self.source, "add", "candidate-notes.txt")
        self.fixture.git(self.source, "commit", "-qm", "second candidate")
        new_head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = new_head
        self.api.append_round(
            self.study, self.selection(2), coordinator_root=self.source
        )
        self.assertEqual(len(self.calls()), 1)  # Sealing never starts inference.
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(manifest["coordinator"], new_head)
        self.assertEqual(set(manifest["sources"]), {self.head, new_head})
        self.assertEqual(
            manifest["scopes"][DEV]["children"], [ROUND, f"{DEV}/round-02"]
        )
        for relative, original in before.items():
            self.assertEqual((self.study / relative).read_bytes(), original, relative)
        for scope in (ROUND, f"{DEV}/round-02"):
            result = self.launch(scope)
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(path.read_text()) for path in self.calls()]
        self.assertEqual(sorted(row["candidate"] for row in calls), [1, 1, 2])
        second = next(row for row in calls if row["candidate"] == 2)
        self.assertEqual(second["config"]["models"][0]["source"]["head"], new_head)
        self.assertTrue(second["env"]["PYTHONPATH"].endswith(new_head))

    def test_append_refuses_existing_round_and_changed_old_inventory(self):
        self.create()
        manifest_path = self.study / "snapshot/manifest.json"
        original_manifest = manifest_path.read_bytes()
        with self.assertRaises(ValueError):
            self.api.append_round(
                self.study, self.selection(1), coordinator_root=self.source
            )
        config = self.study / ROUND / "config.json"
        original_config = config.read_bytes()
        config.write_bytes(original_config + b"\n")
        with self.assertRaisesRegex(ValueError, "Frozen experiment file differs"):
            self.api.append_round(
                self.study, self.selection(2), coordinator_root=self.source
            )
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertFalse((self.study / DEV / "round-02").exists())
        config.write_bytes(original_config)
        self.api.verify_experiment(self.study)

    def test_failed_append_publication_leaves_old_round_usable_and_retryable(self):
        self.create()
        old = (self.study / "snapshot/manifest.json").read_bytes()
        (self.source / "new-source.txt").write_text("Second source\n")
        self.fixture.git(self.source, "add", "new-source.txt")
        self.fixture.git(self.source, "commit", "-qm", "second source")
        self.fixture.values["models"][0]["source"]["head"] = self.fixture.git(
            self.source, "rev-parse", "HEAD"
        ).strip()
        selection = self.selection(2)
        with (
            patch.object(self.api.os, "replace", side_effect=OSError("disk error")),
            self.assertRaisesRegex(OSError, "disk error"),
        ):
            self.api.append_round(self.study, selection, coordinator_root=self.source)
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), old)
        self.api.verify_experiment(self.study)
        self.assertFalse((self.study / DEV / "round-02").exists())
        self.assertEqual(
            [path.name for path in (self.study / "snapshot/sources").iterdir()],
            [self.head],
        )
        result = self.launch(ROUND)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.api.append_round(self.study, selection, coordinator_root=self.source)
        result = self.launch(f"{DEV}/round-02")
        self.assertEqual(result.returncode, 0, result.stderr)

    def valid_selection(self):
        selection = self.selection(2, path="stages/val")
        config = json.loads(selection["config"].read_text())
        config.update(split="VALID", purpose="research")
        del config["case_ids"]
        selection["config"].write_text(json.dumps(config))
        return selection

    def legacy_tree_with_test_selection(self):
        """Historical hardcoded shell and TEST-unaware parser, not today's bootstrap."""
        parser = self.source / "scripts/dev/assistant_experiment_config.py"
        original_parser = parser.read_text()
        parser.write_text(
            original_parser.replace('{"DEV", "VALID", "TEST"}', '{"DEV", "VALID"}')
        )
        self.fixture.git(self.source, "add", ".")
        self.fixture.git(self.source, "commit", "-qm", "Historical TEST-unaware parser")
        old_head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = old_head
        self.create()
        manifest = self.api.verify_experiment(self.study)
        entries = [
            (scope, "run.sh", f"--scope {scope}") for scope in manifest["scopes"]
        ]
        entries.append((".", "compare.sh", "--compare"))
        for scope, filename, action in entries:
            directory = self.study if scope == "." else self.study / scope
            relative = os.path.relpath(self.study, directory)
            entry = directory / filename
            entry.write_text(
                "#!/bin/sh\nset -eu\n"
                f'EXPERIMENT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/{relative}" && pwd)\n'
                f"exec python{sys.version_info.major}.{sys.version_info.minor} -I -B "
                f'"$EXPERIMENT_ROOT/snapshot/sources/{old_head}/scripts/dev/assistant_experiment_batch.py" '
                f'--experiment "$EXPERIMENT_ROOT" {action} "$@"\n'
            )
            manifest["files"][entry.relative_to(self.study).as_posix()] = (
                self.api.package_api._digest(entry)
            )
        self.api.package_api._write(self.study / "snapshot/manifest.json", manifest)
        parser.write_text(original_parser)
        self.fixture.git(self.source, "add", ".")
        self.fixture.git(self.source, "commit", "-qm", "TEST-capable coordinator")
        candidate_head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = candidate_head
        selection = self.selection(5, path="stages/test")
        config = json.loads(selection["config"].read_text())
        config.update(split="TEST", purpose="research")
        del config["case_ids"]
        config["models"][0]["alias"] = "phi4"
        selection["config"].write_text(json.dumps(config))
        self.api.activate_test_stage(
            self.study, selection, coordinator_root=self.source
        )
        return candidate_head

    def test_migrate_real_old_bootstrap_before_schema_validation_preserves_research(
        self,
    ):
        candidate_head = self.legacy_tree_with_test_selection()
        for scope in (DEV, "stages/test"):
            result = self.launch(scope, "--check-environment")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsupported experiment schema", result.stderr)
        before = {
            p.relative_to(self.study).as_posix(): p.read_bytes()
            for p in self.study.rglob("*")
            if p.is_file()
        }
        # Neither coordinator nor measured candidate/config changes for this repair.
        history = self.api.migrate_launchers(self.study)
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(manifest["coordinator"], candidate_head)
        self.assertEqual(
            (history / "manifest.json").read_bytes(), before["snapshot/manifest.json"]
        )
        for name, content in before.items():
            if name == "snapshot/manifest.json":
                continue
            if name in {"compare.sh", "run.sh"} or (
                name.startswith("stages/") and name.endswith("/run.sh")
            ):
                self.assertEqual((history / "entries" / name).read_bytes(), content)
            else:
                self.assertEqual((self.study / name).read_bytes(), content, name)
        for scope in (DEV, "stages/test"):
            result = self.launch(scope, "--check-environment")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        result = self.launch("stages/test")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(self.calls()[0].read_text())
        self.assertEqual(call["config"]["models"][0]["source"]["head"], candidate_head)
        self.assertTrue(call["env"]["PYTHONPATH"].endswith(candidate_head))
        after = (self.study / "snapshot/manifest.json").read_bytes()
        self.assertIsNone(self.api.migrate_launchers(self.study))
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), after)

    def test_launcher_migration_failed_manifest_publish_restores_entries_and_keeps_history(
        self,
    ):
        self.legacy_tree_with_test_selection()
        before = {
            p.relative_to(self.study).as_posix(): p.read_bytes()
            for p in self.study.rglob("*")
            if p.is_file()
        }
        replace = self.api.os.replace

        def fail_publication(source, destination):
            if Path(destination) == self.study / "snapshot/manifest.json":
                raise OSError("Injected manifest publication failure")
            return replace(source, destination)

        with (
            patch.object(self.api.os, "replace", side_effect=fail_publication),
            self.assertRaisesRegex(OSError, "publication"),
        ):
            self.api.migrate_launchers(self.study)
        for name, content in before.items():
            self.assertEqual((self.study / name).read_bytes(), content, name)
        self.api.verify_experiment(self.study)
        histories = list((self.study / "snapshot/bootstrap-history").iterdir())
        self.assertEqual(len(histories), 1)
        self.assertEqual(
            (histories[0] / "manifest.json").read_bytes(),
            before["snapshot/manifest.json"],
        )
        self.api.migrate_launchers(self.study)
        self.assertEqual(
            len(list((self.study / "snapshot/bootstrap-history").iterdir())), 2
        )
        self.assertEqual(
            self.launch("stages/test", "--check-environment").returncode, 0
        )

    def test_launcher_migration_refuses_modified_entry_before_any_write(self):
        self.legacy_tree_with_test_selection()
        entry = self.study / "stages/test/run.sh"
        entry.write_text(entry.read_text() + "# user modification\n")
        before = entry.read_bytes()
        with self.assertRaisesRegex(ValueError, "Frozen experiment file differs"):
            self.api.migrate_launchers(self.study)
        self.assertEqual(entry.read_bytes(), before)
        self.assertFalse((self.study / "snapshot/bootstrap-history").exists())

    def test_launcher_migration_interrupt_after_manifest_commit_keeps_committed_tree(
        self,
    ):
        self.legacy_tree_with_test_selection()
        replace = self.api.os.replace

        def interrupt_after_publication(source, destination):
            result = replace(source, destination)
            if Path(destination) == self.study / "snapshot/manifest.json":
                raise KeyboardInterrupt("after manifest publication")
            return result

        with (
            patch.object(
                self.api.os, "replace", side_effect=interrupt_after_publication
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.api.migrate_launchers(self.study)
        self.api.verify_experiment(self.study)
        self.assertEqual(
            self.launch("stages/test", "--check-environment").returncode, 0
        )
        self.assertEqual(self.calls(), [])

    def test_launcher_migration_interrupt_after_entry_swap_restores_old_tree(self):
        self.legacy_tree_with_test_selection()
        original_manifest = (self.study / "snapshot/manifest.json").read_bytes()
        original_entry = (self.study / "compare.sh").read_bytes()
        replace = self.api.os.replace

        def interrupt_after_entry(source, destination):
            result = replace(source, destination)
            if Path(destination) == self.study / "compare.sh":
                raise KeyboardInterrupt("after entry replacement")
            return result

        with (
            patch.object(self.api.os, "replace", side_effect=interrupt_after_entry),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.api.migrate_launchers(self.study)
        self.api.verify_experiment(self.study)
        self.assertEqual(
            (self.study / "snapshot/manifest.json").read_bytes(), original_manifest
        )
        self.assertEqual((self.study / "compare.sh").read_bytes(), original_entry)

    def test_new_dynamic_entry_rejects_invalid_coordinator_before_launch(self):
        self.create()
        path = self.study / "snapshot/manifest.json"
        manifest = json.loads(path.read_text())
        unlisted = (
            self.study
            / "snapshot/sources"
            / ("b" * 40)
            / "scripts/dev/assistant_experiment_batch.py"
        )
        unlisted.parent.mkdir(parents=True)
        unlisted.write_text("print('UNTRUSTED ENTRY EXECUTED')\n")
        for coordinator in ("../../untrusted-source", "b" * 40):
            manifest["coordinator"] = coordinator
            path.write_text(json.dumps(manifest))
            result = self.launch(ROUND)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid experiment coordinator", result.stderr)
            self.assertNotIn("UNTRUSTED", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_activate_test_preserves_prior_scopes_and_frozen_shell(self):
        self.create()
        original = {
            path.relative_to(self.study): path.read_bytes()
            for path in self.study.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        selection = self.selection(5, path="stages/test")
        config = json.loads(selection["config"].read_text())
        config.update(split="TEST", purpose="research")
        del config["case_ids"]
        config["models"][0]["alias"] = "phi4"
        selection["config"].write_text(json.dumps(config))
        self.api.activate_test_stage(
            self.study, selection, coordinator_root=self.source
        )
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(
            self.api.select_scopes(manifest, "stages/test"), ["stages/test"]
        )
        self.assertIn("blocked_reason", manifest["scopes"]["stages/val"])
        for path, content in original.items():
            self.assertEqual((self.study / path).read_bytes(), content, path)
        result = self.launch("stages/test")
        self.assertEqual(result.returncode, 0, result.stderr)
        called = json.loads(self.calls()[0].read_text())
        self.assertEqual(called["config"]["split"], "TEST")
        self.assertEqual(called["config"]["models"][0]["candidate_index"], 5)
        with self.assertRaisesRegex(ValueError, "blocked TEST"):
            self.api.activate_test_stage(
                self.study, selection, coordinator_root=self.source
            )

    def test_test_activation_rejects_wrong_split_and_preserves_blocked_stage(self):
        self.create()
        original = (self.study / "snapshot/manifest.json").read_bytes()
        selection = self.valid_selection()
        selection["path"] = "stages/test"
        with self.assertRaisesRegex(ValueError, "TEST configuration"):
            self.api.activate_test_stage(
                self.study, selection, coordinator_root=self.source
            )
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), original)
        self.assertFalse((self.study / "stages/test/config.json").exists())

    def test_activate_valid_preserves_old_files_and_launches_frozen_selection(self):
        self.create()
        before = {
            path.relative_to(self.study): path.read_bytes()
            for path in self.study.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        (self.source / "valid-notes.txt").write_text("Selected DEV candidates\n")
        self.fixture.git(self.source, "add", "valid-notes.txt")
        self.fixture.git(self.source, "commit", "-qm", "VALID coordinator")
        new_head = self.fixture.git(self.source, "rev-parse", "HEAD").strip()
        self.fixture.values["models"][0]["source"]["head"] = new_head
        selection = self.valid_selection()
        result = self.api.activate_valid_stage(
            self.study, selection, coordinator_root=self.source
        )
        self.assertEqual(result, self.study / "stages/val")
        self.assertEqual(self.calls(), [])
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(manifest["coordinator"], new_head)
        self.assertEqual(self.api.select_scopes(manifest, "stages/val"), ["stages/val"])
        self.assertEqual(manifest["scopes"][DEV]["children"], [ROUND])
        for relative, original in before.items():
            self.assertEqual((self.study / relative).read_bytes(), original, relative)
        for scope in (ROUND, "stages/val"):
            result = self.launch(scope)
            self.assertEqual(result.returncode, 0, result.stderr)
        saved = next(
            json.loads(path.read_text())
            for path in self.calls()
            if json.loads(path.read_text())["config"]["split"] == "VALID"
        )
        self.assertEqual(saved["config"]["models"][0]["candidate_index"], 2)
        self.assertTrue(saved["env"]["PYTHONPATH"].endswith(new_head))
        self.assertEqual(
            self.api.package_api.experiment_identity(saved["config"])["repeats"],
            [0, 1, 2],
        )
        self.assertNotEqual(self.launch("stages/test").returncode, 0)
        old = (self.study / "snapshot/manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "blocked VALID"):
            self.api.activate_valid_stage(
                self.study, selection, coordinator_root=self.source
            )
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), old)

    def test_activate_valid_rejects_other_paths_and_wrong_split_without_publication(
        self,
    ):
        self.create()
        old = (self.study / "snapshot/manifest.json").read_bytes()
        selection = self.valid_selection()
        for key in ("stages/test", "stages/unknown", ROUND, "stages/val/../test"):
            with self.subTest(path=key), self.assertRaises(ValueError):
                self.api.activate_valid_stage(
                    self.study, dict(selection, path=key), coordinator_root=self.source
                )
        with self.assertRaisesRegex(ValueError, "VALID configuration"):
            self.api.activate_valid_stage(
                self.study,
                self.selection(3, path="stages/val"),
                coordinator_root=self.source,
            )
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), old)
        self.assertFalse((self.study / "stages/val/config.json").exists())
        self.assertEqual(self.calls(), [])

    def test_activate_valid_refuses_existing_unsealed_destination(self):
        self.create()
        existing = self.study / "stages/val/README.md"
        existing.write_text("User notes must survive\n")
        old = (self.study / "snapshot/manifest.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.api.activate_valid_stage(
                self.study, self.valid_selection(), coordinator_root=self.source
            )
        self.assertEqual(existing.read_text(), "User notes must survive\n")
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), old)
        self.assertFalse((self.study / "stages/val/config.json").exists())

    def test_failed_valid_publication_preserves_blocked_stage_and_is_retryable(self):
        self.create()
        old = (self.study / "snapshot/manifest.json").read_bytes()
        entry = (self.study / "stages/val/run.sh").read_bytes()
        (self.source / "valid-notes.txt").write_text("New VALID coordinator\n")
        self.fixture.git(self.source, "add", "valid-notes.txt")
        self.fixture.git(self.source, "commit", "-qm", "VALID coordinator")
        self.fixture.values["models"][0]["source"]["head"] = self.fixture.git(
            self.source, "rev-parse", "HEAD"
        ).strip()
        selection = self.valid_selection()
        with (
            patch.object(self.api.os, "replace", side_effect=OSError("disk error")),
            self.assertRaisesRegex(OSError, "disk error"),
        ):
            self.api.activate_valid_stage(
                self.study, selection, coordinator_root=self.source
            )
        self.assertEqual((self.study / "snapshot/manifest.json").read_bytes(), old)
        self.assertEqual((self.study / "stages/val/run.sh").read_bytes(), entry)
        self.assertEqual(
            sorted(path.name for path in (self.study / "stages/val").iterdir()),
            ["run.sh"],
        )
        self.assertEqual(
            [path.name for path in (self.study / "snapshot/sources").iterdir()],
            [self.head],
        )
        self.api.verify_experiment(self.study)
        self.assertNotEqual(self.launch("stages/val").returncode, 0)
        self.api.activate_valid_stage(
            self.study, selection, coordinator_root=self.source
        )
        result = self.launch("stages/val")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_move_chinese_space_path_runs_twice_without_original_source(self):
        self.create()
        original = self.study
        self.study = self.root / "接收者 space" / "整包 experiment"
        self.study.parent.mkdir()
        shutil.copytree(original, self.study)
        self.source.rename(self.root / "source-unavailable")
        self.fixture.bank.rename(self.root / "bank-unavailable")
        poison = dict.fromkeys(
            (
                "PYTHONHOME",
                "PYTHONPATH",
                "VIRTUAL_ENV",
                "XBL_PYTHON",
                "XBRAINLAB_CONFIG_DIR",
                "XBRAINLAB_CACHE_DIR",
                "HF_HOME",
            ),
            "/must/not/be/used",
        )
        for _ in range(2):
            result = self.launch(ROUND, env=poison)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 2)
        for call in self.calls():
            saved = json.loads(call.read_text())
            self.assertEqual(saved["prefix"], self.environment.name)
            for name in (
                "XBRAINLAB_CACHE_DIR",
                "XBRAINLAB_LOG_DIR",
                "HF_HOME",
                "TMPDIR",
            ):
                self.assertTrue(Path(saved["env"][name]).is_relative_to(self.study))
            args = saved["args"]
            self.assertEqual(
                Path(args[args.index("--output") + 1]).parent,
                self.study / "results/runs",
            )
            config = Path(args[args.index("--config") + 1])
            source = saved["config"]["models"][0]["source"]["root"]
            self.assertEqual(
                (config.parent / source).resolve(),
                self.study / "snapshot/sources" / self.head,
            )
        self.assertFalse(list((original / "results/runs").glob("*")))
        self.api.verify_experiment(self.study)

    def test_root_and_unready_scopes_refuse_before_development_run(self):
        self.create()
        for scope in (".", "stages/val", "stages/test"):
            with self.subTest(scope=scope):
                result = self.launch(scope)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "frozen" if scope != "stages/test" else "sealed", result.stderr
                )
                self.assertEqual(self.calls(), [])
        result = self.launch(DEV)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)

    def test_explicit_selection_order_ignores_unlisted_stage_directory(self):
        self.create([self.selection(2), self.selection(1)])
        extra = self.study / "stages/dev/unselected"
        extra.mkdir()
        (extra / "run.sh").write_text("#!/bin/sh\nexit 99\n")
        manifest = self.api.verify_experiment(self.study)
        self.assertEqual(
            self.api.select_scopes(manifest, DEV), [f"{DEV}/round-02", ROUND]
        )
        result = self.launch(DEV)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = sorted(
            (json.loads(path.read_text()) for path in self.calls()),
            key=lambda row: row["started_ns"],
        )
        self.assertEqual([row["candidate"] for row in calls], [2, 1])

    def test_duplicate_missing_cycle_and_escape_scopes_are_rejected(self):
        self.create()
        manifest = self.api.verify_experiment(self.study)
        for children in ([ROUND, ROUND], ["stages/dev/missing"], [DEV], ["../escape"]):
            with self.subTest(children=children):
                changed = json.loads(json.dumps(manifest))
                changed["scopes"][DEV]["children"] = children
                with self.assertRaises(ValueError):
                    self.api.select_scopes(changed, DEV)
        self.assertEqual(self.calls(), [])

    def test_changed_or_missing_later_config_prevents_first_inference(self):
        self.create([self.selection(1), self.selection(2)])
        config = self.study / f"{DEV}/round-02/config.json"
        original = config.read_bytes()
        for damage in ("changed", "missing"):
            with self.subTest(damage=damage):
                if damage == "changed":
                    config.write_bytes(original + b"\n")
                else:
                    config.unlink()
                try:
                    result = self.launch(DEV)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.calls(), [])
                finally:
                    config.write_bytes(original)

    def test_help_writes_nothing_and_preflight_creates_no_results(self):
        self.create()
        before = sorted(path.relative_to(self.study) for path in self.study.rglob("*"))
        result = self.launch(".", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check-environment", result.stdout)
        self.assertEqual(
            sorted(path.relative_to(self.study) for path in self.study.rglob("*")),
            before,
        )
        result = self.launch(DEV, "--check-environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list((self.study / "results/runs").glob("*")), [])

    def test_missing_later_shared_model_prevents_first_inference(self):
        model = self.root / "other-model"
        model.mkdir()
        self.create([self.selection(1), self.selection(2, model=model)])
        model.rmdir()
        result = self.launch(DEV)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_shared_python_is_rejected(self):
        local = self.root / "private-shared-env"
        venv.EnvBuilder(with_pip=False).create(local)
        self.python = local / "bin/python"
        self.create()
        local.rename(self.root / "environment-unavailable")
        result = self.launch(DEV, "--check-environment")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_changed_shared_environment_is_rejected(self):
        local = self.root / "private-shared-env"
        venv.EnvBuilder(with_pip=False).create(local)
        self.python = local / "bin/python"
        self.create()
        site = next((local / "lib").glob("python*/site-packages"))
        distribution = site / "unexpected-1.0.dist-info"
        distribution.mkdir()
        (distribution / "METADATA").write_text("Name: unexpected\nVersion: 1.0\n")
        result = self.launch(DEV)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("environment", result.stderr.lower())
        self.assertEqual(self.calls(), [])

    def test_symlinked_outputs_cannot_write_to_external_directory(self):
        self.create()
        external = self.root / "other-results"
        external.mkdir()
        outputs = self.study / "results/runs"
        outputs.parent.mkdir(exist_ok=True)
        if outputs.exists():
            outputs.rmdir()
        outputs.symlink_to(external, target_is_directory=True)
        result = self.launch(DEV)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_nested_cache_symlink_is_rejected_before_run(self):
        self.create()
        result = self.launch(DEV, "--check-environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        external = self.root / "other-cache"
        external.mkdir()
        (self.study / ".runtime/cache/injected").symlink_to(
            external, target_is_directory=True
        )
        result = self.launch(DEV)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(list(external.iterdir()), [])

    def test_symlinked_results_parent_cannot_write_to_external_directory(self):
        self.create()
        external = self.root / "other-results-parent"
        external.mkdir()
        outputs = self.study / "results"
        outputs.rename(self.study / "original-results")
        outputs.symlink_to(external, target_is_directory=True)
        result = self.launch(DEV)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_failure_preserves_run_and_stops_later_selection(self):
        self.create([self.selection(1), self.selection(2)])
        result = self.launch(DEV, env={"XBL_FIXTURE_CANDIDATE_1": "fail"})
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(json.loads(self.calls()[0].read_text())["candidate"], 1)
        index = self.scope_index()
        self.assertIn("failed", index)
        self.assertIn("unattempted", index)

    def test_zero_exit_without_actual_run_is_failure(self):
        self.create()
        result = self.launch(ROUND, env={"XBL_FIXTURE_CANDIDATE_1": "empty"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def _assert_parent_signal(self, number):
        self.create([self.selection(1), self.selection(2)])
        process = subprocess.Popen(
            [str(self.study / DEV / "run.sh")],
            cwd=self.root,
            env=dict(os.environ, XBL_FIXTURE_CANDIDATE_1="wait"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            while not list((self.study / "results/runs").glob("*/waiting")):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail("Frozen runner fixture did not start")
                time.sleep(0.05)
            process.send_signal(number)
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 128 + number, error)
            self.assertEqual(
                len(list((self.study / "results/runs").glob("*/terminated"))), 1
            )
            self.assertEqual(len(self.calls()), 1)
            self.assertIn("unattempted", self.scope_index())
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_parent_termination_reaches_child_and_stops_next_selection(self):
        self._assert_parent_signal(signal.SIGTERM)

    def test_parent_interrupt_reaches_child_and_stops_next_selection(self):
        self._assert_parent_signal(signal.SIGINT)

    def test_reference_copy_preserves_original_bytes_and_comparison_uses_central_output(
        self,
    ):
        reference = compare_tests.fixture(
            self.root / "original-successful-run",
            [[("resample", {"sfreq": 64}, True)]],
        )
        linked_cache = reference / "raw/rag/models"
        linked_cache.parent.mkdir()
        linked_cache.symlink_to(self.root / "shared/model", target_is_directory=True)
        before = evidence_digest(reference)
        self.create(references=[reference])
        copied = self.study / "results/reference" / reference.name
        self.assertEqual(evidence_digest(copied), before)
        self.assertTrue((copied / "raw/rag/models").is_symlink())
        self.assertEqual(
            os.readlink(copied / "raw/rag/models"), os.readlink(linked_cache)
        )
        self.assertEqual(
            (copied / "raw/manifest.json").read_bytes(),
            (reference / "raw/manifest.json").read_bytes(),
        )
        result = self.launch(".", copied, copied, entry="compare.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        comparisons = list(
            (self.study / "results/comparisons").glob("*/comparison.json")
        )
        self.assertEqual(len(comparisons), 1)
        comparison = json.loads(comparisons[0].read_text())
        self.assertEqual(comparison["classification"], "same_config_reproduction")
        self.assertTrue(comparison["original_evidence_unchanged"])
        self.assertEqual(evidence_digest(reference), before)
        self.assertEqual(evidence_digest(copied), before)
        self.assertEqual(self.calls(), [])

    def test_changed_reference_copy_is_rejected_without_altering_original(self):
        reference = compare_tests.fixture(
            self.root / "original-successful-run",
            [[("resample", {"sfreq": 64}, True)]],
        )
        before = evidence_digest(reference)
        self.create(references=[reference])
        copied = self.study / "results/reference" / reference.name
        manifest = copied / "raw/manifest.json"
        changed = manifest.read_bytes() + b"\n"
        manifest.write_bytes(changed)
        result = self.launch(".", copied, copied, entry="compare.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Reference evidence differs", result.stderr)
        self.assertEqual(
            list((self.study / "results/comparisons").glob("*/comparison.json")), []
        )
        self.assertEqual(manifest.read_bytes(), changed)
        self.assertEqual(evidence_digest(reference), before)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
