"""Executable manifest for the immediate high-difference product scenarios."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Final, Literal

from scripts.dev.agent_toolcall_showcase.cases import SHOWCASE_CASES
from scripts.dev.handoff_gate_spec import (
    EVIDENCE_ROOT_TOKEN,
    HANDOFF_GATE_SPECS,
)

IMMEDIATE_PROFILE_ID: Final = "immediate-20"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_AGENT_CASE_IDS = (
    "import.scan_source",
    "blocked.preprocess_without_data",
    "settings.model_approved",
    "navigation.reset_cancelled",
    "import.apply_review_handoff",
    "safety.stale_revision",
    "recovery.runtime_error_retry",
    "analysis.evaluate_before_run",
)

ValidatorKind = Literal[
    "execution_artifacts",
    "json_object",
    "json_truthy",
    "json_equals",
    "pytest_attestation",
    "agent_showcase_case",
    "dpi_scale",
]


class ScenarioManifestError(RuntimeError):
    """Raised when scenario definitions cannot support a fail-closed run."""


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """One bounded command, possibly shared by several scenario validators."""

    execution_id: str
    timeout_seconds: float
    native: bool
    gate_id: str | None = None
    argv: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    required_artifact_paths: tuple[str, ...] = ()
    stdout_artifact_path: str | None = None
    depends_on_execution_ids: tuple[str, ...] = ()

    def command_template(self) -> tuple[str, ...]:
        if self.gate_id is not None:
            return HANDOFF_GATE_SPECS[self.gate_id].argv
        return self.argv

    def resolve_command(self, evidence_root: str) -> tuple[str, ...]:
        return tuple(
            part.replace(EVIDENCE_ROOT_TOKEN, evidence_root)
            for part in self.command_template()
        )

    def resolved_environment(self) -> dict[str, str]:
        if self.gate_id is not None:
            return HANDOFF_GATE_SPECS[self.gate_id].environment.as_dict()
        return dict(self.environment)

    def artifacts(self) -> tuple[str, ...]:
        if self.gate_id is not None:
            return HANDOFF_GATE_SPECS[self.gate_id].required_artifact_paths
        return self.required_artifact_paths

    def stdout_artifact(self) -> str | None:
        if self.gate_id is not None:
            return HANDOFF_GATE_SPECS[self.gate_id].stdout_artifact_path
        return self.stdout_artifact_path


@dataclass(frozen=True, slots=True)
class ArtifactPolicy:
    """Scenario-specific evidence needed in addition to process success."""

    description: str
    required_paths: tuple[str, ...]
    human_review_required: bool = False


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    """Inline validator selecting one unique result from a shared execution."""

    kind: ValidatorKind
    artifact_path: str | None = None
    key: str = ""
    json_path: tuple[str, ...] = ()
    expected: Any = None


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """One report row in a product scenario profile."""

    scenario_id: str
    title: str
    scope: str
    execution_id: str
    timeout_seconds: float
    artifact_policy: ArtifactPolicy
    validator: ValidatorSpec
    evidence_key: str
    pass_criteria: tuple[str, ...]
    claim_boundary: str
    coverage_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    """A named denominator over the configurable scenario catalog."""

    profile_id: str
    scenario_ids: tuple[str, ...]
    expected_scenario_count: int
    purpose: str
    claim_boundary: str
    denominator_kind: str = "product_scenarios"
    moabb_dataset_campaign_in_scope: bool = False


def _gate_execution(
    gate_id: str,
    *,
    native: bool = True,
    depends_on: tuple[str, ...] = (),
) -> ExecutionSpec:
    gate = HANDOFF_GATE_SPECS[gate_id]
    return ExecutionSpec(
        execution_id=gate_id,
        timeout_seconds=gate.timeout_seconds,
        native=native,
        gate_id=gate_id,
        depends_on_execution_ids=depends_on,
    )


_agent_showcase_argv = [
    "prlimit",
    "--core=0",
    "--",
    "poetry",
    "run",
    "--",
    "python",
    "scripts/dev/run_agent_toolcall_showcase.py",
]
for _case_id in _AGENT_CASE_IDS:
    _agent_showcase_argv.extend(("--case", _case_id))
_agent_showcase_argv.extend(
    (
        "--json-out",
        f"{EVIDENCE_ROOT_TOKEN}/agent-toolcall-showcase/selected.json",
        "--markdown-out",
        f"{EVIDENCE_ROOT_TOKEN}/agent-toolcall-showcase/selected.md",
    )
)

_EXECUTIONS = (
    _gate_execution("fetch-required-ci", native=False),
    _gate_execution(
        "verify-required-ci",
        native=False,
        depends_on=("fetch-required-ci",),
    ),
    _gate_execution(
        "dataset-validation-matrix",
        depends_on=("verify-required-ci",),
    ),
    _gate_execution(
        "data-interpretation-matrix",
        depends_on=("verify-required-ci",),
    ),
    _gate_execution(
        "real-data-interpretation-training",
        depends_on=("verify-required-ci",),
    ),
    _gate_execution(
        "public-cross-source-training",
        depends_on=("verify-required-ci",),
    ),
    _gate_execution("command-spine"),
    _gate_execution("data-import-wizard-capture"),
    _gate_execution("visualization-render"),
    _gate_execution("human-like-product"),
    _gate_execution("dataset-narrow"),
    _gate_execution("chatpanel-dpi"),
    ExecutionSpec(
        execution_id="agent-showcase-selected",
        timeout_seconds=900,
        native=True,
        argv=tuple(_agent_showcase_argv),
        environment=(
            ("QT_QPA_PLATFORM", "offscreen"),
            ("MNE_DONTWRITE_HOME", "true"),
            ("HF_HUB_OFFLINE", "1"),
            ("TRANSFORMERS_OFFLINE", "1"),
        ),
        required_artifact_paths=(
            "agent-toolcall-showcase/selected.json",
            "agent-toolcall-showcase/selected.md",
        ),
    ),
)
PRODUCT_SCENARIO_EXECUTIONS: Final = MappingProxyType(
    {item.execution_id: item for item in _EXECUTIONS}
)


def _artifact(
    description: str,
    *paths: str,
    human_review_required: bool = False,
) -> ArtifactPolicy:
    return ArtifactPolicy(
        description=description,
        required_paths=tuple(paths),
        human_review_required=human_review_required,
    )


def _scenario(
    *,
    scenario_id: str,
    title: str,
    scope: str,
    execution_id: str,
    artifact_policy: ArtifactPolicy,
    validator: ValidatorSpec,
    evidence_key: str,
    pass_criteria: tuple[str, ...],
    claim_boundary: str,
    coverage_tags: tuple[str, ...],
) -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id=scenario_id,
        title=title,
        scope=scope,
        execution_id=execution_id,
        timeout_seconds=PRODUCT_SCENARIO_EXECUTIONS[execution_id].timeout_seconds,
        artifact_policy=artifact_policy,
        validator=validator,
        evidence_key=evidence_key,
        pass_criteria=pass_criteria,
        claim_boundary=claim_boundary,
        coverage_tags=coverage_tags,
    )


_SCENARIOS = (
    _scenario(
        scenario_id="data.source-format-capability-matrix",
        title="Real-source and format capability matrix",
        scope=(
            "Strict inventory of checked-in and public EEG sources, including at "
            "least PhysioNet, BBCI/Graz, SCCN, MNE and BIDS families across GDF, "
            "EDF, SET, CNT, BrainVision, FIF and BIDS entry points."
        ),
        execution_id="dataset-validation-matrix",
        artifact_policy=_artifact(
            "Parseable strict dataset matrix JSON captured from stdout.",
            "dataset-validation-matrix.json",
        ),
        validator=ValidatorSpec(
            kind="json_object",
            artifact_path="dataset-validation-matrix.json",
            key="strict-dataset-matrix",
        ),
        evidence_key="dataset-validation-matrix.strict",
        pass_criteria=(
            "The canonical --strict matrix command exits zero.",
            "Its JSON artifact exists and is an object.",
        ),
        claim_boundary=(
            "Fixed fixture/source coverage only; not arbitrary clinical format or "
            "full BIDS compliance."
        ),
        coverage_tags=("data-import", "real-source-3plus", "multi-format-import"),
    ),
    _scenario(
        scenario_id="data.interpretation-label-lifecycle",
        title="Interpretation and label lifecycle matrix",
        scope=(
            "Scan, preview, validate and apply real source workflows with external "
            "labels, internal events, reviewed classes and format boundaries."
        ),
        execution_id="data-interpretation-matrix",
        artifact_policy=_artifact(
            "Strict Data Interpretation JSON and Markdown matrix artifacts.",
            "data-interpretation/data-interpretation-format-matrix.json",
            "data-interpretation/data-interpretation-format-matrix.md",
        ),
        validator=ValidatorSpec(
            kind="json_truthy",
            artifact_path="data-interpretation/data-interpretation-format-matrix.json",
            key="strict-validation",
            json_path=("strict_validation", "ok"),
        ),
        evidence_key="data-interpretation.strict-validation",
        pass_criteria=(
            "Every required real workflow and capability contract passes.",
            "The artifact records strict_validation.ok=true.",
        ),
        claim_boundary=(
            "Format and label/event interpretation evidence; not scientific class "
            "validity for unreviewed data."
        ),
        coverage_tags=(
            "data-import",
            "real-source-3plus",
            "multi-format-import",
            "label",
        ),
    ),
    _scenario(
        scenario_id="data.real-source-interpretation-training",
        title="Three-source interpretation-to-training spine",
        scope=(
            "Required Graz external-label, PhysioNet internal-event and public BIDS "
            "workflows from Data Interpretation through epoch, dataset and training."
        ),
        execution_id="real-data-interpretation-training",
        artifact_policy=_artifact(
            "Strict pytest completion attestation for the combined real-data gate.",
            "pytest-attestations/real-data-interpretation-training.json",
        ),
        validator=ValidatorSpec(
            kind="pytest_attestation",
            artifact_path=(
                "pytest-attestations/real-data-interpretation-training.json"
            ),
            key="real-data-combined-gate",
        ),
        evidence_key="real-data.interpretation-training.combined",
        pass_criteria=(
            "The canonical combined real-data test gate completes normally.",
            "No required case is skipped, xfailed, failed or deselected.",
        ),
        claim_boundary=(
            "The combined gate is one scenario success, not three independent "
            "successes and not a statistical sample."
        ),
        coverage_tags=(
            "data-import",
            "real-source-3plus",
            "label",
            "epoch",
            "training",
        ),
    ),
    _scenario(
        scenario_id="data.cross-source-training-persistence",
        title="Cross-source training and persistence",
        scope=(
            "Class-grounded PhysioNet EDF and BBCI GDF training plus SCCN SET and "
            "MNE CNT import/preprocess-only boundary cases where supervised epoch "
            "is intentionally blocked, with safe artifact reload for training cases."
        ),
        execution_id="public-cross-source-training",
        artifact_policy=_artifact(
            "Strict public cross-source smoke JSON captured from stdout.",
            "public-cross-source-training-smoke.json",
        ),
        validator=ValidatorSpec(
            kind="json_truthy",
            artifact_path="public-cross-source-training-smoke.json",
            key="all-required-cross-source-cases",
            json_path=("summary", "all_required_passed"),
        ),
        evidence_key="cross-source-training.all-required",
        pass_criteria=(
            "All four fixed required source cases pass their declared protocols.",
            "Training cases persist and safely reload their artifacts.",
        ),
        claim_boundary=(
            "Only fixtures with protocol-grounded classes count as training "
            "evidence; import/preprocess-only fixtures are not relabeled as "
            "supervised data."
        ),
        coverage_tags=("real-source-3plus", "epoch", "training", "evaluation"),
    ),
    _scenario(
        scenario_id="workflow.application-command-spine",
        title="ApplicationService command spine",
        scope=(
            "Real FIF import through preprocess, labels, epochs, split, persisted "
            "training, held-out evaluation and visualization readiness."
        ),
        execution_id="command-spine",
        artifact_policy=_artifact(
            "Strict pytest completion attestation for command-spine and oracle tests.",
            "pytest-attestations/command-spine.json",
        ),
        validator=ValidatorSpec(
            kind="pytest_attestation",
            artifact_path="pytest-attestations/command-spine.json",
            key="command-spine-combined-gate",
        ),
        evidence_key="application-service.command-spine",
        pass_criteria=(
            "The real ApplicationService workflow and deterministic oracle pass.",
            "The completion attestation reports positive passed tests and no forbidden outcomes.",
        ),
        claim_boundary=(
            "Representative command-spine correctness, not scientific model quality "
            "or every UI panel workflow."
        ),
        coverage_tags=(
            "data-import",
            "label",
            "epoch",
            "training",
            "evaluation",
            "visualization",
        ),
    ),
    _scenario(
        scenario_id="workflow.data-import-wizard",
        title="Visible Data Import wizard workflow",
        scope=(
            "Canonical Data Import wizard steps, label placement modes, blocked and "
            "review-required states in a bounded xcb capture."
        ),
        execution_id="data-import-wizard-capture",
        artifact_policy=_artifact(
            "Source-bound wizard manifest and screenshots requiring artifact review.",
            "ui/data-import-wizard-steps/data-import-wizard-steps-evidence.json",
            human_review_required=True,
        ),
        validator=ValidatorSpec(
            kind="json_truthy",
            artifact_path=(
                "ui/data-import-wizard-steps/data-import-wizard-steps-evidence.json"
            ),
            key="complete-wizard-capture",
            json_path=("capture_scope", "complete"),
        ),
        evidence_key="data-import-wizard.complete-capture",
        pass_criteria=(
            "The source-bound capture command validates before publishing.",
            "The manifest declares a complete capture scope.",
        ),
        claim_boundary=(
            "Automated Linux xcb evidence; requires human artifact review and does "
            "not replace Windows interaction acceptance."
        ),
        coverage_tags=("data-import", "label", "full"),
    ),
    _scenario(
        scenario_id="workflow.visualization-render",
        title="Evaluation visualization render",
        scope=(
            "Evaluation and saliency render surfaces backed by a bounded training "
            "output and source-bound walkthrough artifact."
        ),
        execution_id="visualization-render",
        artifact_policy=_artifact(
            "Visualization JSON/Markdown and screenshots requiring artifact review.",
            "ui/visualization-render/visualization-render-walkthrough.json",
            human_review_required=True,
        ),
        validator=ValidatorSpec(
            kind="json_equals",
            artifact_path=(
                "ui/visualization-render/visualization-render-walkthrough.json"
            ),
            key="visualization-status",
            json_path=("status",),
            expected="passed",
        ),
        evidence_key="visualization-render.status",
        pass_criteria=(
            "The render walkthrough exits zero and records status=passed.",
            "Required render artifacts exist for human review.",
        ),
        claim_boundary=(
            "Offscreen render evidence; not interactive 3D, scientific saliency "
            "validity or Windows GPU acceptance."
        ),
        coverage_tags=("evaluation", "visualization", "full"),
    ),
    _scenario(
        scenario_id="ui.human-like-full",
        title="Human-like full product walkthrough",
        scope=(
            "Full product shell workflow with Assistant states and user-visible "
            "pipeline transitions, captured from real widgets."
        ),
        execution_id="human-like-product",
        artifact_policy=_artifact(
            "Human-like walkthrough JSON/Markdown and screenshots requiring review.",
            "ui/human-like-product/human-like-walkthrough.json",
            human_review_required=True,
        ),
        validator=ValidatorSpec(
            kind="json_equals",
            artifact_path="ui/human-like-product/human-like-walkthrough.json",
            key="human-like-status",
            json_path=("status",),
            expected="passed",
        ),
        evidence_key="human-like-product.full-window",
        pass_criteria=(
            "The source-bound walkthrough records status=passed.",
            "Full-window screenshots remain available for main-agent review.",
        ),
        claim_boundary=(
            "Automated Linux walkthrough, not human usability or Windows native acceptance."
        ),
        coverage_tags=("full", "workflow", "agent-success", "agent-blocked"),
    ),
    _scenario(
        scenario_id="ui.dataset-narrow",
        title="Narrow dataset workflow",
        scope=(
            "Dataset panel and state-truth presentation at constrained width, "
            "including readable loaded and dataset-ready states."
        ),
        execution_id="dataset-narrow",
        artifact_policy=_artifact(
            "Narrow dataset evidence JSON and screenshots requiring review.",
            "ui/dataset-narrow/dataset-narrow-evidence.json",
            human_review_required=True,
        ),
        validator=ValidatorSpec(
            kind="json_truthy",
            artifact_path="ui/dataset-narrow/dataset-narrow-evidence.json",
            key="dataset-narrow-passed",
            json_path=("passed",),
        ),
        evidence_key="dataset-narrow.layout-and-state",
        pass_criteria=(
            "Every narrow scenario reports passed=true.",
            "Captured tables and state labels remain readable and consistent.",
        ),
        claim_boundary=(
            "One automated narrow-width contract, not all monitor geometries or font settings."
        ),
        coverage_tags=("narrow", "workflow"),
    ),
)


def _agent_scenario(
    *,
    scenario_id: str,
    title: str,
    case_id: str,
    scope: str,
    tags: tuple[str, ...],
    boundary: str,
) -> ScenarioSpec:
    return _scenario(
        scenario_id=scenario_id,
        title=title,
        scope=scope,
        execution_id="agent-showcase-selected",
        artifact_policy=_artifact(
            f"One unique {case_id} row in the source-bound showcase report.",
            "agent-toolcall-showcase/selected.json",
        ),
        validator=ValidatorSpec(
            kind="agent_showcase_case",
            artifact_path="agent-toolcall-showcase/selected.json",
            key=case_id,
        ),
        evidence_key=f"agent-case:{case_id}",
        pass_criteria=(
            f"The report contains exactly one passing {case_id} case.",
            "The case has a terminal outcome validated by the showcase contract.",
        ),
        claim_boundary=boundary,
        coverage_tags=tags,
    )


_SCENARIOS += (
    _agent_scenario(
        scenario_id="agent.import-success",
        title="Agent import success",
        case_id="import.scan_source",
        scope="Successful scan_source selection, verification and structured result.",
        tags=("agent", "agent-success", "data-import"),
        boundary="Deterministic selector product diagnostic, not raw-model accuracy.",
    ),
    _agent_scenario(
        scenario_id="agent.precondition-blocked",
        title="Agent precondition block",
        case_id="blocked.preprocess_without_data",
        scope="Preprocessing request is blocked before data import with a typed reason.",
        tags=("agent", "agent-blocked"),
        boundary="One wrong-stage contract, not exhaustive negative-case coverage.",
    ),
    _agent_scenario(
        scenario_id="agent.confirmation-approved",
        title="Agent confirmation approval",
        case_id="settings.model_approved",
        scope="A model-setting change requires and receives explicit approval.",
        tags=("agent", "agent-success", "agent-confirmation"),
        boundary="Host-assisted confirmation contract, not autonomous model consent judgment.",
    ),
    _agent_scenario(
        scenario_id="agent.confirmation-cancelled",
        title="Agent confirmation cancellation",
        case_id="navigation.reset_cancelled",
        scope="A destructive session reset is cancelled without applying the command.",
        tags=("agent", "agent-confirmation"),
        boundary="One cancellation path, not every destructive command or UI gesture.",
    ),
    _agent_scenario(
        scenario_id="agent.import-ui-handoff",
        title="Agent import review handoff",
        case_id="import.apply_review_handoff",
        scope="Unresolved import review yields a structured UI handoff instead of bypassing review.",
        tags=("agent", "agent-blocked", "data-import", "label"),
        boundary="Handoff contract evidence, not proof a human completed the review.",
    ),
    _agent_scenario(
        scenario_id="agent.stale-revision-recovery",
        title="Agent stale revision rejection",
        case_id="safety.stale_revision",
        scope="A stale workflow revision is rejected at the execution boundary.",
        tags=("agent", "agent-blocked", "agent-recovery"),
        boundary="One stale-publication race contract, not all concurrent state races.",
    ),
    _agent_scenario(
        scenario_id="agent.runtime-error-retry",
        title="Agent runtime recovery retry",
        case_id="recovery.runtime_error_retry",
        scope="A recoverable runtime failure follows the exact retry sequence to success.",
        tags=("agent", "agent-success", "agent-recovery"),
        boundary="Injected recoverable failure path, not long-session runtime reliability.",
    ),
    _agent_scenario(
        scenario_id="agent.evaluation-before-training-blocked",
        title="Agent evaluation block",
        case_id="analysis.evaluate_before_run",
        scope="Evaluation before a completed training run is blocked with a typed precondition.",
        tags=("agent", "agent-blocked", "evaluation"),
        boundary="Readiness policy contract, not evidence of evaluation metric correctness.",
    ),
)


def _dpi_scenario(scale: float) -> ScenarioSpec:
    percent = round(scale * 100)
    return _scenario(
        scenario_id=f"ui.dpi-{percent}",
        title=f"Full and narrow UI at {percent}% DPI",
        scope=(
            f"Qt {percent}% scale record with full-window dock, narrow crops and "
            "message/error/confirmation content at bounded widths."
        ),
        execution_id="chatpanel-dpi",
        artifact_policy=_artifact(
            f"Unique scale={scale:g} record and screenshots in the DPI manifest.",
            "ui/chatpanel-dpi/dpi-gate.json",
            human_review_required=True,
        ),
        validator=ValidatorSpec(
            kind="dpi_scale",
            artifact_path="ui/chatpanel-dpi/dpi-gate.json",
            key=f"scale-{percent}",
            expected=scale,
        ),
        evidence_key=f"chatpanel-dpi.scale-{scale:g}",
        pass_criteria=(
            f"Exactly one passing scale={scale:g} record exists.",
            "The record contains full-window, narrow and DPI-content evidence.",
        ),
        claim_boundary=(
            "Linux Qt scale evidence only; not Windows native DPI, multi-monitor, "
            "remote desktop or human acceptance."
        ),
        coverage_tags=("full", "narrow", f"dpi-{percent}"),
    )


_SCENARIOS += tuple(_dpi_scenario(scale) for scale in (1.0, 1.25, 1.5))
PRODUCT_SCENARIOS: Final = MappingProxyType(
    {item.scenario_id: item for item in _SCENARIOS}
)

_IMMEDIATE_IDS = tuple(item.scenario_id for item in _SCENARIOS)
_IMMEDIATE_CLAIM_BOUNDARY = (
    "This immediate 20-scenario product checkpoint is a fixed engineering gate. "
    "It does not establish statistical bug risk <5%, product completion, Windows "
    "native acceptance, or any MOABB dataset campaign result. The 20 product "
    "scenarios must not be extrapolated to a MOABB dataset denominator."
)
_PROFILES = (
    ProfileSpec(
        profile_id=IMMEDIATE_PROFILE_ID,
        scenario_ids=_IMMEDIATE_IDS,
        expected_scenario_count=20,
        purpose=(
            "Execute the current handoff checkpoint's 20 high-difference product scenarios."
        ),
        claim_boundary=_IMMEDIATE_CLAIM_BOUNDARY,
    ),
)
PRODUCT_SCENARIO_PROFILES: Final = MappingProxyType(
    {item.profile_id: item for item in _PROFILES}
)


def _validate_artifact_path(path_value: str, *, owner: str) -> None:
    path = PurePosixPath(path_value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ScenarioManifestError(f"{owner} has unsafe artifact path {path_value!r}.")


def validate_manifest(
    *,
    scenarios: Mapping[str, ScenarioSpec] = PRODUCT_SCENARIOS,
    executions: Mapping[str, ExecutionSpec] = PRODUCT_SCENARIO_EXECUTIONS,
    profiles: Mapping[str, ProfileSpec] = PRODUCT_SCENARIO_PROFILES,
) -> None:
    """Validate identity, coverage references and evidence-counting invariants."""
    if not scenarios or not executions or not profiles:
        raise ScenarioManifestError("Scenario manifest registries must be non-empty.")
    for execution_id, execution in executions.items():
        if execution_id != execution.execution_id or not _SAFE_ID.fullmatch(
            execution_id
        ):
            raise ScenarioManifestError(
                f"Invalid execution identity: {execution_id!r}."
            )
        if execution.timeout_seconds <= 0 or not execution.command_template():
            raise ScenarioManifestError(f"Execution {execution_id!r} is not bounded.")
        if execution.gate_id is not None:
            gate = HANDOFF_GATE_SPECS.get(execution.gate_id)
            if gate is None:
                raise ScenarioManifestError(
                    f"Execution {execution_id!r} references an unknown handoff gate."
                )
            if execution.timeout_seconds != gate.timeout_seconds:
                raise ScenarioManifestError(
                    f"Execution {execution_id!r} timeout drifted from its handoff gate."
                )
        if execution.native and execution.command_template()[:3] != (
            "prlimit",
            "--core=0",
            "--",
        ):
            raise ScenarioManifestError(
                f"Native execution {execution_id!r} must disable core dumps."
            )
        for path in execution.artifacts():
            _validate_artifact_path(path, owner=execution_id)
        unknown_dependencies = set(execution.depends_on_execution_ids).difference(
            executions
        )
        if unknown_dependencies or execution_id in execution.depends_on_execution_ids:
            raise ScenarioManifestError(
                f"Execution {execution_id!r} has invalid dependencies: "
                f"{sorted(unknown_dependencies)}."
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(execution_id: str) -> None:
        if execution_id in visiting:
            raise ScenarioManifestError(
                "Scenario execution dependencies contain a cycle."
            )
        if execution_id in visited:
            return
        visiting.add(execution_id)
        for dependency_id in executions[execution_id].depends_on_execution_ids:
            visit(dependency_id)
        visiting.remove(execution_id)
        visited.add(execution_id)

    for execution_id in executions:
        visit(execution_id)
    evidence_owners: dict[tuple[str, str], str] = {}
    for scenario_id, scenario in scenarios.items():
        if scenario_id != scenario.scenario_id or not _SAFE_ID.fullmatch(scenario_id):
            raise ScenarioManifestError(f"Invalid scenario identity: {scenario_id!r}.")
        execution = executions.get(scenario.execution_id)
        if execution is None:
            raise ScenarioManifestError(
                f"Scenario {scenario_id!r} references an unknown execution."
            )
        if scenario.timeout_seconds != execution.timeout_seconds:
            raise ScenarioManifestError(
                f"Scenario {scenario_id!r} timeout drifted from its execution."
            )
        if not scenario.scope.strip() or not scenario.pass_criteria:
            raise ScenarioManifestError(
                f"Scenario {scenario_id!r} lacks scope or pass criteria."
            )
        if not scenario.claim_boundary.strip() or not scenario.coverage_tags:
            raise ScenarioManifestError(
                f"Scenario {scenario_id!r} lacks claim boundary or coverage tags."
            )
        owner_key = (scenario.execution_id, scenario.evidence_key)
        prior = evidence_owners.setdefault(owner_key, scenario_id)
        if prior != scenario_id:
            raise ScenarioManifestError(
                f"Scenario {scenario_id!r} reuses evidence already counted by {prior!r}."
            )
        for path in scenario.artifact_policy.required_paths:
            _validate_artifact_path(path, owner=scenario_id)
        if scenario.validator.artifact_path is not None:
            _validate_artifact_path(
                scenario.validator.artifact_path,
                owner=scenario_id,
            )
        if scenario.validator.kind == "agent_showcase_case":
            catalog_ids = {case.case_id for case in SHOWCASE_CASES}
            if scenario.validator.key not in catalog_ids:
                raise ScenarioManifestError(
                    f"Scenario {scenario_id!r} references an unknown showcase case."
                )
    for profile_id, profile in profiles.items():
        if profile_id != profile.profile_id or not _SAFE_ID.fullmatch(profile_id):
            raise ScenarioManifestError(f"Invalid profile identity: {profile_id!r}.")
        if len(profile.scenario_ids) != len(set(profile.scenario_ids)):
            raise ScenarioManifestError(f"Profile {profile_id!r} repeats scenarios.")
        if len(profile.scenario_ids) != profile.expected_scenario_count:
            raise ScenarioManifestError(
                f"Profile {profile_id!r} expected scenario count does not match its IDs."
            )
        unknown = set(profile.scenario_ids).difference(scenarios)
        if unknown:
            raise ScenarioManifestError(
                f"Profile {profile_id!r} references unknown scenarios: {sorted(unknown)}."
            )
        if not profile.purpose.strip() or not profile.claim_boundary.strip():
            raise ScenarioManifestError(
                f"Profile {profile_id!r} lacks purpose or claim boundary."
            )
        if (
            profile.denominator_kind != "product_scenarios"
            or profile.moabb_dataset_campaign_in_scope
        ):
            raise ScenarioManifestError(
                f"Profile {profile_id!r} conflates product scenarios with MOABB datasets."
            )


validate_manifest()
