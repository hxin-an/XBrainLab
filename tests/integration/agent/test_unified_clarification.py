"""Unified model-proposal turns through real import and preprocessing commands.

Inference is isolated; these tests prove execution/state contracts, not model
accuracy. Every ordinary reply must still dispatch generation.
"""

import json

import pytest

from tests.integration.agent.test_product_flow import (
    _load_tiny_raw_via_command_spine,
    product_harness,
)
from tests.integration.ui.test_main_window_training_refresh_runtime import (
    runtime_lifecycle,
)
from XBrainLab.backend.application import (
    PreprocessCommand,
    PreprocessOperation,
    get_application_service,
)

__all__ = ["product_harness", "runtime_lifecycle"]


def proposal(
    decision,
    *,
    mode="update_pending",
    action="apply_bandpass_filter",
    changes=None,
    message=None,
):
    return json.dumps(
        {
            "decision": decision,
            "mode": mode,
            "action": action,
            "changes": changes or {},
            "message": message,
        }
    )


def change(value, turn, quote):
    return {"value": value, "source_turn": turn, "quote": quote}


def begin_lower(harness):
    harness.send(
        "Bandpass, lower cutoff 7 Hz.",
        proposal(
            "clarify",
            mode="new_request",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(7, "U1", "lower cutoff 7 Hz")},
        ),
    )


def test_initial_value_correction_and_bare_reply_execute_real_filter_once(
    product_harness, tmp_path, qtbot
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    requests, results = [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    begin_lower(product_harness)
    assert controller.pending_interactions.request.parameter_values() == {"low_freq": 7}
    assert not results
    product_harness.send(
        "Change lower cutoff to 8 Hz.",
        proposal(
            "clarify",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(8, "U2", "lower cutoff to 8 Hz")},
        ),
    )
    product_harness.send(
        "30 Hz.",
        proposal(
            "execute",
            changes={"high_freq": change(30, "U3", "30 Hz")},
        ),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    assert len(requests) == 3
    context = json.loads(requests[-1].to_model_messages()[-1]["content"])
    assert context["pending_request"]["parameters"]["low_freq"]["value"] == 8
    assert (
        context["pending_request"]["user_sources"]["U2"]
        == "Change lower cutoff to 8 Hz."
    )
    raw = controller.study.preprocessed_data_list[0].get_mne()
    assert raw.info["highpass"] == 8
    assert raw.info["lowpass"] == 30
    assert controller.pending_interactions.request is None


def test_explanation_keeps_request_without_executing_and_cancel_clears_it(
    product_harness, tmp_path
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    requests, results = [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    begin_lower(product_harness)
    product_harness.send(
        "Why use a bandpass?",
        json.dumps(
            {
                "decision": "reply",
                "mode": None,
                "action": None,
                "changes": {},
                "message": "A bandpass keeps a selected frequency range.",
            }
        ),
    )
    assert controller.pending_interactions.request.parameter_values() == {"low_freq": 7}
    assert not results
    product_harness.send(
        "Cancel that.",
        proposal(
            "reply",
            mode="cancel_pending",
            action=None,
            message="Cancelled.",
        ),
    )
    assert controller.pending_interactions.request is None
    assert len(requests) == 3
    assert not results


def test_changed_data_blocks_old_draft_even_when_new_model_values_are_valid(
    product_harness, tmp_path
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    begin_lower(product_harness)
    result = get_application_service(controller.study).execute(
        PreprocessCommand(operation=PreprocessOperation.RESAMPLE, rate=128)
    )
    assert result.ok
    results = []
    controller.application_command_completed.connect(results.append)
    product_harness.send(
        "30 Hz.",
        proposal(
            "execute",
            changes={"high_freq": change(30, "U2", "30 Hz")},
        ),
    )
    assert not results
    assert "state changed" in product_harness.visible_assistant_text.lower()


def test_stopping_generation_and_new_chat_clear_unexecuted_request(
    product_harness, tmp_path, qtbot
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    begin_lower(product_harness)
    product_harness.send("30 Hz.")
    product_harness.wait_for_generation_start()
    controller.stop_generation()
    qtbot.waitUntil(lambda: not controller.is_processing, timeout=2000)
    assert controller.pending_interactions.request is None
    assert controller._tool_attempt_session.execution_count == 0
    product_harness.send(
        "Bandpass, lower cutoff 7 Hz.",
        proposal(
            "clarify",
            mode="new_request",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(7, "U3", "lower cutoff 7 Hz")},
        ),
    )
    assert controller.pending_interactions.request is not None
    controller.reset_conversation()
    assert controller.pending_interactions.request is None


def test_ambiguous_correction_keeps_value_and_evidence_until_user_resolves_it(
    product_harness,
    tmp_path,
    qtbot,
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    results = []
    controller.application_command_completed.connect(results.append)
    begin_lower(product_harness)
    product_harness.send(
        "Change it to 8 Hz.",
        json.dumps(
            {
                "decision": "clarify",
                "mode": None,
                "action": None,
                "changes": {},
                "message": "Do you mean the lower or upper cutoff?",
            }
        ),
    )
    assert controller.pending_interactions.request.parameter_values() == {"low_freq": 7}
    assert (
        dict(controller.pending_interactions.request.sources)["U2"]
        == "Change it to 8 Hz."
    )
    assert not results
    product_harness.send(
        "I meant the lower cutoff.",
        proposal(
            "clarify",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(8, "U2", "8 Hz")},
        ),
    )
    assert controller.pending_interactions.request.parameter_values() == {"low_freq": 8}
    product_harness.send(
        "30 Hz.",
        proposal(
            "execute",
            changes={"high_freq": change(30, "U4", "30 Hz")},
        ),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    raw = controller.study.preprocessed_data_list[0].get_mne()
    assert (raw.info["highpass"], raw.info["lowpass"]) == (8, 30)


def test_explicit_replacement_executes_only_new_action(
    product_harness, tmp_path, qtbot
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    results = []
    controller.application_command_completed.connect(results.append)
    begin_lower(product_harness)
    product_harness.send(
        "Instead, apply a notch filter at 50 Hz.",
        proposal(
            "execute",
            mode="new_request",
            action="apply_notch_filter",
            changes={"freq": change(50, "U2", "50 Hz")},
        ),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    assert results[0].tool_name == "apply_notch_filter"
    assert controller.study.preprocessed_data_list[0].get_mne().info["highpass"] == 0
    assert controller.pending_interactions.request is None


@pytest.mark.parametrize(
    "failure", ["error", "empty", "rejected_update", "multiple_proposals"]
)
def test_failed_correction_invalidates_draft_so_next_reply_cannot_execute_old_value(
    product_harness, tmp_path, failure
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    requests = []
    controller.sig_generate.connect(requests.append)
    begin_lower(product_harness)
    product_harness.send("Change the lower cutoff to 8 Hz.")
    product_harness.wait_for_generation_start()
    generation = controller._turn_orchestrator.active_generation_id
    if failure == "error":
        controller._on_generation_error(generation, "Generation failed.")
    elif failure == "rejected_update":
        controller.current_response = proposal(
            "clarify",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(8, "U99", "8 Hz")},
        )
        controller._on_generation_finished(generation, [])
    elif failure == "multiple_proposals":
        update = proposal(
            "clarify",
            message="What upper cutoff should I use?",
            changes={"low_freq": change(8, "U2", "8 Hz")},
        )
        controller.current_response = update + "\n" + update
        controller._on_generation_finished(generation, [])
    else:
        controller._on_generation_finished(generation, [])
    assert controller.pending_interactions.request.parameter_values() == {"low_freq": 7}
    results = []
    controller.application_command_completed.connect(results.append)
    product_harness.send(
        "30 Hz.",
        proposal(
            "execute",
            changes={"high_freq": change(30, "U3", "30 Hz")},
        ),
    )
    pending = json.loads(requests[-1].to_model_messages()[-1]["content"])[
        "pending_request"
    ]
    assert pending["invalidated"] is True
    assert pending["parameters"]["low_freq"]["value"] == 7
    assert not results
    assert "Restate the complete request" in product_harness.visible_assistant_text


def test_oversized_request_never_dispatches_and_new_chat_recovers(
    product_harness, tmp_path, qtbot
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    begin_lower(product_harness)
    requests, results = [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    # Valid per-message character length, too large with required saved context.
    product_harness.send("😀" * 16_384)
    qtbot.waitUntil(lambda: not controller.is_processing, timeout=2000)
    assert not requests
    assert not results
    pending = controller.pending_interactions.request
    assert pending.parameter_values() == {"low_freq": 7}
    assert pending.invalidated
    assert "New chat" in product_harness.visible_assistant_text
    controller.reset_conversation()
    assert controller.pending_interactions.request is None
    product_harness.send(
        "What is a bandpass?",
        json.dumps(
            {
                "decision": "reply",
                "mode": None,
                "action": None,
                "changes": {},
                "message": "A bandpass keeps a selected frequency range.",
            }
        ),
    )
    assert len(requests) == 1
    assert "selected frequency range" in product_harness.visible_assistant_text
    assert not results


def test_gui_panel_switch_preserves_draft_and_rechecks_current_publication(
    product_harness,
    tmp_path,
    qtbot,
    runtime_lifecycle,
):
    from XBrainLab.ui.main_window import MainWindow

    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    service = get_application_service(controller.study)
    window = MainWindow(controller.study)
    qtbot.addWidget(window)
    runtime_lifecycle(window, service)
    window.show()
    begin_lower(product_harness)
    draft = controller.pending_interactions.request
    before = service.get_view_publication()
    ready = []
    window.switch_page(1, on_ready=ready.append)
    qtbot.waitUntil(lambda: len(ready) == 1, timeout=5000)
    assert ready[0] is window.preprocess_panel
    assert window.stack.currentWidget() is window.preprocess_panel
    assert controller.pending_interactions.request is draft
    assert draft.parameter_values() == {"low_freq": 7}
    after = service.get_view_publication()
    assert after.generation == before.generation

    requests, results = [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    product_harness.send(
        "30 Hz.",
        proposal(
            "execute",
            changes={"high_freq": change(30, "U2", "30 Hz")},
        ),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    captured = json.loads(requests[0].to_model_messages()[-1]["content"])
    assert captured["application_state"]["backend_generation"] == after.generation
    assert captured["pending_request"]["parameters"]["low_freq"]["value"] == 7
    raw = controller.study.preprocessed_data_list[0].get_mne()
    assert (raw.info["highpass"], raw.info["lowpass"]) == (7, 30)


@pytest.mark.parametrize("retrieval_error", ["", "Lookup failed."])
def test_zero_rag_and_retrieval_failure_keep_contract_and_execute_real_command(
    product_harness,
    tmp_path,
    qtbot,
    monkeypatch,
    retrieval_error,
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    requests, results, observed = [], [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    controller.decision_observed.connect(observed.append)
    retrievals = []

    def retrieve(turn_id, query, callback, *, allowed_tool_names=None):
        retrievals.append(allowed_tool_names)
        callback(
            turn_id,
            query,
            "UNUSABLE_PARTIAL_CONTEXT" if retrieval_error else "",
            retrieval_error,
        )
        return True

    monkeypatch.setattr(product_harness.rag_lifecycle, "retrieve", retrieve)
    product_harness.send(
        "Resample to 128 Hz.",
        proposal(
            "execute",
            mode="new_request",
            action="resample_data",
            changes={"rate": change(128, "U1", "128 Hz")},
        ),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    assert len(retrievals) == 1
    assert "resample_data" in retrievals[0]
    messages = requests[0].to_model_messages()
    assert "STRICT RESPONSE CONTRACT" in messages[0]["content"]
    assert '"name": "resample_data"' in messages[0]["content"]
    assert "UNUSABLE_PARTIAL_CONTEXT" not in json.dumps(messages)
    assert len(messages) == 2  # Required policy/state/user only; no invented examples.
    rag_event = next(event for event in observed if event["kind"] == "rag")
    assert rag_event["error"] == retrieval_error  # Fault is not recorded as zero-hit.
    assert controller.study.preprocessed_data_list[0].get_mne().info["sfreq"] == 128


def test_training_start_and_delayed_stop_report_real_nonterminal_truth(
    product_harness,
    tmp_path,
    qtbot,
    monkeypatch,
):
    from threading import Event

    from tests.integration.agent.deferred_split_support import (
        build_saved_split_runtime,
        install_materialized_candidate,
    )
    from XBrainLab.backend.application import ConfigureTrainingCommand
    from XBrainLab.backend.training.training_plan import TrainingPlanHolder
    from XBrainLab.backend.training_state_contract import TrainingOutcomeState
    from XBrainLab.llm.agent.confirmation import (
        AgentConfirmationResolution,
        AgentConfirmationResolutionStatus,
    )

    controller = product_harness.controller
    service, epoch = build_saved_split_runtime(controller.study)
    install_materialized_candidate(controller.study, epoch)
    configured = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(tmp_path / "training-output"),
            save_checkpoints_every=0,
        )
    )
    assert configured.ok, configured.message
    entered, release = Event(), Event()

    def paused_compute(_holder):
        entered.set()
        assert release.wait(timeout=20)

    # Isolate only expensive compute; real Trainer owns run/stop/terminal state.
    monkeypatch.setattr(TrainingPlanHolder, "train", paused_compute)
    confirmations, results, requests = [], [], []
    controller.confirmation_requested.connect(confirmations.append)
    controller.application_command_completed.connect(results.append)
    controller.sig_generate.connect(requests.append)
    try:
        product_harness.send(
            "Start training now.",
            proposal(
                "execute",
                mode="new_request",
                action="start_training",
            ),
        )
        assert len(confirmations) == 1
        assert not entered.is_set()
        controller.on_user_confirmation_resolved(
            AgentConfirmationResolution.for_request(
                confirmations[0],
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )
        qtbot.waitUntil(lambda: entered.is_set() and len(results) == 1, timeout=10000)
        assert results[0].ok
        assert results[0].tool_name == "start_training"
        assert (
            service.training_runtime.terminal_outcome().state
            is TrainingOutcomeState.RUNNING
        )
        assert "Training started" in product_harness.visible_assistant_text
        assert "Training completed" not in product_harness.visible_assistant_text
        assert len(requests) == 1  # Starting never chains another model/tool turn.

        product_harness.send(
            "Stop the current training run.",
            proposal(
                "execute",
                mode="new_request",
                action="stop_training",
            ),
        )
        assert len(confirmations) == 2
        assert confirmations[-1].command_name == "stop_training"
        state = json.loads(requests[-1].to_model_messages()[-1]["content"])[
            "application_state"
        ]
        assert state["workflow_stage"] == "training"
        assert state["running"] is True
        controller.on_user_confirmation_resolved(
            AgentConfirmationResolution.for_request(
                confirmations[-1],
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )
        qtbot.waitUntil(lambda: len(results) == 2, timeout=5000)
        assert results[1].ok
        assert results[1].tool_name == "stop_training"
        assert (
            service.training_runtime.terminal_outcome().state
            is TrainingOutcomeState.STOP_REQUESTED
        )
        assert "Training stop requested" in product_harness.visible_assistant_text
        assert "Training stopped" not in product_harness.visible_assistant_text
        assert len(requests) == 2
        release.set()
        qtbot.waitUntil(
            lambda: service.training_runtime.terminal_outcome().state
            is TrainingOutcomeState.CANCELLED,
            timeout=5000,
        )
        assert len(results) == 2
    finally:
        release.set()
        service.training_runtime.stop_training(wait_timeout=5)
        service.wait_for_background_tasks(timeout=5)
        service.close()
