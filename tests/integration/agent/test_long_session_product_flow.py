"""Bounded Qt product soak for long assistant conversations."""

from __future__ import annotations

import json
from itertools import pairwise
from time import monotonic
from typing import Any, cast
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application import (
    LoadDataCommand,
    ResetSessionCommand,
    get_application_service,
)
from XBrainLab.backend.application.pipeline_stage import pipeline_stage_status_label
from XBrainLab.backend.controller.chat_controller import (
    ChatActionState,
    ChatController,
    ChatMessagePresentationKind,
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.backend.study import Study
from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MODEL_REQUEST_UTF8_BYTES,
)
from XBrainLab.llm.agent.context_encoding import decode_untrusted_context
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.product_turn_policy import ProductTurnPolicy
from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationRequest,
    AssistantResponseContract,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeCommandAdmissionStatus,
)
from XBrainLab.ui.components.assistant_status_projection import (
    build_assistant_status_projection,
)

_PRUNE_NOTICE = (
    "Older messages were removed from this view to keep the conversation responsive."
)
_HARD_BLOCK_NOTICE = (
    "Chat history is full. Clear the conversation before sending another request."
)
_EARLIER_ACTION_REQUEST = "Use the option you recommended earlier."


class _RawState:
    """Small state object sufficient for the real ApplicationService snapshot."""

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath

    def get_filepath(self) -> str:
        return self._filepath

    def get_filename(self) -> str:
        return "external-session.fif"

    def get_subject_name(self) -> str:
        return "S01"

    def get_session_name(self) -> str:
        return "session-01"

    def get_mne(self) -> object:
        return type("MNE", (), {"ch_names": ["C3", "C4"]})()

    def get_preprocess_history(self) -> list[str]:
        return []


class _DeterministicRagRetriever:
    """Cheap retrieval double at the external embedding/index boundary."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.requests: list[tuple[str, frozenset[str] | None]] = []

    def initialize(self) -> None:
        self.started = True

    def get_similar_examples(
        self,
        text: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        self.requests.append((text, allowed_tool_names))
        return ""

    def close(self) -> None:
        self.closed = True


class _ImmediateRagLifecycle:
    """Run deterministic retrieval without bypassing controller RAG admission."""

    def __init__(self, retriever: _DeterministicRagRetriever) -> None:
        self.retriever = retriever

    def start(self) -> bool:
        self.retriever.initialize()
        return True

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: Any,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        callback(
            turn_id,
            query,
            self.retriever.get_similar_examples(
                query,
                allowed_tool_names=allowed_tool_names,
            ),
            "",
        )
        return True

    def close(self) -> bool:
        self.retriever.close()
        return True


class _DeterministicModelWorker(AgentWorker):
    """Worker-contract model double that still crosses the queued Qt boundary."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[AssistantGenerationRequest] = []

    def generate_from_messages(self, request: AssistantGenerationRequest) -> None:
        self.requests.append(request)
        generation_id = request.generation_id
        response_text = f"Bounded deterministic response {len(self.requests)}."
        if request.response_contract is AssistantResponseContract.STRUCTURED_ACTION:
            response_text = json.dumps(
                {
                    "tool_name": "respond_to_user",
                    "parameters": {
                        "decision": "answer",
                        "message": response_text,
                    },
                },
                separators=(",", ":"),
            )
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=generation_id,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=generation_id,
                phase=AssistantGenerationDispatchPhase.STARTED,
            )
        )
        self.generation_chunk_received.emit(
            generation_id,
            response_text,
        )
        self.generation_finished.emit(generation_id, [])

    def shutdown(self, wait_ms: int = 0) -> bool:
        del wait_ms
        self.shutdown_finished.emit(True)
        return True


class _ControllerRuntime(QObject):
    """Lifecycle-shaped host around the real product agent controller."""

    controller_created = pyqtSignal(object)
    runtime_snapshot_changed = pyqtSignal(object)
    turn_finished = pyqtSignal(object)

    def __init__(
        self,
        controller: LLMController,
        rag_lifecycle: _ImmediateRagLifecycle,
    ) -> None:
        super().__init__()
        self.controller = controller
        self._rag_lifecycle = rag_lifecycle
        self.initialized = True
        self.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="deterministic-long-session-model",
        )
        self.admissions: list[RuntimeCommandAdmissionResult] = []
        self.terminals: list[AssistantTurnTerminal] = []
        self._started = False
        self._next_turn_id = 1
        controller.turn_finished.connect(self._forward_terminal)

    def _forward_terminal(self, payload: object) -> None:
        if isinstance(payload, AssistantTurnTerminal):
            self.terminals.append(payload)
        self.turn_finished.emit(payload)

    def replay_runtime_snapshot(self) -> None:
        self.runtime_snapshot_changed.emit(self.current)

    def start(self) -> bool:
        if not self._started:
            self._started = True
            self._rag_lifecycle.start()
            self.controller_created.emit(self.controller)
        self.runtime_snapshot_changed.emit(self.current)
        return True

    def submit(
        self,
        text: str,
        *,
        generation: int | None = None,
    ) -> RuntimeCommandAdmissionResult:
        correlation = AssistantTurnCorrelation(
            generation=1 if generation is None else generation,
            turn_id=self._next_turn_id,
        )
        self._next_turn_id += 1
        delivery = self.controller.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=correlation,
                text=text,
            )
        )
        accepted = delivery.phase is AssistantTurnDeliveryPhase.ACCEPTED
        admission = RuntimeCommandAdmissionResult(
            command_name="submit",
            status=(
                RuntimeCommandAdmissionStatus.ACCEPTED
                if accepted
                else RuntimeCommandAdmissionStatus.REJECTED
            ),
            message=delivery.message,
            turn_id=correlation.turn_id if accepted else None,
            generation=correlation.generation if accepted else None,
        )
        self.admissions.append(admission)
        return admission

    def activate_persisted(self) -> RuntimeActivationResult:
        return RuntimeActivationResult(RuntimeActivationStatus.ALREADY_READY)

    def active_local_runtime_blocks_model_deletion(self) -> bool:
        return False

    def close(self) -> bool:
        return self.controller.close()


def _send_ui_turn(
    manager: AgentManager,
    runtime: _ControllerRuntime,
    text: str,
    qtbot: Any,
) -> tuple[float, int]:
    panel = manager.chat_panel
    assert panel is not None
    admission_count = len(runtime.admissions)
    terminal_count = len(runtime.terminals)
    panel.input_field.setText(text)

    started = monotonic()
    panel._on_send()
    pruned_at_boundary = manager.chat_controller.pruned_row_count
    qtbot.waitUntil(
        lambda: len(runtime.terminals) == terminal_count + 1,
        timeout=2_000,
    )
    latency = monotonic() - started

    assert len(runtime.admissions) == admission_count + 1
    assert runtime.admissions[-1].accepted
    assert runtime.terminals[-1].outcome == "completed"
    assert manager.chat_controller.pruned_row_count == pruned_at_boundary
    return latency, pruned_at_boundary


def _request_latest_user_text(request: AssistantGenerationRequest) -> str:
    for message in reversed(request.to_model_messages()):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and decode_untrusted_context(content) is None:
                return content
    raise AssertionError("Model request omitted the latest user turn.")


def _request_workflow_stage(request: AssistantGenerationRequest) -> str:
    for message in request.to_model_messages():
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != "xbrainlab.untrusted_context.v1"
            or payload.get("trust") != "untrusted"
        ):
            continue
        items = payload.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "workflow_decision":
                continue
            assert item.get("source") == {"kind": "application_service_publication"}
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            stage = data.get("workflow_stage")
            if isinstance(stage, str):
                return stage
    raise AssertionError("Model request omitted current workflow publication context.")


def _request_utf8_bytes(request: AssistantGenerationRequest) -> int:
    encoded = json.dumps(
        request.to_model_messages(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return len(encoded.encode("utf-8"))


def _record_by_message_id(
    records: tuple[ChatMessageRecord, ...],
    message_id: str,
) -> ChatMessageRecord | None:
    return next((record for record in records if record.message_id == message_id), None)


def _layout_bubble_ids(panel: Any) -> list[str]:
    ids: list[str] = []
    for index in range(panel.chat_layout.count()):
        item = panel.chat_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, MessageBubble):
            message_id = widget.property("chatMessageId")
            assert isinstance(message_id, str) and message_id
            ids.append(message_id)
    return ids


def _assert_turn_transcript_parity(
    *,
    before_records: tuple[ChatMessageRecord, ...],
    before_bubble_ids: list[str],
    after_records: tuple[ChatMessageRecord, ...],
    after_bubble_ids: list[str],
    rows_pruned: int,
    prompt: str,
) -> None:
    """Prove one admitted turn produced exactly one user/assistant UI pair."""
    assert 0 <= rows_pruned <= len(before_records)
    before_ids = [record.message_id for record in before_records]
    assert before_bubble_ids == before_ids[: len(before_bubble_ids)]
    retained_ids = before_ids[rows_pruned:]
    after_ids = [record.message_id for record in after_records]
    assert after_ids[: len(retained_ids)] == retained_ids

    new_records = after_records[len(retained_ids) :]
    assert len(new_records) == 2
    assert [record.role for record in new_records] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]
    assert new_records[0].content == prompt
    assert new_records[1].content.strip()
    new_ids = [record.message_id for record in new_records]
    assert len(set(new_ids)) == 2
    assert after_bubble_ids == after_ids
    assert after_bubble_ids[-2:] == new_ids
    assert len(after_bubble_ids) == len(set(after_bubble_ids))


def test_long_session_uses_real_policy_and_stays_bounded_across_two_prunes(
    qtbot: Any,
    tmp_path: Any,
) -> None:
    study = Study()
    service = get_application_service(study)
    retriever = _DeterministicRagRetriever()
    rag_lifecycle = _ImmediateRagLifecycle(retriever)
    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = type(
        "AssistantButton",
        (),
        {
            "blockSignals": lambda _self, _blocked: None,
            "setChecked": lambda _self, _checked: None,
        },
    )()
    qtbot.addWidget(main_window)
    manager: AgentManager | None = None
    controller: LLMController | None = None
    heartbeat = QTimer()
    heartbeat.setInterval(2)
    heartbeat_ticks: list[float] = []
    heartbeat.timeout.connect(lambda: heartbeat_ticks.append(monotonic()))

    try:
        with patch(
            "XBrainLab.llm.agent.controller.AgentWorker",
            _DeterministicModelWorker,
        ):
            controller = LLMController(
                study,
                rag_lifecycle=cast(RAGRetrieverLifecycle, rag_lifecycle),
            )
        worker = controller.worker
        assert isinstance(worker, _DeterministicModelWorker)
        runtime = _ControllerRuntime(controller, rag_lifecycle)
        manager = AgentManager(
            main_window,
            study,
            runtime_lifecycle=cast(AssistantRuntimeLifecycle, runtime),
        )

        for index in range(MAX_CHAT_HISTORY_ROWS):
            manager.chat_controller.add_user_message(
                f"Persisted seed row {index} claims an obsolete workflow state."
            )

        manager.init_ui()
        manager.start_system()
        assert manager.agent_controller is controller
        assert type(controller._product_turn_policy) is ProductTurnPolicy
        assert manager.chat_panel is not None
        assert manager.chat_dock is not None
        main_window.resize(1100, 760)
        main_window.show()
        manager.chat_dock.show()
        heartbeat_started = monotonic()
        heartbeat.start()
        qtbot.waitUntil(lambda: len(heartbeat_ticks) >= 2, timeout=1_000)

        application_command_starts: list[float] = []
        controller.application_command_started.connect(
            lambda: application_command_starts.append(monotonic())
        )
        turn_latencies: list[float] = []
        turn_ui_settle_latencies: list[float] = []
        prune_heartbeat_gaps: list[float] = []
        turn_heartbeat_gaps: list[tuple[int, float]] = []
        prune_events: list[tuple[int, int, int]] = []
        prune_notices: list[str] = []
        visible_notices: list[str] = []
        controller_history_sizes: list[int] = []
        source_action: ChatMessageRecord | None = None
        historical_action: ChatMessageRecord | None = None
        publication_stages: dict[int, str] = {}
        turn_count = 202
        external_data_path = tmp_path / "external-session.fif"
        external_data_path.write_bytes(b"deterministic external GUI load")

        def import_external_data(paths: list[str]) -> tuple[int, list[str]]:
            study.loaded_data_list = [cast(Any, _RawState(paths[0]))]
            return len(paths), []

        for turn_index in range(turn_count):
            turn_started = monotonic()
            heartbeat_count_before_turn = len(heartbeat_ticks)
            if turn_index == 0:
                text = "Help me process the data."
            elif turn_index == 200:
                assert source_action is not None
                assert (
                    _record_by_message_id(
                        manager.chat_controller.get_typed_history(),
                        source_action.message_id,
                    )
                    is None
                )
                evidence_before_reference = (
                    len(retriever.requests),
                    len(worker.requests),
                    len(application_command_starts),
                )
                text = _EARLIER_ACTION_REQUEST
            else:
                text = f"Record a bounded session checkpoint for turn {turn_index}."

            if turn_index == turn_count // 4:
                with patch.object(
                    service.dataset,
                    "import_files",
                    side_effect=import_external_data,
                ):
                    result = service.execute(
                        LoadDataCommand(paths=[str(external_data_path)])
                    )
                assert result.success is True
                publication = service.get_view_publication()
                assert publication.state.pipeline_stage == "data_loaded"
                expected_revision = publication.revision
                qtbot.waitUntil(
                    lambda expected_revision=expected_revision: manager is not None
                    and manager.assistant_status_projection is not None
                    and manager.assistant_status_projection.publication_revision
                    == expected_revision,
                    timeout=2_000,
                )
            elif turn_index == (turn_count * 3) // 4:
                result = service.execute(ResetSessionCommand(confirmed=True))
                assert result.success is True
                publication = service.get_view_publication()
                assert publication.state.pipeline_stage == "empty"
                expected_revision = publication.revision
                qtbot.waitUntil(
                    lambda expected_revision=expected_revision: manager is not None
                    and manager.assistant_status_projection is not None
                    and manager.assistant_status_projection.publication_revision
                    == expected_revision,
                    timeout=2_000,
                )

            if turn_index in {turn_count // 3, (turn_count * 2) // 3}:
                main_window.resize(
                    960 if turn_index == turn_count // 3 else 1240,
                    700 if turn_index == turn_count // 3 else 820,
                )

            records_before_turn = manager.chat_controller.get_typed_history()
            bubble_ids_before_turn = _layout_bubble_ids(manager.chat_panel)
            pruned_before = manager.chat_controller.pruned_row_count
            latency, pruned_at_boundary = _send_ui_turn(
                manager,
                runtime,
                text,
                qtbot,
            )
            turn_latencies.append(latency)
            if pruned_at_boundary != pruned_before:
                prune_events.append((turn_index, pruned_before, pruned_at_boundary))
                prune_notices.append(manager.chat_panel.notice_label.text())
                assert (
                    manager.chat_controller.get_typed_history()[0].role
                    is ChatMessageRole.USER
                )
                expected_ids = [
                    record.message_id
                    for record in manager.chat_controller.get_typed_history()
                ]
                qtbot.waitUntil(
                    lambda expected_ids=expected_ids: _layout_bubble_ids(
                        manager.chat_panel
                    )
                    == expected_ids,
                    timeout=5_000,
                )
            visible_notices.append(manager.chat_panel.notice_label.text())
            controller_history_sizes.append(len(controller.history))
            expected_turn_ids = [
                record.message_id
                for record in manager.chat_controller.get_typed_history()
            ]
            try:
                qtbot.waitUntil(
                    lambda expected_turn_ids=expected_turn_ids: _layout_bubble_ids(
                        manager.chat_panel
                    )
                    == expected_turn_ids,
                    timeout=2_000,
                )
            except Exception as exc:
                actual_turn_ids = _layout_bubble_ids(manager.chat_panel)
                pytest.fail(
                    "typed transcript did not converge after turn "
                    f"{turn_index}: expected={len(expected_turn_ids)} "
                    f"actual={len(actual_turn_ids)} "
                    f"phase={manager.chat_panel._history_rebuild_phase} "
                    f"deltas={len(manager.chat_panel._history_rebuild_deltas)}; "
                    f"{exc}"
                )
            _assert_turn_transcript_parity(
                before_records=records_before_turn,
                before_bubble_ids=bubble_ids_before_turn,
                after_records=manager.chat_controller.get_typed_history(),
                after_bubble_ids=_layout_bubble_ids(manager.chat_panel),
                rows_pruned=pruned_at_boundary - pruned_before,
                prompt=text,
            )
            qtbot.waitUntil(
                lambda heartbeat_count_before_turn=heartbeat_count_before_turn: (
                    len(heartbeat_ticks) > heartbeat_count_before_turn
                ),
                timeout=1_000,
            )
            turn_ticks = heartbeat_ticks[max(0, heartbeat_count_before_turn - 1) :]
            turn_tick_gaps = [
                current - previous for previous, current in pairwise(turn_ticks)
            ]
            if turn_tick_gaps:
                turn_heartbeat_gaps.append((turn_index, max(turn_tick_gaps)))
            turn_ui_settle_latencies.append(monotonic() - turn_started)
            if pruned_at_boundary != pruned_before:
                prune_ticks = heartbeat_ticks[max(0, heartbeat_count_before_turn - 1) :]
                prune_heartbeat_gaps.extend(
                    current - previous for previous, current in pairwise(prune_ticks)
                )

            if turn_index == 0:
                source_action = manager.chat_controller.get_typed_history()[-1]
                assert (
                    source_action.presentation_kind
                    is ChatMessagePresentationKind.CLARIFICATION
                )
                assert source_action.has_active_actions
                assert manager._active_response_presentation_id == (
                    source_action.presentation_id
                )
                assert manager.chat_panel.response_actions_widget.isVisible()
                assert retriever.requests == []
                assert worker.requests == []
            elif turn_index == 1:
                assert source_action is not None
                consumed = _record_by_message_id(
                    manager.chat_controller.get_typed_history(),
                    source_action.message_id,
                )
                assert consumed is not None
                assert consumed.action_state is ChatActionState.CONSUMED
                assert not consumed.has_active_actions
                assert manager._active_response_presentation_id is None
                assert not manager.chat_panel.response_actions_widget.isVisible()
            elif turn_index in {
                turn_count // 4,
                (turn_count * 3) // 4,
            }:
                model_request = worker.requests[-1]
                assert _request_latest_user_text(model_request) == text
                publication_stages[turn_index] = _request_workflow_stage(model_request)
            elif turn_index == 200:
                assert evidence_before_reference == (
                    len(retriever.requests),
                    len(worker.requests),
                    len(application_command_starts),
                )
                historical_action = manager.chat_controller.get_typed_history()[-1]
                assert (
                    historical_action.presentation_kind
                    is ChatMessagePresentationKind.CLARIFICATION
                )
                assert "which earlier option" in historical_action.content
                assert historical_action.has_active_actions
                assert manager._active_response_presentation_id == (
                    historical_action.presentation_id
                )
                assert manager.chat_panel.response_actions_widget.isVisible()
                assert controller._tool_attempt_session.execution_count == 0
                assert not controller.is_processing
            elif turn_index == 201:
                assert historical_action is not None
                consumed = _record_by_message_id(
                    manager.chat_controller.get_typed_history(),
                    historical_action.message_id,
                )
                assert consumed is not None
                assert consumed.action_state is ChatActionState.CONSUMED
                assert not consumed.has_active_actions
                assert manager._active_response_presentation_id is None
                assert not manager.chat_panel.response_actions_widget.isVisible()

            if turn_index % 8 == 0:
                qtbot.wait(5)

        qtbot.waitUntil(
            lambda: manager is not None
            and manager.chat_panel is not None
            and len(manager.chat_panel.chat_content_widget.findChildren(MessageBubble))
            == len(manager.chat_controller.get_typed_history()),
            timeout=5_000,
        )
        heartbeat_stopped = monotonic()
        heartbeat.stop()
        publication = service.get_view_publication()
        qtbot.waitUntil(
            lambda: manager is not None
            and manager.assistant_status_projection is not None
            and manager.assistant_status_projection.publication_revision
            == publication.revision,
            timeout=2_000,
        )

        first_prune = MAX_CHAT_HISTORY_ROWS - CHAT_HISTORY_LIVE_WINDOW_ROWS
        second_prune = first_prune + (
            MAX_CHAT_HISTORY_ROWS - CHAT_HISTORY_LIVE_WINDOW_ROWS - 2
        )
        assert prune_events == [
            (0, 0, first_prune),
            (199, first_prune, second_prune),
        ]
        assert prune_notices == [_PRUNE_NOTICE, _PRUNE_NOTICE]
        assert _HARD_BLOCK_NOTICE not in visible_notices
        assert all(admission.accepted for admission in runtime.admissions)
        assert len(runtime.admissions) == turn_count
        assert len(runtime.terminals) == turn_count
        assert {terminal.outcome for terminal in runtime.terminals} == {"completed"}

        assert publication_stages == {
            turn_count // 4: pipeline_stage_status_label("data_loaded"),
            (turn_count * 3) // 4: pipeline_stage_status_label("empty"),
        }
        assert manager.assistant_status_projection == (
            build_assistant_status_projection(publication)
        )
        assert publication.state.pipeline_stage == "empty"

        records = manager.chat_controller.get_typed_history()
        persisted = manager.chat_controller.get_history()
        layout_bubbles: list[MessageBubble] = []
        for index in range(manager.chat_panel.chat_layout.count()):
            item = manager.chat_panel.chat_layout.itemAt(index)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, MessageBubble):
                layout_bubbles.append(widget)

        assert len(records) == (
            MAX_CHAT_HISTORY_ROWS
            + turn_count * 2
            - manager.chat_controller.pruned_row_count
        )
        assert len(records) <= MAX_CHAT_HISTORY_ROWS
        assert len(persisted) == len(records)
        layout_ids = [bubble.property("chatMessageId") for bubble in layout_bubbles]
        record_ids = [record.message_id for record in records]
        assert layout_ids == record_ids
        assert len(layout_ids) == len(set(layout_ids))
        restored = ChatController()
        assert restored.restore_history(persisted) == len(records)
        restored_records = restored.get_typed_history()
        assert [
            (
                record.role,
                record.content,
                record.presentation_kind,
                record.message_id,
                record.actions,
            )
            for record in restored_records
        ] == [
            (
                record.role,
                record.content,
                record.presentation_kind,
                record.message_id,
                record.actions,
            )
            for record in records
        ]
        assert not any(record.has_active_actions for record in restored_records)
        normalized_persistence = restored.get_history()
        canonical_restore = ChatController()
        assert canonical_restore.restore_history(normalized_persistence) == len(records)
        assert canonical_restore.get_history() == normalized_persistence

        assert max(controller_history_sizes) <= LLMController.MAX_HISTORY
        assert len(controller.history) <= LLMController.MAX_HISTORY
        assert len(worker.requests) == turn_count - 2
        assert len(retriever.requests) == len(worker.requests)
        assert application_command_starts == []
        assert all(
            _request_utf8_bytes(request) <= MAX_CHAT_MODEL_REQUEST_UTF8_BYTES
            for request in worker.requests
        )

        assert heartbeat_ticks
        heartbeat_gaps = [
            current - previous for previous, current in pairwise(heartbeat_ticks)
        ]
        assert heartbeat_gaps
        assert prune_heartbeat_gaps
        assert max(prune_heartbeat_gaps) < 0.25
        worst_turn_gap = max(turn_heartbeat_gaps, key=lambda item: item[1])
        assert max(heartbeat_gaps) < 0.5, worst_turn_gap
        assert len(heartbeat_ticks) >= turn_count + 2
        assert (
            heartbeat_ticks[-1] - heartbeat_ticks[0]
            >= (heartbeat_stopped - heartbeat_started) * 0.9
        )
        assert max(turn_latencies) < 0.75
        assert sum(turn_latencies) / len(turn_latencies) < 0.4
        assert max(turn_ui_settle_latencies) < 0.75
    finally:
        heartbeat.stop()
        if manager is not None:
            closed = manager.close()
            if controller is not None and not closed:
                qtbot.waitUntil(lambda: controller is not None and controller._closed)
                assert controller.close() is True
