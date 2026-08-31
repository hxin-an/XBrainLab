from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import MappingProxyType

import pytest

import scripts.dev.handoff_evidence_recorder as recorder_module
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.handoff_evidence_recorder import (
    HandoffEvidenceError,
    persist_handoff_records,
    record_handoff_command,
    validate_handoff_dossier,
)
from scripts.dev.handoff_gate_spec import (
    EVIDENCE_ROOT_TOKEN,
    MODEL_CACHE_DIR_TOKEN,
    RAG_CACHE_DIR_TOKEN,
    EnvironmentPolicy,
    GateSpec,
    OutcomePolicy,
)
from scripts.dev.sensitive_path_redaction import contains_sensitive_path


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    completed = subprocess.run(  # noqa: S603 - resolved git with test-owned args.
        [git, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / ".gitignore").write_text("build/\nsettings.json\n", encoding="utf-8")
    (repo / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "settings.json").write_text('{"local": false}\n', encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "add", "-f", "settings.json")
    _git(repo, "commit", "-qm", "initial")
    return repo, _git(repo, "rev-parse", "HEAD"), _git(repo, "branch", "--show-current")


def _install_test_gate(monkeypatch: pytest.MonkeyPatch, spec: GateSpec) -> None:
    monkeypatch.setattr(
        recorder_module,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec}),
    )


def _install_test_gates(
    monkeypatch: pytest.MonkeyPatch,
    *specs: GateSpec,
) -> None:
    monkeypatch.setattr(
        recorder_module,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )


def _rewrite_check(
    evidence_root: Path,
    check_id: str,
    **changes: object,
) -> None:
    dossier_path = evidence_root / "handoff-evidence.json"
    payload = json.loads(dossier_path.read_text(encoding="utf-8"))
    payload["checks"][check_id].update(changes)
    dossier_path.write_text(json.dumps(payload), encoding="utf-8")


def _wsl_cache_aliases(path: Path) -> tuple[str, ...]:
    if path.drive:
        remainder = path.as_posix().split(":/", maxsplit=1)[1]
        canonical = f"/mnt/{path.drive[0].lower()}/{remainder}"
    else:
        canonical = path.as_posix()
        remainder = canonical.removeprefix("/mnt/d/")
    windows_remainder = remainder.replace("/", "\\")
    windows = f"D:\\{windows_remainder}"
    return (
        canonical,
        f"D:/{remainder}",
        windows,
        json.dumps(windows)[1:-1],
        f"\\\\wsl.localhost\\Ubuntu\\mnt\\d\\{windows_remainder}",
        f"\\\\wsl$\\Ubuntu\\mnt\\d\\{windows_remainder}",
    )


def _d_cache_path(name: str) -> Path:
    if os.name == "nt":
        return Path(f"D:/XBrainLabCache/{name}")
    return Path(f"/mnt/d/XBrainLabCache/{name}")


def test_recorded_command_is_bound_to_clean_sha_and_hashed_logs(tmp_path) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="1",
        check_id="git-diff-check",
        command=("git", "diff", "--check"),
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["passed"] is True
    assert record["source_before"]["commit_sha"] == sha
    assert record["source_before"] == record["source_after"]
    assert record["stdout_log"]["sha256"]
    dossier = json.loads(
        (evidence_root / "handoff-evidence.json").read_text(encoding="utf-8")
    )
    assert dossier["checks"]["git-diff-check"]["passed"] is True
    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=("git-diff-check",),
        expected_branch=branch,
        require_upstream=False,
    ) == (True, "")


def test_explicit_profile_rejects_a_gate_from_the_other_fixed_profile(
    tmp_path: Path,
) -> None:
    repo, sha, branch = _repo(tmp_path)

    with pytest.raises(HandoffEvidenceError, match="not part of release profile"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=repo / "build" / "handoff-evidence" / sha,
            section="4",
            check_id="stable-assistant-model-eval",
            command=("not-used",),
            timeout_seconds=1800,
            expected_branch=branch,
            require_upstream=False,
            release_profile="desktop-source",
        )


@pytest.mark.parametrize(
    ("profile", "check_ids"),
    [
        ("desktop-source", ("stable-assistant-model-eval",)),
        ("handoff", ("bounded-assistant-model-eval",)),
    ],
)
def test_full_profile_validation_rejects_mixed_gate_sets(
    profile: str,
    check_ids: tuple[str, ...],
) -> None:
    ok, reason = validate_handoff_dossier(
        repo_root=Path("/not-used"),
        evidence_root=Path("/not-used"),
        required_check_ids=check_ids,
        release_profile=profile,
    )

    assert ok is False
    assert "must exactly match the selected release profile" in reason


def test_dossier_rejects_an_injected_registered_gate_from_the_other_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    first = GateSpec(
        check_id="first-gate",
        section="1",
        argv=(sys.executable, "-c", "print('first')"),
        timeout_seconds=30,
    )
    strict = GateSpec(
        check_id="strict-gate",
        section="1",
        argv=(sys.executable, "-c", "print('strict')"),
        timeout_seconds=30,
    )
    bounded = GateSpec(
        check_id="bounded-gate",
        section="1",
        argv=(sys.executable, "-c", "print('bounded')"),
        timeout_seconds=30,
    )
    _install_test_gates(monkeypatch, first, strict, bounded)
    monkeypatch.setattr(
        recorder_module,
        "HANDOFF_RELEASE_PROFILES",
        MappingProxyType(
            {
                "handoff": ("first-gate", "strict-gate"),
                "desktop-source": ("first-gate", "bounded-gate"),
            }
        ),
    )
    for spec in (first, strict, bounded):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=spec.argv,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
        )

    common = {
        "repo_root": repo,
        "evidence_root": evidence_root,
        "expected_branch": branch,
        "require_upstream": False,
    }
    assert validate_handoff_dossier(
        **common,
        required_check_ids=("first-gate", "strict-gate"),
        release_profile="handoff",
    ) == (
        False,
        "Handoff dossier checks do not exactly match the selected profile (missing=[], extras=['bounded-gate']).",
    )

    dossier_path = evidence_root / "handoff-evidence.json"
    payload = json.loads(dossier_path.read_text(encoding="utf-8"))
    payload["profile"] = "desktop-source"
    dossier_path.write_text(json.dumps(payload), encoding="utf-8")
    assert validate_handoff_dossier(
        **common,
        required_check_ids=("first-gate", "bounded-gate"),
        release_profile="desktop-source",
    ) == (
        False,
        "Handoff dossier checks do not exactly match the selected profile (missing=[], extras=['strict-gate']).",
    )


@pytest.mark.parametrize(
    ("profile", "check_id"),
    [
        ("desktop-source", "stable-assistant-model-eval"),
        ("handoff", "bounded-assistant-model-eval"),
    ],
)
def test_deferred_profile_persistence_rejects_mixed_gate_records(
    tmp_path: Path,
    profile: str,
    check_id: str,
) -> None:
    repo, sha, branch = _repo(tmp_path)

    with pytest.raises(HandoffEvidenceError, match="outside release profile"):
        persist_handoff_records(
            repo_root=repo,
            evidence_root=repo / "build" / "handoff-evidence" / sha,
            records=({"check_id": check_id},),
            expected_branch=branch,
            require_upstream=False,
            release_profile=profile,
        )


def test_manifest_source_identity_uses_lightweight_per_gate_guard(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    source_identity = collect_source_identity(repo, refresh=True)

    def reject_full_rehash(*_args, **_kwargs):
        raise AssertionError("per-gate recording must not rehash the full source tree")

    monkeypatch.setattr(
        recorder_module,
        "collect_source_identity",
        reject_full_rehash,
    )
    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="1",
        check_id="git-diff-check",
        command=("git", "diff", "--check"),
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
        manifest_source_identity=source_identity,
    )

    assert record["passed"] is True
    assert record["source_before"] == source_identity
    assert record["source_after"] == source_identity


def test_deferred_records_are_persisted_once_in_registry_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    source_identity = collect_source_identity(repo, refresh=True)
    first = GateSpec(
        check_id="first-gate",
        section="1",
        argv=(sys.executable, "-c", "print('first')"),
        timeout_seconds=30,
    )
    second = GateSpec(
        check_id="second-gate",
        section="2",
        argv=(sys.executable, "-c", "print('second')"),
        timeout_seconds=30,
    )
    _install_test_gates(monkeypatch, first, second)

    records = [
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=spec.argv,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
            manifest_source_identity=source_identity,
            defer_dossier_update=True,
        )
        for spec in (first, second)
    ]

    assert not (evidence_root / "handoff-evidence.json").exists()
    persist_handoff_records(
        repo_root=repo,
        evidence_root=evidence_root,
        records=records,
        expected_branch=branch,
        require_upstream=False,
        manifest_source_identity=source_identity,
    )

    dossier = json.loads(
        (evidence_root / "handoff-evidence.json").read_text(encoding="utf-8")
    )
    assert dossier["execution_order"] == ["first-gate", "second-gate"]
    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=("first-gate", "second-gate"),
        expected_branch=branch,
        require_upstream=False,
    ) == (True, "")


def test_deferred_record_persistence_rejects_out_of_order_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    source_identity = collect_source_identity(repo, refresh=True)
    first = GateSpec(
        check_id="first-gate",
        section="1",
        argv=(sys.executable, "-c", "print('first')"),
        timeout_seconds=30,
    )
    second = GateSpec(
        check_id="second-gate",
        section="2",
        argv=(sys.executable, "-c", "print('second')"),
        timeout_seconds=30,
    )
    _install_test_gates(monkeypatch, first, second)
    records = [
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=spec.argv,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
            manifest_source_identity=source_identity,
            defer_dossier_update=True,
        )
        for spec in (second, first)
    ]

    with pytest.raises(HandoffEvidenceError, match="registry order"):
        persist_handoff_records(
            repo_root=repo,
            evidence_root=evidence_root,
            records=records,
            expected_branch=branch,
            require_upstream=False,
            manifest_source_identity=source_identity,
        )


def test_manifest_source_identity_guard_detects_gate_mutation(
    tmp_path, monkeypatch
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    source_identity = collect_source_identity(repo, refresh=True)
    command = (
        sys.executable,
        "-c",
        "from pathlib import Path; Path('module.py').write_text('VALUE = 2\\n')",
    )
    _install_test_gate(
        monkeypatch,
        GateSpec(
            check_id="manifest-mutating-command",
            section="4",
            argv=command,
            timeout_seconds=30,
        ),
    )

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="4",
        check_id="manifest-mutating-command",
        command=command,
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
        manifest_source_identity=source_identity,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert record["source_stable"] is False
    assert "source changed" in record["failure_reason"].lower()


def test_rerunning_an_earlier_gate_invalidates_later_dossier_records(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    first = GateSpec(
        check_id="first-gate",
        section="1",
        argv=(sys.executable, "-c", "print('first')"),
        timeout_seconds=30,
    )
    second = GateSpec(
        check_id="second-gate",
        section="2",
        argv=(sys.executable, "-c", "print('second')"),
        timeout_seconds=30,
    )
    _install_test_gates(monkeypatch, first, second)

    for spec in (first, second, first):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=spec.argv,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
        )

    dossier = json.loads(
        (evidence_root / "handoff-evidence.json").read_text(encoding="utf-8")
    )
    assert dossier["execution_order"] == ["first-gate"]
    assert set(dossier["checks"]) == {"first-gate"}
    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=("first-gate", "second-gate"),
        expected_branch=branch,
        require_upstream=False,
    ) == (
        False,
        "Handoff dossier checks do not exactly match the selected profile "
        "(missing=['second-gate'], extras=[]).",
    )


def test_dossier_validation_rejects_edited_execution_order(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    spec = GateSpec(
        check_id="ordered-gate",
        section="1",
        argv=(sys.executable, "-c", "print('ordered')"),
        timeout_seconds=30,
    )
    _install_test_gate(monkeypatch, spec)
    record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=spec.argv,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )
    dossier_path = evidence_root / "handoff-evidence.json"
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    dossier["execution_order"] = []
    dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
    )

    assert ok is False
    assert "execution order" in reason.lower()


def test_repo_evidence_root_must_be_gitignored(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "review-output" / sha
    command = (sys.executable, "-c", "print('must not run')")
    spec = GateSpec(
        check_id="unignored-evidence",
        section="1",
        argv=command,
        timeout_seconds=30,
    )
    _install_test_gate(monkeypatch, spec)

    with pytest.raises(HandoffEvidenceError, match="git-ignored"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=command,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
        )


def test_external_evidence_root_requires_explicit_opt_in(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = tmp_path / "external-evidence" / sha
    command = (sys.executable, "-c", "print('external evidence')")
    spec = GateSpec(
        check_id="external-evidence",
        section="1",
        argv=command,
        timeout_seconds=30,
    )
    _install_test_gate(monkeypatch, spec)

    with pytest.raises(HandoffEvidenceError, match="explicit opt-in"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=command,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
        )

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
        allow_external_evidence_root=True,
    )

    assert record["passed"] is True
    dossier = json.loads(
        (evidence_root / "handoff-evidence.json").read_text(encoding="utf-8")
    )
    assert dossier["evidence_root_policy"]["kind"] == "external"
    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
        allow_external_evidence_root=True,
    ) == (True, "")


def test_local_runtime_cache_environment_is_explicit_d_mounted_and_redacted(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    model_cache = _d_cache_path("models")
    rag_cache = _d_cache_path("rag")
    details_artifact = evidence_root / "runtime-details.json"
    source = (
        "from pathlib import Path\n"
        "import json, os, sys\n"
        "def aliases(value):\n"
        "    path = Path(value)\n"
        "    if path.drive:\n"
        "        remainder = path.as_posix().split(':/', maxsplit=1)[1]\n"
        "        canonical = f'/mnt/{path.drive[0].lower()}/{remainder}'\n"
        "    else:\n"
        "        canonical = path.as_posix()\n"
        "        remainder = canonical.removeprefix('/mnt/d/')\n"
        "    windows_remainder = remainder.replace('/', '\\\\')\n"
        "    windows = f'D:\\\\{windows_remainder}'\n"
        "    return (canonical, f'D:/{remainder}', windows, "
        "json.dumps(windows)[1:-1], "
        "f'\\\\\\\\wsl.localhost\\\\Ubuntu\\\\mnt\\\\d\\\\{windows_remainder}', "
        "f'\\\\\\\\wsl$\\\\Ubuntu\\\\mnt\\\\d\\\\{windows_remainder}')\n"
        "model = os.environ['XBRAINLAB_MODEL_CACHE_DIR']\n"
        "rag = os.environ['XBRAINLAB_RAG_CACHE_DIR']\n"
        "payload = {'model_cache_aliases': aliases(model), "
        "'rag_cache_aliases': aliases(rag)}\n"
        "rendered = json.dumps(payload)\n"
        "print(rendered)\n"
        "print(rendered, file=sys.stderr)\n"
        f"Path({str(details_artifact)!r}).write_text(rendered, encoding='utf-8')\n"
    )
    command = (sys.executable, "-c", source)
    spec = GateSpec(
        check_id="local-runtime-cache",
        section="4",
        argv=command,
        timeout_seconds=30,
        environment=EnvironmentPolicy(
            required=(
                ("XBRAINLAB_MODEL_CACHE_DIR", MODEL_CACHE_DIR_TOKEN),
                ("XBRAINLAB_RAG_CACHE_DIR", RAG_CACHE_DIR_TOKEN),
            ),
            redacted_path_names=(
                "XBRAINLAB_MODEL_CACHE_DIR",
                "XBRAINLAB_RAG_CACHE_DIR",
            ),
        ),
        required_artifact_paths=("runtime.json", "runtime-details.json"),
        stdout_artifact_path="runtime.json",
    )
    _install_test_gate(monkeypatch, spec)

    with pytest.raises(HandoffEvidenceError, match="requires --model-cache-dir"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=command,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
        )
    with pytest.raises(HandoffEvidenceError, match="D-mounted"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section=spec.section,
            check_id=spec.check_id,
            command=command,
            timeout_seconds=spec.timeout_seconds,
            expected_branch=branch,
            require_upstream=False,
            model_cache_dir=(
                Path("C:/XBrainLabCache/models")
                if os.name == "nt"
                else Path("/home/test/models")
            ),
            rag_cache_dir=rag_cache,
        )

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
        model_cache_dir=model_cache,
        rag_cache_dir=rag_cache,
    )

    assert record["passed"] is True
    assert str(model_cache) not in json.dumps(record)
    assert str(rag_cache) not in json.dumps(record)
    evidence_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in evidence_root.rglob("*")
        if path.is_file()
    )
    redactions = {
        str(model_cache): "<redacted:XBRAINLAB_MODEL_CACHE_DIR>",
        str(rag_cache): "<redacted:XBRAINLAB_RAG_CACHE_DIR>",
    }
    assert contains_sensitive_path(evidence_text, redactions) is False
    for alias in (*_wsl_cache_aliases(model_cache), *_wsl_cache_aliases(rag_cache)):
        assert alias not in evidence_text
    assert "<redacted:XBRAINLAB_MODEL_CACHE_DIR>" in evidence_text
    assert "<redacted:XBRAINLAB_RAG_CACHE_DIR>" in evidence_text
    assert record["environment"]["XBRAINLAB_MODEL_CACHE_DIR"] == {
        "mount": "D:" if os.name == "nt" else "/mnt/d",
        "path_sha256": hashlib.sha256(str(model_cache).encode()).hexdigest(),
        "redacted": True,
    }
    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
        model_cache_dir=model_cache,
        rag_cache_dir=rag_cache,
    ) == (True, "")

    _rewrite_check(
        evidence_root,
        spec.check_id,
        environment={
            "XBRAINLAB_MODEL_CACHE_DIR": str(model_cache),
            "XBRAINLAB_RAG_CACHE_DIR": str(rag_cache),
        },
    )
    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
        model_cache_dir=model_cache,
        rag_cache_dir=rag_cache,
    )
    assert ok is False
    assert "environment policy was edited" in reason


def test_validator_rejects_cache_path_reintroduced_into_registered_json(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    model_cache = _d_cache_path("models")
    artifact = evidence_root / "runtime.json"
    command = (
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            f'Path({str(artifact)!r}).write_text(\'{{"status":"passed"}}\')'
        ),
    )
    spec = GateSpec(
        check_id="artifact-cache-redaction",
        section="4",
        argv=command,
        timeout_seconds=30,
        environment=EnvironmentPolicy(
            required=(("XBRAINLAB_MODEL_CACHE_DIR", MODEL_CACHE_DIR_TOKEN),),
            redacted_path_names=("XBRAINLAB_MODEL_CACHE_DIR",),
        ),
        required_artifact_paths=("runtime.json",),
    )
    _install_test_gate(monkeypatch, spec)

    record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
        model_cache_dir=model_cache,
    )

    artifact.write_text(
        json.dumps({"cache_dir": str(model_cache)}),
        encoding="utf-8",
    )
    dossier_path = evidence_root / "handoff-evidence.json"
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    artifact_record = dossier["checks"][spec.check_id]["artifacts"][0]
    artifact_bytes = artifact.read_bytes()
    artifact_record["sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_record["byte_size"] = len(artifact_bytes)
    dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
        model_cache_dir=model_cache,
    )

    assert ok is False
    assert "sensitive cache path" in reason


def test_recorder_rejects_unregistered_or_substituted_commands(tmp_path) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha

    with pytest.raises(HandoffEvidenceError, match="registered handoff gate"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section="1",
            check_id="fake-pass",
            command=("/bin/true",),
            timeout_seconds=30,
            expected_branch=branch,
            require_upstream=False,
        )
    with pytest.raises(HandoffEvidenceError, match="exact registered argv"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section="1",
            check_id="git-diff-check",
            command=("/bin/true",),
            timeout_seconds=30,
            expected_branch=branch,
            require_upstream=False,
        )
    with pytest.raises(HandoffEvidenceError, match="registered section"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section="2",
            check_id="git-diff-check",
            command=("git", "diff", "--check"),
            timeout_seconds=30,
            expected_branch=branch,
            require_upstream=False,
        )


def test_recorded_command_fails_when_source_changes_during_gate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    command = (
        sys.executable,
        "-c",
        "from pathlib import Path; Path('module.py').write_text('VALUE = 2\\n')",
    )
    _install_test_gate(
        monkeypatch,
        GateSpec(
            check_id="mutating-command",
            section="4",
            argv=command,
            timeout_seconds=30,
        ),
    )

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="4",
        check_id="mutating-command",
        command=command,
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert record["source_stable"] is False
    assert "source changed" in record["failure_reason"].lower()


def test_recorder_refuses_dirty_product_source_but_allows_local_settings(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    (repo / "settings.json").write_text('{"local": true}\n', encoding="utf-8")
    command = (sys.executable, "-c", "print('ok')")
    _install_test_gate(
        monkeypatch,
        GateSpec(
            check_id="settings-exception",
            section="1",
            argv=command,
            timeout_seconds=30,
        ),
    )

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="1",
        check_id="settings-exception",
        command=command,
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )
    assert record["passed"] is True
    assert record["protected_dirty_paths"] == ["settings.json"]

    (repo / "module.py").write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(HandoffEvidenceError, match="dirty product source"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section="1",
            check_id="settings-exception",
            command=command,
            timeout_seconds=30,
            expected_branch=branch,
            require_upstream=False,
        )


def test_recorder_rejects_staged_local_settings(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    (repo / "settings.json").write_text('{"local": true}\n', encoding="utf-8")
    _git(repo, "add", "-f", "settings.json")
    command = (sys.executable, "-c", "print('must not run')")
    _install_test_gate(
        monkeypatch,
        GateSpec(
            check_id="staged-settings",
            section="1",
            argv=command,
            timeout_seconds=30,
        ),
    )

    with pytest.raises(HandoffEvidenceError, match="dirty product source"):
        record_handoff_command(
            repo_root=repo,
            evidence_root=evidence_root,
            section="1",
            check_id="staged-settings",
            command=command,
            timeout_seconds=30,
            expected_branch=branch,
            require_upstream=False,
        )


def test_recorder_preserves_porcelain_status_columns_for_tracked_settings(
    tmp_path,
) -> None:
    repo, _sha, _branch = _repo(tmp_path)
    (repo / "settings.json").write_text('{"local": true}\n', encoding="utf-8")

    dirty, protected = recorder_module._dirty_paths(repo)

    assert dirty == []
    assert protected == ["settings.json"]


def test_recorder_removes_python_and_pytest_injection_environment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    names = (
        "COVERAGE_PROCESS_START",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTHONBREAKPOINT",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "XBRAINLAB_MODEL_CACHE_DIR",
        "XBRAINLAB_RAG_CACHE_DIR",
    )
    for name in names:
        monkeypatch.setenv(name, "injected")
    source = (
        "import os, sys; "
        f"names = {names!r}; "
        "present = [name for name in names if name in os.environ]; "
        "print(','.join(present)); raise SystemExit(bool(present))"
    )
    command = (sys.executable, "-c", source)
    spec = GateSpec(
        check_id="sanitized-environment",
        section="1",
        argv=command,
        timeout_seconds=30,
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is True
    assert record["sanitized_environment_names"] == list(names)


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group contract")
def test_recorder_timeout_terminates_its_owned_child_process_group(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    child_pid_path = evidence_root / "child.pid"
    source = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        "pathlib.Path(sys.argv[1]).parent.mkdir(parents=True, exist_ok=True); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); "
        "print('child started', flush=True); time.sleep(30)"
    )
    command = (sys.executable, "-c", source, str(child_pid_path))
    spec = GateSpec(
        check_id="timeout-process-group",
        section="6",
        argv=command,
        timeout_seconds=0.5,
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert record["timed_out"] is True
    assert record["return_code"] == 124
    assert not Path(f"/proc/{child_pid}").exists()


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group contract")
def test_recorder_cleans_owned_child_after_parent_exits_normally(tmp_path) -> None:
    child_pid_path = tmp_path / "normal-exit-child.pid"
    source = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
    )

    return_code, _stdout, _stderr, timed_out = recorder_module._run_bounded_command(
        (sys.executable, "-c", source, str(child_pid_path)),
        cwd=tmp_path,
        timeout_seconds=5,
        environment=os.environ.copy(),
    )

    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert return_code == 0
    assert timed_out is False
    assert not Path(f"/proc/{child_pid}").exists()


def test_pytest_skip_summary_cannot_be_recorded_as_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _sha, branch = _repo(tmp_path)
    (repo / "test_required_gate.py").write_text(
        "import pytest\n\n@pytest.mark.skip(reason='required fixture missing')\n"
        "def test_required_case():\n    pass\n",
        encoding="utf-8",
    )
    _git(repo, "add", "test_required_gate.py")
    _git(repo, "commit", "-qm", "add required gate")
    sha = _git(repo, "rev-parse", "HEAD")
    evidence_root = repo / "build" / "handoff-evidence" / sha
    attestation = "pytest-attestations/pytest-with-skip.json"
    runner = Path(recorder_module.__file__).with_name("run_required_pytest_gate.py")
    command = (
        sys.executable,
        str(runner),
        "--result-json",
        f"{EVIDENCE_ROOT_TOKEN}/{attestation}",
        "--",
        "-q",
        "test_required_gate.py",
    )
    spec = GateSpec(
        check_id="pytest-with-skip",
        section="7",
        argv=command,
        timeout_seconds=30,
        outcome=OutcomePolicy.pytest_strict(),
        required_artifact_paths=(attestation,),
        pytest_attestation_path=attestation,
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="7",
        check_id="pytest-with-skip",
        command=spec.resolve_argv(evidence_root),
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 1
    assert record["pytest_outcomes"]["skipped"] == 1
    assert record["passed"] is False
    assert "disallowed pytest outcome" in record["failure_reason"].lower()


def test_pytest_required_selector_without_terminal_evidence_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _sha, branch = _repo(tmp_path)
    (repo / "test_required_gate.py").write_text(
        "def test_present():\n    pass\n",
        encoding="utf-8",
    )
    _git(repo, "add", "test_required_gate.py")
    _git(repo, "commit", "-qm", "add required gate")
    sha = _git(repo, "rev-parse", "HEAD")
    evidence_root = repo / "build" / "handoff-evidence" / sha
    attestation = "pytest-attestations/pytest-required-selector.json"
    runner = Path(recorder_module.__file__).with_name("run_required_pytest_gate.py")
    spec = GateSpec(
        check_id="pytest-required-selector",
        section="7",
        argv=(
            sys.executable,
            str(runner),
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/{attestation}",
            "--",
            "-q",
            "test_required_gate.py",
        ),
        timeout_seconds=30,
        outcome=OutcomePolicy.pytest_strict(),
        required_artifact_paths=(attestation,),
        pytest_attestation_path=attestation,
        required_pytest_selectors=("test_required_gate.py::test_missing",),
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section="7",
        check_id=spec.check_id,
        command=spec.resolve_argv(evidence_root),
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert "no terminal evidence" in record["failure_reason"].lower()


def test_early_pytest_exit_with_fake_summary_cannot_be_recorded_as_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _sha, branch = _repo(tmp_path)
    (repo / "test_early_exit.py").write_text(
        "import os\n\ndef test_early_exit():\n"
        "    print('================ 1 passed in 0.01s ================', flush=True)\n"
        "    os._exit(0)\n",
        encoding="utf-8",
    )
    _git(repo, "add", "test_early_exit.py")
    _git(repo, "commit", "-qm", "add early-exit gate")
    sha = _git(repo, "rev-parse", "HEAD")
    evidence_root = repo / "build" / "handoff-evidence" / sha
    attestation = "pytest-attestations/early-exit.json"
    runner = Path(recorder_module.__file__).with_name("run_required_pytest_gate.py")
    spec = GateSpec(
        check_id="early-exit",
        section="7",
        argv=(
            sys.executable,
            str(runner),
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/{attestation}",
            "--",
            "-s",
            "-q",
            "test_early_exit.py",
        ),
        timeout_seconds=30,
        outcome=OutcomePolicy.pytest_strict(),
        required_artifact_paths=(attestation,),
        pytest_attestation_path=attestation,
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=spec.resolve_argv(evidence_root),
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert record["pytest_outcomes"]["passed"] == 0
    assert "attestation was not produced" in record["failure_reason"].lower()


def test_verifier_rejects_empty_required_check_set(tmp_path) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha

    assert validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(),
        expected_branch=branch,
        require_upstream=False,
    ) == (False, "At least one required handoff check must be specified.")


def _record_artifact_gate(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str, GateSpec]:
    repo, _sha, branch = _repo(tmp_path)
    gate_test = repo / "test_artifact_gate.py"
    gate_test.write_text(
        "import subprocess\n"
        "from pathlib import Path\n\n"
        "def test_artifact_gate():\n"
        "    root = Path(__file__).parent\n"
        "    sha = subprocess.check_output("
        "['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()\n"
        "    output = root / 'build' / 'handoff-evidence' / sha / 'result.json'\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_text('{\"ok\": true}\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    _git(repo, "add", "test_artifact_gate.py")
    _git(repo, "commit", "-qm", "add artifact gate")
    sha = _git(repo, "rev-parse", "HEAD")
    evidence_root = repo / "build" / "handoff-evidence" / sha
    attestation = "pytest-attestations/artifact-pytest.json"
    runner = Path(recorder_module.__file__).with_name("run_required_pytest_gate.py")
    spec = GateSpec(
        check_id="artifact-pytest",
        section="7",
        argv=(
            sys.executable,
            str(runner),
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/{attestation}",
            "--",
            "-q",
            "test_artifact_gate.py",
        ),
        timeout_seconds=30,
        environment=EnvironmentPolicy(
            required=(
                ("TEST_GATE_MODE", "strict"),
                ("PYTHONDONTWRITEBYTECODE", "1"),
            )
        ),
        outcome=OutcomePolicy.pytest_strict(),
        required_artifact_paths=("result.json", attestation),
        pytest_attestation_path=attestation,
    )
    _install_test_gate(monkeypatch, spec)
    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=spec.resolve_argv(evidence_root),
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )
    assert record["passed"] is True
    return repo, evidence_root, branch, spec


@pytest.mark.parametrize(
    ("changes", "reason_fragment"),
    [
        ({"section": "6"}, "section was edited"),
        ({"command": ["/bin/true"]}, "argv was edited"),
        (
            {"environment": {"TEST_GATE_MODE": "loose"}},
            "environment policy was edited",
        ),
        (
            {"sanitized_environment_names": []},
            "sanitized environment was edited",
        ),
        (
            {
                "artifact_policy": {
                    "required_paths": ["result.json"],
                    "preserved_input_paths": ["result.json"],
                }
            },
            "artifact policy was edited",
        ),
        (
            {
                "outcome_policy": {
                    "allowed_return_codes": [0, 7],
                    "require_pytest_attestation": True,
                    "forbidden_pytest_outcomes": [],
                }
            },
            "outcome policy was edited",
        ),
        ({"passed": False}, "passed summary was edited"),
        ({"source_stable": False}, "source_stable summary was edited"),
        (
            {
                "pytest_outcomes": {
                    "passed": 999,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "xfailed": 0,
                    "xpassed": 0,
                    "deselected": 0,
                }
            },
            "pytest summary was edited",
        ),
    ],
)
def test_verifier_rejects_edited_command_and_derived_summaries(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    reason_fragment: str,
) -> None:
    repo, evidence_root, branch, spec = _record_artifact_gate(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    _rewrite_check(evidence_root, spec.check_id, **changes)

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
    )

    assert ok is False
    assert reason_fragment in reason


def test_failed_exit_cannot_be_edited_into_a_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    command = (sys.executable, "-c", "raise SystemExit(7)")
    spec = GateSpec(
        check_id="failed-command",
        section="2",
        argv=command,
        timeout_seconds=30,
    )
    _install_test_gate(monkeypatch, spec)
    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=30,
        expected_branch=branch,
        require_upstream=False,
    )
    assert record["passed"] is False
    _rewrite_check(evidence_root, spec.check_id, passed=True, failure_reason="")

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
    )

    assert ok is False
    assert "passed summary was edited" in reason


def test_verifier_rejects_mutated_registered_artifact(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, evidence_root, branch, spec = _record_artifact_gate(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    (evidence_root / "result.json").write_text(
        '{"ok": false}\n',
        encoding="utf-8",
    )

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
    )

    assert ok is False
    assert "registered artifact identity is stale" in reason


def test_missing_registered_artifact_prevents_recorded_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    command = (sys.executable, "-c", "print('command returned zero')")
    spec = GateSpec(
        check_id="missing-artifact",
        section="5",
        argv=command,
        timeout_seconds=30,
        required_artifact_paths=("required-output",),
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert "required registered artifact" in record["failure_reason"].lower()


def test_stale_registered_artifact_cannot_satisfy_a_new_gate_run(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    stale_path = evidence_root / "fresh-output" / "result.json"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text('{"stale": true}\n', encoding="utf-8")
    command = (sys.executable, "-c", "print('returned zero without output')")
    spec = GateSpec(
        check_id="fresh-artifact",
        section="5",
        argv=command,
        timeout_seconds=30,
        required_artifact_paths=("fresh-output",),
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["return_code"] == 0
    assert record["passed"] is False
    assert not stale_path.exists()
    assert "required registered artifact" in record["failure_reason"].lower()


def test_registered_input_artifact_can_be_preserved_for_validation_gate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    input_path = evidence_root / "capture" / "result.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text('{"captured": true}\n', encoding="utf-8")
    command = (sys.executable, "-c", "print('validated existing capture')")
    spec = GateSpec(
        check_id="preserved-artifact",
        section="5",
        argv=command,
        timeout_seconds=30,
        required_artifact_paths=("capture",),
        preserved_input_artifact_paths=("capture",),
    )
    _install_test_gate(monkeypatch, spec)

    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=command,
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )

    assert record["passed"] is True
    assert input_path.exists()
    assert record["artifact_policy"]["preserved_input_paths"] == ["capture"]


def test_verifier_recursively_hashes_registered_artifact_directories(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha, branch = _repo(tmp_path)
    evidence_root = repo / "build" / "handoff-evidence" / sha
    source = (
        "from pathlib import Path; import sys; "
        "path = Path(sys.argv[1]) / 'nested' / 'result.txt'; "
        "path.parent.mkdir(parents=True); path.write_text('original\\n')"
    )
    spec = GateSpec(
        check_id="artifact-directory",
        section="5",
        argv=(sys.executable, "-c", source, f"{EVIDENCE_ROOT_TOKEN}/bundle"),
        timeout_seconds=30,
        required_artifact_paths=("bundle",),
    )
    _install_test_gate(monkeypatch, spec)
    record = record_handoff_command(
        repo_root=repo,
        evidence_root=evidence_root,
        section=spec.section,
        check_id=spec.check_id,
        command=spec.resolve_argv(evidence_root),
        timeout_seconds=spec.timeout_seconds,
        expected_branch=branch,
        require_upstream=False,
    )
    assert record["passed"] is True
    (evidence_root / "bundle" / "nested" / "result.txt").write_text(
        "mutated\n",
        encoding="utf-8",
    )

    ok, reason = validate_handoff_dossier(
        repo_root=repo,
        evidence_root=evidence_root,
        required_check_ids=(spec.check_id,),
        expected_branch=branch,
        require_upstream=False,
    )

    assert ok is False
    assert "registered artifact identity is stale" in reason
