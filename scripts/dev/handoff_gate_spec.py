"""Immutable command policy for exact-commit handoff evidence gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final

from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    SHARDED_PYTEST_RUNNER_ID,
)

EVIDENCE_ROOT_TOKEN: Final = "{evidence_root}"  # noqa: S105 - path placeholder
MODEL_CACHE_DIR_TOKEN: Final = "{model_cache_dir}"  # noqa: S105 - path placeholder
RAG_CACHE_DIR_TOKEN: Final = "{rag_cache_dir}"  # noqa: S105 - path placeholder
EXPECTED_BRANCH_TOKEN: Final = "{expected_branch}"  # noqa: S105 - argv placeholder
TARGET_SHA_TOKEN: Final = "{target_sha}"  # noqa: S105 - argv placeholder
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_SAFE_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_PYTEST_FORBIDDEN = (
    "failed",
    "errors",
    "skipped",
    "xfailed",
    "xpassed",
    "deselected",
)


@dataclass(frozen=True)
class EnvironmentPolicy:
    """Exact environment values injected for one registered command."""

    required: tuple[tuple[str, str], ...] = ()
    redacted_path_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = [name for name, _value in self.required]
        if len(names) != len(set(names)) or any(
            not _SAFE_ENV_NAME.fullmatch(name) for name in names
        ):
            raise ValueError("Gate environment names must be unique and canonical.")
        if len(self.redacted_path_names) != len(set(self.redacted_path_names)):
            raise ValueError("Redacted environment path names must be unique.")
        if not set(self.redacted_path_names).issubset(names):
            raise ValueError("Redacted environment paths must also be required.")

    def as_dict(self) -> dict[str, str]:
        return dict(self.required)


@dataclass(frozen=True)
class OutcomePolicy:
    """Raw process and pytest outcomes required for a recorded PASS."""

    allowed_return_codes: tuple[int, ...] = (0,)
    require_pytest_attestation: bool = False
    forbidden_pytest_outcomes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_return_codes or len(self.allowed_return_codes) != len(
            set(self.allowed_return_codes)
        ):
            raise ValueError("Gate return-code policy must be non-empty and unique.")

    @classmethod
    def pytest_strict(cls) -> OutcomePolicy:
        return cls(
            require_pytest_attestation=True,
            forbidden_pytest_outcomes=_PYTEST_FORBIDDEN,
        )


@dataclass(frozen=True)
class GateSpec:
    """One source-controlled handoff command and its evidence contract."""

    check_id: str
    section: str
    argv: tuple[str, ...]
    timeout_seconds: float
    environment: EnvironmentPolicy = EnvironmentPolicy()
    outcome: OutcomePolicy = OutcomePolicy()
    required_artifact_paths: tuple[str, ...] = ()
    preserved_input_artifact_paths: tuple[str, ...] = ()
    stdout_artifact_path: str | None = None
    pytest_attestation_path: str | None = None

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.check_id):
            raise ValueError(f"Invalid handoff check id: {self.check_id!r}.")
        if self.section not in {str(number) for number in range(1, 9)}:
            raise ValueError(f"Invalid handoff manifest section: {self.section!r}.")
        if not self.argv or any(not part for part in self.argv):
            raise ValueError(f"Gate {self.check_id!r} requires exact non-empty argv.")
        if self.timeout_seconds <= 0:
            raise ValueError(f"Gate {self.check_id!r} requires a positive timeout.")
        pytest_contract = _pytest_attestation_contract(self.argv)
        if self.outcome.require_pytest_attestation:
            if pytest_contract is None or self.pytest_attestation_path is None:
                raise ValueError(
                    f"Gate {self.check_id!r} requires an attesting pytest entrypoint."
                )
        elif self.pytest_attestation_path is not None:
            raise ValueError(
                f"Gate {self.check_id!r} registers pytest evidence without a policy."
            )
        if len(self.required_artifact_paths) != len(set(self.required_artifact_paths)):
            raise ValueError(f"Gate {self.check_id!r} repeats an artifact path.")
        if len(self.preserved_input_artifact_paths) != len(
            set(self.preserved_input_artifact_paths)
        ):
            raise ValueError(
                f"Gate {self.check_id!r} repeats a preserved input artifact path."
            )
        if not set(self.preserved_input_artifact_paths).issubset(
            self.required_artifact_paths
        ):
            raise ValueError(
                f"Gate {self.check_id!r} preserved inputs must also be required."
            )
        for artifact_path in self.required_artifact_paths:
            path = PurePosixPath(artifact_path)
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError(f"Gate {self.check_id!r} has an unsafe artifact path.")
        if (
            self.stdout_artifact_path is not None
            and self.stdout_artifact_path not in self.required_artifact_paths
        ):
            raise ValueError(
                f"Gate {self.check_id!r} stdout artifact must also be required."
            )
        if self.pytest_attestation_path is not None:
            if self.pytest_attestation_path not in self.required_artifact_paths:
                raise ValueError(
                    f"Gate {self.check_id!r} pytest attestation must also be required."
                )
            expected_argument = f"{EVIDENCE_ROOT_TOKEN}/{self.pytest_attestation_path}"
            if expected_argument not in self.argv:
                raise ValueError(
                    f"Gate {self.check_id!r} does not write its registered pytest "
                    "attestation path."
                )

    def resolve_argv(
        self,
        evidence_root: Path,
        *,
        expected_branch: str | None = None,
        target_sha: str | None = None,
    ) -> tuple[str, ...]:
        root = str(evidence_root.expanduser().resolve())
        branch = (expected_branch or "").strip()
        target = (target_sha or "").strip()
        if any(EXPECTED_BRANCH_TOKEN in part for part in self.argv) and not branch:
            raise ValueError(
                f"Gate {self.check_id!r} requires an explicit expected branch."
            )
        if any(TARGET_SHA_TOKEN in part for part in self.argv) and not (
            _FULL_SHA.fullmatch(target)
        ):
            raise ValueError(
                f"Gate {self.check_id!r} requires an immutable 40-character target SHA."
            )
        return tuple(
            part.replace(EVIDENCE_ROOT_TOKEN, root)
            .replace(
                EXPECTED_BRANCH_TOKEN,
                branch,
            )
            .replace(TARGET_SHA_TOKEN, target)
            for part in self.argv
        )

    def pytest_attestation_contract(self) -> tuple[str, tuple[str, ...]] | None:
        """Return the trusted runner identity and its exact logical arguments."""
        return _pytest_attestation_contract(self.argv)


def _pytest_attestation_contract(
    argv: tuple[str, ...],
) -> tuple[str, tuple[str, ...]] | None:
    """Recognize only source-controlled runners that attest normal completion."""
    tokens = list(argv)
    if tokens[:1] == ["prlimit"] and "--" in tokens:
        tokens = tokens[tokens.index("--") + 1 :]
    if tokens[:2] == ["poetry", "run"]:
        tokens = tokens[2:]
        if tokens[:1] == ["--"]:
            tokens = tokens[1:]
    if not tokens:
        return None
    executable = tokens[0].replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if not executable.casefold().startswith("python"):
        return None
    runner_name = ""
    runner_args: list[str]
    if tokens[1:2] == ["-m"] and len(tokens) >= 3:
        runner_name = tokens[2].casefold()
        runner_args = tokens[3:]
    elif len(tokens) >= 2:
        runner_name = tokens[1].replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        runner_name = runner_name.casefold()
        runner_args = tokens[2:]
    else:
        return None
    if runner_name in {
        "run_required_pytest_gate.py",
        "scripts.dev.run_required_pytest_gate",
    }:
        if "--result-json" not in runner_args or "--" not in runner_args:
            return None
        separator = runner_args.index("--")
        return REQUIRED_PYTEST_RUNNER_ID, tuple(runner_args[separator + 1 :])
    if runner_name in {"run_tests.py", "scripts.dev.run_tests"}:
        if "--result-json" not in runner_args or not runner_args:
            return None
        command = runner_args[0]
        return SHARDED_PYTEST_RUNNER_ID, (command,)
    return None


_POETRY_EXEC = ("poetry", "run", "--")
_PRLIMIT = ("prlimit", "--core=0", "--")
_PYTEST_BUILTINS_ONLY = EnvironmentPolicy(
    required=(("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),)
)
_MNE = EnvironmentPolicy(required=(("MNE_DONTWRITE_HOME", "true"),))
_QT = EnvironmentPolicy(required=(("QT_QPA_PLATFORM", "offscreen"),))
_QT_MNE = EnvironmentPolicy(
    required=(
        ("QT_QPA_PLATFORM", "offscreen"),
        ("MNE_DONTWRITE_HOME", "true"),
    )
)
_LOCAL_RUNTIME_OFFLINE = EnvironmentPolicy(
    required=(
        ("HF_HUB_OFFLINE", "1"),
        ("TRANSFORMERS_OFFLINE", "1"),
        ("XBRAINLAB_MODEL_CACHE_DIR", MODEL_CACHE_DIR_TOKEN),
        ("XBRAINLAB_RAG_CACHE_DIR", RAG_CACHE_DIR_TOKEN),
    ),
    redacted_path_names=(
        "XBRAINLAB_MODEL_CACHE_DIR",
        "XBRAINLAB_RAG_CACHE_DIR",
    ),
)
_QT_MNE_OFFLINE = EnvironmentPolicy(
    required=(
        ("QT_QPA_PLATFORM", "offscreen"),
        ("MNE_DONTWRITE_HOME", "true"),
        ("HF_HUB_OFFLINE", "1"),
        ("TRANSFORMERS_OFFLINE", "1"),
    )
)
_QT_MNE_LOCAL_RUNTIME = EnvironmentPolicy(
    required=(
        *_QT_MNE_OFFLINE.required,
        ("XBRAINLAB_MODEL_CACHE_DIR", MODEL_CACHE_DIR_TOKEN),
        ("XBRAINLAB_RAG_CACHE_DIR", RAG_CACHE_DIR_TOKEN),
    ),
    redacted_path_names=(
        "XBRAINLAB_MODEL_CACHE_DIR",
        "XBRAINLAB_RAG_CACHE_DIR",
    ),
)
_STRICT_PYTEST = OutcomePolicy.pytest_strict()
# The complete cross-platform suite contains intentional platform-only skips.
_COMPLETE_REGRESSION_OUTCOME = OutcomePolicy(
    require_pytest_attestation=True,
    forbidden_pytest_outcomes=(
        "failed",
        "errors",
        "xfailed",
        "xpassed",
        "deselected",
    ),
)


_GATE_SPECS = (
    GateSpec(
        check_id="git-status",
        section="1",
        argv=("git", "status", "--short", "--branch"),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="git-head",
        section="1",
        argv=("git", "rev-parse", "HEAD"),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="git-upstream",
        section="1",
        argv=(
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        ),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="git-divergence",
        section="1",
        argv=(
            "git",
            "rev-list",
            "--left-right",
            "--count",
            "HEAD...@{upstream}",
        ),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="git-worktrees",
        section="1",
        argv=("git", "worktree", "list", "--porcelain"),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="git-diff-check",
        section="1",
        argv=("git", "diff", "--check"),
        timeout_seconds=30,
    ),
    GateSpec(
        check_id="ruff-check",
        section="1",
        argv=(*_POETRY_EXEC, "ruff", "check", "."),
        timeout_seconds=1800,
    ),
    GateSpec(
        check_id="ruff-format-check",
        section="1",
        argv=(*_POETRY_EXEC, "ruff", "format", "--check", "."),
        timeout_seconds=1800,
    ),
    GateSpec(
        check_id="basedpyright",
        section="1",
        argv=(
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_basedpyright_regression.py",
            "--repo-root",
            ".",
            "--target-sha",
            TARGET_SHA_TOKEN,
        ),
        timeout_seconds=3600,
        required_artifact_paths=("basedpyright-regression.json",),
        stdout_artifact_path="basedpyright-regression.json",
    ),
    GateSpec(
        check_id="mkdocs-strict",
        section="1",
        argv=(*_POETRY_EXEC, "mkdocs", "build", "--strict"),
        timeout_seconds=600,
    ),
    GateSpec(
        check_id="architecture-compliance",
        section="2",
        argv=(
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_architecture_compliance_regression.py",
            "--repo-root",
            ".",
            "--target-sha",
            TARGET_SHA_TOKEN,
        ),
        timeout_seconds=900,
        required_artifact_paths=("architecture-compliance-regression.json",),
        stdout_artifact_path="architecture-compliance-regression.json",
    ),
    GateSpec(
        check_id="architecture-unit",
        section="2",
        argv=(
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/architecture-unit.json",
            "--",
            "--capture=sys",
            "tests/unit/test_architecture.py",
            "tests/unit/test_architecture_compliance.py",
            "tests/unit/test_evaluation_read_side_architecture.py",
            "-q",
        ),
        timeout_seconds=1200,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/architecture-unit.json",),
        pytest_attestation_path="pytest-attestations/architecture-unit.json",
    ),
    GateSpec(
        check_id="guidance-contract",
        section="2",
        argv=(
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/guidance-contract.json",
            "--",
            "--capture=sys",
            "--confcutdir=tests/unit",
            "tests/unit/test_agent_guidance_contract.py",
            "tests/unit/scripts/test_audit_agent_guidance.py",
            "-q",
        ),
        timeout_seconds=1200,
        environment=_PYTEST_BUILTINS_ONLY,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/guidance-contract.json",),
        pytest_attestation_path="pytest-attestations/guidance-contract.json",
    ),
    GateSpec(
        check_id="persistence-path-stop-barrier",
        section="2",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/persistence-path-stop-barrier.json",
            "--",
            "--capture=sys",
            "tests/unit/backend/training/record/test_safe_artifact_store.py",
            "tests/unit/backend/training/record/test_output_path_policy.py",
            "tests/unit/backend/utils/test_filesystem_identity.py",
            "tests/unit/backend/training/test_trainer_optimizer_step_stop_barrier.py",
            "-q",
        ),
        timeout_seconds=1200,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=(
            "pytest-attestations/persistence-path-stop-barrier.json",
        ),
        pytest_attestation_path=(
            "pytest-attestations/persistence-path-stop-barrier.json"
        ),
    ),
    GateSpec(
        check_id="complete-regression",
        section="2",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_tests.py",
            "all",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/complete-regression.json",
        ),
        timeout_seconds=7200,
        environment=_QT_MNE_LOCAL_RUNTIME,
        outcome=_COMPLETE_REGRESSION_OUTCOME,
        required_artifact_paths=("pytest-attestations/complete-regression.json",),
        pytest_attestation_path="pytest-attestations/complete-regression.json",
    ),
    GateSpec(
        check_id="command-spine",
        section="3",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/command-spine.json",
            "--",
            "--capture=sys",
            "tests/integration/pipeline/test_application_service_fif_visualization_smoke.py",
            "tests/integration/pipeline/test_deterministic_oracle_training_evidence.py",
            "-q",
        ),
        timeout_seconds=1800,
        environment=_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/command-spine.json",),
        pytest_attestation_path="pytest-attestations/command-spine.json",
    ),
    GateSpec(
        check_id="assistant-security-suite",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/assistant-security-suite.json",
            "--",
            "--capture=sys",
            "tests/integration/agent/test_product_flow.py",
            "tests/integration/agent/test_controller_lifecycle_faults.py",
            "tests/integration/agent/test_long_session_product_flow.py",
            "tests/integration/agent/test_rag_readmission.py",
            "tests/integration/agent/test_resource_confirmation_generation.py",
            "tests/integration/agent/test_strict_recovery_execution_boundary.py",
            "tests/unit/llm/rag/test_security_policy.py",
            "tests/unit/llm/rag/test_untrusted_context.py",
            "tests/unit/llm/agent/test_worker_process_supervision.py",
            "tests/unit/llm/agent/test_worker_timeout.py",
            "-q",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE_OFFLINE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/assistant-security-suite.json",),
        pytest_attestation_path="pytest-attestations/assistant-security-suite.json",
    ),
    GateSpec(
        check_id="granite-runtime",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/inspect_local_assistant_runtime.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--format",
            "json",
            "--prompt-smoke",
            "--structured-smoke",
            "--strict",
        ),
        timeout_seconds=900,
        environment=_LOCAL_RUNTIME_OFFLINE,
        required_artifact_paths=("granite-runtime.json",),
        stdout_artifact_path="granite-runtime.json",
    ),
    GateSpec(
        check_id="rag-offline",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/verify_rag.py",
            "--format",
            "json",
            "--strict",
            "--write-artifact",
            "--artifact-path",
            f"{EVIDENCE_ROOT_TOKEN}/rag-offline.json",
        ),
        timeout_seconds=900,
        environment=_LOCAL_RUNTIME_OFFLINE,
        required_artifact_paths=("rag-offline.json",),
    ),
    GateSpec(
        check_id="chatpanel-guided-boundary",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_chatpanel_local_guided_boundary_walkthrough.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--timeout-seconds",
            "600",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-guided-boundary",
        ),
        timeout_seconds=720,
        environment=_QT_MNE_LOCAL_RUNTIME,
        required_artifact_paths=("ui/chatpanel-guided-boundary",),
    ),
    GateSpec(
        check_id="chatpanel-training-readiness",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--timeout-seconds",
            "720",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-training-readiness",
        ),
        timeout_seconds=840,
        environment=_QT_MNE_LOCAL_RUNTIME,
        required_artifact_paths=("ui/chatpanel-training-readiness",),
    ),
    GateSpec(
        check_id="chatpanel-training-completion",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--timeout-seconds",
            "1080",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-training-completion",
            "--training-output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/runtime/training-completion",
        ),
        timeout_seconds=1200,
        environment=_QT_MNE_LOCAL_RUNTIME,
        required_artifact_paths=(
            "ui/chatpanel-training-completion",
            "runtime/training-completion",
        ),
    ),
    GateSpec(
        check_id="chatpanel-local-recovery",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_chatpanel_local_recovery_walkthrough.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--timeout-seconds",
            "600",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-local-recovery",
        ),
        timeout_seconds=720,
        environment=_QT_MNE_LOCAL_RUNTIME,
        required_artifact_paths=("ui/chatpanel-local-recovery",),
    ),
    GateSpec(
        check_id="chatpanel-local-long-session",
        section="4",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_chatpanel_exact_granite_long_session.py",
            "--model",
            "ibm-granite/granite-3.3-2b-instruct",
            "--timeout-seconds",
            "600",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-local-long-session",
        ),
        timeout_seconds=720,
        environment=_QT_MNE_LOCAL_RUNTIME,
        required_artifact_paths=("ui/chatpanel-local-long-session",),
    ),
    GateSpec(
        check_id="human-like-product",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_human_like_product_walkthrough.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/human-like-product",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        required_artifact_paths=("ui/human-like-product",),
    ),
    GateSpec(
        check_id="ui-reviewer-fixes",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_ui_reviewer_fixes.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/reviewer-fixes",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        required_artifact_paths=("ui/reviewer-fixes",),
    ),
    GateSpec(
        check_id="dataset-narrow",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_dataset_narrow_walkthrough.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/dataset-narrow",
        ),
        timeout_seconds=900,
        environment=_QT,
        required_artifact_paths=("ui/dataset-narrow",),
    ),
    GateSpec(
        check_id="visualization-render",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_visualization_render_walkthrough.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/visualization-render",
            "--training-output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/runtime/visualization-training",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        required_artifact_paths=(
            "ui/visualization-render",
            "runtime/visualization-training",
        ),
    ),
    GateSpec(
        check_id="chatpanel-dpi",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_chatpanel_ui_dpi_gate.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/chatpanel-dpi",
        ),
        timeout_seconds=900,
        environment=_QT,
        required_artifact_paths=("ui/chatpanel-dpi",),
    ),
    GateSpec(
        check_id="data-import-wizard-capture",
        section="5",
        argv=(
            *_PRLIMIT,
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1600x1400x24",
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_data_import_wizard_steps.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/data-import-wizard-steps",
        ),
        timeout_seconds=1800,
        environment=EnvironmentPolicy(
            required=(
                ("QT_QPA_PLATFORM", "xcb"),
                ("MNE_DONTWRITE_HOME", "true"),
            )
        ),
        required_artifact_paths=("ui/data-import-wizard-steps",),
    ),
    GateSpec(
        check_id="data-import-wizard-validate",
        section="5",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/capture_data_import_wizard_steps.py",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/ui/data-import-wizard-steps",
            "--validate-only",
        ),
        timeout_seconds=300,
        environment=_QT,
        required_artifact_paths=("ui/data-import-wizard-steps",),
        preserved_input_artifact_paths=("ui/data-import-wizard-steps",),
    ),
    GateSpec(
        check_id="native-lifecycle-tests",
        section="6",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/native-lifecycle-tests.json",
            "--",
            "--capture=sys",
            "tests/integration/ui/test_preprocess_async_filter_lifecycle.py",
            "tests/integration/ui/test_preprocess_native_lifecycle.py",
            "tests/integration/ui/test_native_render_lifecycle.py",
            "-q",
        ),
        timeout_seconds=1200,
        environment=_QT_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/native-lifecycle-tests.json",),
        pytest_attestation_path="pytest-attestations/native-lifecycle-tests.json",
    ),
    GateSpec(
        check_id="preprocess-native-stress",
        section="6",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_preprocess_native_lifecycle_stress.py",
            "--cycles",
            "8",
        ),
        timeout_seconds=1200,
        environment=_QT_MNE,
    ),
    GateSpec(
        check_id="ui-native-render-stress",
        section="6",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_ui_native_render_stress.py",
            "--cycles",
            "12",
            "--warmup-cycles",
            "2",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
    ),
    GateSpec(
        check_id="fetch-required-ci",
        section="7",
        argv=(
            *_POETRY_EXEC,
            "python",
            "scripts/dev/fetch_public_eeg_fixtures.py",
            "--profile",
            "required-ci",
        ),
        timeout_seconds=3600,
    ),
    GateSpec(
        check_id="verify-required-ci",
        section="7",
        argv=(
            *_POETRY_EXEC,
            "python",
            "scripts/dev/fetch_public_eeg_fixtures.py",
            "--profile",
            "required-ci",
            "--verify-only",
        ),
        timeout_seconds=900,
    ),
    GateSpec(
        check_id="dataset-validation-matrix",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/report_dataset_validation_matrix.py",
            "--strict",
            "--format",
            "json",
        ),
        timeout_seconds=1200,
        environment=_MNE,
        required_artifact_paths=("dataset-validation-matrix.json",),
        stdout_artifact_path="dataset-validation-matrix.json",
    ),
    GateSpec(
        check_id="data-interpretation-matrix",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/report_data_interpretation_format_matrix.py",
            "--strict",
            "--format",
            "json",
            "--write-artifacts",
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/data-interpretation",
        ),
        timeout_seconds=1200,
        environment=_MNE,
        required_artifact_paths=("data-interpretation",),
    ),
    GateSpec(
        check_id="real-data-interpretation-training",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/real-data-interpretation-training.json",
            "--",
            "--capture=sys",
            "tests/integration/pipeline/test_real_data_handoff_gate.py",
            "-q",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=(
            "pytest-attestations/real-data-interpretation-training.json",
        ),
        pytest_attestation_path=(
            "pytest-attestations/real-data-interpretation-training.json"
        ),
    ),
    GateSpec(
        check_id="wizard-format-matrix",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/wizard-format-matrix.json",
            "--",
            "--capture=sys",
            "tests/integration/ui/test_data_import_wizard_format_matrix.py",
            "-q",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/wizard-format-matrix.json",),
        pytest_attestation_path="pytest-attestations/wizard-format-matrix.json",
    ),
    GateSpec(
        check_id="required-public-io",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/required-public-io.json",
            "--",
            "--capture=sys",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_gdf_file_success",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_gdf_file_restores_known_graz_channel_names",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_supported_real_formats",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_application_service_import_supported_real_formats",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_application_service_summary_excludes_resolved_gdf_channel_normalization",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_public_real_formats",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_application_service_import_public_real_formats",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_non_existent_file",
            "tests/integration/io/test_io_integration.py::TestIOIntegration::test_load_invalid_extension",
            "tests/integration/io/test_public_bids_fixture.py",
            "tests/integration/pipeline/test_public_cross_source_training_smoke.py",
            "-q",
        ),
        timeout_seconds=1800,
        environment=_QT_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/required-public-io.json",),
        pytest_attestation_path="pytest-attestations/required-public-io.json",
    ),
    GateSpec(
        check_id="public-cross-source-training",
        section="7",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/run_public_cross_source_training_smoke.py",
            "--format",
            "json",
            "--strict",
        ),
        timeout_seconds=1800,
        environment=_MNE,
        required_artifact_paths=("public-cross-source-training-smoke.json",),
        stdout_artifact_path="public-cross-source-training-smoke.json",
    ),
    GateSpec(
        check_id="resource-contract",
        section="8",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "-m",
            "scripts.dev.run_required_pytest_gate",
            "--result-json",
            f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/resource-contract.json",
            "--",
            "--capture=sys",
            "tests/unit/scripts/test_calibrate_resource_guard.py",
            "tests/integration/backend/test_resource_confirmation_publication.py",
            "-q",
        ),
        timeout_seconds=1200,
        environment=_MNE,
        outcome=_STRICT_PYTEST,
        required_artifact_paths=("pytest-attestations/resource-contract.json",),
        pytest_attestation_path="pytest-attestations/resource-contract.json",
    ),
    GateSpec(
        check_id="resource-calibration",
        section="8",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/calibrate_resource_guard.py",
            "--strict",
            "--output",
            f"{EVIDENCE_ROOT_TOKEN}/resource-calibration.json",
        ),
        timeout_seconds=900,
        required_artifact_paths=("resource-calibration.json",),
    ),
    GateSpec(
        check_id="handoff-dashboard",
        section="8",
        argv=(
            *_PRLIMIT,
            *_POETRY_EXEC,
            "python",
            "scripts/dev/update_quality_dashboard.py",
            "--handoff",
            "--expected-branch",
            EXPECTED_BRANCH_TOKEN,
            "--output-dir",
            f"{EVIDENCE_ROOT_TOKEN}/dashboard",
            "--resource-calibration-path",
            f"{EVIDENCE_ROOT_TOKEN}/resource-calibration.json",
        ),
        timeout_seconds=7200,
        required_artifact_paths=("resource-calibration.json", "dashboard"),
        preserved_input_artifact_paths=("resource-calibration.json",),
    ),
)

if len({spec.check_id for spec in _GATE_SPECS}) != len(_GATE_SPECS):
    raise RuntimeError("Handoff gate check ids must be unique.")

HANDOFF_GATE_SPECS: Final = MappingProxyType(
    {spec.check_id: spec for spec in _GATE_SPECS}
)
REQUIRED_HANDOFF_CHECK_IDS: Final = tuple(HANDOFF_GATE_SPECS)
