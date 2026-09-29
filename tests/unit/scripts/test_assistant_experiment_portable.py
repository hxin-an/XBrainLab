"""Copy-and-run contracts with real Git, offline pip, venv, and shell entries."""

# ruff: noqa: S603, S607 -- fixed disposable fixture processes, no external input.

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.unit.scripts import test_assistant_experiment_package as package_fixture

ROOT = package_fixture.ROOT


@unittest.skipUnless(sys.platform == "linux", "Linux portable shell integration")
class PortableExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = tempfile.TemporaryDirectory(prefix="portable-test-wheels-")
        cls.addClassCleanup(cls.assets.cleanup)
        cls.wheels = Path(cls.assets.name)
        pip = importlib.metadata.distribution("pip")
        cls.pip_version = pip.version
        # Build an offline wheel from this interpreter's installed, real pip.
        # No downloader, network access, fake installer, or install subprocess mock.
        pip_wheel = cls.wheels / f"pip-{pip.version}-py3-none-any.whl"
        with zipfile.ZipFile(pip_wheel, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative in pip.files or []:
                if ".." not in relative.parts and relative.suffix != ".pyc":
                    source = pip.locate_file(relative)
                    if source.is_file():
                        archive.write(source, str(relative))
        with zipfile.ZipFile(
            cls.wheels / "portable_fixture-1.0-py3-none-any.whl", "w"
        ) as archive:
            contents = {
                "portable_fixture.py": "VALUE = 'installed offline'\n",
                "portable_fixture-1.0.dist-info/METADATA": (
                    "Metadata-Version: 2.1\nName: portable-fixture\nVersion: 1.0\n"
                ),
                "portable_fixture-1.0.dist-info/WHEEL": (
                    "Wheel-Version: 1.0\nGenerator: fixture\n"
                    "Root-Is-Purelib: true\nTag: py3-none-any\n"
                ),
            }
            contents["portable_fixture-1.0.dist-info/RECORD"] = (
                "".join(f"{name},,\n" for name in contents)
                + "portable_fixture-1.0.dist-info/RECORD,,\n"
            )
            for name, content in contents.items():
                archive.writestr(name, content)

    def setUp(self):
        # Composition reuses the actual package fixture without inheriting and
        # accidentally re-running all of its unrelated test methods.
        self.fixture = package_fixture.ExperimentPackageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.output = self.fixture.output
        scripts = self.fixture.source / "scripts/dev"
        portable_source = ROOT / "scripts/dev/assistant_experiment_portable.py"
        if portable_source.exists():
            shutil.copyfile(portable_source, scripts / portable_source.name)
        runner = scripts / "run_assistant_dev.py"
        runner.write_text(
            "import json, os, pathlib, sys\n"
            "import portable_fixture\n"
            "args = sys.argv[1:]\n"
            "out = pathlib.Path(args[args.index('--output') + 1])\n"
            "out.mkdir(parents=True, exist_ok=True)\n"
            "(out / 'called.json').write_text(json.dumps({\n"
            "  'args': args, 'prefix': sys.prefix, 'fixture': portable_fixture.VALUE,\n"
            "  'cache': {key: os.environ.get(key) for key in\n"
            "    ('HF_HOME', 'XDG_CACHE_HOME', 'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE')}\n"
            "}))\n",
            encoding="utf-8",
        )
        self.fixture.git(self.fixture.source, "add", ".")
        self.fixture.git(self.fixture.source, "commit", "-qm", "portable fixture")
        self.fixture.head = self.fixture.git(
            self.fixture.source, "rev-parse", "HEAD"
        ).strip()
        self.fixture.values["models"][0]["source"]["head"] = self.fixture.head
        self.model_cache = self.root / "private cache"
        self.model_cache.mkdir()
        resources = []
        for repo in (
            "ibm-granite/granite-4.0-micro",
            "sentence-transformers/all-MiniLM-L6-v2",
        ):
            revision = "a" * 40
            snapshot = (
                self.model_cache
                / ("models--" + repo.replace("/", "--"))
                / "snapshots"
                / revision
            )
            snapshot.mkdir(parents=True)
            payload = b'{"tiny": true}\n'
            (snapshot / "config.json").write_bytes(payload)
            resources.append(
                {
                    "repo": repo,
                    "revision": revision,
                    "files": {
                        "config.json": {
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                        }
                    },
                }
            )
        (self.model_cache / "token").write_text("private-token-not-for-transfer")
        (self.model_cache / "unrelated-model.bin").write_bytes(b"unrelated")
        self.resources = self.root / "resource-copy.json"
        self.resources.write_text(json.dumps({"resources": resources}))
        self.fixture.values["models"][0]["model_cache"] = str(self.model_cache)
        self.fixture.values["embedding_cache"] = str(self.model_cache)
        self.fixture.save_config()

    def create(self):
        portable = importlib.import_module("scripts.dev.assistant_experiment_portable")
        with patch.object(
            portable,
            "installed_versions",
            return_value={"pip": self.pip_version, "portable-fixture": "1.0"},
        ):
            self.fixture.api.create_package(
                self.fixture.bank,
                self.fixture.config,
                self.output,
                coordinator_root=self.fixture.source,
                wheel_cache=self.wheels,
            )

    def launch(self, *args, entry="run.sh"):
        return subprocess.run(
            ["bash", str(self.output / entry), *args],
            cwd=self.root,
            env=dict(
                os.environ,
                XBL_PYTHON="/does/not/exist/old-user-python",
                PIP_NO_INDEX="1",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
            ),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )

    def calls(self):
        return [
            json.loads(path.read_text())
            for path in (self.output / "runs").glob("*/called.json")
        ]

    def test_moved_copy_runs_offline_without_original_source_or_environment(self):
        self.create()
        moved = self.root / "其他使用者 space" / "實驗包"
        shutil.copytree(self.output, moved)
        self.output = moved
        self.fixture.source.rename(self.root / "unavailable-source")
        self.model_cache.rename(self.root / "unavailable-models")
        shutil.rmtree(self.fixture.output)
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        called = self.calls()[0]
        self.assertEqual(called["fixture"], "installed offline")
        self.assertTrue(Path(called["prefix"]).is_relative_to(moved / ".runtime"))
        for name in ("HF_HOME", "XDG_CACHE_HOME"):
            self.assertTrue(
                Path(called["cache"][name]).is_relative_to(moved / ".runtime/cache")
            )
        self.assertEqual(called["cache"]["HF_HUB_OFFLINE"], "1")

    def test_only_inventoried_models_are_copied_as_regular_files(self):
        self.create()
        config = json.loads((self.output / "inputs/config.json").read_text())
        self.assertEqual(config["embedding_cache"], "../models")
        self.assertEqual(config["models"][0]["model_cache"], "../models")
        payloads = list((self.output / "models").rglob("config.json"))
        self.assertEqual(len(payloads), 2)
        self.assertTrue(
            all(path.is_file() and not path.is_symlink() for path in payloads)
        )
        self.assertFalse((self.output / "models/token").exists())
        self.assertFalse((self.output / "models/unrelated-model.bin").exists())
        self.assertTrue((self.output / "environment/portable.json").is_file())
        self.assertEqual(
            len(list((self.output / "environment/wheels").glob("*.whl"))), 2
        )

    def test_repeat_launch_reuses_environment_but_keeps_separate_runs(self):
        self.create()
        first = self.launch()
        self.assertEqual(first.returncode, 0, first.stderr)
        prefix = Path(self.calls()[0]["prefix"])
        executable = prefix / "bin/python"
        before = executable.lstat().st_mtime_ns
        second = self.launch()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual({call["prefix"] for call in self.calls()}, {str(prefix)})
        self.assertEqual(executable.lstat().st_mtime_ns, before)

    def test_check_environment_prepares_without_starting_any_run(self):
        self.create()
        result = self.launch("--check-environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.output / "runs").exists())
        self.assertEqual(
            len(list((self.output / ".runtime").glob("env-*/bin/python"))), 1
        )

    def test_changed_installed_distribution_is_not_silently_reused(self):
        self.create()
        first = self.launch()
        self.assertEqual(first.returncode, 0, first.stderr)
        prefix = Path(self.calls()[0]["prefix"])
        metadata = next(
            prefix.glob(
                "lib/python*/site-packages/portable_fixture*.dist-info/METADATA"
            )
        )
        metadata.write_text(
            metadata.read_text().replace("Version: 1.0", "Version: 2.0")
        )
        second = self.launch()
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_copy_after_use_creates_a_new_path_local_environment(self):
        self.create()
        first = self.launch()
        self.assertEqual(first.returncode, 0, first.stderr)
        old_prefix = self.calls()[0]["prefix"]
        copied = self.root / "second user" / "copied package"
        shutil.copytree(self.output, copied, symlinks=True)
        self.output = copied
        second = self.launch()
        self.assertEqual(second.returncode, 0, second.stderr)
        new_calls = [call for call in self.calls() if call["prefix"] != old_prefix]
        self.assertEqual(len(new_calls), 1)
        self.assertTrue(
            Path(new_calls[0]["prefix"]).is_relative_to(copied / ".runtime")
        )

    def test_corrupt_wheel_fails_before_install_or_runner(self):
        self.create()
        wheel = next((self.output / "environment/wheels").glob("portable_fixture*.whl"))
        wheel.write_bytes(b"corrupt wheel")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "runs").exists())
        self.assertFalse(list((self.output / ".runtime").glob("env-*/bin/python")))

    def test_changed_source_model_payload_cannot_be_published(self):
        payload = next(self.model_cache.rglob("config.json"))
        payload.write_bytes(b"changed model")
        with self.assertRaisesRegex(ValueError, "(?i)(resource|inventory)"):
            self.create()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_huggingface_inward_blob_link_is_materialized(self):
        payload = next(self.model_cache.rglob("config.json"))
        blob = payload.parents[2] / "blobs" / "fixture-hash"
        blob.parent.mkdir()
        payload.rename(blob)
        payload.symlink_to(os.path.relpath(blob, payload.parent))
        self.create()
        copied = self.output / "models" / payload.relative_to(self.model_cache)
        self.assertFalse(copied.is_symlink())
        self.assertEqual(copied.read_bytes(), blob.read_bytes())

    def test_outward_snapshot_symlink_is_rejected_during_packaging(self):
        payload = next(self.model_cache.rglob("config.json"))
        external = self.root / "external-private.json"
        payload.rename(external)
        payload.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "(?i)(outside|escape|symlink|contain)"):
            self.create()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_runtime_symlink_cannot_redirect_writes_outside_package(self):
        self.create()
        external = self.root / "another-user"
        external.mkdir()
        (self.output / ".runtime").symlink_to(external, target_is_directory=True)
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])
        self.assertFalse((self.output / "runs").exists())

    def test_runs_symlink_cannot_redirect_experiment_output(self):
        self.create()
        external = self.root / "another-users-results"
        external.mkdir()
        (self.output / "runs").symlink_to(external, target_is_directory=True)
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_retained_run_write_links_are_rejected_before_dispatch(self):
        self.create()
        for action in ("--report-only", "--resume"):
            for name in ("reports", "launches", "index.html"):
                with self.subTest(action=action, link=name):
                    identifier = f"retained-{action[2:]}-{name}"
                    retained = self.fixture.retained_run(identifier)
                    external = self.root / f"external-{identifier}"
                    if name == "index.html":
                        external.write_text("unrelated page")
                    else:
                        external.mkdir()
                    (retained / name).symlink_to(
                        external, target_is_directory=name != "index.html"
                    )
                    result = self.launch(action, identifier)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((retained / "called.json").exists())
                    if external.is_file():
                        self.assertEqual(external.read_text(), "unrelated page")
                    else:
                        self.assertEqual(list(external.iterdir()), [])

    def test_retained_readonly_rag_link_to_own_models_is_allowed(self):
        self.create()
        retained = self.fixture.retained_run()
        rag = retained / "raw/rag"
        rag.mkdir(parents=True)
        (rag / "models").symlink_to(
            os.path.relpath(self.output / "models", rag), target_is_directory=True
        )
        for action, command in (("--report-only", "report"), ("--resume", "resume")):
            with self.subTest(action=action):
                result = self.launch(action, "retained")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads((retained / "called.json").read_text())["args"],
                    [command, "--output", str(retained)],
                )

    def test_retained_rag_link_cannot_point_to_another_bundle(self):
        self.create()
        retained = self.fixture.retained_run()
        rag = retained / "raw/rag"
        rag.mkdir(parents=True)
        (rag / "models").symlink_to(self.model_cache, target_is_directory=True)
        result = self.launch("--resume", "retained")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((retained / "called.json").exists())

    def test_comparisons_symlink_cannot_redirect_comparison_output(self):
        self.create()
        first = self.fixture.retained_run("first")
        second = self.fixture.retained_run("second")
        external = self.root / "another-users-comparisons"
        external.mkdir()
        (self.output / "comparisons").symlink_to(external, target_is_directory=True)
        result = self.launch(str(first), str(second), entry="compare.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_explicit_comparison_output_must_stay_in_package(self):
        self.create()
        first = self.fixture.retained_run("first")
        second = self.fixture.retained_run("second")
        external = self.root / "external-comparison"
        result = self.launch(
            str(first), str(second), "--output", str(external), entry="compare.sh"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(external.exists())

    def test_platform_mismatch_is_reported_before_environment_creation(self):
        self.create()
        path = self.output / "environment/portable.json"
        metadata = json.loads(path.read_text())
        metadata["platform"]["machine"] = "different-machine"
        path.write_text(json.dumps(metadata))
        # Simulate a coherent package built on a different platform, not a
        # corrupt file: reseal this fixture's intentionally changed metadata.
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["environment/portable.json"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("platform", result.stderr.lower())
        self.assertFalse((self.output / ".runtime").exists())
        self.assertFalse((self.output / "runs").exists())

    def test_report_and_compare_keep_existing_delegation(self):
        self.create()
        retained = self.fixture.retained_run()
        report = self.launch("--report-only", "retained")
        self.assertEqual(report.returncode, 0, report.stderr)
        called = json.loads((retained / "called.json").read_text())
        self.assertEqual(called["args"], ["report", "--output", str(retained)])
        other = self.root / "other-run"
        other.mkdir()
        compared = self.output / "comparisons/compared"
        compared.parent.mkdir()
        result = self.launch(
            str(retained), str(other), "--output", str(compared), entry="compare.sh"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads((compared / "called.json").read_text())["args"],
            [str(retained), str(other), "--output", str(compared)],
        )
