"""Pure change-to-validation planning primitives.

This module deliberately knows semantic validation rule IDs, not how a gate is
executed.  The executable gate registry remains the single source of truth and
is supplied by the caller through ``gate_catalog``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum, IntEnum
from pathlib import PurePosixPath
from typing import Any, Protocol


class ChangeIntent(str, Enum):
    """Why a change is being made."""

    FEATURE = "feature"
    BUG_FIX = "bug-fix"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DOCS = "docs"
    TESTS = "tests"
    CI = "ci"


class ClaimLevel(str, Enum):
    """The delivery claim the resulting evidence must support."""

    CHECKPOINT = "checkpoint"
    BOUNDED_COMPLETE = "bounded-complete"
    PRODUCT_PR = "product-pr"
    HANDOFF = "handoff"
    RELEASE = "release"
    THESIS = "thesis"


class Layer(str, Enum):
    """Semantic product layers that can be affected by a change."""

    UNKNOWN = "unknown"
    GUIDANCE_DOCS = "guidance-docs"
    TEST_INFRASTRUCTURE = "test-infrastructure"
    CI_VALIDATION = "ci-validation"
    DEPENDENCY = "dependency"
    UI_PRESENTATION = "ui-presentation"
    UI_BEHAVIOR = "ui-behavior"
    APPLICATION_SERVICE = "application-service"
    BACKEND_DOMAIN = "backend-domain"
    PERSISTENCE = "persistence"
    DATA_SEMANTICS = "data-semantics"
    MODEL_RUNTIME = "model-runtime"
    ASSISTANT = "assistant"
    NATIVE_LIFECYCLE = "native-lifecycle"
    PLATFORM_PACKAGING = "platform-packaging"
    SECURITY_PRIVACY = "security-privacy"


class RiskLevel(IntEnum):
    """Monotonic validation risk floor."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class VerdictStatus(str, Enum):
    """Machine verdict for one plan/receipt pair."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class GateCatalogEntry(Protocol):
    """Minimal external gate metadata consumed by the planner."""

    tags: Iterable[str]
    dependencies: Iterable[str]
    expensive: bool


@dataclass(frozen=True, slots=True)
class ChangeDescriptor:
    """Agent-declared change semantics, which may only increase inferred scope."""

    intent: ChangeIntent
    claim_level: ClaimLevel = ClaimLevel.CHECKPOINT
    declared_layers: frozenset[Layer] = field(default_factory=frozenset)
    declared_risk: RiskLevel = RiskLevel.LOW
    required_rule_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "declared_layers", frozenset(self.declared_layers))
        object.__setattr__(
            self,
            "required_rule_ids",
            frozenset(_clean_identifiers(self.required_rule_ids, "required rule")),
        )

    def to_json(self) -> str:
        return _stable_json(_descriptor_payload(self))

    @classmethod
    def from_json(cls, value: str) -> ChangeDescriptor:
        payload = _load_json_object(value)
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported ChangeDescriptor schema version")
        return _descriptor_from_payload(payload)

    def digest(self) -> str:
        return _digest(self.to_json())


@dataclass(frozen=True, slots=True)
class ChangedPath:
    """Canonical path inference result, optionally augmented by an agent."""

    path: str
    layers: frozenset[Layer]
    risk_floor: RiskLevel
    matched_rule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _canonical_path(self.path))
        object.__setattr__(self, "layers", frozenset(self.layers))
        object.__setattr__(
            self,
            "matched_rule_ids",
            _clean_identifiers(self.matched_rule_ids, "matched rule"),
        )


@dataclass(frozen=True, slots=True)
class PlannedExecution:
    """One catalog gate in dependency-first execution order."""

    gate_id: str
    dependencies: tuple[str, ...] = ()
    satisfies_rules: tuple[str, ...] = ()
    expensive: bool = False

    def __post_init__(self) -> None:
        gate_id = self.gate_id.strip()
        if not gate_id:
            raise ValueError("gate ID must not be empty")
        object.__setattr__(self, "gate_id", gate_id)
        object.__setattr__(
            self,
            "dependencies",
            _clean_identifiers(self.dependencies, "gate dependency"),
        )
        object.__setattr__(
            self,
            "satisfies_rules",
            _clean_identifiers(self.satisfies_rules, "satisfied rule"),
        )


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    """Deterministic, immutable output of validation selection."""

    descriptor: ChangeDescriptor
    changed_paths: tuple[ChangedPath, ...]
    layers: frozenset[Layer]
    risk_level: RiskLevel
    required_rule_ids: tuple[str, ...]
    applied_rule_ids: tuple[str, ...]
    executions: tuple[PlannedExecution, ...]
    unresolved_rule_ids: tuple[str, ...] = ()
    unknown_paths: tuple[str, ...] = ()
    source_sha: str | None = None
    base_sha: str | None = None
    change_set_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "changed_paths",
            tuple(sorted(self.changed_paths, key=lambda changed: changed.path)),
        )
        object.__setattr__(self, "layers", frozenset(self.layers))
        for attribute in (
            "required_rule_ids",
            "applied_rule_ids",
            "unresolved_rule_ids",
            "unknown_paths",
        ):
            object.__setattr__(
                self,
                attribute,
                _clean_identifiers(getattr(self, attribute), attribute),
            )
        object.__setattr__(self, "executions", tuple(self.executions))
        lineage = (self.source_sha, self.base_sha, self.change_set_digest)
        if any(value is not None for value in lineage):
            if not all(value is not None for value in lineage):
                raise ValueError("plan source lineage must be complete or absent")
            if not _GIT_SHA.fullmatch(str(self.source_sha)):
                raise ValueError("plan source SHA must be a lowercase Git hash")
            if not _GIT_SHA.fullmatch(str(self.base_sha)):
                raise ValueError("plan base SHA must be a lowercase Git hash")
            if not _SHA256.fullmatch(str(self.change_set_digest)):
                raise ValueError("plan change-set digest must be lowercase SHA-256")
            if self.change_set_digest != _changed_paths_digest(self.changed_paths):
                raise ValueError("plan change-set digest does not match changed paths")

    @property
    def ready(self) -> bool:
        return (
            bool(self.changed_paths)
            and not self.unresolved_rule_ids
            and not self.unknown_paths
        )

    @property
    def execution_ids(self) -> tuple[str, ...]:
        return tuple(execution.gate_id for execution in self.executions)

    def to_json(self) -> str:
        return _stable_json(_plan_payload(self))

    @classmethod
    def from_json(cls, value: str) -> ValidationPlan:
        payload = _load_json_object(value)
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported ValidationPlan schema version")
        return _plan_from_payload(payload)

    def digest(self) -> str:
        return _digest(self.to_json())


def bind_validation_plan(
    plan: ValidationPlan,
    *,
    source_sha: str,
    base_sha: str,
) -> ValidationPlan:
    """Bind a pure semantic plan to one exact Git source and comparison base."""

    return replace(
        plan,
        source_sha=source_sha,
        base_sha=base_sha,
        change_set_digest=_changed_paths_digest(plan.changed_paths),
    )


@dataclass(frozen=True, slots=True)
class ValidationReceipt:
    """Stable reference to the evidence produced for a validation plan."""

    plan_digest: str
    source_sha: str
    completed_gate_ids: tuple[str, ...]
    failed_gate_ids: tuple[str, ...] = ()
    evidence_digests: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        plan_digest = _nonempty(self.plan_digest, "plan digest")
        source_sha = _nonempty(self.source_sha, "source SHA")
        if not _SHA256.fullmatch(plan_digest):
            raise ValueError("plan digest must be a lowercase SHA-256 digest")
        if not _GIT_SHA.fullmatch(source_sha):
            raise ValueError("source SHA must be a lowercase 40- or 64-digit hash")
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(self, "source_sha", source_sha)
        object.__setattr__(
            self,
            "completed_gate_ids",
            _clean_ordered_identifiers(
                self.completed_gate_ids,
                "completed gate",
            ),
        )
        object.__setattr__(
            self,
            "failed_gate_ids",
            _clean_ordered_identifiers(
                self.failed_gate_ids,
                "failed gate",
            ),
        )
        failed = set(self.failed_gate_ids)
        completed = set(self.completed_gate_ids)
        if not failed <= completed:
            raise ValueError("failed gates must also be completed gate IDs")
        evidence_by_gate: dict[str, str] = {}
        for gate_id, digest in self.evidence_digests:
            clean_gate_id = _nonempty(gate_id, "evidence gate ID")
            clean_digest = _nonempty(digest, "evidence digest")
            if not _SHA256.fullmatch(clean_digest):
                raise ValueError("evidence digest must be a lowercase SHA-256 digest")
            if clean_gate_id in evidence_by_gate:
                raise ValueError(f"gate {clean_gate_id!r} repeats evidence")
            evidence_by_gate[clean_gate_id] = clean_digest
        if not set(evidence_by_gate) <= completed:
            raise ValueError("evidence gates must also be completed gate IDs")
        evidence = tuple(sorted(evidence_by_gate.items()))
        object.__setattr__(self, "evidence_digests", evidence)

    def to_json(self) -> str:
        return _stable_json(
            {
                "schema_version": 1,
                "plan_digest": self.plan_digest,
                "source_sha": self.source_sha,
                "completed_gate_ids": list(self.completed_gate_ids),
                "failed_gate_ids": list(self.failed_gate_ids),
                "evidence_digests": [list(item) for item in self.evidence_digests],
            }
        )

    @classmethod
    def from_json(cls, value: str) -> ValidationReceipt:
        payload = _load_json_object(value)
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported ValidationReceipt schema version")
        return cls(
            plan_digest=str(payload["plan_digest"]),
            source_sha=str(payload["source_sha"]),
            completed_gate_ids=tuple(map(str, payload["completed_gate_ids"])),
            failed_gate_ids=tuple(map(str, payload["failed_gate_ids"])),
            evidence_digests=tuple(
                (str(item[0]), str(item[1])) for item in payload["evidence_digests"]
            ),
        )

    def digest(self) -> str:
        return _digest(self.to_json())


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    """Fail-closed result derived from an immutable plan and receipt."""

    status: VerdictStatus
    claim_level: ClaimLevel
    plan_digest: str
    source_sha: str
    missing_gate_ids: tuple[str, ...] = ()
    failed_gate_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for attribute in ("missing_gate_ids", "failed_gate_ids", "reasons"):
            object.__setattr__(
                self,
                attribute,
                _clean_identifiers(getattr(self, attribute), attribute),
            )

    def to_json(self) -> str:
        return _stable_json(
            {
                "schema_version": 1,
                "status": self.status.value,
                "claim_level": self.claim_level.value,
                "plan_digest": self.plan_digest,
                "source_sha": self.source_sha,
                "missing_gate_ids": list(self.missing_gate_ids),
                "failed_gate_ids": list(self.failed_gate_ids),
                "reasons": list(self.reasons),
            }
        )


def evaluate_validation_receipt(
    plan: ValidationPlan,
    receipt: ValidationReceipt,
) -> ClaimVerdict:
    """Derive the only claim verdict; incomplete evidence never passes."""

    expected = set(plan.execution_ids)
    completed = set(receipt.completed_gate_ids)
    evidence = {gate_id for gate_id, _digest_value in receipt.evidence_digests}
    missing = tuple(expected.difference(completed))
    extra = tuple(completed.difference(expected))
    missing_evidence = tuple(completed.difference(evidence))
    reasons: set[str] = set()
    if not plan.ready:
        reasons.add("plan-not-ready")
    if receipt.plan_digest != plan.digest():
        reasons.add("plan-digest-mismatch")
    if plan.source_sha is not None and receipt.source_sha != plan.source_sha:
        reasons.add("source-sha-mismatch")
    if missing:
        reasons.add("missing-selected-gates")
    if extra:
        reasons.add("unselected-gates-in-receipt")
    if missing_evidence:
        reasons.add("missing-gate-evidence")

    failed = tuple(receipt.failed_gate_ids)
    if failed:
        status = VerdictStatus.FAILED
        reasons.add("gate-failure")
    elif reasons:
        status = VerdictStatus.BLOCKED
    else:
        status = VerdictStatus.PASSED
    return ClaimVerdict(
        status=status,
        claim_level=plan.descriptor.claim_level,
        plan_digest=plan.digest(),
        source_sha=receipt.source_sha,
        missing_gate_ids=missing,
        failed_gate_ids=failed,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class _CatalogGate:
    gate_id: str
    tags: frozenset[str]
    dependencies: tuple[str, ...]
    expensive: bool


_CLAIM_RANK = {
    ClaimLevel.CHECKPOINT: 0,
    ClaimLevel.BOUNDED_COMPLETE: 1,
    ClaimLevel.PRODUCT_PR: 2,
    ClaimLevel.HANDOFF: 3,
    ClaimLevel.RELEASE: 4,
    ClaimLevel.THESIS: 5,
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

_DOC_LAYERS = frozenset({Layer.GUIDANCE_DOCS})
_PATH_SELECTION_RULES = {
    "path:performance-resource": "performance-resource",
}

_INTENT_RULES: Mapping[ChangeIntent, frozenset[str]] = {
    ChangeIntent.FEATURE: frozenset(),
    ChangeIntent.BUG_FIX: frozenset(),
    ChangeIntent.REFACTOR: frozenset(),
    ChangeIntent.PERFORMANCE: frozenset({"performance-resource"}),
    ChangeIntent.SECURITY: frozenset({"security-privacy"}),
    ChangeIntent.DOCS: frozenset({"docs"}),
    ChangeIntent.TESTS: frozenset({"test-infrastructure"}),
    ChangeIntent.CI: frozenset({"ci-validation"}),
}

_INTENT_RISK_FLOORS: Mapping[ChangeIntent, RiskLevel] = {
    ChangeIntent.FEATURE: RiskLevel.MEDIUM,
    ChangeIntent.BUG_FIX: RiskLevel.MEDIUM,
    ChangeIntent.REFACTOR: RiskLevel.MEDIUM,
    ChangeIntent.PERFORMANCE: RiskLevel.HIGH,
    ChangeIntent.SECURITY: RiskLevel.CRITICAL,
    ChangeIntent.DOCS: RiskLevel.LOW,
    ChangeIntent.TESTS: RiskLevel.HIGH,
    ChangeIntent.CI: RiskLevel.CRITICAL,
}

_LAYER_RULES: Mapping[Layer, frozenset[str]] = {
    Layer.UNKNOWN: frozenset({"unknown-change"}),
    Layer.GUIDANCE_DOCS: frozenset({"docs", "guidance-contract"}),
    Layer.TEST_INFRASTRUCTURE: frozenset({"test-infrastructure"}),
    Layer.CI_VALIDATION: frozenset({"ci-validation"}),
    Layer.DEPENDENCY: frozenset({"dependency-change"}),
    Layer.UI_PRESENTATION: frozenset({"ui-visible"}),
    Layer.UI_BEHAVIOR: frozenset(),
    Layer.APPLICATION_SERVICE: frozenset({"application-service"}),
    Layer.BACKEND_DOMAIN: frozenset({"backend"}),
    Layer.PERSISTENCE: frozenset({"persistence"}),
    Layer.DATA_SEMANTICS: frozenset({"data-semantics", "data-diversity"}),
    # Product-PR automation exercises the assistant/runtime contract without
    # pretending an ephemeral CI runner owns the offline exact-model cache.
    # Exact Granite and RAG runtime evidence enter through the complete
    # handoff inventory (or an explicit caller-required rule).
    Layer.MODEL_RUNTIME: frozenset({"assistant"}),
    Layer.ASSISTANT: frozenset({"assistant"}),
    Layer.NATIVE_LIFECYCLE: frozenset({"native-lifecycle"}),
    Layer.PLATFORM_PACKAGING: frozenset({"platform-packaging"}),
    Layer.SECURITY_PRIVACY: frozenset({"security-privacy"}),
}


def infer_changed_path(path: str) -> ChangedPath:
    """Infer all matching layers and the highest mandatory risk floor."""

    canonical = _canonical_path(path)
    lowered = canonical.casefold()
    basename = PurePosixPath(lowered).name
    layers: set[Layer] = set()
    rules: set[str] = set()
    floor = RiskLevel.LOW

    def match(layer: Layer, risk: RiskLevel, rule_id: str) -> None:
        nonlocal floor
        layers.add(layer)
        rules.add(rule_id)
        floor = max(floor, risk)

    is_docs = (
        lowered.startswith(("docs/", "user_docs/", ".agents/"))
        or (lowered.startswith(".github/") and basename.endswith(".md"))
        or basename in {"agents.md", "readme.md", "contributing.md"}
        or basename.startswith("mkdocs")
    )
    if is_docs:
        match(Layer.GUIDANCE_DOCS, RiskLevel.LOW, "path:docs")

    if lowered.startswith("tests/"):
        match(Layer.TEST_INFRASTRUCTURE, RiskLevel.HIGH, "path:tests")
    if lowered.startswith("tests/fixtures/") or "/fixtures/" in lowered:
        match(Layer.DATA_SEMANTICS, RiskLevel.CRITICAL, "path:fixtures")

    selector_or_registry = any(
        marker in lowered
        for marker in (
            "handoff_gate_spec",
            "validation_control_plane",
            "validation_ci_evidence",
            "validation_ci_plan",
            "validation_pr_declaration",
            "run_validation_ci_owner",
            "ci_gate_ownership",
            "ci_test_command_catalog",
            "gate_registry",
            "gate_catalog",
            "select_validation_gate",
            "validation_registry",
            "validation_selector",
        )
    )
    if (
        lowered.startswith((".github/workflows/", "scripts/ci/"))
        or selector_or_registry
    ):
        match(Layer.CI_VALIDATION, RiskLevel.CRITICAL, "path:validation-control")

    dependency_files = {
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "environment.yml",
        "dockerfile",
    }
    if basename in dependency_files or lowered.startswith(".github/dependabot"):
        match(Layer.DEPENDENCY, RiskLevel.CRITICAL, "path:dependency")

    if lowered.startswith("xbrainlab/ui/"):
        match(Layer.UI_BEHAVIOR, RiskLevel.MEDIUM, "path:ui-behavior")
        wiring_only_markers = (
            "/controllers/",
            "/core/",
            "/services/",
            "/adapters/",
            "/state/",
        )
        visible_markers = (
            "/components/",
            "/dialogs/",
            "/panels/",
            "/chat/",
            "/styles/",
            "/views/",
            "/widgets/",
            "theme",
            "stylesheet",
            "main_window",
        )
        is_explicit_wiring = any(marker in lowered for marker in wiring_only_markers)
        if (
            not is_explicit_wiring
            or any(marker in lowered for marker in visible_markers)
            or basename.endswith(".ui")
        ):
            match(Layer.UI_PRESENTATION, RiskLevel.HIGH, "path:ui-visible")

    application_markers = (
        "/backend/application/",
        "application_service",
        "command_api",
        "capability",
        "publication",
        "state_snapshot",
        "state_manager",
    )
    is_product_state = lowered.startswith(
        ("xbrainlab/backend/", "xbrainlab/llm/")
    ) and (
        basename == "state.py" or "/state/" in lowered or basename.startswith("state_")
    )
    if any(marker in lowered for marker in application_markers) or is_product_state:
        match(
            Layer.APPLICATION_SERVICE,
            RiskLevel.CRITICAL,
            "path:application-service",
        )

    if lowered.startswith("xbrainlab/backend/"):
        match(Layer.BACKEND_DOMAIN, RiskLevel.MEDIUM, "path:backend")

    persistence_markers = (
        "/record/",
        "persistence",
        "artifact_store",
        "output_path",
        "checkpoint_store",
    )
    if any(marker in lowered for marker in persistence_markers):
        match(Layer.PERSISTENCE, RiskLevel.CRITICAL, "path:persistence")

    security_markers = (
        "/security/",
        "security",
        "privacy",
        "authorized_path",
        "redaction",
        "secret",
    )
    if any(marker in lowered for marker in security_markers):
        match(Layer.SECURITY_PRIVACY, RiskLevel.CRITICAL, "path:security-privacy")

    data_owned_markers = (
        "xbrainlab/backend/dataset/",
        "xbrainlab/backend/load_data/",
        "xbrainlab/backend/io/",
        "xbrainlab/backend/epoch/",
        "xbrainlab/ui/dataset/",
        "xbrainlab/ui/data_import/",
        "data_interpretation",
        "split_audit",
        "bids",
    )
    if any(marker in lowered for marker in data_owned_markers):
        match(Layer.DATA_SEMANTICS, RiskLevel.CRITICAL, "path:data-semantics")

    if lowered.startswith("xbrainlab/llm/"):
        match(Layer.ASSISTANT, RiskLevel.HIGH, "path:assistant")

    model_markers = (
        "modelcatalog",
        "model_catalog",
        "local_llm",
        "inference_runtime",
    )
    is_assistant_model = lowered.startswith("xbrainlab/llm/") and any(
        marker in lowered for marker in ("/model/", "/models/", "model_")
    )
    if any(marker in lowered for marker in model_markers) or is_assistant_model:
        match(Layer.MODEL_RUNTIME, RiskLevel.CRITICAL, "path:model-runtime")

    native_markers = (
        "native_lifecycle",
        "/native/",
        "qthread",
        "pyvista",
        "launcher",
        "packaging",
    )
    if any(marker in lowered for marker in native_markers):
        match(Layer.NATIVE_LIFECYCLE, RiskLevel.CRITICAL, "path:native-lifecycle")

    platform_markers = (
        "/packaging/",
        "installer",
        "launcher",
        "pyinstaller",
        "desktop_entry",
    )
    if any(marker in lowered for marker in platform_markers):
        match(
            Layer.PLATFORM_PACKAGING,
            RiskLevel.CRITICAL,
            "path:platform-packaging",
        )

    if lowered.startswith("scripts/") and not is_docs:
        match(Layer.TEST_INFRASTRUCTURE, RiskLevel.HIGH, "path:developer-tooling")

    resource_policy_markers = (
        "resource_admission",
        "resource_calibration",
        "resource_confirmation",
        "resource_guard",
        "resource_preflight",
        "resource_receipt",
    )
    if any(marker in lowered for marker in resource_policy_markers):
        rules.add("path:performance-resource")
        floor = max(floor, RiskLevel.HIGH)

    if not layers:
        match(Layer.UNKNOWN, RiskLevel.CRITICAL, "path:unknown")

    return ChangedPath(
        path=canonical,
        layers=frozenset(layers),
        risk_floor=floor,
        matched_rule_ids=tuple(rules),
    )


def plan_validation(
    descriptor: ChangeDescriptor,
    changed_paths: Iterable[str | ChangedPath],
    *,
    gate_catalog: Mapping[str, object] | None = None,
) -> ValidationPlan:
    """Union path and agent semantics, then route rule IDs through a catalog.

    Caller-provided path metadata is deliberately re-inferred and unioned so a
    forged low-risk declaration cannot downgrade a mandatory path floor.
    """

    paths = _merge_changed_paths(changed_paths)
    layers = set(descriptor.declared_layers)
    risk = max(descriptor.declared_risk, _INTENT_RISK_FLOORS[descriptor.intent])
    applied_rules: set[str] = set()
    for changed in paths:
        layers.update(changed.layers)
        risk = max(risk, changed.risk_floor)
        applied_rules.update(changed.matched_rule_ids)

    docs_only = bool(paths) and bool(layers) and layers <= _DOC_LAYERS
    required_rules = set(descriptor.required_rule_ids)
    required_rules.update(_INTENT_RULES[descriptor.intent])
    required_rules.update(
        selection_rule
        for path_rule, selection_rule in _PATH_SELECTION_RULES.items()
        if path_rule in applied_rules
    )
    claim_rank = _CLAIM_RANK[descriptor.claim_level]
    if docs_only:
        required_rules.update({"identity", "docs", "guidance-contract"})
    else:
        required_rules.update({"identity", "static", "focused"})
        for layer in layers:
            required_rules.update(_LAYER_RULES[layer])

        if claim_rank >= _CLAIM_RANK[ClaimLevel.BOUNDED_COMPLETE]:
            required_rules.add("product-regression")
        if risk >= RiskLevel.CRITICAL:
            required_rules.add("product-regression")

    if claim_rank >= _CLAIM_RANK[ClaimLevel.HANDOFF]:
        required_rules.add("handoff")
    if descriptor.claim_level is ClaimLevel.RELEASE:
        required_rules.add("release")
    if descriptor.claim_level is ClaimLevel.THESIS:
        required_rules.add("thesis")

    catalog = _normalize_catalog(gate_catalog or {})
    required_gate_ids = (
        frozenset(catalog)
        if claim_rank >= _CLAIM_RANK[ClaimLevel.HANDOFF]
        else frozenset()
    )
    executions, unresolved = _route_rules(
        required_rules,
        catalog,
        required_gate_ids=required_gate_ids,
    )
    unknown_paths = tuple(
        changed.path for changed in paths if Layer.UNKNOWN in changed.layers
    )

    return ValidationPlan(
        descriptor=descriptor,
        changed_paths=paths,
        layers=frozenset(layers),
        risk_level=risk,
        required_rule_ids=tuple(required_rules),
        applied_rule_ids=tuple(applied_rules | required_rules),
        executions=executions,
        unresolved_rule_ids=tuple(unresolved),
        unknown_paths=unknown_paths,
    )


def _merge_changed_paths(
    changed_paths: Iterable[str | ChangedPath],
) -> tuple[ChangedPath, ...]:
    merged: dict[str, ChangedPath] = {}
    for supplied in changed_paths:
        if isinstance(supplied, ChangedPath):
            declared = supplied
            supplied_path = supplied.path
        else:
            declared = None
            supplied_path = supplied
        inferred = infer_changed_path(supplied_path)
        if declared:
            inferred = ChangedPath(
                path=inferred.path,
                layers=inferred.layers | declared.layers,
                risk_floor=max(inferred.risk_floor, declared.risk_floor),
                matched_rule_ids=tuple(
                    set(inferred.matched_rule_ids) | set(declared.matched_rule_ids)
                ),
            )
        previous = merged.get(inferred.path)
        if previous:
            inferred = ChangedPath(
                path=inferred.path,
                layers=inferred.layers | previous.layers,
                risk_floor=max(inferred.risk_floor, previous.risk_floor),
                matched_rule_ids=tuple(
                    set(inferred.matched_rule_ids) | set(previous.matched_rule_ids)
                ),
            )
        merged[inferred.path] = inferred
    return tuple(sorted(merged.values(), key=lambda changed: changed.path))


def _normalize_catalog(
    catalog: Mapping[str, object],
) -> dict[str, _CatalogGate]:
    normalized: dict[str, _CatalogGate] = {}
    for raw_gate_id, raw_entry in catalog.items():
        gate_id = _nonempty(str(raw_gate_id), "catalog gate ID")
        if isinstance(raw_entry, Mapping):
            tags = raw_entry.get("tags", ())
            dependencies = raw_entry.get("dependencies", ())
            expensive = raw_entry.get("expensive", False)
        else:
            tags = getattr(raw_entry, "tags", ())
            dependencies = getattr(raw_entry, "dependencies", ())
            expensive = getattr(raw_entry, "expensive", False)
        normalized[gate_id] = _CatalogGate(
            gate_id=gate_id,
            tags=frozenset(_clean_identifiers(tags, f"tags for {gate_id}")),
            dependencies=_clean_identifiers(
                dependencies, f"dependencies for {gate_id}"
            ),
            expensive=bool(expensive),
        )
    return normalized


def _route_rules(
    required_rules: set[str],
    catalog: Mapping[str, _CatalogGate],
    *,
    required_gate_ids: frozenset[str] = frozenset(),
) -> tuple[tuple[PlannedExecution, ...], frozenset[str]]:
    roots: set[str] = set(required_gate_ids)
    unresolved: set[str] = set()
    for rule_id in sorted(required_rules):
        matches = {gate_id for gate_id, gate in catalog.items() if rule_id in gate.tags}
        if matches:
            roots.update(matches)
        else:
            unresolved.add(rule_id)

    ordered: list[str] = []
    state: dict[str, str] = {}

    def visit(gate_id: str, trail: tuple[str, ...]) -> None:
        current_state = state.get(gate_id)
        if current_state == "done":
            return
        if current_state == "visiting":
            cycle = " -> ".join((*trail, gate_id))
            raise ValueError(f"gate dependency cycle: {cycle}")
        gate = catalog.get(gate_id)
        if gate is None:
            unresolved.add(f"missing-gate:{gate_id}")
            return
        state[gate_id] = "visiting"
        for dependency in gate.dependencies:
            visit(dependency, (*trail, gate_id))
        state[gate_id] = "done"
        ordered.append(gate_id)

    for root in sorted(roots):
        visit(root, ())

    selected = frozenset(ordered)
    executions = tuple(
        PlannedExecution(
            gate_id=gate_id,
            dependencies=tuple(
                dependency
                for dependency in catalog[gate_id].dependencies
                if dependency in selected
            ),
            satisfies_rules=tuple(catalog[gate_id].tags & required_rules),
            expensive=catalog[gate_id].expensive,
        )
        for gate_id in ordered
    )
    return executions, frozenset(unresolved)


def _canonical_path(path: str) -> str:
    value = str(path).strip().replace("\\", "/")
    if not value:
        raise ValueError("changed path must not be empty")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"changed path must be repository-relative: {path!r}")
    canonical = candidate.as_posix()
    if canonical == ".":
        raise ValueError("changed path must name a file or directory")
    return canonical


def _clean_identifiers(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    cleaned = {_nonempty(str(value), label) for value in values}
    return tuple(sorted(cleaned))


def _clean_ordered_identifiers(
    values: Iterable[str],
    label: str,
) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    cleaned = tuple(_nonempty(str(value), label) for value in values)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"receipt repeats {label} IDs")
    return cleaned


def _nonempty(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty")
    return cleaned


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("serialized validation value must be a JSON object")
    return payload


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _changed_paths_digest(changed_paths: Iterable[ChangedPath]) -> str:
    return _digest(
        _stable_json(
            {
                "paths": [
                    changed.path
                    for changed in sorted(changed_paths, key=lambda item: item.path)
                ]
            }
        )
    )


def _descriptor_payload(descriptor: ChangeDescriptor) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "intent": descriptor.intent.value,
        "claim_level": descriptor.claim_level.value,
        "declared_layers": sorted(layer.value for layer in descriptor.declared_layers),
        "declared_risk": descriptor.declared_risk.name.casefold(),
        "required_rule_ids": sorted(descriptor.required_rule_ids),
    }


def _descriptor_from_payload(payload: Mapping[str, Any]) -> ChangeDescriptor:
    return ChangeDescriptor(
        intent=ChangeIntent(str(payload["intent"])),
        claim_level=ClaimLevel(str(payload["claim_level"])),
        declared_layers=frozenset(
            Layer(str(value)) for value in payload["declared_layers"]
        ),
        declared_risk=RiskLevel[str(payload["declared_risk"]).upper()],
        required_rule_ids=frozenset(map(str, payload["required_rule_ids"])),
    )


def _plan_payload(plan: ValidationPlan) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "descriptor": _descriptor_payload(plan.descriptor),
        "changed_paths": [
            {
                "path": changed.path,
                "layers": sorted(layer.value for layer in changed.layers),
                "risk_floor": changed.risk_floor.name.casefold(),
                "matched_rule_ids": list(changed.matched_rule_ids),
            }
            for changed in plan.changed_paths
        ],
        "layers": sorted(layer.value for layer in plan.layers),
        "risk_level": plan.risk_level.name.casefold(),
        "required_rule_ids": list(plan.required_rule_ids),
        "applied_rule_ids": list(plan.applied_rule_ids),
        "executions": [
            {
                "gate_id": execution.gate_id,
                "dependencies": list(execution.dependencies),
                "satisfies_rules": list(execution.satisfies_rules),
                "expensive": execution.expensive,
            }
            for execution in plan.executions
        ],
        "unresolved_rule_ids": list(plan.unresolved_rule_ids),
        "unknown_paths": list(plan.unknown_paths),
        "source_sha": plan.source_sha,
        "base_sha": plan.base_sha,
        "change_set_digest": plan.change_set_digest,
    }


def _plan_from_payload(payload: Mapping[str, Any]) -> ValidationPlan:
    descriptor_payload = payload["descriptor"]
    if not isinstance(descriptor_payload, Mapping):
        raise ValueError("plan descriptor must be a JSON object")
    return ValidationPlan(
        descriptor=_descriptor_from_payload(descriptor_payload),
        changed_paths=tuple(
            ChangedPath(
                path=str(changed["path"]),
                layers=frozenset(Layer(str(value)) for value in changed["layers"]),
                risk_floor=RiskLevel[str(changed["risk_floor"]).upper()],
                matched_rule_ids=tuple(map(str, changed["matched_rule_ids"])),
            )
            for changed in payload["changed_paths"]
        ),
        layers=frozenset(Layer(str(value)) for value in payload["layers"]),
        risk_level=RiskLevel[str(payload["risk_level"]).upper()],
        required_rule_ids=tuple(map(str, payload["required_rule_ids"])),
        applied_rule_ids=tuple(map(str, payload["applied_rule_ids"])),
        executions=tuple(
            PlannedExecution(
                gate_id=str(execution["gate_id"]),
                dependencies=tuple(map(str, execution["dependencies"])),
                satisfies_rules=tuple(map(str, execution["satisfies_rules"])),
                expensive=bool(execution["expensive"]),
            )
            for execution in payload["executions"]
        ),
        unresolved_rule_ids=tuple(map(str, payload["unresolved_rule_ids"])),
        unknown_paths=tuple(map(str, payload["unknown_paths"])),
        source_sha=(
            str(payload["source_sha"])
            if payload.get("source_sha") is not None
            else None
        ),
        base_sha=(
            str(payload["base_sha"]) if payload.get("base_sha") is not None else None
        ),
        change_set_digest=(
            str(payload["change_set_digest"])
            if payload.get("change_set_digest") is not None
            else None
        ),
    )
