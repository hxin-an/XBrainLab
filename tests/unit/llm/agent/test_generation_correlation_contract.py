"""Strict generation-correlation guards for the desktop assistant runtime."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QObject

from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
)
from XBrainLab.llm.agent.turn_orchestrator import AssistantTurnOrchestrator
from XBrainLab.llm.agent.worker import AgentWorker


def _expression_path(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expression_path(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> set[str]:
    raw_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        path
        for target in raw_targets
        if isinstance(target, ast.expr)
        if (path := _expression_path(target)) is not None
    }


def _walk_function_scope(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
):
    """Walk one function body without leaking aliases across nested scopes."""
    pending: list[ast.AST] = list(reversed(function.body))
    while pending:
        node = pending.pop()
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _module_controller_symbols(
    tree: ast.Module,
) -> tuple[set[str], dict[str, str]]:
    constructors = {"LLMController"}
    imported_modules: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for imported in node.names:
                if imported.name == "LLMController":
                    constructors.add(imported.asname or imported.name)
                elif (
                    imported.name == "controller"
                    and node.module is not None
                    and node.module.endswith("llm.agent")
                ):
                    imported_modules[imported.asname or imported.name] = (
                        f"{node.module}.controller"
                    )
        elif isinstance(node, ast.Import):
            for imported in node.names:
                imported_modules[imported.asname or imported.name.split(".")[0]] = (
                    imported.name
                )

    changed = True
    while changed:
        changed = False
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in constructors:
                continue
            if _function_returns_controller(
                node,
                constructors,
                imported_modules,
            ):
                constructors.add(node.name)
                changed = True
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None:
                continue
            is_constructor_alias = _is_controller_constructor(
                value,
                constructors,
                imported_modules,
            )
            is_annotation_alias = not isinstance(
                value, ast.Call
            ) and _annotation_mentions_controller(
                value,
                constructors,
                imported_modules,
            )
            if not is_constructor_alias and not is_annotation_alias:
                continue
            aliases = {
                target for target in _assignment_targets(node) if "." not in target
            }
            if not aliases <= constructors:
                constructors.update(aliases)
                changed = True
    return constructors, imported_modules


def _is_controller_constructor(
    node: ast.expr,
    constructors: set[str],
    imported_modules: dict[str, str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in constructors
    path = _expression_path(node)
    if path is None or not path.endswith(".LLMController"):
        return False
    root = path.split(".", maxsplit=1)[0]
    module_name = imported_modules.get(root, "")
    return (
        module_name.endswith("llm.agent.controller")
        or ".llm.agent.controller.LLMController" in path
    )


def _annotation_mentions_controller(
    annotation: ast.expr | None,
    constructors: set[str],
    imported_modules: dict[str, str],
) -> bool:
    """Return whether an annotation denotes a controller instance.

    Optional/Union/Annotated are transparent wrappers around an instance type.
    Containers and callables are intentionally not transparent: a
    ``Callable[[], LLMController]`` is a factory, not a controller receiver.
    """
    if annotation is None:
        return False
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            parsed = ast.parse(annotation.value, mode="eval")
        except SyntaxError:
            return False
        return _annotation_mentions_controller(
            parsed.body,
            constructors,
            imported_modules,
        )
    if _is_controller_constructor(annotation, constructors, imported_modules):
        return True
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotation_mentions_controller(
            annotation.left,
            constructors,
            imported_modules,
        ) or _annotation_mentions_controller(
            annotation.right,
            constructors,
            imported_modules,
        )
    if not isinstance(annotation, ast.Subscript):
        return False
    wrapper = _expression_path(annotation.value)
    wrapper_name = wrapper.rsplit(".", maxsplit=1)[-1] if wrapper else ""
    arguments = (
        tuple(annotation.slice.elts)
        if isinstance(annotation.slice, ast.Tuple)
        else (annotation.slice,)
    )
    if wrapper_name == "Annotated":
        arguments = arguments[:1]
    elif wrapper_name not in {"Optional", "Union"}:
        return False
    return any(
        _annotation_mentions_controller(
            argument,
            constructors,
            imported_modules,
        )
        for argument in arguments
    )


def _function_returns_controller(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    constructors: set[str],
    imported_modules: dict[str, str],
) -> bool:
    """Infer factories from safe return annotations or local instance flow."""
    if _annotation_mentions_controller(
        function.returns,
        constructors,
        imported_modules,
    ):
        return True

    receivers: set[str] = set()
    changed = True
    scoped_nodes = tuple(_walk_function_scope(function))
    while changed:
        changed = False
        for node in scoped_nodes:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            value_path = _expression_path(value) if value is not None else None
            constructs_controller = isinstance(
                value, ast.Call
            ) and _is_controller_constructor(
                value.func,
                constructors,
                imported_modules,
            )
            annotation_is_controller = isinstance(
                node, ast.AnnAssign
            ) and _annotation_mentions_controller(
                node.annotation,
                constructors,
                imported_modules,
            )
            targets = _assignment_targets(node)
            if (
                constructs_controller
                or value_path in receivers
                or annotation_is_controller
            ) and not targets <= receivers:
                receivers.update(targets)
                changed = True

    for node in scoped_nodes:
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Call) and _is_controller_constructor(
            node.value.func,
            constructors,
            imported_modules,
        ):
            return True
        if _expression_path(node.value) in receivers:
            return True
    return False


def _function_controller_receivers(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    module_constructors: set[str],
    imported_modules: dict[str, str],
) -> tuple[set[str], set[str]]:
    constructors = set(module_constructors)
    constructors.update(
        node.name
        for node in function.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _function_returns_controller(
            node,
            constructors,
            imported_modules,
        )
    )
    receivers = {
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        if _annotation_mentions_controller(
            argument.annotation,
            constructors,
            imported_modules,
        )
    }

    changed = True
    while changed:
        changed = False
        for node in _walk_function_scope(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = _assignment_targets(node)
            value = node.value
            if value is not None and _is_controller_constructor(
                value,
                constructors,
                imported_modules,
            ):
                aliases = {target for target in targets if "." not in target}
                if not aliases <= constructors:
                    constructors.update(aliases)
                    changed = True
                continue

            constructs_controller = isinstance(
                value, ast.Call
            ) and _is_controller_constructor(
                value.func,
                constructors,
                imported_modules,
            )
            value_path = _expression_path(value) if value is not None else None
            aliases_controller = value_path in receivers
            annotation_is_controller = isinstance(
                node, ast.AnnAssign
            ) and _annotation_mentions_controller(
                node.annotation,
                constructors,
                imported_modules,
            )
            if (
                constructs_controller or aliases_controller or annotation_is_controller
            ) and not targets <= receivers:
                receivers.update(targets)
                changed = True
    return constructors, receivers


def _module_controller_receivers(
    tree: ast.Module,
    constructors: set[str],
    imported_modules: dict[str, str],
) -> set[str]:
    receivers: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = _assignment_targets(node)
            value = node.value
            constructs_controller = isinstance(
                value, ast.Call
            ) and _is_controller_constructor(
                value.func,
                constructors,
                imported_modules,
            )
            value_path = _expression_path(value) if value is not None else None
            annotation_is_controller = isinstance(
                node, ast.AnnAssign
            ) and _annotation_mentions_controller(
                node.annotation,
                constructors,
                imported_modules,
            )
            if (
                constructs_controller
                or value_path in receivers
                or annotation_is_controller
            ) and not targets <= receivers:
                receivers.update(targets)
                changed = True
    return receivers


def _is_direct_controller_input_call(
    node: ast.AST,
    constructors: set[str],
    receivers: set[str],
    imported_modules: dict[str, str],
) -> bool:
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Attribute)
        or node.func.attr != "handle_user_input"
    ):
        return False
    receiver = node.func.value
    receiver_path = _expression_path(receiver)
    direct_construction = isinstance(receiver, ast.Call) and _is_controller_constructor(
        receiver.func,
        constructors,
        imported_modules,
    )
    return receiver_path in receivers or direct_construction


def _walk_module_scope(tree: ast.Module):
    pending: list[ast.AST] = list(reversed(tree.body))
    while pending:
        node = pending.pop()
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _node_line(node: ast.AST) -> int:
    """Return the source line for a parsed node used in one violation."""
    return int(getattr(node, "lineno", 0))


def _direct_controller_input_calls(
    source: str,
) -> list[tuple[str, int]]:
    tree = ast.parse(source)
    module_constructors, imported_modules = _module_controller_symbols(tree)
    violations: list[tuple[str, int]] = []
    module_receivers = _module_controller_receivers(
        tree,
        module_constructors,
        imported_modules,
    )
    violations.extend(
        ("<module>", _node_line(node))
        for node in _walk_module_scope(tree)
        if _is_direct_controller_input_call(
            node,
            module_constructors,
            module_receivers,
            imported_modules,
        )
    )
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        constructors, receivers = _function_controller_receivers(
            function,
            module_constructors,
            imported_modules,
        )
        violations.extend(
            (function.name, _node_line(node))
            for node in _walk_function_scope(function)
            if _is_direct_controller_input_call(
                node,
                constructors,
                receivers,
                imported_modules,
            )
        )
    return violations


def test_worker_exposes_only_correlated_generation_signals() -> None:
    assert "finished" not in AgentWorker.__dict__
    assert "chunk_received" not in AgentWorker.__dict__
    assert "generation_finished" in AgentWorker.__dict__
    assert "generation_chunk_received" in AgentWorker.__dict__
    assert "generation_error" in AgentWorker.__dict__
    assert "generation_dispatch_acknowledged" in AgentWorker.__dict__


def test_generation_dispatch_acknowledgement_is_typed_and_correlated() -> None:
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    assert accepted.generation_id == started.generation_id
    assert accepted.phase is AssistantGenerationDispatchPhase.ACCEPTED
    assert started.phase is AssistantGenerationDispatchPhase.STARTED


def test_host_turn_delivery_acknowledgement_is_typed_and_correlated() -> None:
    correlation = AssistantTurnCorrelation(generation=7, turn_id=13)

    accepted = AssistantTurnDeliveryAcknowledgement(
        correlation=correlation,
        phase=AssistantTurnDeliveryPhase.ACCEPTED,
    )
    failed = AssistantTurnDeliveryAcknowledgement(
        correlation=correlation,
        phase=AssistantTurnDeliveryPhase.ERROR,
        message="controller setup failed",
    )

    assert accepted.correlation == failed.correlation
    assert accepted.phase is AssistantTurnDeliveryPhase.ACCEPTED
    assert failed.phase is AssistantTurnDeliveryPhase.ERROR
    assert failed.message == "controller setup failed"


def test_host_turn_delivery_error_redacts_private_exception_context() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"

    failed = AssistantTurnDeliveryAcknowledgement(
        correlation=AssistantTurnCorrelation(generation=7, turn_id=13),
        phase=AssistantTurnDeliveryPhase.ERROR,
        message=f"Controller failed for {private_path}; subject_id=Alice-Smith.",
    )

    assert private_path not in failed.message
    assert "subject-17" not in failed.message
    assert "Alice-Smith" not in failed.message
    assert "events.tsv" in failed.message
    assert "[REDACTED_PATH]" in failed.message
    assert "[SUBJECT_REF:" in failed.message


def test_controller_has_a_distinct_worker_dispatch_acknowledgement_handler() -> None:
    parameters = list(
        inspect.signature(
            LLMController._on_generation_dispatch_acknowledged
        ).parameters.values()
    )
    assert [parameter.name for parameter in parameters] == ["self", "payload"]
    assert parameters[1].default is inspect.Parameter.empty


def test_dispatch_acknowledgements_are_ordered_exactly_once_and_correlated() -> None:
    controller = LLMController.__new__(LLMController)
    QObject.__init__(controller)
    controller._turn_orchestrator = AssistantTurnOrchestrator()
    controller._turn_orchestrator.active_generation_id = 41
    controller._turn_orchestrator.dispatch_phase = None
    controller._turn_orchestrator.cancelled = False
    controller._closing = False
    controller._closed = False
    controller.generation_event = MagicMock()
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)
    controller._on_generation_dispatch_acknowledged(started)

    assert (
        controller._turn_orchestrator.dispatch_phase
        is AssistantGenerationDispatchPhase.STARTED
    )
    controller.generation_event.emit.assert_called_once_with(
        AssistantGenerationEvent(
            generation_id=41,
            phase=AssistantGenerationEventPhase.STARTED,
        )
    )

    controller._turn_orchestrator.active_generation_id = 42
    controller._turn_orchestrator.dispatch_phase = None
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)

    assert controller._turn_orchestrator.dispatch_phase is None
    assert controller.generation_event.emit.call_count == 1


def test_cancelled_or_closing_turn_ignores_late_dispatch_acknowledgements() -> None:
    controller = LLMController.__new__(LLMController)
    QObject.__init__(controller)
    controller._turn_orchestrator = AssistantTurnOrchestrator()
    controller._turn_orchestrator.active_generation_id = 51
    controller._turn_orchestrator.dispatch_phase = None
    controller._turn_orchestrator.cancelled = True
    controller._closing = False
    controller._closed = False
    controller.generation_event = MagicMock()
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=51,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=51,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)
    controller._turn_orchestrator.cancelled = False
    controller._closing = True
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)

    assert controller._turn_orchestrator.dispatch_phase is None
    controller.generation_event.emit.assert_not_called()


def test_generation_stop_channel_is_typed_and_requires_a_request() -> None:
    worker_source = inspect.getsource(AgentWorker)
    assert "generation_stop_finished = pyqtSignal(object)" in worker_source
    assert "generation_stop_finished = pyqtSignal(bool)" not in worker_source

    parameters = list(
        inspect.signature(AgentWorker.cancel_generation).parameters.values()
    )
    assert [parameter.name for parameter in parameters] == ["self", "payload"]
    assert parameters[1].default is inspect.Parameter.empty


def test_controller_generation_callbacks_require_explicit_correlation() -> None:
    for callback_name in (
        "_on_chunk_received",
        "_on_generation_finished",
        "_on_generation_error",
    ):
        parameters = list(
            inspect.signature(getattr(LLMController, callback_name)).parameters.values()
        )[1:]
        assert parameters
        assert all(
            parameter.default is inspect.Parameter.empty for parameter in parameters
        )


def test_runtime_and_generation_errors_have_distinct_handlers() -> None:
    assert hasattr(LLMController, "_on_runtime_error")
    assert hasattr(LLMController, "_on_generation_error")
    assert not hasattr(LLMController, "_on_uncorrelated_worker_error")
    assert not hasattr(LLMController, "_on_worker_error")


def test_product_walkthrough_scripts_avoid_legacy_generation_channels() -> None:
    forbidden = (
        "agent_controller.worker",
        "controller.worker",
        "_active_generation_id",
        "generation_started = pyqtSignal",
        "generation_started.emit(",
        "generation_started.connect(",
    )
    violations: list[str] = []
    for path in Path("scripts/dev").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        violations.extend(f"{path}: {token}" for token in forbidden if token in source)

    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: LLMController) -> None:
            controller.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: "LLMController") -> None:
            controller.handle_user_input("bad")
        """,
        """
        from typing import Optional
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: Optional[LLMController]) -> None:
            controller.handle_user_input("bad")
        """,
        """
        from typing import Optional
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: "Optional[LLMController]") -> None:
            controller.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: LLMController | None) -> None:
            controller.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(controller: "LLMController | None") -> None:
            controller.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(study: object) -> None:
            LLMController(study).handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        LLMController(object()).handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        Controller = LLMController
        ControllerAlias = Controller
        def bad(study: object) -> None:
            ControllerAlias(study).handle_user_input("bad")
        """,
        """
        import XBrainLab.llm.agent.controller as controller_module
        def bad(study: object) -> None:
            controller_module.LLMController(study).handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent import controller as controller_module
        def bad(study: object) -> None:
            controller_module.LLMController(study).handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(study: object) -> None:
            controller = LLMController(study)
            alias = controller
            alias.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def bad(host: object) -> None:
            host.controller: LLMController
            host.controller.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def build_controller() -> LLMController:
            return LLMController(object())
        def bad() -> None:
            build_controller().handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def build_controller() -> "LLMController | None":
            return LLMController(object())
        def bad() -> None:
            controller = build_controller()
            controller.handle_user_input("bad")
        """,
        """
        from typing import Annotated, Optional
        from XBrainLab.llm.agent.controller import LLMController
        def build_controller() -> Annotated[Optional[LLMController], "runtime"]:
            return LLMController(object())
        factory = build_controller
        factory_alias = factory
        def bad() -> None:
            controller = factory_alias()
            instance_alias = controller
            instance_alias.handle_user_input("bad")
        """,
        """
        from XBrainLab.llm.agent.controller import LLMController
        def build_controller():
            controller = LLMController(object())
            return controller
        def bad() -> None:
            controller = build_controller()
            controller.handle_user_input("bad")
        """,
    ],
    ids=[
        "direct-annotation",
        "string-annotation",
        "optional-union",
        "string-optional-union",
        "pep604-union",
        "string-pep604-union",
        "direct-constructor-call",
        "module-direct-constructor-call",
        "constructor-alias-fixed-point",
        "module-attribute-constructor",
        "from-import-module-constructor",
        "instance-alias-fixed-point",
        "annotated-attribute-receiver",
        "factory-direct-call",
        "factory-string-pep604-return",
        "annotated-optional-factory-alias-chain",
        "inferred-factory-return",
    ],
)
def test_direct_controller_input_guard_mutation_matrix(source: str) -> None:
    assert _direct_controller_input_calls(dedent(source))


def test_direct_controller_input_guard_allows_manager_receiver() -> None:
    source = dedent(
        """
        from XBrainLab.llm.agent.controller import LLMController
        from XBrainLab.ui.components.agent_manager import AgentManager

        def legal(manager: AgentManager) -> None:
            manager.handle_user_input("legal")
        """
    )

    assert _direct_controller_input_calls(source) == []


@pytest.mark.parametrize(
    "source",
    [
        """
        from collections.abc import Callable
        from XBrainLab.llm.agent.controller import LLMController

        def legal(factory: Callable[[], LLMController]) -> None:
            factory.handle_user_input("callable-owned method")
        """,
        """
        from collections.abc import Callable
        from XBrainLab.llm.agent.controller import LLMController

        def build_factory() -> Callable[[], LLMController]:
            return lambda: LLMController(object())

        callback = build_factory()
        callback.handle_user_input("callable-owned method")
        """,
    ],
    ids=["callable-parameter", "callable-factory-result"],
)
def test_direct_controller_input_guard_does_not_treat_callable_as_instance(
    source: str,
) -> None:
    assert _direct_controller_input_calls(dedent(source)) == []


def test_product_and_tests_use_typed_host_turn_admission() -> None:
    """Keep direct controller input calls isolated to the fail-closed regression."""
    allowed = {
        (
            Path("tests/unit/llm/agent/test_controller_integration.py"),
            "test_direct_uncorrelated_user_input_fails_closed",
        )
    }
    violations: list[str] = []
    roots = (Path("XBrainLab"), Path("tests"), Path("scripts"))
    for root in roots:
        for path in root.rglob("*.py"):
            for function_name, line_number in _direct_controller_input_calls(
                path.read_text(encoding="utf-8")
            ):
                if (path, function_name) not in allowed:
                    violations.append(f"{path}:{line_number}:{function_name}")

    assert violations == []
