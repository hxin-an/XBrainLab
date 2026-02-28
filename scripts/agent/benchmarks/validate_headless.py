#!/usr/bin/env python3
"""Backend Headless Verification — Validates backend imports without Qt.

Ensures that the core backend modules (Study, BackendFacade, controllers,
training, dataset, preprocessing, LLM pipeline) can be imported and
instantiated without a running Qt application or display server.

This is a prerequisite for Docker / CI environments and headless batch
processing.

Usage:
    poetry run python scripts/agent/benchmarks/validate_headless.py
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════
# Test specifications:  (module_path, class_name | None, description)
# ═══════════════════════════════════════════════════════════════
_IMPORT_TESTS: list[tuple[str, str | None, str]] = [
    # ── Core backend ──
    ("XBrainLab.backend.study", "Study", "Backend Study singleton"),
    ("XBrainLab.backend.facade", "BackendFacade", "High-level facade"),
    ("XBrainLab.backend.training_manager", "TrainingManager", "Training lifecycle"),
    ("XBrainLab.backend.data_manager", "DataManager", "Data lifecycle"),
    # ── Controllers (Observable, no Qt) ──
    (
        "XBrainLab.backend.controller.dataset_controller",
        "DatasetController",
        "Dataset controller",
    ),
    (
        "XBrainLab.backend.controller.training_controller",
        "TrainingController",
        "Training controller",
    ),
    (
        "XBrainLab.backend.controller.evaluation_controller",
        "EvaluationController",
        "Evaluation controller",
    ),
    (
        "XBrainLab.backend.controller.preprocess_controller",
        "PreprocessController",
        "Preprocess controller",
    ),
    # ── Training primitives ──
    ("XBrainLab.backend.training", "TrainingOption", "TrainingOption dataclass"),
    ("XBrainLab.backend.training", "ModelHolder", "ModelHolder"),
    ("XBrainLab.backend.training", "TrainingEvaluation", "TrainingEvaluation"),
    # ── Dataset / splitting ──
    ("XBrainLab.backend.dataset", "DataSplitter", "DataSplitter"),
    ("XBrainLab.backend.dataset", "DataSplittingConfig", "DataSplittingConfig"),
    # ── Model architectures ──
    ("XBrainLab.backend.model_base.EEGNet", "EEGNet", "EEGNet model"),
    ("XBrainLab.backend.model_base.SCCNet", "SCCNet", "SCCNet model"),
    ("XBrainLab.backend.model_base.ShallowConvNet", "ShallowConvNet", "ShallowConvNet"),
    # ── Preprocessing ──
    ("XBrainLab.backend.preprocessor", None, "Preprocessor registry module"),
    # ── LLM pipeline (non-Qt parts) ──
    ("XBrainLab.llm.core.config", "LLMConfig", "LLM config dataclass"),
    ("XBrainLab.llm.core.engine", "LLMEngine", "LLM engine"),
    ("XBrainLab.llm.agent.parser", "CommandParser", "Command parser"),
    ("XBrainLab.llm.pipeline_state", "PipelineStage", "Pipeline stage enum"),
    ("XBrainLab.llm.tools.tool_registry", "ToolRegistry", "Tool registry"),
    # ── RAG ──
    ("XBrainLab.llm.rag.config", "RAGConfig", "RAG config"),
    ("XBrainLab.llm.rag.bm25", "BM25Index", "BM25 keyword scorer"),
    # ── Utilities ──
    ("XBrainLab.backend.utils.logger", "logger", "Backend logger"),
    ("XBrainLab.backend.utils.observer", "Observable", "Observer pattern base"),
    ("XBrainLab.config", "AppConfig", "Application config"),
]

_INSTANTIATION_TESTS: list[tuple[str, str, dict, str]] = [
    # (module, class, kwargs, description)
    ("XBrainLab.llm.core.config", "LLMConfig", {}, "LLMConfig()"),
    ("XBrainLab.llm.agent.parser", "CommandParser", {}, "CommandParser()"),
    ("XBrainLab.llm.tools.tool_registry", "ToolRegistry", {}, "ToolRegistry()"),
    ("XBrainLab.llm.rag.bm25", "BM25Index", {}, "BM25Index()"),
    ("XBrainLab.llm.pipeline_state", "PipelineStage", {}, "PipelineStage enum access"),
]


def _run_import_tests() -> tuple[int, int, list[str]]:
    """Run all import tests. Returns (passed, total, errors)."""
    passed = 0
    errors: list[str] = []

    for mod_path, cls_name, desc in _IMPORT_TESTS:
        try:
            mod = importlib.import_module(mod_path)
            if cls_name:
                obj = getattr(mod, cls_name)
                if obj is None:
                    errors.append(f"{desc}: {cls_name} is None")
                    print(f"  [FAIL] {desc:40} — {cls_name} is None")
                    continue
            passed += 1
            print(f"  [PASS] {desc:40} ({mod_path}.{cls_name or '*'})")
        except Exception as e:
            msg = f"{desc}: {e}"
            errors.append(msg)
            print(f"  [FAIL] {desc:40} — {e}")

    return passed, len(_IMPORT_TESTS), errors


def _run_instantiation_tests() -> tuple[int, int, list[str]]:
    """Run instantiation tests. Returns (passed, total, errors)."""
    passed = 0
    errors: list[str] = []

    for mod_path, cls_name, kwargs, desc in _INSTANTIATION_TESTS:
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            _ = cls.EMPTY if cls_name == "PipelineStage" else cls(**kwargs)
            passed += 1
            print(f"  [PASS] {desc}")
        except Exception as e:
            msg = f"{desc}: {e}"
            errors.append(msg)
            print(f"  [FAIL] {desc} — {e}")

    return passed, len(_INSTANTIATION_TESTS), errors


def _check_no_qt_at_import() -> tuple[bool, str]:
    """Verify that QtWidgets was NOT imported as a side effect."""
    qt_loaded = "PyQt6.QtWidgets" in sys.modules
    if qt_loaded:
        return False, "PyQt6.QtWidgets was imported — backend is not headless-safe"
    return True, "No Qt modules loaded during backend imports"


def main():
    print("=" * 60)
    print("BACKEND HEADLESS VERIFICATION")
    print("=" * 60)
    t0 = time.time()

    # ── Phase 1: Import tests ──
    print("\n── Phase 1: Import Tests ──")
    ip, it, ie = _run_import_tests()

    # ── Phase 2: Instantiation tests ──
    print("\n── Phase 2: Instantiation Tests ──")
    np_, nt, ne = _run_instantiation_tests()

    # ── Phase 3: Qt side-effect check ──
    print("\n── Phase 3: Qt Side-Effect Check ──")
    qt_ok, qt_msg = _check_no_qt_at_import()
    print(f"  [{'PASS' if qt_ok else 'FAIL'}] {qt_msg}")

    elapsed = time.time() - t0

    # ── Summary ──
    all_errors = ie + ne
    total_pass = ip + np_ + (1 if qt_ok else 0)
    total_tests = it + nt + 1

    print(f"\n{'=' * 60}")
    print(f"RESULT: {total_pass}/{total_tests} passed ({elapsed:.1f}s)")
    if all_errors:
        print("\nFailures:")
        for e in all_errors:
            print(f"  - {e}")
    if not qt_ok:
        print(f"  - {qt_msg}")
    print()

    return 0 if total_pass == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())
