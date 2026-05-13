from tests.architecture_compliance import (
    check_backend_facade_test_usage,
    check_docs_current_truth_overclaims,
    check_llm_direct_study_state_reads,
    check_product_runtime_backend_facade_usage,
    check_product_success_backend_facade_tests,
    check_product_success_controller_lookup_assertions,
    check_product_success_direct_study_state_tests,
    check_product_success_legacy_fallback_tests,
    check_ui_capability_gated_controller_readiness,
    check_ui_command_execution_suppresses_observer_refresh,
    check_ui_controller_fallbacks,
    check_ui_controller_render_fallbacks,
    check_ui_controller_study_get_controller_fallbacks,
    check_ui_direct_backend_service_execute,
    check_ui_direct_controller_mutations,
    check_ui_direct_loader_apply,
    check_ui_direct_study_get_controller_lookups,
    check_ui_direct_study_state_reads,
    check_ui_legacy_fallback_helper_scope,
    check_ui_legacy_mutation_helper_calls,
    check_ui_observer_direct_update_bridges,
    check_ui_observer_handlers_call_refresh_coordinator,
    check_ui_post_command_controller_echoes,
    check_ui_post_command_local_refreshes,
    check_ui_refresh_false_commands,
    check_weak_test_names,
)


def _write_ui_file(root, source: str) -> None:
    path = root / "XBrainLab" / "ui" / "panels" / "demo" / "sidebar.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def _write_llm_file(root, source: str) -> None:
    path = root / "XBrainLab" / "llm" / "pipeline_state.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def test_weak_test_name_guard_flags_ambiguous_names(tmp_path):
    path = tmp_path / "tests" / "unit" / "ui" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_open_dialog_accepted():
    pass


def test_panel_no_crash():
    pass
""",
        encoding="utf-8",
    )

    violations = check_weak_test_names(tmp_path)

    assert len(violations) == 2
    assert "test_open_dialog_accepted" in violations[0]
    assert "behavior-specific" in violations[0]
    assert "test_panel_no_crash" in violations[1]


def test_weak_test_name_guard_allows_behavior_specific_names(tmp_path):
    path = tmp_path / "tests" / "unit" / "ui" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_open_dialog_accepts_preview_result():
    pass


def test_none_figure_is_ignored():
    pass
""",
        encoding="utf-8",
    )

    assert check_weak_test_names(tmp_path) == []


def test_docs_current_truth_guard_flags_product_complete_overclaim(tmp_path):
    path = tmp_path / "docs" / "current.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
# Current

XBrainLab is product complete and ready for release approval.
The UI is now full zero-controller UI.
""",
        encoding="utf-8",
    )

    violations = check_docs_current_truth_overclaims(tmp_path)

    assert len(violations) == 3
    assert "product complete" in violations[0]
    assert "release approval" in violations[1]
    assert "full zero-controller UI" in violations[2]


def test_docs_current_truth_guard_allows_explicit_claim_boundaries(tmp_path):
    path = tmp_path / "docs" / "current.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
# Current

XBrainLab 還不能宣稱 product complete。
這些 guard 不是 full zero-controller UI 證明。
Human Windows Desktop Acceptance Gap remains open.
""",
        encoding="utf-8",
    )

    assert check_docs_current_truth_overclaims(tmp_path) == []


def test_product_runtime_facade_guard_flags_agent_facade_import(tmp_path):
    path = tmp_path / "XBrainLab" / "llm" / "tools" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.facade import BackendFacade


def run(study):
    return BackendFacade(study).get_capabilities()
""",
        encoding="utf-8",
    )

    violations = check_product_runtime_backend_facade_usage(tmp_path)

    assert len(violations) == 2
    assert "XBrainLab/llm/tools/demo.py" in violations[0]
    assert "ApplicationService / Command API" in violations[0]


def test_product_runtime_facade_guard_allows_application_service(tmp_path):
    path = tmp_path / "XBrainLab" / "llm" / "tools" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.application import get_application_service


def run(study):
    return get_application_service(study).get_capabilities()
""",
        encoding="utf-8",
    )

    assert check_product_runtime_backend_facade_usage(tmp_path) == []


def test_product_success_facade_test_guard_flags_integration_facade(tmp_path):
    path = tmp_path / "tests" / "integration" / "pipeline" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.facade import BackendFacade


def test_pipeline():
    facade = BackendFacade()
    facade.generate_dataset()
""",
        encoding="utf-8",
    )

    violations = check_product_success_backend_facade_tests(tmp_path)

    assert len(violations) == 2
    assert "tests/integration/pipeline/test_demo.py" in violations[0]
    assert "product-success evidence" in violations[0]


def test_product_success_facade_test_guard_does_not_scan_unit_tests(tmp_path):
    path = tmp_path / "tests" / "unit" / "backend" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.facade import BackendFacade


def test_old_facade_usage():
    return BackendFacade()
""",
        encoding="utf-8",
    )

    assert check_product_success_backend_facade_tests(tmp_path) == []


def test_backend_facade_test_guard_flags_new_unit_facade_usage(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.facade import BackendFacade


def test_tool_path(study):
    return BackendFacade(study).get_capabilities()
""",
        encoding="utf-8",
    )

    violations = check_backend_facade_test_usage(tmp_path)

    assert len(violations) == 2
    assert "tests/unit/llm/test_demo.py" in violations[0]
    assert "physical facade removal" in violations[0]


def test_backend_facade_test_guard_flags_marked_compatibility_file(tmp_path):
    path = tmp_path / "tests" / "unit" / "backend" / "test_facade_coverage.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
import pytest

from XBrainLab.backend.facade import BackendFacade

pytestmark = pytest.mark.legacy_marker


def test_old_facade_api(study):
    return BackendFacade(study).get_capabilities()
""",
        encoding="utf-8",
    )

    violations = check_backend_facade_test_usage(tmp_path)

    assert len(violations) == 2
    assert "tests/unit/backend/test_facade_coverage.py" in violations[0]
    assert "replacement coverage" in violations[0]


def test_backend_facade_test_guard_flags_unmarked_old_compatibility_file(tmp_path):
    path = tmp_path / "tests" / "unit" / "backend" / "test_facade_coverage.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.backend.facade import BackendFacade


def test_old_facade_api(study):
    return BackendFacade(study).get_capabilities()
""",
        encoding="utf-8",
    )

    violations = check_backend_facade_test_usage(tmp_path)

    assert len(violations) == 2
    assert "physical facade removal" in violations[0]
    assert "replacement coverage" in violations[0]


def test_backend_facade_test_guard_flags_function_level_marker(tmp_path):
    path = tmp_path / "tests" / "unit" / "backend" / "application" / "test_runtime.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
import pytest


@pytest.mark.legacy_marker
def test_old_facade_uses_existing_application_service(study):
    from XBrainLab.backend.facade import BackendFacade

    return BackendFacade(study).get_capabilities()
""",
        encoding="utf-8",
    )

    violations = check_backend_facade_test_usage(tmp_path)

    assert len(violations) == 2
    assert "tests/unit/backend/application/test_runtime.py" in violations[0]
    assert "ApplicationService / Command API" in violations[0]


def test_product_success_legacy_fallback_test_guard_flags_integration_fallback(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.ui.application_capabilities import run_legacy_controller_fallback


def test_product_action():
    run_legacy_controller_fallback(widget, lambda: controller.start_training())
""",
        encoding="utf-8",
    )

    violations = check_product_success_legacy_fallback_tests(tmp_path)

    assert len(violations) == 2
    assert "tests/integration/ui/test_demo.py" in violations[0]
    assert "legacy fallback product-success evidence" in violations[0]


def test_product_success_legacy_fallback_test_guard_flags_controller_lookup(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "backend" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.ui import application_capabilities


def test_product_action(study):
    return application_capabilities.get_legacy_controller_from_study(
        widget,
        study,
        "training",
    )
""",
        encoding="utf-8",
    )

    violations = check_product_success_legacy_fallback_tests(tmp_path)

    assert len(violations) == 1
    assert "get_legacy_controller_from_study" in violations[0]


def test_product_success_legacy_fallback_test_guard_allows_unit_compatibility_test(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "ui" / "test_legacy_compat.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.ui.application_capabilities import run_legacy_controller_fallback


def test_legacy_compat():
    return run_legacy_controller_fallback(object(), lambda: "legacy-ok")
""",
        encoding="utf-8",
    )

    assert check_product_success_legacy_fallback_tests(tmp_path) == []


def test_product_success_study_state_guard_flags_walkthrough_state_truth(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_product_walkthrough.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_walkthrough(test_app):
    assert len(test_app.study.loaded_data_list) == 1
    assert test_app.study.epoch_data is not None
    generator = test_app.study.get_datasets_generator(config)
    return generator
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 3
    assert "study.loaded_data_list" in violations[0]
    assert "study.epoch_data" in violations[1]
    assert "study.get_datasets_generator" in violations[2]


def test_product_success_study_state_guard_flags_real_tools_e2e_state_truth(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_real_tools_e2e.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_real_tools_e2e_flow(study):
    assert len(study.loaded_data_list) == 1
    assert study.model_holder.target_model.__name__ == "EEGNet"
    assert study.training_option.epoch == 5
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 3
    assert "study.loaded_data_list" in violations[0]
    assert "study.model_holder" in violations[1]
    assert "study.training_option" in violations[2]


def test_product_success_study_state_guard_flags_training_integration_state_truth(
    tmp_path,
):
    path = (
        tmp_path / "tests" / "integration" / "training" / "test_training_integration.py"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_training_panel_state(study):
    assert study.training_option is not None
    assert study.training_option.epoch == 5
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 2
    assert "study.training_option" in violations[0]
    assert "study.training_option" in violations[1]


def test_product_success_study_state_guard_flags_e2e_training_state_truth(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "pipeline" / "test_e2e_training.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_progress_bar_calculation_with_string_epoch(study):
    assert study.training_option is not None
    assert study.training_option.epoch == 10
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 2
    assert "study.training_option" in violations[0]
    assert "study.training_option" in violations[1]


def test_product_success_study_state_guard_flags_application_workflow_generator(
    tmp_path,
):
    path = (
        tmp_path
        / "tests"
        / "integration"
        / "backend"
        / "test_application_service_workflow.py"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_application_service_workflow(service):
    generator = service.study.get_datasets_generator(config)
    return generator
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 1
    assert "study.get_datasets_generator()" in violations[0]


def test_product_success_study_state_guard_flags_real_data_pipeline_truth(
    tmp_path,
):
    path = (
        tmp_path / "tests" / "integration" / "pipeline" / "test_real_data_pipeline.py"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_real_data_pipeline():
    processed = study.preprocessed_data_list[0]
    generator = study.get_datasets_generator(config)
    assert study.epoch_data is not None
    assert study.trainer is not None
    return processed, generator
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 4
    assert "study.preprocessed_data_list" in violations[0]
    assert "study.epoch_data" in violations[1]
    assert "study.trainer" in violations[2]
    assert "study.get_datasets_generator()" in violations[3]


def test_product_success_study_state_guard_flags_preprocess_validation_setup_truth(
    tmp_path,
):
    path = (
        tmp_path
        / "tests"
        / "integration"
        / "pipeline"
        / "test_preprocess_validation.py"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_preprocess_fixture_setup(study):
    assert study.loaded_data_list
""",
        encoding="utf-8",
    )

    violations = check_product_success_direct_study_state_tests(tmp_path)

    assert len(violations) == 1
    assert "study.loaded_data_list" in violations[0]


def test_product_success_study_state_guard_allows_command_state_truth(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_product_walkthrough.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_walkthrough(test_app):
    state = _application_state(test_app.study)
    assert state["raw"]["count"] == 1
    split_context = _query_diagnostics(
        test_app.study,
        "dataset_generation_context",
        include_objects=True,
    )
    assert split_context["epoch_available"] is True
""",
        encoding="utf-8",
    )

    assert check_product_success_direct_study_state_tests(tmp_path) == []


def test_product_success_controller_lookup_guard_flags_direct_lookup_assertion(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_panel_binding.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_controller_resolution(mock_study):
    panel = TrainingPanel(parent=parent)
    assert panel.controller is not None
    mock_study.get_controller.assert_any_call("training")
""",
        encoding="utf-8",
    )

    violations = check_product_success_controller_lookup_assertions(tmp_path)

    assert len(violations) == 1
    assert "study.get_controller() lookup" in violations[0]
    assert "assert_not_called" in violations[0]


def test_product_success_controller_lookup_guard_allows_negative_boundary_assertion(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "ui" / "test_panel_binding.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_injected_controller_is_used(main_window):
    panel = TrainingPanel(controller=training_controller, parent=main_window)
    assert panel.controller is training_controller
    main_window.study.get_controller.assert_not_called()
""",
        encoding="utf-8",
    )

    assert check_product_success_controller_lookup_assertions(tmp_path) == []


def test_direct_backend_service_execute_guard_flags_ui_bypass(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self, study):
    result = BackendFacade(study).service.execute(QueryStateCommand())
    return result
""",
    )

    violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(violations) == 1
    assert "BackendFacade" in violations[0]
    assert "execute_application_command" in violations[0]


def test_direct_backend_service_execute_guard_flags_get_application_service_ui_bypass(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def run(self, study):
    result = get_application_service(study).execute(QueryStateCommand())
    return result
""",
    )

    violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(violations) == 1
    assert "ApplicationService.execute" in violations[0]
    assert "execute_application_command" in violations[0]


def test_direct_backend_service_execute_guard_allows_application_helper(tmp_path):
    path = tmp_path / "XBrainLab" / "ui" / "application_capabilities.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def execute_application_command(study, command):
    return BackendFacade(study).service.execute(command)
""",
        encoding="utf-8",
    )

    assert check_ui_direct_backend_service_execute(tmp_path) == []


def test_command_execution_suppression_guard_flags_missing_scope(tmp_path):
    path = tmp_path / "XBrainLab" / "ui" / "application_capabilities.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def execute_application_command(context, command):
    result = get_application_service(study).execute(command)
    refresh_after_command(context, result)
    return result
""",
        encoding="utf-8",
    )

    violations = check_ui_command_execution_suppresses_observer_refresh(tmp_path)

    assert len(violations) == 1
    assert "suppress_observer_refresh_during_command" in violations[0]


def test_command_execution_suppression_guard_allows_scoped_execute(tmp_path):
    path = tmp_path / "XBrainLab" / "ui" / "application_capabilities.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def execute_application_command(context, command):
    with suppress_observer_refresh_during_command(context):
        result = get_application_service(study).execute(command)
    refresh_after_command(context, result)
    return result
""",
        encoding="utf-8",
    )

    assert check_ui_command_execution_suppresses_observer_refresh(tmp_path) == []


def test_post_command_refresh_guard_flags_direct_local_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result.failed:
        return
    self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]
    assert "execute_application_command" in violations[0]


def test_post_command_refresh_guard_allows_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result.failed:
        return
    self._update_panel_after_legacy_result(result)
""",
    )

    assert check_ui_post_command_local_refreshes(tmp_path) == []


def test_post_command_refresh_guard_flags_success_guard_local_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if not result.failed:
        self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]


def test_post_command_refresh_guard_flags_missing_result_direct_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "legacy-result helper" in violations[0]


def test_post_command_refresh_guard_allows_refresh_false_query(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand(), refresh=False)
    if result.failed:
        return
    self.on_update()
""",
    )

    assert check_ui_post_command_local_refreshes(tmp_path) == []


def test_refresh_false_guard_flags_mutating_command(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    execute_application_command(self, ApplySmartParseCommand(results={}), refresh=False)
""",
    )

    violations = check_ui_refresh_false_commands(tmp_path)

    assert len(violations) == 1
    assert "ApplySmartParseCommand" in violations[0]
    assert "refresh=False" in violations[0]


def test_refresh_false_guard_allows_query_commands(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    execute_application_command(self, QueryStateCommand(query="state"), refresh=False)
    execute_application_command(self, EvaluateCommand(include_objects=True), refresh=False)
    execute_application_command(self, VisualizeCommand(view="summary"), refresh=False)
    execute_application_command(self, SaliencyCommand(), refresh=False)
""",
    )

    assert check_ui_refresh_false_commands(tmp_path) == []


def test_refresh_false_guard_flags_saliency_configuration(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self, params):
    execute_application_command(self, SaliencyCommand(params=params), refresh=False)
""",
    )

    violations = check_ui_refresh_false_commands(tmp_path)

    assert len(violations) == 1
    assert "SaliencyCommand" in violations[0]


def test_post_command_controller_echo_guard_flags_service_success_echo(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def select_model(self):
    result = execute_application_command(self, ConfigureTrainingCommand())
    if result is None:
        run_legacy_controller_fallback(
            self,
            lambda: self.controller.set_model_holder(holder),
        )
    elif result.failed:
        return
    holder = self.controller.get_model_holder()
""",
    )

    violations = check_ui_post_command_controller_echoes(tmp_path)

    assert len(violations) == 1
    assert "get_model_holder" in violations[0]
    assert "service-backed success" in violations[0]


def test_post_command_controller_echo_guard_allows_legacy_branch(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def select_model(self):
    result = execute_application_command(self, ConfigureTrainingCommand())
    if result is None:
        run_legacy_controller_fallback(
            self,
            lambda: self.controller.set_model_holder(holder),
        )
        holder = self.controller.get_model_holder()
    elif result.failed:
        return
""",
    )

    assert check_ui_post_command_controller_echoes(tmp_path) == []


def test_controller_fallback_guard_allows_named_legacy_wrapper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self._run_legacy_preprocess_fallback(
            "Filtering Blocked",
            lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
        )
""",
    )

    assert check_ui_controller_fallbacks(tmp_path) == []


def test_controller_fallback_guard_flags_direct_mutation_in_missing_result(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self.controller.apply_filter(1.0, 40.0, [50.0])
""",
    )

    violations = check_ui_controller_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "apply_filter" in violations[0]


def test_controller_render_fallback_guard_flags_stale_read_in_missing_result(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def update_panel(self):
    result = execute_application_command(self, QueryStateCommand(), refresh=False)
    if result is None:
        rows = self.controller.get_loaded_data_list()
    return rows
""",
    )

    violations = check_ui_controller_render_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "get_loaded_data_list" in violations[0]
    assert "run_legacy_controller_fallback" in violations[0]


def test_controller_render_fallback_guard_flags_model_holder_echo_in_missing_result(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def select_model(self):
    result = execute_application_command(self, ConfigureTrainingCommand())
    if result is None:
        holder = self.controller.get_model_holder()
    return holder
""",
    )

    violations = check_ui_controller_render_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "get_model_holder" in violations[0]
    assert "run_legacy_controller_fallback" in violations[0]


def test_controller_render_fallback_guard_allows_explicit_legacy_wrapper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_panel(self):
    result = execute_application_command(self, QueryStateCommand(), refresh=False)
    if result is None:
        rows = run_legacy_controller_fallback(
            self,
            self.controller.get_loaded_data_list,
        )
    return rows
""",
    )

    assert check_ui_controller_render_fallbacks(tmp_path) == []


def test_capability_readiness_guard_flags_controller_gate_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is not None and not train_capability.enabled:
        return
    if not self.controller.is_training():
        execute_application_command(self, TrainCommand())
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_training" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_validate_ready_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def check_ready(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    ready = (
        train_capability.enabled
        if train_capability is not None
        else self.controller.validate_ready()
    )
    self.btn_start.setEnabled(ready)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.validate_ready" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_lock_state_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
    is_locked = self.controller.is_locked()
    if scan_capability is not None:
        self.import_btn.setEnabled(scan_capability.enabled)
    elif is_locked:
        self.import_btn.setToolTip("Dataset is locked.")
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_locked" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_saliency_params_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def set_saliency(self):
    capability = get_command_capability(self, CommandName.SALIENCY)
    if capability is not None and not capability.enabled:
        return
    params = self.controller.get_saliency_params()
    return SaliencyDialog(self, params)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_saliency_params" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_channel_names_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def set_montage(self):
    capability = get_command_capability(self, CommandName.APPLY_MONTAGE)
    if capability is not None and not capability.enabled:
        return
    channels = self.controller.get_channel_names()
    return MontageDialog(self, channels)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_channel_names" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_filenames_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def open_smart_parser(self):
    capability = get_command_capability(self, CommandName.APPLY_SMART_PARSE)
    if capability is not None and not capability.enabled:
        return
    files = self.controller.get_filenames()
    return SmartParserDialog(files, self)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_filenames" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_preprocessed_list_after_capability(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
    if preprocess_capability is not None and not preprocess_capability.enabled:
        return
    data_list = self.controller.get_preprocessed_data_list()
    self._update_button_states(bool(data_list))
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_preprocessed_data_list" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_explicit_legacy_none_branch(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is None and self.controller.is_training():
        return
    execute_application_command(self, TrainCommand())
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_training" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_allows_explicit_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is None:
        ok, running = run_legacy_controller_fallback(
            self,
            lambda: self.controller.is_training(),
        )
        if ok and running:
            return
    execute_application_command(self, TrainCommand())
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_capability_readiness_guard_allows_local_legacy_value_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
    if scan_capability is None:
        available, is_locked = self._legacy_controller_value(
            lambda: self.controller.is_locked(),
        )
        if available and is_locked:
            return
    execute_application_command(self, ScanSourceCommand())
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_capability_readiness_guard_ignores_non_capability_legacy_function(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    if not self.controller.is_training():
        self.controller.start_training()
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_observer_bridge_guard_flags_direct_update_panel(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "data_changed", self.update_panel)
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]
    assert "refresh_from_observer" in violations[0]


def test_observer_bridge_guard_flags_direct_refresh_from_observer(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "data_changed", self.refresh_from_observer)
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "_create_refresh_bridge" in violations[0]


def test_observer_bridge_guard_allows_create_refresh_bridge(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_refresh_bridge(self.controller, "data_changed")
""",
    )

    assert check_ui_observer_direct_update_bridges(tmp_path) == []


def test_observer_bridge_guard_flags_import_finished_simple_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_refresh_bridge(self.controller, "import_finished")
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "import_finished" in violations[0]
    assert "named callback" in violations[0]


def test_observer_bridge_guard_flags_direct_import_finished_bridge(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self.import_bridge = QtObserverBridge(
        self.controller,
        "import_finished",
        self,
    )
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "import_finished" in violations[0]
    assert "named callback" in violations[0]


def test_observer_bridge_guard_allows_callback_handlers(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "training_started", self._on_training_started)
""",
    )

    assert check_ui_observer_direct_update_bridges(tmp_path) == []


def test_observer_handler_refresh_guard_flags_handler_without_coordinator(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "training_updated",
        self._on_training_updated,
    )

def _on_training_updated(self):
    self.update_loop()
""",
    )

    violations = check_ui_observer_handlers_call_refresh_coordinator(tmp_path)

    assert len(violations) == 1
    assert "_on_training_updated" in violations[0]
    assert "refresh_after_observer" in violations[0]


def test_observer_handler_refresh_guard_allows_handler_with_coordinator(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "training_updated",
        self._on_training_updated,
    )

def _on_training_updated(self):
    self.update_loop()
    refresh_after_observer(self, event_name="training_updated")
""",
    )

    assert check_ui_observer_handlers_call_refresh_coordinator(tmp_path) == []


def test_observer_handler_refresh_guard_allows_import_finished_callback(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "import_finished",
        self._on_import_finished,
    )

def _on_import_finished(self):
    self.show_import_warnings()
""",
    )

    assert check_ui_observer_handlers_call_refresh_coordinator(tmp_path) == []


def test_direct_loader_apply_guard_flags_product_ui_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def apply_loader(self, loader):
    loader.apply(self.controller.study, force_update=True)
""",
    )

    violations = check_ui_direct_loader_apply(tmp_path)

    assert len(violations) == 1
    assert "loader.apply" in violations[0]
    assert "legacy loader adapter" in violations[0]


def test_direct_loader_apply_guard_allows_legacy_adapter(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _apply_legacy_loader(self, loader):
    loader.apply(self.controller.study, force_update=True)
""",
    )

    assert check_ui_direct_loader_apply(tmp_path) == []


def test_direct_controller_mutation_guard_flags_product_ui_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def rename_subject(self):
    controller = self.controller
    controller.update_metadata(0, subject="S01")
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.update_metadata" in violations[0]
    assert "ApplicationService" in violations[0]


def test_direct_controller_mutation_guard_flags_self_controller_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run_training(self):
    self.controller.start_training()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.start_training" in violations[0]


def test_direct_controller_mutation_guard_flags_named_controller_attribute(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def apply_montage(self):
    self.preprocess_controller.apply_montage(["C3", "C4"])
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.apply_montage" in violations[0]


def test_direct_controller_mutation_guard_allows_legacy_fallback_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    run_legacy_controller_fallback(
        self,
        lambda: self.controller.start_training(),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_allows_named_legacy_wrapper_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_legacy_preprocess_fallback(
        "Filtering Blocked",
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_allows_named_fallback_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _run_metadata_update_fallback(self, controller):
    controller.update_metadata(0, subject="S01")
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_legacy_mutation_helper_guard_flags_unwrapped_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_legacy_label_import()

def _run_legacy_label_import(self):
    self.controller.apply_labels_legacy([], [], None, None)
""",
    )

    violations = check_ui_legacy_mutation_helper_calls(tmp_path)

    assert len(violations) == 1
    assert "_run_legacy_label_import" in violations[0]
    assert "run_legacy_controller_fallback" in violations[0]


def test_legacy_mutation_helper_guard_allows_wrapped_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    run_legacy_controller_fallback(
        self,
        lambda: self._run_legacy_label_import(),
    )

def _run_legacy_label_import(self):
    self.controller.apply_labels_legacy([], [], None, None)
""",
    )

    assert check_ui_legacy_mutation_helper_calls(tmp_path) == []


def test_legacy_fallback_scope_guard_flags_product_method_gate(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    return run_legacy_controller_fallback(
        self,
        lambda: self.controller.get_loaded_data_list(),
    )
""",
    )

    violations = check_ui_legacy_fallback_helper_scope(tmp_path)

    assert len(violations) == 1
    assert "run_legacy_controller_fallback" in violations[0]
    assert "explicit legacy/fallback helper" in violations[0]


def test_legacy_fallback_scope_guard_allows_named_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    return self._legacy_loaded_rows()

def _legacy_loaded_rows(self):
    return run_legacy_controller_fallback(
        self,
        lambda: self.controller.get_loaded_data_list(),
    )
""",
    )

    assert check_ui_legacy_fallback_helper_scope(tmp_path) == []


def test_direct_controller_mutation_guard_ignores_non_controller_methods(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def clear_ui_table(self):
    self.history_table.clear_history()
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_study_state_guard_flags_product_ui_read(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def open_montage(self):
    epoch_data = self.study.epoch_data
    return epoch_data.get_mne().ch_names
""",
    )

    violations = check_ui_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "study.epoch_data" in violations[0]
    assert "ApplicationService" in violations[0]


def test_direct_study_state_guard_allows_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_montage_channels(self):
    epoch_data = self.study.epoch_data
    return epoch_data.get_mne().ch_names
""",
    )

    assert check_ui_direct_study_state_reads(tmp_path) == []


def test_llm_direct_study_state_guard_flags_product_stage_read(tmp_path):
    _write_llm_file(
        tmp_path,
        """
def compute_pipeline_stage(study):
    if study.loaded_data_list:
        return "data_loaded"
    return "empty"
""",
    )

    violations = check_llm_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "study.loaded_data_list" in violations[0]
    assert "ApplicationService state snapshot" in violations[0]


def test_llm_direct_study_state_guard_allows_legacy_stage_helper(tmp_path):
    _write_llm_file(
        tmp_path,
        """
def _legacy_study_pipeline_stage(study):
    if study.loaded_data_list:
        return "data_loaded"
    return "empty"
""",
    )

    assert check_llm_direct_study_state_reads(tmp_path) == []


def test_controller_study_get_controller_guard_flags_product_fallback(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    training_ctrl = self.training_controller
    if not training_ctrl and self.controller and hasattr(self.controller, "study"):
        training_ctrl = self.controller.study.get_controller("training")
    if training_ctrl:
        self._create_refresh_bridge(training_ctrl, "training_stopped")
""",
    )

    violations = check_ui_controller_study_get_controller_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "controller.study.get_controller" in violations[0]
    assert "explicit legacy/fallback helper" in violations[0]


def test_controller_study_get_controller_guard_allows_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_training_controller_for_bridges(self):
    return run_legacy_controller_fallback(
        self,
        lambda: self.controller.study.get_controller("training"),
    )
""",
    )

    assert check_ui_controller_study_get_controller_fallbacks(tmp_path) == []


def test_direct_study_get_controller_guard_flags_product_parent_fallback(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def __init__(self, controller=None, parent=None):
    if controller is None and parent and hasattr(parent, "study"):
        controller = parent.study.get_controller("dataset")
    super().__init__(parent=parent, controller=controller)
""",
    )

    violations = check_ui_direct_study_get_controller_lookups(tmp_path)

    assert len(violations) == 1
    assert "study.get_controller" in violations[0]
    assert "legacy/fallback helper" in violations[0]


def test_direct_study_get_controller_guard_flags_product_study_lookup(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def __init__(self, study):
    self.preprocess_controller = study.get_controller("preprocess")
""",
    )

    violations = check_ui_direct_study_get_controller_lookups(tmp_path)

    assert len(violations) == 1
    assert "study.get_controller" in violations[0]


def test_direct_study_get_controller_guard_flags_main_window_lookup(tmp_path):
    path = tmp_path / "XBrainLab" / "ui" / "main_window.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def init_panels(self):
    dataset_ctrl = self.study.get_controller("dataset")
    self.dataset_panel = DatasetPanel(dataset_ctrl, self)
""",
        encoding="utf-8",
    )

    violations = check_ui_direct_study_get_controller_lookups(tmp_path)

    assert len(violations) == 1
    assert "XBrainLab/ui/main_window.py" in violations[0]
    assert "study.get_controller" in violations[0]


def test_direct_study_get_controller_guard_allows_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_controller_from_parent(self, parent):
    return parent.study.get_controller("dataset")
""",
    )

    assert check_ui_direct_study_get_controller_lookups(tmp_path) == []
