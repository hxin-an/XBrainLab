"""Risk-selection metadata layered over the canonical handoff gate registry.

This module intentionally owns no command, timeout, environment, artifact, or
outcome policy. Those executable facts remain in :mod:`handoff_gate_spec`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS


@dataclass(frozen=True)
class ValidationGateCatalogEntry:
    """Selection-only metadata for one registered executable gate."""

    gate_id: str
    tags: frozenset[str]
    dependencies: tuple[str, ...] = ()
    expensive: bool = False

    def __post_init__(self) -> None:
        if not self.tags or any(not tag for tag in self.tags):
            raise ValueError(f"Gate {self.gate_id!r} requires coverage tags.")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError(f"Gate {self.gate_id!r} repeats dependencies.")


CONTROL_PLANE_RULE_TAGS: Final = frozenset(
    {
        "application-service",
        "assistant",
        "backend",
        "ci-validation",
        "data-diversity",
        "data-semantics",
        "dependency-change",
        "docs",
        "exact-model",
        "focused",
        "guidance-contract",
        "handoff",
        "identity",
        "model-runtime",
        "native-lifecycle",
        "performance-resource",
        "persistence",
        "platform-packaging",
        "product-regression",
        "release",
        "security-privacy",
        "static",
        "test-infrastructure",
        "thesis",
        "ui-behavior",
        "ui-visible",
        "unknown-change",
    }
)


def _entry(
    gate_id: str,
    *tags: str,
    dependencies: tuple[str, ...] = (),
    expensive: bool = False,
) -> ValidationGateCatalogEntry:
    return ValidationGateCatalogEntry(
        gate_id=gate_id,
        tags=frozenset(tags),
        dependencies=dependencies,
        expensive=expensive,
    )


_CATALOG_ENTRIES = (
    _entry("git-status", "branch-hygiene"),
    _entry("git-head", "source-identity"),
    _entry("git-upstream", "branch-hygiene"),
    _entry("git-divergence", "branch-hygiene"),
    _entry("git-worktrees", "branch-hygiene"),
    _entry("git-diff-check", "identity"),
    _entry("ruff-check", "static", dependencies=("git-diff-check",)),
    _entry("ruff-format-check", "static", dependencies=("git-diff-check",)),
    _entry("basedpyright", "static", dependencies=("git-diff-check",)),
    _entry("mkdocs-strict", "docs", dependencies=("git-diff-check",)),
    _entry(
        "architecture-compliance",
        "architecture",
        "ci-validation",
        dependencies=("ruff-check",),
    ),
    _entry(
        "architecture-unit",
        "backend",
        "focused",
        dependencies=("ruff-check",),
    ),
    _entry(
        "guidance-contract",
        "guidance-contract",
        dependencies=("mkdocs-strict",),
    ),
    _entry(
        "persistence-path-stop-barrier",
        "persistence",
        dependencies=("architecture-unit",),
    ),
    _entry(
        "security-contract",
        "security-privacy",
        dependencies=("architecture-unit",),
    ),
    _entry(
        "complete-regression",
        "ci-validation",
        "dependency-change",
        "platform-packaging",
        "product-regression",
        "test-infrastructure",
        "ui-behavior",
        "unknown-change",
        dependencies=("ruff-check",),
        expensive=True,
    ),
    _entry(
        "command-spine",
        "application-service",
        "backend",
        dependencies=("architecture-unit",),
    ),
    _entry(
        "assistant-security-suite",
        "assistant",
        dependencies=("command-spine",),
    ),
    _entry(
        "granite-runtime",
        "exact-model",
        "model-runtime",
        dependencies=("assistant-security-suite",),
        expensive=True,
    ),
    _entry(
        "rag-offline",
        "assistant-rag",
        "model-runtime",
        dependencies=("assistant-security-suite",),
    ),
    _entry(
        "chatpanel-guided-boundary",
        "assistant-ui-guidance",
        dependencies=("assistant-security-suite",),
        expensive=True,
    ),
    _entry(
        "chatpanel-training-readiness",
        "assistant-ui-training",
        dependencies=("assistant-security-suite",),
        expensive=True,
    ),
    _entry(
        "chatpanel-training-completion",
        "assistant-ui-training",
        dependencies=("chatpanel-training-readiness",),
        expensive=True,
    ),
    _entry(
        "chatpanel-local-recovery",
        "assistant-ui-recovery",
        dependencies=("assistant-security-suite",),
        expensive=True,
    ),
    _entry(
        "chatpanel-local-long-session",
        "assistant-ui-endurance",
        dependencies=("assistant-security-suite",),
        expensive=True,
    ),
    _entry(
        "human-like-product",
        "ui-visible",
        dependencies=("complete-regression",),
        expensive=True,
    ),
    _entry(
        "ui-reviewer-fixes",
        "ui-review-artifacts",
        dependencies=("complete-regression",),
        expensive=True,
    ),
    _entry(
        "dataset-narrow",
        "ui-dataset-narrow",
        dependencies=("architecture-unit",),
        expensive=True,
    ),
    _entry(
        "visualization-render",
        "ui-visualization",
        dependencies=("architecture-unit",),
        expensive=True,
    ),
    _entry(
        "chatpanel-dpi",
        "ui-layout",
        dependencies=("architecture-unit",),
        expensive=True,
    ),
    _entry(
        "data-import-wizard-capture",
        "ui-data-import",
        dependencies=("architecture-unit",),
        expensive=True,
    ),
    _entry(
        "data-import-wizard-validate",
        "ui-data-import",
        dependencies=("data-import-wizard-capture",),
    ),
    _entry(
        "native-lifecycle-tests",
        "native-lifecycle",
        dependencies=("architecture-unit",),
        expensive=True,
    ),
    _entry(
        "preprocess-native-stress",
        "native-preprocess-stress",
        dependencies=("native-lifecycle-tests",),
        expensive=True,
    ),
    _entry(
        "ui-native-render-stress",
        "native-render-stress",
        dependencies=("native-lifecycle-tests",),
        expensive=True,
    ),
    _entry("fetch-required-ci", "public-fixture-fetch", expensive=True),
    _entry(
        "verify-required-ci",
        "public-fixture-verify",
        dependencies=("fetch-required-ci",),
    ),
    _entry(
        "dataset-validation-matrix",
        "data-semantics",
        dependencies=("verify-required-ci",),
        expensive=True,
    ),
    _entry(
        "data-interpretation-matrix",
        "data-semantics",
        dependencies=("verify-required-ci",),
        expensive=True,
    ),
    _entry(
        "real-data-interpretation-training",
        "data-semantics",
        dependencies=("verify-required-ci",),
        expensive=True,
    ),
    _entry(
        "wizard-format-matrix",
        "data-semantics",
        dependencies=("verify-required-ci",),
        expensive=True,
    ),
    _entry(
        "required-public-io",
        "data-diversity",
        dependencies=("verify-required-ci",),
        expensive=True,
    ),
    _entry(
        "public-cross-source-training",
        "data-diversity",
        dependencies=("required-public-io",),
        expensive=True,
    ),
    _entry(
        "resource-contract",
        "performance-resource",
        dependencies=("architecture-unit",),
    ),
    _entry(
        "resource-calibration",
        "handoff-resource",
        dependencies=("complete-regression",),
        expensive=True,
    ),
    _entry(
        "handoff-dashboard",
        "handoff",
        "release",
        "thesis",
        dependencies=("complete-regression", "resource-calibration"),
        expensive=True,
    ),
)


def _build_catalog() -> MappingProxyType[str, ValidationGateCatalogEntry]:
    entries = {entry.gate_id: entry for entry in _CATALOG_ENTRIES}
    registered_ids = tuple(HANDOFF_GATE_SPECS)
    if tuple(entries) != registered_ids:
        missing = sorted(set(registered_ids).difference(entries))
        extra = sorted(set(entries).difference(registered_ids))
        raise RuntimeError(
            "Validation gate catalog drifted from the executable registry: "
            f"missing={missing}, extra={extra}."
        )
    positions = {gate_id: index for index, gate_id in enumerate(registered_ids)}
    for gate_id, entry in entries.items():
        unknown = set(entry.dependencies).difference(entries)
        if unknown:
            raise RuntimeError(
                f"Gate {gate_id!r} has unknown dependencies: {sorted(unknown)}."
            )
        if any(
            positions[dependency] >= positions[gate_id]
            for dependency in entry.dependencies
        ):
            raise RuntimeError(f"Gate {gate_id!r} dependencies are not topological.")
    supported = frozenset(tag for entry in entries.values() for tag in entry.tags)
    missing_rules = CONTROL_PLANE_RULE_TAGS.difference(supported)
    if missing_rules:
        raise RuntimeError(
            f"Validation catalog does not support rules: {sorted(missing_rules)}."
        )
    return MappingProxyType(entries)


HANDOFF_VALIDATION_GATE_CATALOG: Final = _build_catalog()
