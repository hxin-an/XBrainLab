"""Single CI execution-owner map for risk-selected validation gates.

An owner is an executable CI job, not evidence that a broader test suite might
incidentally contain the same code path.  Selected gates missing from this map
make CI plan expansion fail closed.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

CI_GATE_OWNERS: Final = MappingProxyType(
    {
        "git-diff-check": "plan",
        "ruff-check": "lint",
        "ruff-format-check": "lint",
        "basedpyright": "lint",
        "mkdocs-strict": "docs",
        "architecture-compliance": "lint",
        "architecture-unit": "focused",
        "guidance-contract": "docs",
        "persistence-path-stop-barrier": "focused",
        "security-contract": "focused",
        "complete-regression": "product",
        "command-spine": "focused",
        "assistant-security-suite": "focused",
        "resource-contract": "focused",
        "human-like-product": "ui",
        "native-lifecycle-tests": "native",
        "fetch-required-ci": "public-data",
        "verify-required-ci": "public-data",
        "dataset-validation-matrix": "public-data",
        "data-interpretation-matrix": "public-data",
        "real-data-interpretation-training": "public-data",
        "wizard-format-matrix": "public-data",
        "required-public-io": "public-data",
        "public-cross-source-training": "public-data",
    }
)

CI_GATE_OWNER_IDS: Final = frozenset(CI_GATE_OWNERS.values())

CI_OWNER_EXECUTION_MODES: Final = MappingProxyType(
    {
        owner: ("ci-native-equivalent" if owner in {"plan", "product"} else "registry")
        for owner in CI_GATE_OWNER_IDS
    }
)

CI_NATIVE_OWNER_GATE_IDS: Final = MappingProxyType(
    {
        "plan": ("git-diff-check",),
        "product": ("complete-regression",),
    }
)

CI_NATIVE_OWNER_EVIDENCE_PATHS: Final = MappingProxyType(
    {
        "plan": (
            "build/ci-validation/ci-plan.json",
            "build/ci-validation/git-diff-check.log",
            "build/ci-validation/validation-plan.json",
        ),
        "product": (
            "build/ci-native-product/all-regression.json",
            "build/ci-native-product/coverage.xml",
        ),
    }
)
