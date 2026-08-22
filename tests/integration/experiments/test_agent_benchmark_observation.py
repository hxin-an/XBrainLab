from __future__ import annotations

from XBrainLab.backend.application import (
    ApplicationService,
    ChangedState,
    CommandResult,
    QueryStateCommand,
)
from XBrainLab.experiments.agent_benchmark.observation import (
    capture_command_result,
    capture_publication,
)


def test_observation_projects_real_application_service_public_contract() -> None:
    service = ApplicationService()
    try:
        before = service.get_view_publication()
        result = service.execute(QueryStateCommand(query="state"))
        after = service.get_view_publication()

        before_observation = capture_publication(before, sequence=1)
        result_observation = capture_command_result(result, sequence=2)
        after_observation = capture_publication(after, sequence=3)

        assert before_observation["kind"] == "publication"
        assert before_observation["payload"]["generation"] == before.generation
        assert before_observation["payload"]["state"] == before.state.to_dict()
        assert result_observation["payload"]["command_name"] == "query_state"
        assert result_observation["payload"]["status"] == "ok"
        assert after_observation["payload"]["generation"] == after.generation
        assert after_observation["payload"]["state"] == after.state.to_dict()
    finally:
        service.close()


def test_command_observation_redacts_local_paths_and_subject_metadata() -> None:
    result = CommandResult.success_result(
        command_name="query_state",
        message="State ready.",
        state={
            "raw": {
                "loaded": True,
                "files": ["/private/study/S01.edf"],
                "metadata": [{"subject": "patient-001"}],
            }
        },
        changed_state=ChangedState(),
        diagnostics={"source_path": "/private/study/S01.edf", "count": 1},
    )

    observation = capture_command_result(result, sequence=1)

    assert observation["payload"]["state"] == {
        "raw": {
            "loaded": True,
            "files": "[redacted]",
            "metadata": "[redacted]",
        }
    }
    assert observation["payload"]["diagnostics"] == "[redacted]"
