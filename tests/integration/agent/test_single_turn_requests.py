"""Complete requests through real Commands; scripted inference is not model evidence."""

import json

import pytest

from tests.integration.agent.test_product_flow import (
    _load_tiny_raw_via_command_spine,
    _tool_json,
    product_harness,
)
from tests.integration.ui.test_main_window_training_refresh_runtime import (
    runtime_lifecycle,
)
from XBrainLab.backend.application import get_application_service

__all__ = ["product_harness", "runtime_lifecycle"]


@pytest.mark.parametrize("latest", ["30 Hz.", "Change the upper cutoff to 30 Hz."])
def test_partial_request_does_not_merge_history_or_rewrite_numeric_model_proposal(
    product_harness, tmp_path, qtbot, latest
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    requests, results, decisions = [], [], []
    controller.sig_generate.connect(requests.append)
    controller.application_command_completed.connect(results.append)
    controller.decision_observed.connect(decisions.append)
    product_harness.send(
        "Bandpass with lower cutoff 7 Hz.",
        _tool_json(
            "respond_to_user",
            {
                "message": "Please restate the bandpass request with both lower and upper cutoffs."
            },
        ),
    )
    before = get_application_service(controller.study).get_view_publication()
    expected_messages = controller.assembler.get_messages(
        [{"role": "user", "content": latest}]
    )
    # The model invents 11 Hz. Host validates the numeric contract, not intent;
    # it must neither merge the previous 7 Hz nor repair this wrong proposal.
    product_harness.send(
        latest,
        _tool_json("apply_bandpass_filter", {"low_freq": 11, "high_freq": 30}),
    )
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    assert results[0].ok
    after = get_application_service(controller.study).get_view_publication()
    assert (after.generation, after.revision) != (before.generation, before.revision)
    raw = controller.study.preprocessed_data_list[0].get_mne()
    assert raw.info["highpass"] == 11
    assert raw.info["lowpass"] == 30
    admissions = [item for item in decisions if item["kind"] == "admission"]
    assert admissions[-1]["params"] == {"low_freq": 11, "high_freq": 30}
    assert admissions[-1]["generation_id"] == requests[-1].generation_id
    context = json.loads(requests[-1].to_model_messages()[-1]["content"])
    assert context["current_user"]["text"] == latest
    assert "pending_request" not in context
    assert requests[-1].to_model_messages() == expected_messages
    old_reply = "Please restate the bandpass request with both lower and upper cutoffs."
    assert old_reply in product_harness.visible_transcript
    assert {"role": "assistant", "content": old_reply} in controller.history
    product_harness.send(
        "Apply a bandpass filter from 17 to 25 Hz.",
        _tool_json("apply_bandpass_filter", {"low_freq": 17, "high_freq": 25}),
    )
    qtbot.waitUntil(lambda: len(results) == 2, timeout=5000)
    assert results[1].ok
    raw = controller.study.preprocessed_data_list[0].get_mne()
    assert raw.info["highpass"] == 17
    assert raw.info["lowpass"] == 25
    assert len(requests) == 3


@pytest.mark.parametrize(
    "latest", ["Explain bandpass filtering.", "Do not apply a bandpass filter."]
)
def test_reply_after_partial_request_has_no_data_side_effect(
    product_harness, tmp_path, latest
):
    controller = product_harness.controller
    _load_tiny_raw_via_command_spine(controller.study, tmp_path)
    product_harness.send(
        "Bandpass with lower cutoff 7 Hz.",
        _tool_json(
            "respond_to_user",
            {"message": "Please give a complete bandpass request with both cutoffs."},
        ),
    )
    before = get_application_service(controller.study).get_view_publication()
    results = []
    controller.application_command_completed.connect(results.append)
    product_harness.send(
        latest,
        _tool_json(
            "respond_to_user",
            {
                "message": "A bandpass retains a frequency range. No operation was performed."
            },
        ),
    )
    after = get_application_service(controller.study).get_view_publication()
    assert (after.generation, after.revision) == (before.generation, before.revision)
    assert not results
    assert not controller.pending_interactions.has_pending
