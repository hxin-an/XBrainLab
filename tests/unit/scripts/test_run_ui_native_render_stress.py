"""Source guards for the native-render stress process safety boundary."""

from __future__ import annotations

import ast
import itertools
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "dev"
    / "run_ui_native_render_stress.py"
)
NATIVE_IMPORT_ROOTS = {
    "matplotlib",
    "psutil",
    "PyQt6",
    "pyvista",
    "pyvistaqt",
    "scripts",
    "XBrainLab",
}


def _script_tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def _core_limit_function() -> ast.FunctionDef:
    function = next(
        (
            node
            for node in _script_tree().body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_disable_core_dumps_for_native_stress"
        ),
        None,
    )
    assert function is not None
    return function


def _named_function(name: str) -> ast.FunctionDef:
    function = next(
        (
            node
            for node in _script_tree().body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ),
        None,
    )
    assert function is not None
    return function


def _load_core_limit_function(
    monkeypatch,
    resource_module,
) -> Callable[[], bool]:
    monkeypatch.setitem(sys.modules, "resource", resource_module)
    function = _core_limit_function()
    namespace: dict[str, object] = {}
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SCRIPT_PATH), "exec"), namespace)  # noqa: S102
    return cast(
        Callable[[], bool],
        namespace["_disable_core_dumps_for_native_stress"],
    )


def _load_stress_contract_function() -> Callable[..., list[str]]:
    function = _named_function("_stress_contract_failures")
    namespace: dict[str, Any] = {
        "_NATIVE_QT_PLATFORM": "offscreen",
        "PRODUCT_2D_VIEW_NAMES": ("map", "spectrogram", "topomap"),
    }
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SCRIPT_PATH), "exec"), namespace)  # noqa: S102
    return cast(
        Callable[..., list[str]],
        namespace["_stress_contract_failures"],
    )


def _load_memory_series_metrics_function() -> Callable[..., dict[str, object]]:
    function = _named_function("_memory_series_metrics")
    namespace: dict[str, Any] = {"itertools": itertools}
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SCRIPT_PATH), "exec"), namespace)  # noqa: S102
    return cast(
        Callable[..., dict[str, object]],
        namespace["_memory_series_metrics"],
    )


def _load_memory_contract_function() -> Callable[..., list[str]]:
    function = _named_function("_memory_contract_failures")
    namespace: dict[str, Any] = {
        "MAX_PRODUCT_INITIALIZATION_RSS_GROWTH_BYTES": 384 * 1024 * 1024,
        "MAX_PRODUCT_WARMUP_RSS_GROWTH_BYTES": 448 * 1024 * 1024,
        "MAX_STRESS_RSS_GROWTH_BYTES": 256 * 1024 * 1024,
        "MAX_STEADY_RSS_SLOPE_BYTES_PER_CYCLE": 8 * 1024 * 1024,
        "MAX_STEADY_RSS_CYCLE_DELTA_BYTES": 64 * 1024 * 1024,
    }
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SCRIPT_PATH), "exec"), namespace)  # noqa: S102
    return cast(
        Callable[..., list[str]],
        namespace["_memory_contract_failures"],
    )


def _load_native_qt_platform_function() -> Callable[[str], str]:
    function = _named_function("_native_qt_platform")
    namespace: dict[str, object] = {}
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SCRIPT_PATH), "exec"), namespace)  # noqa: S102
    return cast(Callable[[str], str], namespace["_native_qt_platform"])


def _passing_stress_result(
    *,
    cycles: int = 1,
    interactive_3d: bool = False,
) -> dict[str, object]:
    expected_2d = cycles * 3
    expected_3d_updates = cycles
    result: dict[str, object] = {
        "qt_qpa_platform": "offscreen",
        "core_dumps_disabled": True,
        "active_render_close_fenced": True,
        "active_render_close_completed": True,
        "pool_drained_before_close": True,
        "app_owned_render_idle_after_close": True,
        "unrelated_global_work_started": True,
        "unrelated_global_work_active_at_finalize": True,
        "unrelated_global_work_completed": True,
        "child_finalizers_completed": True,
        "child_finalizers_exactly_once": True,
        "two_d_resources_released": True,
        "active_3d_engine_close_safe": True,
        "active_3d_probe_close_safe": True,
        "active_3d_engine_late_callbacks": 0,
        "active_3d_probe_late_callbacks": 0,
        "active_3d_worker_gui_heartbeat_ticks": 2,
        "resources_finalized": True,
        "product_saliency_cycles": cycles,
        "product_saliency_warmup_cycles": 0,
        "product_saliency_measurement_cycles": cycles,
        "product_memory_sample_count": cycles + 1,
        "product_initialization_rss_growth_bytes": 16 * 1024 * 1024,
        "product_warmup_rss_growth_bytes": 16 * 1024 * 1024,
        "steady_rss_growth_bytes": 2 * 1024 * 1024,
        "steady_rss_peak_growth_bytes": 2 * 1024 * 1024,
        "steady_rss_slope_bytes_per_cycle": 2 * 1024 * 1024,
        "steady_rss_cycle_deltas_bytes": [2 * 1024 * 1024] * cycles,
        "product_memory_samples": [
            {
                "rss_bytes": 100,
                "uss_bytes": 90,
                "saliency_3d_scene_count": int(interactive_3d and index > 0),
                "saliency_3d_engine_count": int(interactive_3d and index > 0),
                "qt_interactor_wrapper_count": int(interactive_3d and index > 0),
            }
            for index in range(cycles + 1)
        ],
        "product_saliency_publications_served": expected_2d + expected_3d_updates,
        "product_2d_renders_installed": expected_2d,
        "product_2d_loading_cleared": expected_2d,
        "product_2d_replaced_resources_released": expected_2d,
        "product_map_renders_installed": cycles,
        "product_spectrogram_renders_installed": cycles,
        "product_topomap_renders_installed": cycles,
        "product_3d_tab_updates": expected_3d_updates,
        "product_3d_status": "SKIP",
        "product_3d_renders_installed": 0,
        "product_3d_replaced_interactors_closed": 0,
        "product_3d_block_reason": "Interactive OpenGL runtime is unavailable.",
        "three_d_interactor_closed": None,
        "three_d_interactor_wrapper_released": None,
        "three_d_interactor_close_verified": None,
        "three_d_interactor_close_attempts": 0,
        "three_d_interactor_close_successes": 0,
        "three_d_finalizer_count": 1,
    }
    if interactive_3d:
        result.update(
            {
                "product_3d_status": "PASS",
                "product_3d_renders_installed": cycles,
                "product_3d_replaced_interactors_closed": max(cycles - 1, 0),
                "product_3d_block_reason": "",
                "three_d_interactor_closed": True,
                "three_d_interactor_wrapper_released": True,
                "three_d_interactor_close_verified": True,
                "three_d_interactor_close_attempts": cycles,
                "three_d_interactor_close_successes": cycles,
            }
        )
    return result


def test_core_dump_limit_is_applied_before_native_imports():
    tree = _script_tree()
    assignment = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "_disable_core_dumps_for_native_stress"
        ),
        None,
    )
    assert assignment is not None

    native_import_lines = [
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name.split(".", 1)[0] in NATIVE_IMPORT_ROOTS
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".", 1)[0] in NATIVE_IMPORT_ROOTS
            )
        )
    ]
    assert native_import_lines
    assert assignment.lineno < min(native_import_lines)


def test_posix_parent_stops_before_native_imports_when_core_guard_fails():
    tree = _script_tree()
    native_import_line = min(
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name.split(".", 1)[0] in NATIVE_IMPORT_ROOTS
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".", 1)[0] in NATIVE_IMPORT_ROOTS
            )
        )
    )
    guard = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and node.lineno < native_import_line
            and any(
                isinstance(candidate, ast.Name)
                and candidate.id == "_CORE_DUMPS_DISABLED"
                for candidate in ast.walk(node.test)
            )
        ),
        None,
    )

    assert guard is not None
    assert any(isinstance(node, ast.Raise) for node in ast.walk(guard))


def test_native_stress_uses_cocoa_on_darwin_and_offscreen_elsewhere() -> None:
    native_qt_platform = _load_native_qt_platform_function()

    assert native_qt_platform("darwin") == "cocoa"
    assert native_qt_platform("linux") == "offscreen"
    assert native_qt_platform("win32") == "offscreen"


def test_native_wait_loop_only_collects_garbage_when_explicitly_requested() -> None:
    function = _named_function("_pump_until")
    collect_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "gc"
        and node.func.attr == "collect"
    ]

    assert collect_calls
    assert all(
        any(
            isinstance(parent, ast.If)
            and any(candidate is call for candidate in ast.walk(parent))
            and any(
                isinstance(candidate, ast.Name) and candidate.id == "collect_garbage"
                for candidate in ast.walk(parent.test)
            )
            for parent in ast.walk(function)
        )
        for call in collect_calls
    )


def test_product_tab_stress_uses_public_panel_publication_path():
    function = _named_function("_exercise_product_saliency_tabs")
    called_attributes = {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_attributes & {"on_update", "update_panel"}
    assert "refresh_combos" in called_attributes
    assert "_render_figure_async" not in called_attributes
    assert "_replace_figure" not in called_attributes

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "actual_saliency_tab" not in source
    assert "_build_tab_stress_figure" not in source
    assert '"product_3d_tab_updates": 1' not in source


def test_visualization_stress_constructs_panel_with_narrow_runtime_ports():
    function = _named_function("_replace_visualization_panel_with_publication_fixture")
    panel_call = next(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "VisualizationPanel"
        ),
        None,
    )
    assert panel_call is not None
    keyword_names = {keyword.arg for keyword in panel_call.keywords}
    assert {"query_port", "publication_port", "action_port"} <= keyword_names
    assert "controller" not in keyword_names
    assert "application_runtime" not in keyword_names

    runtime_class = next(
        (
            node
            for node in _script_tree().body
            if isinstance(node, ast.ClassDef)
            and node.name == "_NativeStressApplicationRuntime"
        ),
        None,
    )
    assert runtime_class is not None
    assert any(
        isinstance(base, ast.Name) and base.id == "Observable"
        for base in runtime_class.bases
    )
    initializer = next(
        (
            node
            for node in runtime_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        ),
        None,
    )
    assert initializer is not None
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "super"
        and node.func.attr == "__init__"
        for node in ast.walk(initializer)
    )


def test_product_tab_stress_repeats_3d_inside_every_cycle():
    function = _named_function("_exercise_product_saliency_tabs")
    cycle_loop = next(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and any(
                isinstance(argument, ast.Name) and argument.id == "cycles"
                for argument in node.iter.args
            )
        ),
        None,
    )
    assert cycle_loop is not None
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_activate_saliency_tab"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == 3
        for node in ast.walk(cycle_loop)
    )


def test_product_tab_stress_records_one_settled_memory_sample_per_cycle():
    function = _named_function("_exercise_product_saliency_tabs")
    source = ast.unparse(function)

    assert "_sample_process_memory" in source
    assert "product_memory_samples" in source


def test_memory_series_separates_warmup_from_steady_state_growth():
    memory_series_metrics = _load_memory_series_metrics_function()
    metrics = memory_series_metrics(
        [
            {"rss_bytes": 100, "uss_bytes": 80},
            {"rss_bytes": 300, "uss_bytes": 260},
            {"rss_bytes": 320, "uss_bytes": 275},
            {"rss_bytes": 330, "uss_bytes": 280},
            {"rss_bytes": 335, "uss_bytes": 282},
        ],
        warmup_cycles=2,
        measurement_cycles=2,
    )

    assert metrics == {
        "product_memory_sample_count": 5,
        "product_initialization_rss_growth_bytes": 200,
        "product_initialization_uss_growth_bytes": 180,
        "product_warmup_rss_growth_bytes": 220,
        "product_warmup_uss_growth_bytes": 195,
        "steady_rss_samples_bytes": [320, 330, 335],
        "steady_uss_samples_bytes": [275, 280, 282],
        "steady_rss_cycle_deltas_bytes": [10, 5],
        "steady_uss_cycle_deltas_bytes": [5, 2],
        "steady_rss_growth_bytes": 15,
        "steady_uss_growth_bytes": 7,
        "steady_rss_peak_growth_bytes": 15,
        "steady_uss_peak_growth_bytes": 7,
        "steady_rss_slope_bytes_per_cycle": 7.5,
        "steady_uss_slope_bytes_per_cycle": 3.5,
    }


@pytest.mark.parametrize(
    ("samples", "warmup_cycles", "measurement_cycles"),
    [
        ([], 2, 3),
        ([{"rss_bytes": 1, "uss_bytes": 1}], 0, 1),
        (
            [
                {"rss_bytes": 1, "uss_bytes": 1},
                {"rss_bytes": 2, "uss_bytes": 2},
            ],
            1,
            1,
        ),
    ],
)
def test_memory_series_rejects_incomplete_evidence(
    samples,
    warmup_cycles,
    measurement_cycles,
):
    memory_series_metrics = _load_memory_series_metrics_function()

    with pytest.raises(ValueError, match="memory samples"):
        memory_series_metrics(
            samples,
            warmup_cycles=warmup_cycles,
            measurement_cycles=measurement_cycles,
        )


def test_memory_contract_accepts_bounded_warmup_and_stable_trend():
    memory_contract_failures = _load_memory_contract_function()
    result = _passing_stress_result(cycles=3, interactive_3d=True)
    result.update(
        {
            "product_memory_sample_count": 6,
            "product_memory_samples": [
                {
                    "rss_bytes": 100,
                    "uss_bytes": 90,
                    "saliency_3d_scene_count": int(index > 0),
                    "saliency_3d_engine_count": int(index > 0),
                    "qt_interactor_wrapper_count": int(index > 0),
                }
                for index in range(6)
            ],
            "product_initialization_rss_growth_bytes": 320 * 1024 * 1024,
            "product_warmup_rss_growth_bytes": 400 * 1024 * 1024,
            "steady_rss_growth_bytes": 9 * 1024 * 1024,
            "steady_rss_peak_growth_bytes": 9 * 1024 * 1024,
            "steady_rss_slope_bytes_per_cycle": 3 * 1024 * 1024,
            "steady_rss_cycle_deltas_bytes": [
                4 * 1024 * 1024,
                3 * 1024 * 1024,
                2 * 1024 * 1024,
            ],
        }
    )

    assert (
        memory_contract_failures(
            result,
            warmup_cycles=2,
            measurement_cycles=3,
        )
        == []
    )


@pytest.mark.parametrize(
    ("metric", "value"),
    [
        ("product_initialization_rss_growth_bytes", 385 * 1024 * 1024),
        ("product_warmup_rss_growth_bytes", 449 * 1024 * 1024),
        ("steady_rss_peak_growth_bytes", 257 * 1024 * 1024),
        ("steady_rss_slope_bytes_per_cycle", 9 * 1024 * 1024),
    ],
)
def test_memory_contract_fails_closed_for_unbounded_native_growth(metric, value):
    memory_contract_failures = _load_memory_contract_function()
    result = _passing_stress_result(cycles=3, interactive_3d=True)
    result.update(
        {
            "product_memory_sample_count": 6,
            "product_memory_samples": [
                {
                    "rss_bytes": 100,
                    "uss_bytes": 90,
                    "saliency_3d_scene_count": int(index > 0),
                    "saliency_3d_engine_count": int(index > 0),
                    "qt_interactor_wrapper_count": int(index > 0),
                }
                for index in range(6)
            ],
            metric: value,
        }
    )

    assert metric in memory_contract_failures(
        result,
        warmup_cycles=2,
        measurement_cycles=3,
    )


def test_memory_contract_rejects_retained_3d_python_owners():
    memory_contract_failures = _load_memory_contract_function()
    result = _passing_stress_result(cycles=3, interactive_3d=True)
    result["product_memory_sample_count"] = 6
    result["product_memory_samples"] = [
        {
            "rss_bytes": 100,
            "uss_bytes": 90,
            "saliency_3d_scene_count": min(index, 2),
            "saliency_3d_engine_count": min(index, 2),
            "qt_interactor_wrapper_count": min(index, 2),
        }
        for index in range(6)
    ]

    failures = memory_contract_failures(
        result,
        warmup_cycles=2,
        measurement_cycles=3,
    )

    assert "product_3d_python_owner_counts" in failures


def test_native_stress_exercises_active_3d_engine_and_probe_deletion():
    function = _named_function("_exercise_one_active_3d_worker_deletion")
    called_attributes = {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "_start_3d_engine_worker" in called_attributes
    assert "_start_interactive_3d_runtime_probe" in called_attributes
    assert "deleteLater" in called_attributes
    assert "waitForDone" not in called_attributes
    assert "globalInstance" not in called_attributes


def test_stress_failures_return_nonzero_without_intentional_native_crash():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "os.abort(",
        "SIGABRT",
        "raise_signal(",
        "_sigsegv(",
        "_sigabrt(",
    ):
        assert forbidden not in source

    main_function = _named_function("main")
    exception_handlers = [
        node for node in ast.walk(main_function) if isinstance(node, ast.ExceptHandler)
    ]
    assert any(
        any(
            isinstance(statement, ast.Return)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value == 1
            for statement in handler.body
        )
        for handler in exception_handlers
    )


@pytest.mark.parametrize(
    "failed_metric",
    [
        "core_dumps_disabled",
        "pool_drained_before_close",
        "unrelated_global_work_started",
        "unrelated_global_work_active_at_finalize",
        "child_finalizers_completed",
        "child_finalizers_exactly_once",
        "two_d_resources_released",
        "active_3d_engine_close_safe",
        "active_3d_probe_close_safe",
        "resources_finalized",
    ],
)
def test_stress_contract_fails_closed_for_required_resource_metrics(failed_metric):
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result()
    result[failed_metric] = False

    assert failed_metric in contract_failures(result, cycles=1)


@pytest.mark.parametrize(
    ("failed_metric", "failed_value"),
    [
        ("product_saliency_publications_served", 3),
        ("product_2d_replaced_resources_released", 2),
        ("product_map_renders_installed", 0),
        ("product_spectrogram_renders_installed", 0),
        ("product_topomap_renders_installed", 0),
        ("active_3d_engine_late_callbacks", 1),
        ("active_3d_probe_late_callbacks", 1),
        ("active_3d_worker_gui_heartbeat_ticks", 0),
    ],
)
def test_stress_contract_fails_closed_for_measured_product_counts(
    failed_metric,
    failed_value,
):
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result()
    result[failed_metric] = failed_value

    assert failed_metric in contract_failures(result, cycles=1)


@pytest.mark.parametrize(
    "failed_metric",
    [
        "three_d_interactor_closed",
        "three_d_interactor_wrapper_released",
        "three_d_interactor_close_verified",
    ],
)
def test_stress_contract_fails_closed_when_interactive_3d_is_not_closed(
    failed_metric,
):
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result(interactive_3d=True)
    result[failed_metric] = False

    assert failed_metric in contract_failures(result, cycles=1)


@pytest.mark.parametrize(
    ("failed_metric", "failed_value"),
    [
        ("three_d_interactor_close_attempts", 0),
        ("three_d_interactor_close_successes", 0),
        ("three_d_finalizer_count", 0),
    ],
)
def test_stress_contract_requires_exact_interactive_3d_close_evidence(
    failed_metric,
    failed_value,
):
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result(interactive_3d=True)
    result[failed_metric] = failed_value

    assert failed_metric in contract_failures(result, cycles=1)


def test_stress_contract_requires_3d_render_for_every_interactive_cycle():
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result(cycles=3, interactive_3d=True)

    assert contract_failures(result, cycles=3) == []

    result["product_3d_tab_updates"] = 1
    result["product_3d_renders_installed"] = 1
    failures = contract_failures(result, cycles=3)

    assert "product_3d_tab_updates" in failures
    assert "product_3d_renders_installed" in failures


@pytest.mark.parametrize("status", ["SKIP", "BLOCKED"])
def test_stress_contract_requires_a_reason_when_interactive_3d_does_not_run(status):
    contract_failures = _load_stress_contract_function()
    result = _passing_stress_result()
    result["product_3d_status"] = status
    result["product_3d_block_reason"] = ""

    assert "product_3d_block_reason" in contract_failures(result, cycles=1)


def test_core_dump_limit_is_process_local_when_posix_supports_it(monkeypatch):
    setrlimit = MagicMock()
    getrlimit = MagicMock(return_value=(0, 0))
    resource_module = SimpleNamespace(
        RLIMIT_CORE=4,
        setrlimit=setrlimit,
        getrlimit=getrlimit,
    )
    disable = _load_core_limit_function(monkeypatch, resource_module)

    assert disable() is True
    setrlimit.assert_called_once_with(4, (0, 0))
    getrlimit.assert_called_once_with(4)


def test_core_dump_limit_fails_closed_when_zero_limit_cannot_be_verified(
    monkeypatch,
):
    resource_module = SimpleNamespace(
        RLIMIT_CORE=4,
        setrlimit=MagicMock(),
        getrlimit=MagicMock(return_value=(1, 1)),
    )
    disable = _load_core_limit_function(monkeypatch, resource_module)

    assert disable() is False


@pytest.mark.parametrize("failure", [AttributeError, OSError, ValueError])
def test_core_dump_limit_safely_skips_unsupported_runtimes(monkeypatch, failure):
    resource_module = SimpleNamespace(
        RLIMIT_CORE=4,
        setrlimit=MagicMock(side_effect=failure("unsupported")),
    )
    disable = _load_core_limit_function(monkeypatch, resource_module)

    assert disable() is False
