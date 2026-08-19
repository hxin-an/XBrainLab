from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from scripts.dev.handoff_gate_spec import (
    EVIDENCE_ROOT_TOKEN,
    HANDOFF_GATE_SPECS,
    MODEL_CACHE_DIR_TOKEN,
    RAG_CACHE_DIR_TOKEN,
    REQUIRED_HANDOFF_CHECK_IDS,
    GateSpec,
    OutcomePolicy,
)
from scripts.dev.update_quality_dashboard import REQUIRED_PUBLIC_IO_TEST_NODES

ROOT = Path(__file__).resolve().parents[3]
VALIDATION_DOC = ROOT / "docs" / "validation" / "README.md"
RUNNER_PATH = ROOT / "scripts" / "dev" / "run_handoff_validation_manifest.py"
EXPECTED_HANDOFF_CHECK_IDS = (
    "git-status",
    "git-head",
    "git-upstream",
    "git-divergence",
    "git-worktrees",
    "git-diff-check",
    "ruff-check",
    "ruff-format-check",
    "basedpyright",
    "mkdocs-strict",
    "architecture-compliance",
    "architecture-unit",
    "persistence-path-stop-barrier",
    "complete-regression",
    "command-spine",
    "assistant-security-suite",
    "assistant-frontend-contract",
    "granite-runtime",
    "stable-assistant-model-eval",
    "rag-offline",
    "human-like-product",
    "ui-reviewer-fixes",
    "dataset-narrow",
    "visualization-render",
    "chatpanel-dpi",
    "data-import-wizard-capture",
    "data-import-wizard-validate",
    "native-lifecycle-tests",
    "preprocess-native-stress",
    "ui-native-render-stress",
    "fetch-required-ci",
    "verify-required-ci",
    "dataset-validation-matrix",
    "data-interpretation-matrix",
    "real-data-interpretation-training",
    "wizard-format-matrix",
    "required-public-io",
    "public-cross-source-training",
    "resource-calibration",
    "startup-smoke",
    "ui-visual-baseline",
    "handoff-dashboard",
)
LOCAL_RUNTIME_CHECK_IDS = (
    "granite-runtime",
    "stable-assistant-model-eval",
    "rag-offline",
)


def test_checked_in_registry_is_nonempty_exact_and_complete() -> None:
    assert REQUIRED_HANDOFF_CHECK_IDS == EXPECTED_HANDOFF_CHECK_IDS
    assert tuple(HANDOFF_GATE_SPECS) == EXPECTED_HANDOFF_CHECK_IDS
    assert {spec.section for spec in HANDOFF_GATE_SPECS.values()} == {
        str(number) for number in range(1, 9)
    }
    sections = tuple(int(spec.section) for spec in HANDOFF_GATE_SPECS.values())
    assert sections == tuple(sorted(sections))
    assert REQUIRED_HANDOFF_CHECK_IDS[-1] == "handoff-dashboard"

    for check_id, spec in HANDOFF_GATE_SPECS.items():
        assert spec.check_id == check_id
        assert spec.argv
        assert spec.timeout_seconds > 0
        assert spec.outcome.allowed_return_codes
        assert "/bin/true" not in spec.argv
        assert len(spec.required_artifact_paths) == len(
            set(spec.required_artifact_paths)
        )
        if spec.stdout_artifact_path is not None:
            assert spec.stdout_artifact_path in spec.required_artifact_paths


def test_strict_pytest_outcome_requires_a_recognized_pytest_entrypoint() -> None:
    with pytest.raises(ValueError, match="pytest entrypoint"):
        GateSpec(
            check_id="spoofed-pytest",
            section="2",
            argv=(sys.executable, "-c", "print('2 passed in 0.01s')"),
            timeout_seconds=30,
            outcome=OutcomePolicy.pytest_strict(),
        )


def test_complete_regression_uses_the_bounded_fail_closed_full_runner() -> None:
    spec = HANDOFF_GATE_SPECS["complete-regression"]

    assert spec.section == "2"
    assert spec.argv == (
        "prlimit",
        "--core=0",
        "--",
        "poetry",
        "run",
        "--",
        "python",
        "scripts/dev/run_tests.py",
        "all",
        "--result-json",
        f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/complete-regression.json",
    )
    assert spec.timeout_seconds == 7200
    assert spec.environment.as_dict() == {
        "QT_QPA_PLATFORM": "offscreen",
        "MNE_DONTWRITE_HOME": "true",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "XBRAINLAB_MODEL_CACHE_DIR": MODEL_CACHE_DIR_TOKEN,
        "XBRAINLAB_RAG_CACHE_DIR": RAG_CACHE_DIR_TOKEN,
    }
    assert spec.environment.redacted_path_names == (
        "XBRAINLAB_MODEL_CACHE_DIR",
        "XBRAINLAB_RAG_CACHE_DIR",
    )
    assert spec.outcome.allowed_return_codes == (0,)
    assert spec.outcome.require_pytest_attestation is True
    assert spec.outcome.forbidden_pytest_outcomes == (
        "failed",
        "errors",
        "xfailed",
        "xpassed",
        "deselected",
    )
    assert spec.pytest_attestation_path == (
        "pytest-attestations/complete-regression.json"
    )


def test_stable_assistant_frontend_and_model_gates_are_exact() -> None:
    frontend = HANDOFF_GATE_SPECS["assistant-frontend-contract"]
    assert frontend.section == "4"
    assert frontend.argv == (
        "prlimit",
        "--core=0",
        "--",
        "poetry",
        "run",
        "--",
        "python",
        "-m",
        "scripts.dev.run_required_pytest_gate",
        "--result-json",
        (f"{EVIDENCE_ROOT_TOKEN}/pytest-attestations/assistant-frontend-contract.json"),
        "--",
        "--capture=sys",
        "tests/unit/scripts/test_agent_walkthrough_profiles.py",
        (
            "tests/integration/debug/test_debug_script_execution.py::"
            "test_contract_failure_profile_advances_only_on_real_terminals"
        ),
        "-q",
    )
    assert frontend.timeout_seconds == 600
    assert frontend.outcome == OutcomePolicy.pytest_strict()
    assert frontend.required_artifact_paths == (
        "pytest-attestations/assistant-frontend-contract.json",
    )
    assert frontend.pytest_attestation_path == (
        "pytest-attestations/assistant-frontend-contract.json"
    )

    model_eval = HANDOFF_GATE_SPECS["stable-assistant-model-eval"]
    assert model_eval.section == "4"
    assert model_eval.argv == (
        "prlimit",
        "--core=0",
        "--",
        "poetry",
        "run",
        "--",
        "python",
        "scripts/dev/run_stable_assistant_model_eval.py",
        "--device",
        "cuda",
        "--strict",
        "--json-out",
        f"{EVIDENCE_ROOT_TOKEN}/stable-assistant-model-eval.json",
    )
    assert model_eval.timeout_seconds == 1800
    assert model_eval.required_artifact_paths == ("stable-assistant-model-eval.json",)
    assert model_eval.preserved_input_artifact_paths == ()


def test_resource_calibration_is_generated_then_preserved_for_dashboard() -> None:
    calibration = HANDOFF_GATE_SPECS["resource-calibration"]
    dashboard = HANDOFF_GATE_SPECS["handoff-dashboard"]

    assert calibration.section == "8"
    assert calibration.argv == (
        "prlimit",
        "--core=0",
        "--",
        "poetry",
        "run",
        "--",
        "python",
        "scripts/dev/calibrate_resource_guard.py",
        "--strict",
        "--output",
        f"{EVIDENCE_ROOT_TOKEN}/resource-calibration.json",
    )
    assert calibration.required_artifact_paths == ("resource-calibration.json",)
    calibration_index = dashboard.argv.index("--resource-calibration-path")
    assert dashboard.argv[calibration_index : calibration_index + 2] == (
        "--resource-calibration-path",
        f"{EVIDENCE_ROOT_TOKEN}/resource-calibration.json",
    )
    assert dashboard.required_artifact_paths == (
        "resource-calibration.json",
        "dashboard",
    )
    assert dashboard.preserved_input_artifact_paths == ("resource-calibration.json",)
    assert REQUIRED_HANDOFF_CHECK_IDS[-4:] == (
        "resource-calibration",
        "startup-smoke",
        "ui-visual-baseline",
        "handoff-dashboard",
    )


def test_startup_and_visual_baseline_are_explicit_pre_dashboard_gates() -> None:
    startup = HANDOFF_GATE_SPECS["startup-smoke"]
    baseline = HANDOFF_GATE_SPECS["ui-visual-baseline"]
    dashboard = HANDOFF_GATE_SPECS["handoff-dashboard"]

    assert startup.argv[-1] == "scripts/dev/run_startup_smoke.py"
    assert startup.required_artifact_paths == ("startup-smoke.json",)
    assert startup.stdout_artifact_path == "startup-smoke.json"
    assert baseline.argv[-2:] == (
        "--output-dir",
        f"{EVIDENCE_ROOT_TOKEN}/ui/visual-baseline",
    )
    assert baseline.required_artifact_paths == ("ui/visual-baseline",)
    assert REQUIRED_HANDOFF_CHECK_IDS.index("startup-smoke") < (
        REQUIRED_HANDOFF_CHECK_IDS.index("handoff-dashboard")
    )
    assert REQUIRED_HANDOFF_CHECK_IDS.index("ui-visual-baseline") < (
        REQUIRED_HANDOFF_CHECK_IDS.index("handoff-dashboard")
    )
    assert dashboard.argv[-2:] == (
        "--handoff-evidence-path",
        f"{EVIDENCE_ROOT_TOKEN}/handoff-evidence.json",
    )


def test_local_runtime_gates_bind_both_redacted_d_drive_cache_paths() -> None:
    for check_id in LOCAL_RUNTIME_CHECK_IDS:
        policy = HANDOFF_GATE_SPECS[check_id].environment
        offline_cache_environment = (
            ("HF_HUB_OFFLINE", "1"),
            ("TRANSFORMERS_OFFLINE", "1"),
            ("XBRAINLAB_MODEL_CACHE_DIR", MODEL_CACHE_DIR_TOKEN),
            ("XBRAINLAB_RAG_CACHE_DIR", RAG_CACHE_DIR_TOKEN),
        )
        assert policy.required == offline_cache_environment
        assert policy.as_dict()["XBRAINLAB_MODEL_CACHE_DIR"] == MODEL_CACHE_DIR_TOKEN
        assert policy.as_dict()["XBRAINLAB_RAG_CACHE_DIR"] == RAG_CACHE_DIR_TOKEN
        assert policy.redacted_path_names == (
            "XBRAINLAB_MODEL_CACHE_DIR",
            "XBRAINLAB_RAG_CACHE_DIR",
        )
        assert policy.as_dict()["HF_HUB_OFFLINE"] == "1"
        assert policy.as_dict()["TRANSFORMERS_OFFLINE"] == "1"


def test_gate_registry_tracks_security_and_artifact_policy() -> None:
    command_spine = HANDOFF_GATE_SPECS["command-spine"]
    assert command_spine.environment.as_dict() == {"MNE_DONTWRITE_HOME": "true"}
    assert command_spine.outcome.require_pytest_attestation is True
    assert command_spine.argv[3:7] == (
        "poetry",
        "run",
        "--",
        "python",
    )
    assert (
        "tests/integration/pipeline/test_application_service_fif_visualization_smoke.py"
        in command_spine.argv
    )
    assert (
        "tests/integration/pipeline/test_deterministic_oracle_training_evidence.py"
        in command_spine.argv
    )

    persistence = HANDOFF_GATE_SPECS["persistence-path-stop-barrier"]
    assert "tests/unit/backend/training/record/test_safe_artifact_store.py" in (
        persistence.argv
    )
    assert "tests/unit/backend/training/record/test_output_path_policy.py" in (
        persistence.argv
    )
    assert (
        "tests/unit/backend/training/test_trainer_optimizer_step_stop_barrier.py"
        in persistence.argv
    )

    granite = HANDOFF_GATE_SPECS["granite-runtime"]
    assert granite.stdout_artifact_path == "granite-runtime.json"
    assert granite.required_artifact_paths == ("granite-runtime.json",)

    frontend = HANDOFF_GATE_SPECS["assistant-frontend-contract"]
    assert frontend.required_artifact_paths == (
        "pytest-attestations/assistant-frontend-contract.json",
    )
    model_eval = HANDOFF_GATE_SPECS["stable-assistant-model-eval"]
    assert model_eval.required_artifact_paths == ("stable-assistant-model-eval.json",)
    assert any(EVIDENCE_ROOT_TOKEN in part for part in model_eval.argv)

    data_import_validation = HANDOFF_GATE_SPECS["data-import-wizard-validate"]
    assert data_import_validation.required_artifact_paths == (
        "ui/data-import-wizard-steps",
    )
    assert data_import_validation.preserved_input_artifact_paths == (
        "ui/data-import-wizard-steps",
    )


def test_every_attested_pytest_gate_uses_poetry_argument_separator() -> None:
    attested = tuple(
        spec
        for spec in HANDOFF_GATE_SPECS.values()
        if spec.outcome.require_pytest_attestation
    )

    assert attested
    for spec in attested:
        poetry_index = spec.argv.index("poetry")
        assert spec.argv[poetry_index : poetry_index + 4] == (
            "poetry",
            "run",
            "--",
            "python",
        ), spec.check_id


def test_every_registered_poetry_gate_uses_argument_separator() -> None:
    poetry_gates = tuple(
        spec for spec in HANDOFF_GATE_SPECS.values() if "poetry" in spec.argv
    )

    assert poetry_gates
    for spec in poetry_gates:
        poetry_index = spec.argv.index("poetry")
        assert spec.argv[poetry_index : poetry_index + 3] == (
            "poetry",
            "run",
            "--",
        ), spec.check_id


def test_required_public_io_gate_uses_exact_mandatory_nodes() -> None:
    argv = HANDOFF_GATE_SPECS["required-public-io"].argv
    declared_nodes = tuple(item for item in argv if item.startswith("tests/"))

    assert declared_nodes[: len(REQUIRED_PUBLIC_IO_TEST_NODES)] == (
        REQUIRED_PUBLIC_IO_TEST_NODES
    )
    assert "test_openneuro_bids_channels_apply_to_real_mne_raw" not in argv
    assert "test_sleep_edf_infers_prefixed_types_without_renaming_channels" not in argv
    assert "test_chbmit_duplicate_channel_names_keep_mne_unique_identity" not in argv


def test_real_data_interpretation_training_gate_is_strict_and_continuous() -> None:
    spec = HANDOFF_GATE_SPECS["real-data-interpretation-training"]

    assert spec.section == "7"
    assert spec.outcome == OutcomePolicy.pytest_strict()
    assert "tests/integration/pipeline/test_real_data_handoff_gate.py" in spec.argv
    assert spec.pytest_attestation_path == (
        "pytest-attestations/real-data-interpretation-training.json"
    )


def test_registered_python_entrypoints_exist() -> None:
    for spec in HANDOFF_GATE_SPECS.values():
        for item in spec.argv:
            if item.endswith(".py"):
                assert (ROOT / item).is_file(), f"missing gate entrypoint: {item}"


def test_docs_name_the_runner_as_the_canonical_manifest() -> None:
    text = VALIDATION_DOC.read_text(encoding="utf-8")

    assert RUNNER_PATH.is_file()
    assert "scripts/dev/run_handoff_validation_manifest.py" in text
    assert "scripts/dev/handoff_gate_spec.py" in text
    assert "唯一 command manifest" not in text
    assert "--model-cache-dir" in text
    assert "--rag-cache-dir" in text
    assert "--allow-external-evidence-root" in text
    assert 'git check-ignore -q "$HANDOFF_EVIDENCE_ROOT/.gitignore-probe"' not in text


def test_docs_preserve_evidence_and_cache_claim_boundaries() -> None:
    text = VALIDATION_DOC.read_text(encoding="utf-8")

    assert "repo-contained" in text
    assert "external" in text
    assert "D-mounted" in text
    assert "redacted" in text
    assert "sections 3-6" in text
    assert "does not run or certify" in text
    assert re.search(r"Windows.*acceptance", text, flags=re.IGNORECASE | re.DOTALL)
