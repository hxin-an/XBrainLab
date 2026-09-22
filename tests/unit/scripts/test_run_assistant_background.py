"""Real subprocess tests for one-shot background experiment handoff (no GPU)."""

# Explicit disposable fixture commands only; subprocess behavior is under test.
# ruff: noqa: S603, S607

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from scripts.dev import run_assistant_background as background


@unittest.skipUnless(os.name == "posix", "WSL/POSIX supervisor")
class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "repo"
        self.cwd.mkdir()
        subprocess.run(["git", "init", "-q", str(self.cwd)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.cwd),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        self.sha = subprocess.check_output(
            ["git", "-C", str(self.cwd), "rev-parse", "HEAD"], text=True
        ).strip()
        self.session = "00000000-0000-4000-8000-000000000001"
        self.turn = "00000000-0000-4000-8000-000000000002"
        self.rollout = self.root / "rollout.jsonl"
        self.rollout.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": self.session}}) + "\n"
        )
        self.offset = self.rollout.stat().st_size
        self.event("task_started", self.turn)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"source": {"head": self.sha}, "jobs": []}))
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text(
            "Verify the saved run, continue only approved DEV initial baseline. No new candidate."
        )
        self.codex = self.root / "codex-fake"
        self.codex.write_text(
            "#!/usr/bin/env python3\nimport json,sys,pathlib\npathlib.Path(__file__).with_name('wake.json').write_text(json.dumps({'argv':sys.argv[1:],'cwd':str(pathlib.Path.cwd())}))\n"
        )
        self.codex.chmod(0o700)
        self.state = self.root / "state"

    def event(self, kind, turn):
        with self.rollout.open("a") as stream:
            stream.write(
                json.dumps(
                    {"type": "event_msg", "payload": {"type": kind, "turn_id": turn}}
                )
                + "\n"
            )

    def config(self, code=0):
        return {
            "cwd": str(self.cwd),
            "source_sha": self.sha,
            "manifest": str(self.manifest),
            "session_id": self.session,
            "turn_id": self.turn,
            "turn_offset": self.offset,
            "rollout": str(self.rollout),
            "codex": str(self.codex),
            "prompt_file": str(self.prompt),
            "command": [
                sys.executable,
                "-c",
                f"import sys,time; print('experiment'); time.sleep(.1); sys.exit({code})",
            ],
            "release_timeout_seconds": 5,
            "wake_timeout_seconds": 5,
            "poll_seconds": 0.03,
        }

    def wait_status(self, wanted):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            path = self.state / "status.json"
            if path.exists():
                status = json.loads(path.read_text())
                if status["status"] == wanted:
                    return status
            time.sleep(0.03)
        self.fail(
            f"Never reached {wanted}: {path.read_text() if path.exists() else 'missing status'}"
        )

    def test_success_waits_for_arm_and_later_active_turn_then_wakes_exact_session(self):
        process = background.launch(self.config(), self.state)
        self.addCleanup(process.wait, 8)
        self.wait_status("waiting_for_release")
        self.event("task_complete", self.turn)
        with self.rollout.open("ab") as stream:
            stream.write(b'{"type":"event_msg","payload":{"type":"task_started",')
        background.arm(self.state)
        time.sleep(0.15)
        self.assertFalse((self.root / "wake.json").exists())
        with self.rollout.open("ab") as stream:
            stream.write(b'"turn_id":"later"}}\n')
        time.sleep(0.15)
        self.assertFalse((self.root / "wake.json").exists())
        self.event("task_complete", "later")
        self.wait_status("wake_queued")
        process.wait(8)
        wake = json.loads((self.root / "wake.json").read_text())
        self.assertEqual(wake["cwd"], str(self.cwd))
        self.assertEqual(
            wake["argv"][:6],
            ["--cd", str(self.cwd), "queue", "--thread", self.session, "--message"],
        )
        self.assertEqual(len(wake["argv"]), 7)
        self.assertIn("Background handoff evidence", wake["argv"][6])
        self.assertNotIn("resume", wake["argv"])
        self.assertNotIn("--last", wake["argv"])
        self.assertIn("experiment", (self.state / "experiment.log").read_text())
        with self.assertRaises(FileExistsError):
            background.launch(self.config(), self.state)
        with self.assertRaises(FileExistsError):
            background.launch(self.config(), self.root / "duplicate-state")
        self.assertNotEqual(background.worker(self.state), 0)

    def test_failed_experiment_still_wakes_once_with_recorded_returncode(self):
        self.event("task_complete", self.turn)
        process = background.launch(self.config(7), self.state)
        self.addCleanup(process.wait, 8)
        background.arm(self.state)
        status = self.wait_status("wake_queued")
        self.assertEqual(status["experiment_returncode"], 7)
        self.assertEqual(process.wait(8), 0)

    def test_failed_wake_preserves_manual_recovery_and_intent(self):
        self.codex.write_text(
            "#!/usr/bin/env python3\nimport pathlib\n"
            "with pathlib.Path(__file__).with_name('attempts').open('a') as stream: stream.write('attempt\\n')\n"
            "raise SystemExit(9)\n"
        )
        self.event("task_complete", self.turn)
        process = background.launch(self.config(), self.state)
        self.addCleanup(process.wait, 8)
        background.arm(self.state)
        status = self.wait_status("wake_failed")
        self.assertEqual(status["wake_returncode"], 9)
        self.assertTrue((self.state / "wake-intent.json").is_file())
        self.assertTrue((self.state / "manual-recovery.json").is_file())
        self.assertNotEqual(process.wait(8), 0)
        self.assertEqual(background.worker(self.state), 1)
        self.assertEqual((self.root / "attempts").read_text(), "attempt\n")

    def test_queue_receipt_is_not_completed_continuation_and_submits_once(self):
        self.codex.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib,sys\n"
            "with pathlib.Path(__file__).with_name('attempts').open('a') as stream: stream.write('attempt\\n')\n"
            "print('Queued message fixture-submission')\n"
        )
        self.event("task_complete", self.turn)
        process = background.launch(self.config(), self.state)
        self.addCleanup(process.wait, 8)
        background.arm(self.state)
        status = self.wait_status("wake_queued")
        self.assertEqual(status["experiment_returncode"], 0)
        self.assertEqual(status["wake_returncode"], 0)
        self.assertEqual(process.wait(8), 0)
        self.assertEqual((self.root / "attempts").read_text(), "attempt\n")
        self.assertFalse((self.state / "continuation.md").exists())
        self.assertEqual(
            (self.state / "wake.stdout.log").read_text(),
            "Queued message fixture-submission\n",
        )
        self.assertFalse((self.state / "wake.jsonl").exists())
        self.assertTrue((self.state / "wake-intent.json").exists())
        manual = json.loads((self.state / "manual-recovery.json").read_text())
        self.assertIn(
            "queued receipt is not a completed continuation", manual["instruction"]
        )
        self.assertIn("existing conversation", manual["instruction"])
        self.assertEqual(background.worker(self.state), 1)
        self.assertEqual((self.root / "attempts").read_text(), "attempt\n")

    def test_uncertain_previous_worker_is_never_restarted(self):
        self.state.mkdir()
        (self.state / "worker-started.json").write_text('{"pid":12345}')
        self.assertEqual(background.worker(self.state, "unused"), 1)
        self.assertFalse((self.state / "experiment.log").exists())
        self.assertFalse((self.root / "wake.json").exists())
        self.assertEqual(
            (self.state / "worker-started.json").read_text(), '{"pid":12345}'
        )

    def test_queue_timeout_after_possible_acceptance_is_never_retried(self):
        self.codex.write_text(
            "#!/usr/bin/env python3\nimport pathlib,time\n"
            "with pathlib.Path(__file__).with_name('attempts').open('a') as stream: stream.write('attempt\\n')\n"
            "print('Queued message uncertain-receipt', flush=True)\n"
            "time.sleep(5)\n"
        )
        self.event("task_complete", self.turn)
        config = self.config()
        config["wake_timeout_seconds"] = 0.2
        process = background.launch(config, self.state)
        self.addCleanup(process.wait, 8)
        background.arm(self.state)
        self.wait_status("manual_recovery")
        self.assertEqual(process.wait(8), 1)
        self.assertTrue((self.state / "wake-intent.json").exists())
        self.assertIn("uncertain-receipt", (self.state / "wake.stdout.log").read_text())
        self.assertEqual(background.worker(self.state), 1)
        self.assertEqual((self.root / "attempts").read_text(), "attempt\n")

    def test_aborted_captured_turn_never_wakes(self):
        self.event("turn_aborted", self.turn)
        process = background.launch(self.config(), self.state)
        self.addCleanup(process.wait, 8)
        background.arm(self.state)
        self.wait_status("manual_recovery")
        self.assertFalse((self.root / "wake.json").exists())
        process.wait(8)

    def test_manifest_changed_after_launch_fails_closed(self):
        self.event("task_complete", self.turn)
        process = background.launch(self.config(), self.state)
        self.addCleanup(process.wait, 8)
        self.wait_status("waiting_for_release")
        self.manifest.write_text("{}")
        background.arm(self.state)
        self.wait_status("manual_recovery")
        self.assertFalse((self.root / "wake.json").exists())
        process.wait(8)

    def test_partial_lifecycle_line_is_deferred_and_truncation_rejected(self):
        frozen = background.prepare(self.config())
        cursor = {"offset": self.offset, "active": None, "released": False}
        background.scan_lifecycle(frozen, cursor)
        with self.rollout.open("ab") as stream:
            stream.write(b'{"type":"event_msg","payload":{"type":"task_complete",')
        background.scan_lifecycle(frozen, cursor)
        self.assertEqual(cursor["active"], self.turn)
        with self.rollout.open("ab") as stream:
            stream.write(('"turn_id":' + json.dumps(self.turn) + "}}\n").encode())
        background.scan_lifecycle(frozen, cursor)
        self.assertTrue(cursor["released"])
        self.assertIsNone(cursor["active"])
        with self.rollout.open("ab") as stream:
            stream.write(b'{"type":"event_msg","payload":{"type":"task_started",')
        background.scan_lifecycle(frozen, cursor)
        self.assertTrue(cursor["incomplete"])
        self.rollout.write_text("")
        with self.assertRaises(ValueError):
            background.scan_lifecycle(frozen, cursor)

    def test_detached_worker_survives_launcher_exit(self):
        self.event("task_complete", self.turn)
        config_path = self.root / "launch.json"
        config_path.write_text(json.dumps(self.config()))
        launcher = subprocess.run(
            [
                sys.executable,
                str(Path(background.__file__)),
                "--launch",
                str(config_path),
                "--state",
                str(self.state),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=8,
        )
        self.assertGreater(json.loads(launcher.stdout)["pid"], 0)
        self.wait_status("waiting_for_release")
        self.assertFalse((self.root / "wake.json").exists())
        background.arm(self.state)
        self.wait_status("wake_queued")

    @unittest.skipUnless(
        os.environ.get("XBRAINLAB_TEST_WINDOWS_PYTHON"),
        "Explicit native Windows interop smoke",
    )
    def test_native_windows_child_survives_wsl_launcher_exit(self):
        self.event("task_complete", self.turn)
        config = self.config()
        config["command"] = [
            os.environ["XBRAINLAB_TEST_WINDOWS_PYTHON"],
            "-c",
            "import time; print('native-Windows-start', flush=True); time.sleep(0.5); print('native-Windows-complete', flush=True)",
        ]
        config_path = self.root / "launch.json"
        config_path.write_text(json.dumps(config))
        subprocess.run(
            [
                sys.executable,
                str(Path(background.__file__)),
                "--launch",
                str(config_path),
                "--state",
                str(self.state),
            ],
            capture_output=True,
            check=True,
            timeout=8,
        )
        self.wait_status("waiting_for_release")
        self.assertIn(
            "native-Windows-complete", (self.state / "experiment.log").read_text()
        )
        background.arm(self.state)
        status = self.wait_status("wake_queued")
        self.assertEqual(status["experiment_returncode"], 0)

    def test_rotated_rollout_and_unknown_lifecycle_fail_closed(self):
        frozen = background.prepare(self.config())
        cursor = {"offset": self.offset, "active": None, "released": False}
        self.event("task_new_unknown_state", self.turn)
        with self.assertRaisesRegex(ValueError, "Unknown lifecycle"):
            background.scan_lifecycle(frozen, cursor)
        self.rollout.rename(self.root / "old-rollout")
        self.rollout.write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "rotated or truncated"):
            background.scan_lifecycle(frozen, cursor)


if __name__ == "__main__":
    unittest.main()
