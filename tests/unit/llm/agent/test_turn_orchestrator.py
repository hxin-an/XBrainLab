from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.response_presentation import (
    AssistantResponseKind,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchPhase,
    AssistantGenerationEventPhase,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnScope,
)
from XBrainLab.llm.agent.turn_orchestrator import (
    AssistantToolAttemptSession,
    AssistantTurnOrchestrator,
)


def _request(*, turn_id: int = 11, generation: int = 7) -> AssistantTurnRequest:
    return AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(
            generation=generation,
            turn_id=turn_id,
        ),
        text="Prepare training",
        scope=AssistantTurnScope.GUIDED_WORKFLOW,
        terminal_command=CommandName.TRAIN.value,
        excluded_commands=(CommandName.CLEAR_DATASETS,),
    )


def test_turn_terminal_consumes_host_correlation_exactly_once() -> None:
    lifecycle = AssistantTurnOrchestrator()
    request = _request()

    lifecycle.bind_host_turn(request)

    assert lifecycle.correlation == request.correlation
    assert lifecycle.finish_host_turn() == request.correlation
    assert lifecycle.finish_host_turn() is None
    assert lifecycle.scope is None
    assert lifecycle.terminal_command is None
    assert lifecycle.excluded_commands == frozenset()


def test_generation_terminal_gives_cancellation_priority() -> None:
    lifecycle = AssistantTurnOrchestrator()
    generation_id = lifecycle.begin_generation()
    lifecycle.dispatch_phase = AssistantGenerationDispatchPhase.ACCEPTED
    lifecycle.cancelled = True

    assert (
        lifecycle.accept_generation_terminal(
            generation_id,
            AssistantGenerationEventPhase.FINISHED,
        )
        is False
    )
    assert lifecycle.active_generation_id == generation_id
    assert (
        lifecycle.accept_generation_terminal(
            generation_id,
            AssistantGenerationEventPhase.CANCELLED,
        )
        is True
    )
    assert lifecycle.active_generation_id is None
    assert lifecycle.dispatch_phase is None


def test_generation_dispatch_requires_ordered_owner_transitions() -> None:
    lifecycle = AssistantTurnOrchestrator()
    generation_id = lifecycle.begin_generation()

    assert (
        lifecycle.acknowledge_generation_dispatch(
            generation_id,
            AssistantGenerationDispatchPhase.STARTED,
        )
        is False
    )
    assert (
        lifecycle.acknowledge_generation_dispatch(
            generation_id,
            AssistantGenerationDispatchPhase.ACCEPTED,
        )
        is True
    )
    assert (
        lifecycle.acknowledge_generation_dispatch(
            generation_id,
            AssistantGenerationDispatchPhase.STARTED,
        )
        is True
    )
    assert lifecycle.dispatch_phase is AssistantGenerationDispatchPhase.STARTED


def test_invalidating_rag_turn_makes_the_queued_result_stale() -> None:
    lifecycle = AssistantTurnOrchestrator()
    rag_turn_id = lifecycle.begin_rag_turn()

    cancelled_id = lifecycle.invalidate_rag_turn()

    assert cancelled_id == rag_turn_id
    assert lifecycle.accept_rag_result(rag_turn_id) is False
    assert lifecycle.waiting_for_rag is False
    assert lifecycle.active_rag_turn_id is None


def test_tool_attempt_session_resets_all_user_turn_state() -> None:
    session = AssistantToolAttemptSession()
    session.retry_count = 2
    session.tool_failure_count = 3
    session.loop_break_count = 1
    session.successful_tool_count = 4
    session.execution_count = 5
    session.visible_response_sent = True
    session.last_tool_summary = "old result"
    session.last_tool_summary_kind = AssistantResponseKind.TOOL_RESULT
    session.record_tool_proposal("query_state", {})

    session.reset_for_user_turn()

    assert session.retry_count == 0
    assert session.tool_failure_count == 0
    assert session.loop_break_count == 0
    assert session.successful_tool_count == 0
    assert session.execution_count == 0
    assert session.visible_response_sent is False
    assert session.last_tool_summary is None
    assert session.last_tool_summary_kind is AssistantResponseKind.MESSAGE
    assert list(session.recent_tool_calls) == []


def test_tool_attempt_session_owns_attempt_transition_sequence() -> None:
    session = AssistantToolAttemptSession()

    session.record_format_retry(1)
    assert session.begin_execution() == 1
    assert session.record_failure() == 1

    session.begin_generation()

    assert session.retry_count == 1
    assert session.execution_count == 1
    assert session.tool_failure_count == 1
    assert session.record_success() == 1
    assert session.tool_failure_count == 0


def test_tool_attempt_session_owns_bounded_loop_transition() -> None:
    session = AssistantToolAttemptSession()

    assert session.record_loop_break(limit=2) is False
    assert session.loop_break_count == 1
    assert session.record_loop_break(limit=2) is True
    assert session.loop_break_count == 2


def test_tool_attempt_session_owns_repeated_proposal_detection() -> None:
    session = AssistantToolAttemptSession()
    params = {"opaque": object()}

    assert session.record_tool_proposal("query_state", params) is False
    assert session.record_tool_proposal("query_state", params) is False
    assert session.record_tool_proposal("query_state", params) is True

    session.reset_for_user_turn()

    assert session.record_tool_proposal("query_state", params) is False


def test_tool_attempt_session_arbitrates_visible_terminal_response() -> None:
    session = AssistantToolAttemptSession()
    session.record_summary(
        "The dataset is ready.",
        AssistantResponseKind.TOOL_RESULT,
    )

    decision = session.arbitrate_terminal_response(
        "Tool execution finished, but no assistant message was produced."
    )

    assert decision.text == "The dataset is ready."
    assert decision.kind is AssistantResponseKind.TOOL_RESULT
    assert session.visible_response_sent is False
    assert session.commit_terminal_response(decision) is True
    assert session.visible_response_sent is True
    assert session.arbitrate_terminal_response("fallback").text is None


def test_tool_attempt_session_does_not_commit_failed_terminal_publication() -> None:
    session = AssistantToolAttemptSession()
    session.record_summary(
        "The dataset is ready.",
        AssistantResponseKind.TOOL_RESULT,
    )

    first = session.arbitrate_terminal_response("fallback")

    assert first.text == "The dataset is ready."
    assert session.visible_response_sent is False
    retry = session.arbitrate_terminal_response("fallback")
    assert retry == first
    assert session.commit_terminal_response(retry) is True
    assert session.arbitrate_terminal_response("fallback").text is None


def test_turn_orchestrator_arbitrates_cancelled_terminal_once() -> None:
    lifecycle = AssistantTurnOrchestrator()
    lifecycle.bind_correlation(AssistantTurnCorrelation(generation=3, turn_id=9))
    generation_id = lifecycle.begin_generation()

    assert lifecycle.request_cancellation() is True
    assert lifecycle.begin_stopping_generation() == generation_id
    assert lifecycle.accept_cancellation_terminal() is True
    assert lifecycle.accept_cancellation_terminal() is False
    assert lifecycle.active_generation_id is None
    assert lifecycle.cancellation_response_sent is True
