"""Static architecture compliance checker for the XBrainLab UI layer.

Scans all Python source files under ``XBrainLab/ui`` and reports
violations of the following rules:

1. UI panels must not import from other panels (cross-panel imports).
2. UI panels must inherit from ``BasePanel``.
3. UI panels must not access ``self.main_window.study`` directly;
   interactions with the backend should go through the Controller.
4. Dialogs must inherit from ``BaseDialog``.

Run as a standalone script::

    python tests/architecture_compliance.py
"""

import ast
import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath

_UNRESOLVED_CALLABLE_ORIGIN = "<unresolved-callable-construction>"
_DYNAMIC_CALLABLE_CONTAINER_KEY = object()


def _repo_relative_posix(path: PurePath, root_dir: PurePath) -> str:
    """Render a repository path consistently in guard diagnostics."""
    return path.relative_to(root_dir).as_posix()


FORBIDDEN_PRODUCT_LLM_TOKENS = (
    "APIBackend",
    "GeminiBackend",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XBRAINLAB_SHOW_LEGACY_REMOTE_LLM",
)
LOCAL_ONLY_LLM_TOKEN_ALLOWLIST = {
    Path("XBrainLab/backend/utils/public_diagnostics.py"): frozenset(
        {
            # The privacy boundary must recognize this credential name so it can
            # redact it. It does not read or configure a remote runtime.
            "OPENAI_API_KEY",
        }
    ),
}
REMOTE_SDK_DEFAULT_DEPS = ("openai", "google-genai")
UI_CONTROLLER_FALLBACK_METHODS = (
    "_run_legacy_label_import",
    "_run_metadata_update_fallback",
    "apply_channel_selection",
    "apply_data_splitting",
    "apply_epoching",
    "apply_filter",
    "apply_labels_batch",
    "apply_labels_sequence",
    "apply_montage",
    "apply_normalization",
    "apply_resample",
    "apply_rereference",
    "apply_smart_parse",
    "clean_dataset",
    "clean_datasets",
    "clear_history",
    "import_files",
    "remove_files",
    "reset_preprocess",
    "set_model_holder",
    "set_saliency_params",
    "set_training_option",
    "start_training",
    "stop_training",
    "update_metadata",
)
UI_CONTROLLER_FALLBACK_WRAPPERS = (
    "run_controller_compatibility_call",
    "_compatibility_controller_value",
    "_compatibility_locked_preflight_blocked",
    "_compatibility_preprocessed_data_list_for_render",
    "_run_preprocess_compatibility_call",
)

LEGACY_AGENT_CONTROLLER_LIFECYCLE_ATTRIBUTES = frozenset(
    {
        "_active_generation_dispatch_phase",
        "_active_generation_id",
        "_active_host_turn_generation",
        "_active_host_turn_id",
        "_active_rag_turn_id",
        "_active_tool_publication",
        "_active_turn_excluded_commands",
        "_active_turn_scope",
        "_active_turn_terminal_command",
        "_admitted_command_name",
        "_admitted_publication_generation",
        "_cancellation_response_sent",
        "_generation_dispatch_in_progress",
        "_generation_id",
        "_last_tool_summary",
        "_last_tool_summary_kind",
        "_loop_break_count",
        "_rag_turn_id",
        "_retry_count",
        "_stopping_generation_id",
        "_successful_tool_count",
        "_tool_execution_count",
        "_tool_failure_count",
        "_turn_cancelled",
        "_visible_response_sent",
        "_waiting_for_rag",
    }
)

APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_ATTRIBUTES = frozenset(
    {
        "_closed",
        "_closing",
        "_shutdown_fenced",
        "_shutdown_fence_generation",
    }
)
APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_METHODS = frozenset(
    {
        "_begin_close",
        "_complete_shutdown_fence_release",
        "_runtime_saliency_terminal_delivery_committed",
        "_terminal_saliency_release_obligation",
    }
)
LEGACY_AGENT_MANAGER_PUBLICATION_ALIASES = frozenset(
    {
        "_assistant_training_watch",
        "_pending_application_view_publication",
        "_pending_assistant_training_terminal",
    }
)
PUBLIC_ASSISTANT_PUBLICATION_STATE_FIELDS = frozenset(
    {
        "pending_publication",
        "pending_training_terminal",
        "publication_retry_attempts",
        "training_watch",
    }
)


@dataclass(frozen=True)
class ControllerDirectCallAllowance:
    """One exact non-ApplicationService controller call that UI may retain."""

    function_name: str
    receiver_identity: str
    methods: frozenset[str]


UI_CONTROLLER_DIRECT_CALL_ALLOWLIST = {
    Path("XBrainLab/ui/chat/panel.py"): (
        ControllerDirectCallAllowance(
            "_restore_controller_state",
            "controller",
            frozenset({"get_typed_history"}),
        ),
    ),
    Path("XBrainLab/ui/components/agent_manager.py"): (
        ControllerDirectCallAllowance(
            "_on_application_command_started",
            "self.chat_controller",
            frozenset({"set_processing"}),
        ),
        ControllerDirectCallAllowance(
            "handle_user_input",
            "self.chat_controller",
            frozenset({"add_user_message"}),
        ),
        ControllerDirectCallAllowance(
            "_prepare_admitted_transcript_turn",
            "self.chat_controller",
            frozenset({"prepare_for_turn"}),
        ),
        ControllerDirectCallAllowance(
            "_render_visible_assistant_response",
            "self.chat_controller",
            frozenset({"add_agent_message"}),
        ),
        ControllerDirectCallAllowance(
            "_clear_active_response_actions",
            "self.chat_controller",
            frozenset({"consume_all_response_actions"}),
        ),
        ControllerDirectCallAllowance(
            "_handle_response_action_selection",
            "self.chat_controller",
            frozenset({"resolve_and_consume_response_action"}),
        ),
        ControllerDirectCallAllowance(
            "_restore_rejected_response_action",
            "self.chat_controller",
            frozenset({"active_response_record"}),
        ),
        ControllerDirectCallAllowance(
            "_clear_conversation_presentation",
            "self.chat_controller",
            frozenset({"clear_conversation"}),
        ),
        ControllerDirectCallAllowance(
            "_resolve",
            "self.agent_controller",
            frozenset({"on_panel_navigation_resolved"}),
        ),
        ControllerDirectCallAllowance(
            "handle_panel_navigation",
            "self.agent_controller",
            frozenset({"on_panel_navigation_resolved"}),
        ),
        ControllerDirectCallAllowance(
            "on_assistant_activity_changed",
            "self.chat_controller",
            frozenset({"set_processing"}),
        ),
        ControllerDirectCallAllowance(
            "_on_assistant_turn_finished",
            "self.chat_controller",
            frozenset({"set_processing"}),
        ),
        ControllerDirectCallAllowance(
            "_create_assistant_controller",
            "controller",
            frozenset({"close"}),
        ),
    ),
    Path("XBrainLab/ui/components/assistant_command_dispatcher.py"): (
        ControllerDirectCallAllowance(
            "_invoke_turn_handler",
            "self._controller",
            frozenset({"handle_user_turn"}),
        ),
        ControllerDirectCallAllowance(
            "_invoke_debug_handler",
            "self._controller",
            frozenset({"execute_debug_tool"}),
        ),
        ControllerDirectCallAllowance(
            "shutdown",
            "self._controller",
            frozenset({"close"}),
        ),
        ControllerDirectCallAllowance(
            "_finish",
            "self._controller",
            frozenset({"moveToThread"}),
        ),
        ControllerDirectCallAllowance(
            "bind",
            "controller",
            frozenset({"moveToThread"}),
        ),
        ControllerDirectCallAllowance(
            "_emit_or_call",
            "self._controller",
            frozenset({"<dynamic>"}),
        ),
        ControllerDirectCallAllowance(
            "close",
            "self._controller",
            frozenset({"close"}),
        ),
    ),
    Path("XBrainLab/ui/components/assistant_runtime_lifecycle.py"): (
        ControllerDirectCallAllowance(
            "_rollback_failed_start",
            "controller",
            frozenset({"close"}),
        ),
        ControllerDirectCallAllowance(
            "close",
            "self._controller",
            frozenset({"close"}),
        ),
    ),
    Path("XBrainLab/ui/components/info_panel_service.py"): (
        ControllerDirectCallAllowance(
            "_query_data_lists",
            "compatibility_controller:dataset",
            frozenset({"get_loaded_data_list"}),
        ),
        ControllerDirectCallAllowance(
            "_query_data_lists",
            "compatibility_controller:preprocess",
            frozenset({"get_preprocessed_data_list"}),
        ),
    ),
    Path("XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py"): (
        ControllerDirectCallAllowance(
            "_compatibility_locked_preflight_blocked",
            "controller",
            frozenset({"is_locked"}),
        ),
    ),
    Path("XBrainLab/ui/panels/dataset/sidebar.py"): (
        ControllerDirectCallAllowance(
            "_compatibility_has_epoch_data",
            "self.controller",
            frozenset({"is_epoched"}),
        ),
    ),
}
UI_POST_COMMAND_LOCAL_REFRESH_METHODS = (
    "check_ready_to_train",
    "mark_refresh_dirty",
    "notify_update",
    "on_update",
    "refresh_backend_status",
    "refresh_combos",
    "update_info",
    "update_info_panel",
    "update_panel",
)
UI_POST_COMMAND_PUBLICATION_RENDER_METHODS = (
    "_render_training_publication",
    "_render_training_started",
    "on_training_started",
    "on_training_stopped",
    "reconcile_training_terminal_outcome",
    "training_finished",
)
UI_POST_COMMAND_PUBLICATION_CONTROL_NAMES = ("btn_start", "btn_stop")
UI_POST_COMMAND_PUBLICATION_CONTROL_MUTATORS = (
    "setChecked",
    "setDisabled",
    "setEnabled",
    "setHidden",
    "setText",
    "setVisible",
)
UI_SERVICE_COMMAND_METHODS = (
    "_execute_action",
    "execute_application_command",
)
UI_SERVICE_COMMAND_ASYNC_METHODS = (
    "_execute_action_async",
    "execute_application_command_async",
)
UI_OBSERVER_HANDLER_LOCAL_RENDER_METHODS = (
    *UI_POST_COMMAND_LOCAL_REFRESH_METHODS,
    "update_info",
    "update_loop",
)
UI_OBSERVER_HANDLER_LOCAL_RENDER_ALLOWLIST = {
    ("training_updated", "update_loop"),
}
UI_POST_COMMAND_CONTROLLER_ECHO_METHODS = ("get_model_holder",)
UI_CAPABILITY_GATED_CONTROLLER_READINESS_METHODS = (
    "get_channel_names",
    "get_filenames",
    "get_preprocessed_data_list",
    "get_trainer",
    "get_saliency_params",
    "has_datasets",
    "has_data",
    "has_model",
    "has_training_option",
    "is_training",
    "is_locked",
    "validate_ready",
)
UI_CONTROLLER_RENDER_FALLBACK_METHODS = (
    "get_averaged_record",
    "get_channel_names",
    "get_filenames",
    "get_formatted_history",
    "get_loaded_data_list",
    "get_model_holder",
    "get_model_summary_str",
    "get_plans",
    "get_pooled_eval_result",
    "get_preprocessed_data_list",
    "get_saliency_params",
    "get_trainers",
)
UI_DIRECT_STUDY_STATE_ATTRIBUTES = (
    "loaded_data_list",
    "preprocessed_data_list",
    "epoch_data",
    "datasets",
    "dataset_generator",
    "model_holder",
    "training_option",
    "trainer",
)
PRODUCT_SUCCESS_DIRECT_STUDY_STATE_TEST_FILES = (
    Path("tests/integration/backend/test_application_service_workflow.py"),
    Path("tests/integration/pipeline/test_preprocess_validation.py"),
    Path("tests/integration/pipeline/test_real_data_command_spine.py"),
    Path("tests/integration/ui/test_epoch_runtime.py"),
    Path("tests/integration/ui/test_product_walkthrough.py"),
)
PRODUCT_SUCCESS_DIRECT_STUDY_METHODS = ("get_datasets_generator",)
HEADLESS_VERIFIER_STATE_TRUTH_FILES = (
    Path("scripts/dev/run_public_cross_source_training_smoke.py"),
)
HEADLESS_VERIFIER_DIRECT_STUDY_METHODS = (
    "generate_plan",
    "is_training",
    "stop_training",
    "train",
)
UI_DIRECT_STUDY_CONTROLLER_LOOKUP_ALLOWED_FILES: tuple[str, ...] = ()
UI_AGENT_WORKER_INTERNAL_TOKENS = (
    ".worker.engine",
    ".worker.generation_thread",
    "agent_controller.worker",
)
ASSISTANT_RUNTIME_SELECTION_OWNER = Path("XBrainLab/llm/core/runtime_selection.py")
ASSISTANT_RUNTIME_SELECTION_CONSUMERS = (
    Path("XBrainLab/llm/agent/controller.py"),
    Path("XBrainLab/llm/agent/worker.py"),
    Path("XBrainLab/ui/components/assistant_command_dispatcher.py"),
    Path("XBrainLab/ui/components/assistant_runtime_coordinator.py"),
    Path("XBrainLab/ui/components/assistant_runtime_lifecycle.py"),
)
ASSISTANT_RUNTIME_SELECTION_POLICY_CALLS = frozenset(
    {
        "allowed_local_model_ids",
        "apply_runtime_selection",
        "assistant_runtime_selection",
        "assistant_runtime_selection_from",
        "available_local_model_id",
        "default_local_model_id",
        "local_backend_ready",
        "local_backend_status_message",
        "local_model_policy_error",
        "normalize_backend_mode",
    }
)
ASSISTANT_RUNTIME_STARTUP_FUNCTIONS = frozenset(
    {"initialize_agent", "reinitialize_agent"}
)
UI_OBSERVER_REFRESH_EVENTS = (
    "data_changed",
    "preprocess_changed",
    "training_started",
    "training_stopped",
    "training_updated",
    "config_changed",
    "history_cleared",
    "montage_changed",
    "saliency_changed",
)
UI_REFRESH_FALSE_READ_ONLY_COMMANDS = (
    "EvaluateCommand",
    "QueryStateCommand",
    "VisualizeCommand",
)
PRODUCT_RUNTIME_BACKEND_FACADE_DIRS = (
    Path("XBrainLab/ui"),
    Path("XBrainLab/llm"),
)
MAPPED_REAL_TOOL_FILES = (
    Path("XBrainLab/llm/tools/__init__.py"),
    Path("XBrainLab/llm/tools/real/preprocess_real.py"),
    Path("XBrainLab/llm/tools/real/training_real.py"),
)
CANONICAL_DELEGATING_REAL_TOOL_CLASSES = frozenset(
    {
        "RealBandPassFilterTool",
        "RealNormalizeTool",
        "RealNotchFilterTool",
        "RealRereferenceTool",
        "RealResampleTool",
        "RealStartTrainingTool",
        "RealStopTrainingTool",
    }
)
APPLICATION_SERVICE_CACHE_OWNER_FILES = frozenset(
    {
        Path("XBrainLab/backend/application/runtime.py"),
    }
)
TRAINING_CONFIGURATION_RESET_DELEGATE = Path(
    "XBrainLab/backend/application/training_configuration_reset.py"
)
TRAINING_CONFIGURATION_RESET_FIELDS = frozenset(
    {"model_holder", "training_option", "saliency_params"}
)
TRAINING_RUNTIME_OWNER = Path("XBrainLab/backend/application/training_runtime.py")
STUDY_TRAINING_COMPATIBILITY_FIELDS = frozenset(
    {"trainer", "model_holder", "training_option", "saliency_params"}
)
SALIENCY_PROVENANCE_OWNER = Path("XBrainLab/backend/training/saliency_provenance.py")
SALIENCY_PROVENANCE_COMPATIBILITY_MODULE = Path(
    "XBrainLab/backend/training/record/eval.py"
)
SALIENCY_ARTIFACT_INTEGRITY_OWNER = Path(
    "XBrainLab/backend/training/saliency_artifact_integrity.py"
)
SALIENCY_ARTIFACT_INTEGRITY_ALLOWED_CONSUMERS = frozenset(
    {
        SALIENCY_ARTIFACT_INTEGRITY_OWNER,
        Path("XBrainLab/backend/training/evaluator.py"),
        Path("XBrainLab/backend/training/record/eval.py"),
    }
)
SALIENCY_ARTIFACT_INTEGRITY_REQUIRED_NAMES = frozenset(
    {
        "SaliencyArtifactIntegrityError",
        "SaliencyIntegrityReason",
        "build_saliency_artifact_manifest",
        "normalize_saliency_method_parameters",
        "verify_saliency_artifact_manifest",
    }
)
SALIENCY_ARTIFACT_POLICY_TOKENS = (
    "saliency_integrity_manifest",
    "SaliencyArtifactIntegrityError",
    "SaliencyIntegrityReason",
    "build_saliency_artifact_manifest",
    "verify_saliency_artifact_manifest",
)
SALIENCY_PROVENANCE_PUBLIC_NAMES = frozenset(
    {
        "SALIENCY_CONTEXT_SCHEMA_VERSION",
        "SALIENCY_PRODUCER_SCHEMA_VERSION",
        "SaliencyArtifactContext",
        "SaliencyContextError",
        "SaliencyProducerIdentity",
        "fingerprint_saliency_epoch_data",
        "fingerprint_saliency_model_state",
        "fingerprint_saliency_split_mask",
    }
)
SALIENCY_PROVENANCE_PRIVATE_DEFINITIONS = frozenset(
    {
        "_bounded_array_descriptor",
        "_bounded_indices",
        "_bounded_sequence_descriptor",
        "_canonical_identity_value",
        "_exact_array_descriptor",
        "_fingerprint_identity_payload",
        "_fingerprint_numpy_array_content",
        "_fingerprint_torch_tensor_content",
        "_is_sha256_fingerprint",
        "_iter_torch_tensor_chunks",
        "_numpy_chunk_as_byte_view",
        "_plain_identity_value",
        "_read_channel_names",
        "_read_epoch_model_args",
        "_read_montage_fingerprint",
        "_row_major_coordinates",
        "_torch_chunk_as_byte_view",
    }
)
APPLICATION_STATE_SERVICE_MODULE = Path(
    "XBrainLab/backend/application/state_service.py"
)
SALIENCY_COVERAGE_OWNER = Path("XBrainLab/backend/application/saliency_coverage.py")
QUERY_STATE_SERVICE_OWNER = Path("XBrainLab/backend/application/query_state_service.py")
SALIENCY_COVERAGE_PUBLIC_NAMES = frozenset(
    {
        "SaliencyCoverageProjector",
        "saliency_coverage_for_eval_record",
        "saliency_label_items_from_epoch",
        "saliency_method_coverage",
    }
)
SALIENCY_COVERAGE_COMPATIBILITY_NAMES = frozenset(
    {
        "saliency_coverage_for_eval_record",
        "saliency_label_items_from_epoch",
        "saliency_method_coverage",
    }
)
SALIENCY_COVERAGE_UI_CALL_NAMES = frozenset(
    {
        "SaliencyCoverageProjector",
        "label_items_from_epoch",
        "project_eval_record",
        "project_method",
        "project_run",
        *SALIENCY_COVERAGE_COMPATIBILITY_NAMES,
    }
)
SALIENCY_COVERAGE_POLICY_DEFINITIONS = frozenset(
    {
        "SaliencyCoverageProjector",
        "_SALIENCY_METHOD_STORES",
        "_SALIENCY_STORE_BY_METHOD",
        "_complete_normalized_saliency_store",
        "_has_nonempty_saliency_value",
        "_normalized_saliency_key",
        "_saliency_classes",
        "_saliency_identity_equal",
        "_saliency_method_coverage",
        "_saliency_store_item_for_class",
        "_saliency_store_items",
        "_valid_saliency_label_items",
        *SALIENCY_COVERAGE_COMPATIBILITY_NAMES,
    }
)
SALIENCY_COVERAGE_SNAPSHOT_TYPES = frozenset(
    {
        "SaliencyClassCoverageSnapshot",
        "SaliencyMethodCoverageSnapshot",
        "SaliencyRunCoverageSnapshot",
    }
)
PRODUCT_SUCCESS_BACKEND_FACADE_TEST_DIRS = (
    Path("tests/integration/backend"),
    Path("tests/integration/io"),
    Path("tests/integration/pipeline"),
    Path("tests/integration/ui"),
)
PRODUCT_SUCCESS_CONTROLLER_LOOKUP_ASSERTIONS = (
    "assert_any_call",
    "assert_called",
    "assert_called_once",
    "assert_called_once_with",
    "assert_called_with",
)
STRICT_TOOL_ENVELOPE_ENTRYPOINTS = (
    Path("XBrainLab/llm/agent/controller.py"),
    Path("scripts/dev/run_stable_assistant_model_eval.py"),
)
LLM_AGENT_CONFIRMATION_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/agent/test_confirmation.py"),
    Path("tests/unit/llm/agent/test_controller.py"),
)
AGENT_CONFIRMATION_CONTRACT_EVIDENCE = Path("tests/unit/llm/agent/test_confirmation.py")
AGENT_CONFIRMATION_CORRELATION_FIELDS = frozenset(
    {"request_id", "params_fingerprint", "publication_generation"}
)
PENDING_INTERACTION_RUNTIME_FILES = (
    Path("XBrainLab/llm/agent/controller.py"),
    Path("XBrainLab/llm/agent/pending_interaction.py"),
)
PENDING_INTERACTION_COMPATIBILITY_MEMBERS = frozenset(
    {
        "_pending_confirmation",
        "_pending_confirmation_request",
        "_pending_workflow_handoff",
        "replace_confirmation_for_compatibility",
        "replace_workflow_handoff_for_compatibility",
    }
)
PENDING_INTERACTION_TEST_ROOTS = (
    Path("tests/unit/llm"),
    Path("tests/unit/ui/components"),
)
PENDING_INTERACTION_TEST_FILES = (Path("tests/unit/test_architecture_compliance.py"),)
LEGACY_MONTAGE_HANDOFF_FILE = Path(
    "XBrainLab/ui/components/montage_interaction_coordinator.py"
)
MONTAGE_HANDOFF_CONTROLLER = Path("XBrainLab/llm/agent/controller.py")
MONTAGE_HANDOFF_HOST = Path("XBrainLab/ui/components/workflow_ui_handoff_host.py")
MONTAGE_HANDOFF_MANAGER = Path("XBrainLab/ui/components/agent_manager.py")
LEGACY_MONTAGE_MANAGER_SYMBOLS = (
    "open_montage_picker_dialog",
    "_montage_interactions",
)
LEGACY_MONTAGE_FAKE_USER_MESSAGES = (
    "Montage Confirmed.",
    "Montage Selection Failed.",
)
MUTABLE_BOUNDARY_INCLUDE_OBJECTS = "include_objects"
MUTABLE_BOUNDARY_LOCAL_PAYLOAD = "local_payload"
MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD = "local_result_payload"
MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME = "command_result_runtime"
MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE = "ui_backend_domain_storage"


@dataclass(frozen=True)
class MutableObjectBoundaryDebt:
    """One exact current mutable-object boundary allowed during migration."""

    path: str
    symbol: str
    boundary: str
    form: str
    allowed_occurrences: int = 1


MUTABLE_OBJECT_BOUNDARY_DEBT_ALLOWLIST = (
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/agent_manager.py",
        "AgentManager.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        "AssistantRuntimeLifecycle.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/info_panel_service.py",
        "InfoPanelService.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/plot_figure_window.py",
        "PlotFigureWindow.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
        2,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/plot_figure_window.py",
        "PlotFigureWindow.on_plan_select",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
        2,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/plot_figure_window.py",
        "PlotFigureWindow.on_real_plan_select",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/plot_figure_window.py",
        "PlotFigureWindow.update_loop",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/main_window.py",
        "MainWindow.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/visualization/panel.py",
        "VisualizationPanel._refresh_application_query",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
)


def check_architecture(root_dir: str) -> int:
    """Verify architecture compliance rules for the UI layer.

    Scans every ``*.py`` file under ``<root_dir>/XBrainLab/ui`` and
    checks the following rules:

    1. UI panels should not import from other panels (cross-panel
       imports), except sidebars/dialogs within the same module.
    2. UI panels (``panels/*/panel.py``) should inherit from
       ``BasePanel``.
    3. UI panels should not access ``self.main_window.study`` directly
       — the Controller should be used instead.
    4. Dialogs should inherit from ``BaseDialog``.

    Args:
        root_dir: Absolute path to the project root directory that
            contains the ``XBrainLab/`` package.

    Returns:
        ``0`` if all checks pass, ``1`` if any violation is detected or
        the UI directory is missing.
    """
    print(f"Checking architecture compliance in {root_dir}...")

    ui_dir = Path(root_dir) / "XBrainLab" / "ui"
    if not ui_dir.exists():
        print(f"UI directory not found: {ui_dir}")
        return 1

    violations = []

    # Critical Check: BasePanel inheritance
    for panel_file in ui_dir.glob("panels/*/panel.py"):
        with open(panel_file, encoding="utf-8") as f:
            content = f.read()
            if "class" in content and "BasePanel" not in content:
                violations.append(f"{panel_file.name} does not inherit from BasePanel")

    # Critical Check: Direct Study Access
    for py_file in ui_dir.rglob("*.py"):
        with open(py_file, encoding="utf-8") as f:
            content = f.read()
            if (
                "self.main_window.study" in content
                and "main_window.py" not in py_file.name
            ):
                violations.append(
                    f"{py_file.relative_to(root_dir)} accesses self.main_window.study directy"
                )

    if violations:
        print("\nArchitecture Violations Found:")
        for v in violations:
            print(f" - {v}")
        return 1

    llm_violations = check_local_only_llm_runtime(Path(root_dir))
    if llm_violations:
        print("\nLocal-only LLM Runtime Violations Found:")
        for violation in llm_violations:
            print(f" - {violation}")
        return 1

    backend_llm_import_violations = check_backend_llm_imports(Path(root_dir))
    if backend_llm_import_violations:
        print("\nBackend to LLM Import Violations Found:")
        for violation in backend_llm_import_violations:
            print(f" - {violation}")
        return 1

    saliency_provenance_violations = check_saliency_provenance_ownership(Path(root_dir))
    if saliency_provenance_violations:
        print("\nSaliency Provenance Ownership Violations Found:")
        for violation in saliency_provenance_violations:
            print(f" - {violation}")
        return 1

    saliency_integrity_violations = check_saliency_artifact_integrity_ownership(
        Path(root_dir)
    )
    if saliency_integrity_violations:
        print("\nSaliency Artifact Integrity Ownership Violations Found:")
        for violation in saliency_integrity_violations:
            print(f" - {violation}")
        return 1

    visualization_saliency_violations = (
        check_visualization_saliency_publication_boundary(Path(root_dir))
    )
    if visualization_saliency_violations:
        print("\nVisualization Saliency Publication Violations Found:")
        for violation in visualization_saliency_violations:
            print(f" - {violation}")
        return 1

    application_state_violations = check_application_state_module_boundaries(
        Path(root_dir)
    )
    if application_state_violations:
        print("\nApplication State Module Boundary Violations Found:")
        for violation in application_state_violations:
            print(f" - {violation}")
        return 1

    application_service_ownership_violations = (
        check_application_service_ownership_boundaries(Path(root_dir))
    )
    if application_service_ownership_violations:
        print("\nApplicationService Ownership Boundary Violations Found:")
        for violation in application_service_ownership_violations:
            print(f" - {violation}")
        return 1

    application_shutdown_violations = check_application_shutdown_lifecycle_ownership(
        Path(root_dir)
    )
    if application_shutdown_violations:
        print("\nApplication Shutdown Lifecycle Ownership Violations Found:")
        for violation in application_shutdown_violations:
            print(f" - {violation}")
        return 1

    application_controller_violations = check_application_controller_boundary(
        Path(root_dir)
    )
    if application_controller_violations:
        print("\nApplication Controller Boundary Violations Found:")
        for violation in application_controller_violations:
            print(f" - {violation}")
        return 1

    dataset_product_port_violations = check_dataset_product_port_boundary(
        Path(root_dir)
    )
    if dataset_product_port_violations:
        print("\nDataset Product Port Boundary Violations Found:")
        for violation in dataset_product_port_violations:
            print(f" - {violation}")
        return 1

    preprocess_product_port_violations = check_preprocess_product_port_boundary(
        Path(root_dir)
    )
    if preprocess_product_port_violations:
        print("\nPreprocess Product Port Boundary Violations Found:")
        for violation in preprocess_product_port_violations:
            print(f" - {violation}")
        return 1

    visualization_product_port_violations = check_visualization_product_port_boundary(
        Path(root_dir)
    )
    if visualization_product_port_violations:
        print("\nVisualization Product Port Boundary Violations Found:")
        for violation in visualization_product_port_violations:
            print(f" - {violation}")
        return 1

    publication_lifecycle_port_violations = (
        check_application_publication_lifecycle_port_boundary(Path(root_dir))
    )
    if publication_lifecycle_port_violations:
        print("\nApplication Publication Lifecycle Port Violations Found:")
        for violation in publication_lifecycle_port_violations:
            print(f" - {violation}")
        return 1

    training_runtime_violations = check_training_runtime_port_boundary(Path(root_dir))
    if training_runtime_violations:
        print("\nTraining Runtime Port Boundary Violations Found:")
        for violation in training_runtime_violations:
            print(f" - {violation}")
        return 1

    raw_mutation_atomicity_violations = check_raw_mutation_atomicity_boundaries(
        Path(root_dir)
    )
    if raw_mutation_atomicity_violations:
        print("\nRaw Mutation Atomicity Boundary Violations Found:")
        for violation in raw_mutation_atomicity_violations:
            print(f" - {violation}")
        return 1

    label_resource_violations = check_label_resource_admission_boundary(Path(root_dir))
    if label_resource_violations:
        print("\nLabel Resource Admission Boundary Violations Found:")
        for violation in label_resource_violations:
            print(f" - {violation}")
        return 1

    training_history_violations = check_training_history_projection_boundary(
        Path(root_dir),
    )
    if training_history_violations:
        print("\nTraining History Projection Boundary Violations Found:")
        for violation in training_history_violations:
            print(f" - {violation}")
        return 1

    dataset_read_violations = check_dataset_detached_read_boundary(Path(root_dir))
    if dataset_read_violations:
        print("\nDataset Detached Read Boundary Violations Found:")
        for violation in dataset_read_violations:
            print(f" - {violation}")
        return 1

    dataset_split_violations = check_dataset_split_publication_boundary(Path(root_dir))
    if dataset_split_violations:
        print("\nDataset Split Publication Boundary Violations Found:")
        for violation in dataset_split_violations:
            print(f" - {violation}")
        return 1

    epoch_dialog_violations = check_epoch_dialog_publication_boundary(Path(root_dir))
    if epoch_dialog_violations:
        print("\nEpoch Dialog Publication Boundary Violations Found:")
        for violation in epoch_dialog_violations:
            print(f" - {violation}")
        return 1

    mutable_object_boundary_violations = check_mutable_object_boundaries(
        Path(root_dir),
        validate_allowlist=True,
    )
    if mutable_object_boundary_violations:
        print("\nMutable Object Boundary Violations Found:")
        for violation in mutable_object_boundary_violations:
            print(f" - {violation}")
        return 1

    montage_command_ownership_violations = check_montage_command_ownership(
        Path(root_dir)
    )
    if montage_command_ownership_violations:
        print("\nMontage Command Ownership Violations Found:")
        for violation in montage_command_ownership_violations:
            print(f" - {violation}")
        return 1

    training_reset_ownership_violations = check_training_configuration_reset_ownership(
        Path(root_dir)
    )
    if training_reset_ownership_violations:
        print("\nTraining Configuration Reset Ownership Violations Found:")
        for violation in training_reset_ownership_violations:
            print(f" - {violation}")
        return 1

    runtime_mock_violations = check_product_runtime_mock_dependencies(Path(root_dir))
    if runtime_mock_violations:
        print("\nProduct Runtime Mock Dependency Violations Found:")
        for violation in runtime_mock_violations:
            print(f" - {violation}")
        return 1

    tool_result_contract_violations = check_concrete_llm_tool_result_contracts(
        Path(root_dir)
    )
    if tool_result_contract_violations:
        print("\nConcrete LLM Tool Result Contract Violations Found:")
        for violation in tool_result_contract_violations:
            print(f" - {violation}")
        return 1

    real_tool_command_ownership_violations = check_mapped_real_tool_command_ownership(
        Path(root_dir)
    )
    if real_tool_command_ownership_violations:
        print("\nMapped Real Tool Command Ownership Violations Found:")
        for violation in real_tool_command_ownership_violations:
            print(f" - {violation}")
        return 1

    typed_confirmation_violations = check_typed_agent_confirmation_boundary(
        Path(root_dir)
    )
    if typed_confirmation_violations:
        print("\nTyped Agent Confirmation Boundary Violations Found:")
        for violation in typed_confirmation_violations:
            print(f" - {violation}")
        return 1

    pending_interaction_compatibility_violations = (
        check_pending_interaction_compatibility_api(Path(root_dir))
    )
    if pending_interaction_compatibility_violations:
        print("\nPending Interaction Compatibility API Violations Found:")
        for violation in pending_interaction_compatibility_violations:
            print(f" - {violation}")
        return 1

    controller_lifecycle_alias_violations = check_agent_controller_lifecycle_aliases(
        Path(root_dir)
    )
    if controller_lifecycle_alias_violations:
        print("\nAgent Controller Lifecycle Alias Violations Found:")
        for violation in controller_lifecycle_alias_violations:
            print(f" - {violation}")
        return 1

    manager_publication_state_violations = (
        check_agent_manager_publication_state_ownership(Path(root_dir))
    )
    if manager_publication_state_violations:
        print("\nAgent Manager Publication State Ownership Violations Found:")
        for violation in manager_publication_state_violations:
            print(f" - {violation}")
        return 1

    confirmation_evidence_violations = check_agent_confirmation_contract_evidence(
        Path(root_dir)
    )
    if confirmation_evidence_violations:
        print("\nAgent Confirmation Contract Evidence Violations Found:")
        for violation in confirmation_evidence_violations:
            print(f" - {violation}")
        return 1

    montage_handoff_violations = check_typed_montage_ui_handoff_boundary(Path(root_dir))
    if montage_handoff_violations:
        print("\nTyped Montage UI Handoff Boundary Violations Found:")
        for violation in montage_handoff_violations:
            print(f" - {violation}")
        return 1

    presentation_ownership_violations = check_assistant_presentation_ownership(
        Path(root_dir)
    )
    if presentation_ownership_violations:
        print("\nAssistant Presentation Ownership Violations Found:")
        for violation in presentation_ownership_violations:
            print(f" - {violation}")
        return 1

    turn_scope_ownership_violations = check_assistant_turn_scope_ownership(
        Path(root_dir)
    )
    if turn_scope_ownership_violations:
        print("\nAssistant Turn Scope Ownership Violations Found:")
        for violation in turn_scope_ownership_violations:
            print(f" - {violation}")
        return 1

    llm_study_state_violations = check_llm_direct_study_state_reads(Path(root_dir))
    if llm_study_state_violations:
        print("\nLLM Direct Study State Read Violations Found:")
        for violation in llm_study_state_violations:
            print(f" - {violation}")
        return 1

    facade_usage_violations = check_product_runtime_backend_facade_usage(Path(root_dir))
    if facade_usage_violations:
        print("\nProduct Runtime BackendFacade Usage Violations Found:")
        for violation in facade_usage_violations:
            print(f" - {violation}")
        return 1

    facade_test_violations = check_product_success_backend_facade_tests(Path(root_dir))
    if facade_test_violations:
        print("\nProduct Success BackendFacade Test Violations Found:")
        for violation in facade_test_violations:
            print(f" - {violation}")
        return 1

    facade_test_usage_violations = check_backend_facade_test_usage(Path(root_dir))
    if facade_test_usage_violations:
        print("\nBackendFacade Test Usage Violations Found:")
        for violation in facade_test_usage_violations:
            print(f" - {violation}")
        return 1

    product_success_study_state_violations = (
        check_product_success_direct_study_state_tests(Path(root_dir))
    )
    if product_success_study_state_violations:
        print("\nProduct Success Direct Study State Test Violations Found:")
        for violation in product_success_study_state_violations:
            print(f" - {violation}")
        return 1

    headless_verifier_study_state_violations = (
        check_headless_verifier_direct_study_state(Path(root_dir))
    )
    if headless_verifier_study_state_violations:
        print("\nHeadless Verifier Direct Study State Violations Found:")
        for violation in headless_verifier_study_state_violations:
            print(f" - {violation}")
        return 1

    controller_lookup_test_violations = (
        check_product_success_controller_lookup_assertions(Path(root_dir))
    )
    if controller_lookup_test_violations:
        print("\nProduct Success Controller Lookup Assertion Violations Found:")
        for violation in controller_lookup_test_violations:
            print(f" - {violation}")
        return 1

    worker_internal_violations = check_ui_agent_worker_internal_access(Path(root_dir))
    if worker_internal_violations:
        print("\nUI Agent Worker Internal Access Violations Found:")
        for violation in worker_internal_violations:
            print(f" - {violation}")
        return 1

    runtime_selection_violations = check_assistant_runtime_selection_ownership(
        Path(root_dir)
    )
    if runtime_selection_violations:
        print("\nAssistant Runtime Selection Ownership Violations Found:")
        for violation in runtime_selection_violations:
            print(f" - {violation}")
        return 1

    tool_envelope_boundary_violations = check_product_tool_envelope_boundary(
        Path(root_dir)
    )
    if tool_envelope_boundary_violations:
        print("\nProduct Tool Envelope Boundary Violations Found:")
        for violation in tool_envelope_boundary_violations:
            print(f" - {violation}")
        return 1

    interpretation_action_ownership_violations = (
        check_dataset_data_interpretation_action_ownership(Path(root_dir))
    )
    if interpretation_action_ownership_violations:
        print("\nDataset Data Interpretation Action Ownership Violations Found:")
        for violation in interpretation_action_ownership_violations:
            print(f" - {violation}")
        return 1

    resource_receipt_boundary_violations = check_agent_resource_receipt_boundary(
        Path(root_dir)
    )
    if resource_receipt_boundary_violations:
        print("\nAgent Resource Receipt Boundary Violations Found:")
        for violation in resource_receipt_boundary_violations:
            print(f" - {violation}")
        return 1

    fallback_violations = check_ui_controller_fallbacks(Path(root_dir))
    if fallback_violations:
        print("\nUI Controller Fallback Violations Found:")
        for violation in fallback_violations:
            print(f" - {violation}")
        return 1

    render_fallback_violations = check_ui_controller_render_fallbacks(Path(root_dir))
    if render_fallback_violations:
        print("\nUI Controller Render Fallback Violations Found:")
        for violation in render_fallback_violations:
            print(f" - {violation}")
        return 1

    training_history_fallback_violations = check_training_panel_history_fallback_scope(
        Path(root_dir)
    )
    if training_history_fallback_violations:
        print("\nTraining History Fallback Scope Violations Found:")
        for violation in training_history_fallback_violations:
            print(f" - {violation}")
        return 1

    direct_controller_mutation_violations = check_ui_direct_controller_mutations(
        Path(root_dir)
    )
    if direct_controller_mutation_violations:
        print("\nUI Direct Controller Mutation Violations Found:")
        for violation in direct_controller_mutation_violations:
            print(f" - {violation}")
        return 1

    legacy_helper_call_violations = check_ui_legacy_mutation_helper_calls(
        Path(root_dir)
    )
    if legacy_helper_call_violations:
        print("\nUI Legacy Mutation Helper Call Violations Found:")
        for violation in legacy_helper_call_violations:
            print(f" - {violation}")
        return 1

    legacy_fallback_scope_violations = check_ui_legacy_fallback_helper_scope(
        Path(root_dir)
    )
    if legacy_fallback_scope_violations:
        print("\nUI Legacy Fallback Helper Scope Violations Found:")
        for violation in legacy_fallback_scope_violations:
            print(f" - {violation}")
        return 1

    backend_execute_violations = check_ui_direct_backend_service_execute(Path(root_dir))
    if backend_execute_violations:
        print("\nUI Direct Backend Service Execute Violations Found:")
        for violation in backend_execute_violations:
            print(f" - {violation}")
        return 1

    command_suppression_violations = (
        check_ui_command_execution_suppresses_observer_refresh(Path(root_dir))
    )
    if command_suppression_violations:
        print("\nUI Command Observer Suppression Violations Found:")
        for violation in command_suppression_violations:
            print(f" - {violation}")
        return 1

    loader_apply_violations = check_ui_direct_loader_apply(Path(root_dir))
    if loader_apply_violations:
        print("\nUI Direct Loader Apply Violations Found:")
        for violation in loader_apply_violations:
            print(f" - {violation}")
        return 1

    study_state_violations = check_ui_direct_study_state_reads(Path(root_dir))
    if study_state_violations:
        print("\nUI Direct Study State Read Violations Found:")
        for violation in study_state_violations:
            print(f" - {violation}")
        return 1

    controller_study_violations = check_ui_controller_study_get_controller_fallbacks(
        Path(root_dir)
    )
    if controller_study_violations:
        print("\nUI Controller Study Fallback Violations Found:")
        for violation in controller_study_violations:
            print(f" - {violation}")
        return 1

    study_controller_lookup_violations = check_ui_direct_study_get_controller_lookups(
        Path(root_dir)
    )
    if study_controller_lookup_violations:
        print("\nUI Direct Study Controller Lookup Violations Found:")
        for violation in study_controller_lookup_violations:
            print(f" - {violation}")
        return 1

    controller_echo_violations = check_ui_post_command_controller_echoes(Path(root_dir))
    if controller_echo_violations:
        print("\nUI Post-command Controller Echo Violations Found:")
        for violation in controller_echo_violations:
            print(f" - {violation}")
        return 1

    capability_readiness_violations = check_ui_capability_gated_controller_readiness(
        Path(root_dir)
    )
    if capability_readiness_violations:
        print("\nUI Capability-gated Controller Readiness Violations Found:")
        for violation in capability_readiness_violations:
            print(f" - {violation}")
        return 1

    refresh_violations = check_ui_post_command_local_refreshes(Path(root_dir))
    if refresh_violations:
        print("\nUI Post-command Local Refresh Violations Found:")
        for violation in refresh_violations:
            print(f" - {violation}")
        return 1

    refresh_false_violations = check_ui_refresh_false_commands(Path(root_dir))
    if refresh_false_violations:
        print("\nUI No-refresh Command Violations Found:")
        for violation in refresh_false_violations:
            print(f" - {violation}")
        return 1

    observer_refresh_violations = check_ui_observer_direct_update_bridges(
        Path(root_dir)
    )
    if observer_refresh_violations:
        print("\nUI Observer Direct Refresh Violations Found:")
        for violation in observer_refresh_violations:
            print(f" - {violation}")
        return 1

    observer_handler_violations = check_ui_observer_handlers_call_refresh_coordinator(
        Path(root_dir)
    )
    if observer_handler_violations:
        print("\nUI Observer Handler Refresh Violations Found:")
        for violation in observer_handler_violations:
            print(f" - {violation}")
        return 1

    primary_bootstrap_violations = check_primary_panel_product_bootstrap_boundary(
        Path(root_dir)
    )
    if primary_bootstrap_violations:
        print("\nPrimary Panel Product Bootstrap Boundary Violations Found:")
        for violation in primary_bootstrap_violations:
            print(f" - {violation}")
        return 1

    primary_publication_violations = check_primary_ui_publication_refresh_boundary(
        Path(root_dir)
    )
    if primary_publication_violations:
        print("\nPrimary UI Publication Refresh Boundary Violations Found:")
        for violation in primary_publication_violations:
            print(f" - {violation}")
        return 1

    evaluation_refresh_violations = check_evaluation_publication_refresh_boundary(
        Path(root_dir)
    )
    if evaluation_refresh_violations:
        print("\nEvaluation Publication Refresh Boundary Violations Found:")
        for violation in evaluation_refresh_violations:
            print(f" - {violation}")
        return 1

    visualization_refresh_violations = check_visualization_publication_refresh_boundary(
        Path(root_dir)
    )
    if visualization_refresh_violations:
        print("\nVisualization Publication Refresh Boundary Violations Found:")
        for violation in visualization_refresh_violations:
            print(f" - {violation}")
        return 1

    print("\nArchitecture compliant!")
    return 0


def check_local_only_llm_runtime(root_dir: Path) -> list[str]:
    """Return violations of the product local-only LLM runtime boundary."""
    violations: list[str] = []
    product_dir = root_dir / "XBrainLab"
    if product_dir.exists():
        for py_file in product_dir.rglob("*.py"):
            if "llm/core/models" in py_file.as_posix():
                continue
            content = py_file.read_text(encoding="utf-8")
            relative_path = py_file.relative_to(root_dir)
            allowed_tokens = LOCAL_ONLY_LLM_TOKEN_ALLOWLIST.get(
                relative_path,
                frozenset(),
            )
            violations.extend(
                f"{relative_path} contains forbidden local-only runtime token {token!r}"
                for token in FORBIDDEN_PRODUCT_LLM_TOKENS
                if token in content and token not in allowed_tokens
            )

    pyproject = root_dir / "pyproject.toml"
    if pyproject.exists():
        default_deps = _read_poetry_default_dependency_names(pyproject)
        violations.extend(
            f"pyproject.toml default dependencies include {dep_name!r}; "
            "remote SDKs must stay in optional legacy groups."
            for dep_name in REMOTE_SDK_DEFAULT_DEPS
            if dep_name in default_deps
        )

    return violations


def check_backend_llm_imports(root_dir: Path) -> list[str]:
    """Reject reverse dependencies from the backend package into LLM code."""
    violations: list[str] = []
    backend_dir = root_dir / "XBrainLab" / "backend"
    if not backend_dir.exists():
        return violations

    for py_file in backend_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            imported_name: str | None = None
            if isinstance(node, ast.Import):
                imported_name = next(
                    (
                        alias.name
                        for alias in node.names
                        if alias.name == "XBrainLab.llm"
                        or alias.name.startswith("XBrainLab.llm.")
                    ),
                    None,
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "XBrainLab.llm" or module.startswith("XBrainLab.llm."):
                    imported_name = module
                elif module == "XBrainLab" and any(
                    alias.name == "llm" for alias in node.names
                ):
                    imported_name = "XBrainLab.llm"
                elif node.level and (module == "llm" or module.startswith("llm.")):
                    imported_name = module
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"__import__", "import_module"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and (
                    node.args[0].value == "XBrainLab.llm"
                    or node.args[0].value.startswith("XBrainLab.llm.")
                )
            ):
                imported_name = node.args[0].value

            if imported_name is not None:
                violations.append(
                    f"{py_file.relative_to(root_dir)}:"
                    f"{getattr(node, 'lineno', 0)} imports "
                    f"{imported_name}; backend contracts must not depend on "
                    "XBrainLab.llm."
                )

    return violations


def check_saliency_provenance_ownership(root_dir: Path) -> list[str]:
    """Keep saliency provenance in its domain module, not evaluation persistence."""
    violations: list[str] = []
    owner_path = root_dir / SALIENCY_PROVENANCE_OWNER
    compatibility_path = root_dir / SALIENCY_PROVENANCE_COMPATIBILITY_MODULE

    owner_tree = _parse_python_file(owner_path)
    if owner_tree is None:
        violations.append(
            f"{SALIENCY_PROVENANCE_OWNER} is missing or invalid; saliency provenance "
            "requires one dedicated domain owner."
        )
    else:
        missing_names = SALIENCY_PROVENANCE_PUBLIC_NAMES - _top_level_bound_names(
            owner_tree
        )
        if missing_names:
            violations.append(
                f"{SALIENCY_PROVENANCE_OWNER} does not own: "
                f"{', '.join(sorted(missing_names))}."
            )

    compatibility_tree = _parse_python_file(compatibility_path)
    if compatibility_tree is None:
        violations.append(
            f"{SALIENCY_PROVENANCE_COMPATIBILITY_MODULE} is missing or invalid."
        )
    else:
        forbidden_names = (
            SALIENCY_PROVENANCE_PUBLIC_NAMES | SALIENCY_PROVENANCE_PRIVATE_DEFINITIONS
        ) & _top_level_bound_names(compatibility_tree)
        if forbidden_names:
            violations.append(
                f"{SALIENCY_PROVENANCE_COMPATIBILITY_MODULE} defines saliency "
                f"provenance owned by {SALIENCY_PROVENANCE_OWNER}: "
                f"{', '.join(sorted(forbidden_names))}."
            )

        compatibility_exports = {
            alias.name
            for node in compatibility_tree.body
            if isinstance(node, ast.ImportFrom)
            and _is_saliency_provenance_owner_import(node.module)
            for alias in node.names
        }
        missing_exports = SALIENCY_PROVENANCE_PUBLIC_NAMES - compatibility_exports
        if missing_exports:
            violations.append(
                f"{SALIENCY_PROVENANCE_COMPATIBILITY_MODULE} must explicitly "
                "re-export compatibility names: "
                f"{', '.join(sorted(missing_exports))}."
            )

    product_root = root_dir / "XBrainLab"
    if product_root.exists():
        for py_file in product_root.rglob("*.py"):
            relative_path = py_file.relative_to(root_dir)
            if relative_path in {
                SALIENCY_PROVENANCE_OWNER,
                SALIENCY_PROVENANCE_COMPATIBILITY_MODULE,
            }:
                continue
            tree = _parse_python_file(py_file)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                imported_provenance = SALIENCY_PROVENANCE_PUBLIC_NAMES & {
                    alias.name for alias in node.names
                }
                if not imported_provenance or _is_saliency_provenance_owner_import(
                    node.module
                ):
                    continue
                violations.append(
                    f"{relative_path}:{node.lineno} imports "
                    f"{', '.join(sorted(imported_provenance))} from "
                    f"{node.module or '<relative module>'}; product code must import "
                    f"saliency provenance from {SALIENCY_PROVENANCE_OWNER}."
                )

    return violations


def check_saliency_artifact_integrity_ownership(root_dir: Path) -> list[str]:
    """Keep saliency manifest policy out of UI and application state truth."""
    violations: list[str] = []
    owner_path = root_dir / SALIENCY_ARTIFACT_INTEGRITY_OWNER
    owner_tree = _parse_python_file(owner_path)
    if owner_tree is None:
        return [
            f"{SALIENCY_ARTIFACT_INTEGRITY_OWNER} is missing or invalid; saliency "
            "payload integrity requires one training-domain owner."
        ]
    missing_names = SALIENCY_ARTIFACT_INTEGRITY_REQUIRED_NAMES - (
        _top_level_bound_names(owner_tree)
    )
    if missing_names:
        violations.append(
            f"{SALIENCY_ARTIFACT_INTEGRITY_OWNER} does not own: "
            f"{', '.join(sorted(missing_names))}."
        )

    product_root = root_dir / "XBrainLab"
    if not product_root.exists():
        return violations
    for py_file in product_root.rglob("*.py"):
        relative_path = py_file.relative_to(root_dir)
        source = py_file.read_text(encoding="utf-8")
        tree = _parse_python_file(py_file)
        if (
            tree is not None
            and relative_path not in SALIENCY_ARTIFACT_INTEGRITY_ALLOWED_CONSUMERS
        ):
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                if module == "saliency_artifact_integrity" or module.endswith(
                    ".saliency_artifact_integrity"
                ):
                    violations.append(
                        f"{relative_path}:{node.lineno} imports saliency artifact "
                        "integrity policy outside the training persistence domain."
                    )

        in_ui = Path("XBrainLab/ui") in relative_path.parents
        is_state_service = relative_path == Path(
            "XBrainLab/backend/application/state_service.py"
        )
        if not in_ui and not is_state_service:
            continue
        for line_number, line in enumerate(source.splitlines(), start=1):
            violations.extend(
                (
                    f"{relative_path}:{line_number} uses {token}; saliency "
                    "manifest/integrity policy belongs to training persistence."
                )
                for token in SALIENCY_ARTIFACT_POLICY_TOKENS
                if token in line
            )
    return violations


def check_visualization_saliency_publication_boundary(
    root_dir: Path,
) -> list[str]:
    """Keep all UI saliency readiness on immutable Application publications."""
    ui_root = root_dir / "XBrainLab" / "ui"
    relative_paths = tuple(
        source_path.relative_to(root_dir)
        for source_path in sorted(ui_root.rglob("*.py"))
    )
    projector_names = {
        "saliency_coverage_for_eval_record",
        "saliency_label_items_from_epoch",
        "saliency_method_coverage",
    }
    implicit_render_functions = {
        "on_update",
        "on_tab_changed",
        "_on_method_changed",
        "update_panel",
        "_poll_saliency_status",
    }
    live_training_accessors = {
        "get_dataset",
        "get_eval_record",
        "get_plans",
        "get_trainers",
    }
    live_training_storage_names = {
        "dataset",
        "datasets",
        "eval_record",
        "eval_records",
        "plan",
        "plans",
        "trainer",
        "trainers",
    }
    violations: list[str] = []

    for relative_path in relative_paths:
        source_path = root_dir / relative_path
        if not source_path.exists():
            continue
        source = source_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(source_path))
        except SyntaxError:
            continue

        class BoundaryVisitor(ast.NodeVisitor):
            def __init__(self, source_relative_path: Path) -> None:
                self.relative_path = source_relative_path
                self.functions: list[str] = []
                self.poll_found = False
                self.poll_uses_query_state = False

            @property
            def current_function(self) -> str:
                return self.functions[-1] if self.functions else "<module>"

            @property
            def inside_poll(self) -> bool:
                return "_poll_saliency_status" in self.functions

            def _visit_function(
                self,
                node: ast.FunctionDef | ast.AsyncFunctionDef,
            ) -> None:
                self.functions.append(node.name)
                if node.name == "_poll_saliency_status":
                    self.poll_found = True
                self.generic_visit(node)
                self.functions.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._visit_function(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._visit_function(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                imported = projector_names & {alias.name for alias in node.names}
                if (
                    node.module == "XBrainLab.backend.application.state_service"
                    and imported
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "visualization UI imports a coverage projector from "
                        f"state_service: {', '.join(sorted(imported))}"
                    )
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call) -> None:
                call_name = _call_name(node.func)
                in_visualization_ui = "visualization" in self.relative_path.parts
                is_saliency_view = (
                    "ui/panels/visualization/saliency_views/"
                    in self.relative_path.as_posix()
                )
                if (
                    is_saliency_view
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "singleShot"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "QTimer"
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        "saliency figure layout must use deterministic Qt layout/"
                        "resize lifecycle handling, not QTimer.singleShot"
                    )
                if (
                    is_saliency_view
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "processEvents"
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        "saliency rendering must not pump nested Qt events"
                    )
                configures_saliency = call_name == "SaliencyCommand" and (
                    bool(node.args)
                    or any(
                        keyword.arg in {"method", "params"}
                        and not (
                            isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is None
                        )
                        for keyword in node.keywords
                    )
                )
                if call_name in projector_names:
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        f"visualization UI calls coverage projector {call_name}; "
                        "read ApplicationViewPublication.saliency_coverage instead"
                    )
                if (
                    in_visualization_ui
                    and call_name == "VisualizeCommand"
                    and not self.inside_poll
                ):
                    violations.extend(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI cannot "
                        f"set {keyword.arg}=True; mutable render objects must not "
                        "cross CommandResult"
                        for keyword in node.keywords
                        if keyword.arg
                        in {"include_objects", "include_averaged_records"}
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    )
                if in_visualization_ui and call_name == "local_result_payload":
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI cannot call "
                        "local_result_payload; read serializable diagnostics and the "
                        "immutable Application publication"
                    )
                if (
                    in_visualization_ui
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in live_training_accessors
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI cannot call "
                        f"{node.func.attr}(); read typed identities and immutable "
                        "Application/render publications instead"
                    )
                if call_name == "_start_saliency_compute" and (
                    "_compute_saliency_from_action_bar" not in self.functions
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "saliency compute may start only from the explicit button "
                        "handler"
                    )
                if call_name == "_dispatch_saliency_compute_command" and not any(
                    function
                    in {
                        "_start_saliency_compute",
                        "_handle_saliency_resource_confirmation",
                    }
                    for function in self.functions
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "saliency dispatch helper may be called only by the explicit "
                        "Compute/Recompute path or its confirmed resource replay"
                    )
                if configures_saliency and any(
                    function in implicit_render_functions for function in self.functions
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "render, tab switching, and polling cannot configure saliency"
                    )
                elif configures_saliency and not any(
                    function
                    in {
                        "_start_saliency_compute",
                        "_dispatch_saliency_compute_command",
                    }
                    for function in self.functions
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] only the explicit Compute/"
                        "Recompute path may dispatch a saliency mutation"
                    )
                if self.inside_poll:
                    if call_name == "QueryStateCommand":
                        self.poll_uses_query_state = True
                    if any(
                        (
                            keyword.arg == "include_objects"
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True
                        )
                        for keyword in node.keywords
                    ):
                        violations.append(
                            f"{self.relative_path}:{node.lineno} "
                            f"[{self.current_function}] saliency polling cannot "
                            "set include_objects=True"
                        )
                self.generic_visit(node)

            def visit_Constant(self, node: ast.Constant) -> None:
                if "visualization" in self.relative_path.parts and node.value in {
                    "trainer_objects",
                    "averaged_records",
                }:
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI reads mutable "
                        f"CommandResult field {node.value!r}"
                    )

            def visit_Assign(self, node: ast.Assign) -> None:
                if self.inside_poll and any(
                    isinstance(target, ast.Attribute)
                    and target.attr == "last_application_query"
                    for target in node.targets
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "saliency polling cannot store a CommandResult"
                    )
                if "visualization" in self.relative_path.parts:
                    violations.extend(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI cannot "
                        f"store self.{target.attr}; keep live Trainer/Plan/"
                        "EvalRecord/Dataset objects behind the application "
                        "publication boundary"
                        for target in node.targets
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                            and target.attr.lstrip("_") in live_training_storage_names
                        )
                    )
                self.generic_visit(node)

            def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
                target = node.target
                if (
                    "visualization" in self.relative_path.parts
                    and isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr.lstrip("_") in live_training_storage_names
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] visualization UI cannot store "
                        f"self.{target.attr}; keep live Trainer/Plan/EvalRecord/"
                        "Dataset objects behind the application publication boundary"
                    )
                self.generic_visit(node)

        visitor = BoundaryVisitor(relative_path)
        visitor.visit(tree)
        if visitor.poll_found and not visitor.poll_uses_query_state:
            violations.append(
                f"{relative_path} [_poll_saliency_status] saliency polling must use "
                "QueryStateCommand"
            )

    return violations


def check_raw_mutation_atomicity_boundaries(root_dir: Path) -> list[str]:
    """Protect centralized interpretation invalidation and label transactions."""
    violations: list[str] = []
    service_path = root_dir / "XBrainLab/backend/application/service.py"
    compatibility_path = (
        root_dir / "XBrainLab/backend/application/data_compatibility_service.py"
    )
    label_service_path = root_dir / "XBrainLab/backend/services/label_import_service.py"

    service_tree = _parse_python_file(service_path)
    coordinator = _class_node(service_tree, "_LegacyRawMutationLifecycleCoordinator")
    expected_commands = {
        "LoadDataCommand",
        "AttachLabelsCommand",
        "UpdateMetadataCommand",
        "ApplySmartParseCommand",
        "RemoveFilesCommand",
    }
    actual_commands = _class_name_collection(coordinator, "COMMAND_TYPES")
    if actual_commands != expected_commands:
        violations.append(
            "XBrainLab/backend/application/service.py must route every legacy raw "
            "mutation through one lifecycle coordinator; expected "
            f"{sorted(expected_commands)}, found {sorted(actual_commands)}."
        )
    execute_method = _class_method_node(
        service_tree,
        "ApplicationService",
        "_execute_verified_command",
    )
    execute_calls = _function_call_names(execute_method)
    violations.extend(
        "XBrainLab/backend/application/service.py "
        "ApplicationService._execute_verified_command must call "
        f"legacy raw lifecycle {required_call}()."
        for required_call in ("commit", "fail_closed")
        if required_call not in execute_calls
    )

    compatibility_tree = _parse_python_file(compatibility_path)
    for method_name in ("handle_attach_labels", "handle_import_labels"):
        method = _class_method_node(
            compatibility_tree,
            "DataCompatibilityCommandService",
            method_name,
        )
        calls = _function_calls_in_order(method)
        completion_lines = [
            line for line, name in calls if name == "_ensure_complete_label_batch"
        ]
        if not completion_lines:
            violations.append(
                "XBrainLab/backend/application/data_compatibility_service.py "
                f"{method_name}() must reject incomplete label batches."
            )
        if method_name == "handle_import_labels":
            recipe_lines = [
                line for line, name in calls if name == "record_label_import_for_recipe"
            ]
            if (
                not recipe_lines
                or not completion_lines
                or min(recipe_lines) < max(completion_lines)
            ):
                violations.append(
                    "XBrainLab/backend/application/data_compatibility_service.py "
                    "must verify the complete label batch before updating recipe truth."
                )

    label_tree = _parse_python_file(label_service_path)
    batch_wrapper = _class_method_node(
        label_tree,
        "LabelImportService",
        "apply_labels_batch",
    )
    batch_wrapper_calls = _resolved_function_call_names(batch_wrapper, label_tree)
    if (
        not {
            "apply_labels_batch_checked",
            "_apply_label_operations_atomically",
        }
        & batch_wrapper_calls
    ):
        violations.append(
            "XBrainLab/backend/services/label_import_service.py "
            "apply_labels_batch() must delegate to the checked atomic batch path."
        )
    forbidden_wrapper_calls = {
        "apply_labels_to_single_file",
        "_force_apply_single",
    } & batch_wrapper_calls
    if forbidden_wrapper_calls:
        violations.append(
            "XBrainLab/backend/services/label_import_service.py "
            "apply_labels_batch() directly mutates label targets via "
            f"{', '.join(sorted(forbidden_wrapper_calls))}."
        )
    if _UNRESOLVED_CALLABLE_ORIGIN in batch_wrapper_calls:
        violations.append(
            "XBrainLab/backend/services/label_import_service.py "
            "apply_labels_batch() cannot prove callable construction is atomic."
        )

    for method_name in ("apply_labels_batch_checked", "apply_labels_sequence"):
        method = _class_method_node(
            label_tree,
            "LabelImportService",
            method_name,
        )
        calls = _resolved_function_call_names(method, label_tree)
        if "_apply_label_operations_atomically" not in calls:
            violations.append(
                "XBrainLab/backend/services/label_import_service.py "
                f"{method_name}() must delegate to the atomic copy/commit helper."
            )
        forbidden = {"apply_labels_to_single_file", "_force_apply_single"} & calls
        if forbidden:
            violations.append(
                "XBrainLab/backend/services/label_import_service.py "
                f"{method_name}() directly mutates label targets via "
                f"{', '.join(sorted(forbidden))}."
            )
        if _UNRESOLVED_CALLABLE_ORIGIN in calls:
            violations.append(
                "XBrainLab/backend/services/label_import_service.py "
                f"{method_name}() cannot prove callable construction is atomic."
            )
    return violations


def check_label_resource_admission_boundary(root_dir: Path) -> list[str]:
    """Keep label materialization behind exact admitted parser owners."""
    violations: list[str] = []
    violations.extend(_check_public_label_import_schemas(root_dir))
    allowed_loader_owners = {
        Path("XBrainLab/backend/application/label_resource_reader.py"),
    }
    scan_roots = (
        root_dir / "XBrainLab/backend/application",
        root_dir / "XBrainLab/ui",
        root_dir / "XBrainLab/llm",
    )
    for package in scan_roots:
        if not package.exists():
            continue
        for path in package.rglob("*.py"):
            relative = path.relative_to(root_dir)
            relative_posix = _repo_relative_posix(path, root_dir)
            tree = _parse_python_file(path)
            if tree is None:
                continue
            direct_loader_lines: set[int] = set()
            for node in ast.walk(tree):
                is_loader_import = (
                    isinstance(node, ast.ImportFrom)
                    and str(node.module or "").endswith("load_data.label_loader")
                    and any(alias.name == "load_label_file" for alias in node.names)
                )
                is_loader_call = isinstance(node, ast.Call) and (
                    (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "load_label_file"
                    )
                    or (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "load_label_file"
                    )
                )
                if is_loader_import or is_loader_call:
                    direct_loader_lines.add(int(getattr(node, "lineno", 0)))
            if direct_loader_lines and relative not in allowed_loader_owners:
                violations.extend(
                    (
                        f"{relative_posix}:{line} calls label_loader outside an admitted "
                        "parser owner"
                    )
                    for line in sorted(direct_loader_lines)
                )

            if relative == Path(
                "XBrainLab/backend/application/data_interpretation_apply.py"
            ):
                direct_file_io_lines = {
                    int(getattr(node, "lineno", 0))
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and (
                        (isinstance(node.func, ast.Name) and node.func.id == "open")
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"open", "read_bytes", "read_text"}
                        )
                    )
                }
                violations.extend(
                    f"{relative_posix}:{line} uses direct file IO for label apply; "
                    "external labels must use the admitted bounded reader."
                    for line in sorted(direct_file_io_lines)
                )

            is_ui_module = relative.parts[:2] == ("XBrainLab", "ui")
            is_llm_module = relative.parts[:2] == ("XBrainLab", "llm")
            if is_ui_module or is_llm_module:
                violations.extend(
                    _check_label_ui_owner_boundary(relative=relative, tree=tree)
                )
            if is_ui_module:
                imports_admission_owner = any(
                    isinstance(node, ast.ImportFrom)
                    and str(node.module or "").endswith(
                        "application.label_resource_admission"
                    )
                    and any(
                        alias.name
                        in {
                            "AdmittedLabelResourceSession",
                            "LabelResourceAdmissionService",
                            "AdmittedLabelResourceReader",
                        }
                        for alias in node.names
                    )
                    for node in ast.walk(tree)
                )
                if imports_admission_owner:
                    violations.append(
                        f"{relative_posix} imports LabelResourceAdmissionService or its "
                        "materialized session; UI must use an ApplicationService "
                        "preview command."
                    )
                admitted_session_names = {
                    target.id
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Assign, ast.AnnAssign))
                    for target in (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    )
                    if isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "admit"
                }
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "load"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id in admitted_session_names
                    ):
                        violations.append(
                            f"{relative_posix}:{node.lineno} calls session.load(); UI must "
                            "not materialize external label payloads."
                        )
                    if (
                        isinstance(node, ast.Attribute)
                        and node.attr == "label_data_map"
                    ):
                        violations.append(
                            f"{relative_posix}:{node.lineno} retains a materialized label "
                            "payload cache; UI state must remain path/config/summary based."
                        )

    reader_path = root_dir / "XBrainLab/backend/application/label_resource_reader.py"
    reader_tree = _parse_python_file(reader_path)
    if reader_tree is not None:
        loader_calls = [
            node
            for node in ast.walk(reader_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "load_label_file"
        ]
        if not loader_calls:
            violations.append(
                "XBrainLab/backend/application/label_resource_reader.py must own "
                "the bounded legacy label_loader call."
            )
        unbounded_calls = [
            call
            for call in loader_calls
            if not any(
                keyword.arg == "resource_reader"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "self"
                for keyword in call.keywords
            )
        ]
        violations.extend(
            (
                "XBrainLab/backend/application/label_resource_reader.py:"
                f"{call.lineno} must pass resource_reader=self to label_loader."
            )
            for call in unbounded_calls
        )

    interpretation_service = (
        root_dir / "XBrainLab/backend/application/data_interpretation_service.py"
    )
    interpretation_tree = _parse_python_file(interpretation_service)
    if interpretation_tree is not None:
        handle_apply = _class_method_node(
            interpretation_tree,
            "DataInterpretationCommandService",
            "handle_apply_interpretation",
        )
        calls = _function_calls_in_order(handle_apply)
        preflight_lines = [
            line for line, name in calls if name == "_resolve_apply_resource_preflight"
        ]
        admission_lines = [
            line for line, name in calls if name == "_admitted_reviewed_label_resources"
        ]
        apply_lines = [line for line, name in calls if name == "apply_label_carriers"]
        if (
            not preflight_lines
            or not admission_lines
            or not apply_lines
            or min(preflight_lines) > min(apply_lines)
            or min(admission_lines) > min(apply_lines)
        ):
            violations.append(
                "XBrainLab/backend/application/data_interpretation_service.py must "
                "bind reviewed labels to the authorized preflight before apply."
            )

    compatibility_path = (
        root_dir / "XBrainLab/backend/application/data_compatibility_service.py"
    )
    compatibility_tree = _parse_python_file(compatibility_path)
    if compatibility_tree is not None:
        for method_name in ("handle_attach_labels", "handle_import_labels"):
            method = _class_method_node(
                compatibility_tree,
                "DataCompatibilityCommandService",
                method_name,
            )
            calls = _function_calls_in_order(method)
            boundary_call = (
                "admit" if method_name == "handle_attach_labels" else "materialize"
            )
            admission_lines = [line for line, name in calls if name == boundary_call]
            parser_lines = [
                line
                for line, name in calls
                if name in {"load", "materialize", "materialize_reviewed_label_map"}
            ]
            if (
                not admission_lines
                or not parser_lines
                or min(admission_lines) > min(parser_lines)
            ):
                violations.append(
                    "XBrainLab/backend/application/data_compatibility_service.py "
                    f"{method_name}() must admit paths before session.load()."
                )

    for package_name in ("ui", "llm"):
        package = root_dir / "XBrainLab" / package_name
        if not package.exists():
            continue
        for path in package.rglob("*.py"):
            tree = _parse_python_file(path)
            if tree is None:
                continue
            relative = path.relative_to(root_dir)
            relative_posix = _repo_relative_posix(path, root_dir)
            module_aliases, symbol_aliases = _label_import_bindings(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                qualified = _label_qualified_name(
                    node.func,
                    module_aliases=module_aliases,
                    symbol_aliases=symbol_aliases,
                )
                command_name = qualified.rsplit(".", maxsplit=1)[-1]
                if command_name == "AttachLabelsCommand":
                    keywords = {keyword.arg for keyword in node.keywords}
                    required = {
                        "label_paths",
                        "resource_preflight_confirmed",
                        "resource_preflight_token",
                    }
                    missing = sorted(required - keywords)
                    if missing:
                        violations.append(
                            f"{relative_posix}:{node.lineno} AttachLabelsCommand is "
                            f"missing {', '.join(missing)}"
                        )
                if command_name == "LabelImportPlan" and any(
                    keyword.arg == "label_map" for keyword in node.keywords
                ):
                    violations.append(
                        f"{relative_posix}:{node.lineno} public label import cannot pass "
                        "a pre-materialized label_map"
                    )
    return violations


_LABEL_UI_OWNER_MODULES = frozenset(
    {
        Path("XBrainLab/ui/dialogs/dataset/import_label_dialog.py"),
        Path("XBrainLab/ui/panels/dataset/actions.py"),
    }
)
_LABEL_PATH_READ_METHODS = frozenset({"open", "read_bytes", "read_text"})
_LABEL_PATH_TRANSFORM_METHODS = frozenset(
    {"absolute", "expanduser", "resolve", "with_name", "with_suffix"}
)


def _check_public_label_import_schemas(root_dir: Path) -> list[str]:
    violations: list[str] = []
    schema_classes = _label_schema_dataclasses(root_dir)
    classes_by_name: dict[str, list[tuple[Path, ast.ClassDef]]] = {}
    for relative, node in schema_classes:
        classes_by_name.setdefault(node.name, []).append((relative, node))
    annotation_aliases: dict[Path, dict[str, str]] = {}
    for relative, _node in schema_classes:
        if relative in annotation_aliases:
            continue
        tree = _parse_python_file(root_dir / relative)
        if tree is None:
            annotation_aliases[relative] = {}
            continue
        _module_aliases, symbol_aliases = _label_import_bindings(tree)
        annotation_aliases[relative] = {
            local_name: origin.rsplit(".", maxsplit=1)[-1]
            for local_name, origin in symbol_aliases.items()
        }
    for relative, root in schema_classes:
        if not _is_public_schema_root(relative, root):
            continue
        pending = [(relative, root, "label" in root.name.casefold())]
        visited: set[tuple[Path, str, bool]] = set()
        while pending:
            current_relative, current, label_context = pending.pop()
            identity = (current_relative, current.name, label_context)
            if identity in visited:
                continue
            visited.add(identity)
            for statement in current.body:
                field_name = _label_schema_field_name(statement)
                annotation = _label_schema_field_annotation(statement)
                annotation_names = _annotation_class_names(annotation)
                resolved_annotation_names = {
                    annotation_aliases.get(current_relative, {}).get(name, name)
                    for name in annotation_names
                }
                field_label_context = (
                    label_context
                    or bool(field_name is not None and "label" in field_name.casefold())
                    or any(
                        "label" in name.casefold() for name in resolved_annotation_names
                    )
                )
                if (
                    field_label_context
                    and field_name is not None
                    and _is_forbidden_label_public_field(
                        field_name,
                        annotation=annotation,
                    )
                ):
                    violations.append(
                        f"{current_relative.as_posix()}:{statement.lineno} public label schema "
                        f"{root.name} reaches {current.name}.{field_name}, which "
                        "cannot expose materialized label maps, arrays, values, "
                        "or payloads."
                    )
                for referenced_name in resolved_annotation_names:
                    pending.extend(
                        (*referenced, field_label_context)
                        for referenced in classes_by_name.get(referenced_name, ())
                    )

    preview_path = root_dir / "XBrainLab/backend/application/label_import_preview.py"
    preview_tree = _parse_python_file(preview_path)
    if preview_tree is None:
        return violations
    summary_function = next(
        (
            node
            for node in preview_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_preview_summary"
        ),
        None,
    )
    if summary_function is None:
        return violations
    for return_node in (
        node for node in ast.walk(summary_function) if isinstance(node, ast.Return)
    ):
        if not isinstance(return_node.value, ast.Dict):
            continue
        for key in return_node.value.keys:
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if not _is_forbidden_label_public_field(key.value):
                continue
            violations.append(
                "XBrainLab/backend/application/label_import_preview.py:"
                f"{key.lineno} public label preview result field {key.value!r} "
                "cannot expose materialized label maps, arrays, or payloads."
            )
    return violations


def _label_schema_dataclasses(root_dir: Path) -> list[tuple[Path, ast.ClassDef]]:
    packages = (
        root_dir / "XBrainLab/backend/application",
        root_dir / "XBrainLab/ui",
        root_dir / "XBrainLab/llm",
    )
    result: list[tuple[Path, ast.ClassDef]] = []
    for package in packages:
        if not package.exists():
            continue
        for path in package.rglob("*.py"):
            tree = _parse_python_file(path)
            if tree is None:
                continue
            relative = path.relative_to(root_dir)
            result.extend(
                (relative, node)
                for node in tree.body
                if isinstance(node, ast.ClassDef) and _is_dataclass_class(node)
            )
    return result


def _is_dataclass_class(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False


def _is_public_schema_root(relative: Path, node: ast.ClassDef) -> bool:
    if node.name.startswith("_"):
        return False
    is_application_module = relative.parts[:3] == (
        "XBrainLab",
        "backend",
        "application",
    )
    is_central_application_schema = relative in {
        Path("XBrainLab/backend/application/commands.py"),
        Path("XBrainLab/backend/application/results.py"),
    }
    module_stem = relative.stem.casefold()
    is_application_contract_module = is_application_module and any(
        marker in module_stem
        for marker in ("command", "result", "schema", "contract", "tool")
    )
    class_name = node.name.casefold()
    is_application_contract_class = is_application_module and any(
        marker in class_name
        for marker in (
            "command",
            "result",
            "request",
            "response",
            "schema",
            "contract",
            "tool",
            "envelope",
        )
    )
    is_product_ui_schema = relative.parts[:2] == ("XBrainLab", "ui")
    is_llm_schema = relative.parts[:2] == ("XBrainLab", "llm")
    return (
        is_central_application_schema
        or is_application_contract_module
        or is_application_contract_class
        or is_product_ui_schema
        or is_llm_schema
    )


def _label_schema_field_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    return None


def _label_schema_field_annotation(node: ast.stmt) -> ast.AST | None:
    return node.annotation if isinstance(node, ast.AnnAssign) else None


def _annotation_class_names(annotation: ast.AST | None) -> set[str]:
    if annotation is None:
        return set()

    result: set[str] = set()
    pending = [annotation]
    parsed_forward_refs: set[str] = set()
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Name):
            result.add(node.id)
            continue
        if isinstance(node, ast.Attribute):
            result.add(node.attr)
            pending.append(node.value)
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            forward_ref = node.value.strip()
            if not forward_ref or forward_ref in parsed_forward_refs:
                continue
            parsed_forward_refs.add(forward_ref)
            try:
                parsed = ast.parse(forward_ref, mode="eval")
            except (SyntaxError, ValueError):
                continue
            pending.append(parsed.body)
            continue
        if isinstance(node, ast.Subscript):
            pending.append(node.value)
            arguments = (
                tuple(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else (node.slice,)
            )
            wrapper_name = _annotation_terminal_name(node.value).casefold()
            if wrapper_name == "annotated":
                if arguments:
                    pending.append(arguments[0])
                continue
            if wrapper_name == "literal":
                continue
            pending.extend(arguments)
            continue
        pending.extend(ast.iter_child_nodes(node))
    return result


def _annotation_terminal_name(annotation: ast.AST) -> str:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return ""


def _is_forbidden_label_public_field(
    field_name: str,
    *,
    annotation: ast.AST | None = None,
) -> bool:
    normalized = str(field_name).strip().casefold()
    if (
        normalized == "label_map"
        or "payload" in normalized
        or "materialized" in normalized
        or normalized == "array"
        or normalized.endswith("_array")
    ):
        return True
    if "label" not in normalized:
        return False
    if normalized.endswith(("_path", "_paths", "_config", "_configs")):
        return False
    annotation_names = {name.casefold() for name in _annotation_class_names(annotation)}
    materialized_types = {
        "array",
        "ndarray",
        "bytes",
        "bytearray",
        "memoryview",
    }
    if annotation_names & materialized_types:
        return True
    collection_types = {"list", "tuple", "set", "dict", "mapping", "sequence"}
    return bool(
        annotation_names & collection_types
        and (
            normalized in {"label", "labels", "label_data", "label_values"}
            or normalized.endswith(("_values", "_samples", "_data"))
        )
    )


def _check_label_ui_owner_boundary(
    *,
    relative: Path,
    tree: ast.Module,
) -> list[str]:
    module_aliases, symbol_aliases = _label_import_bindings(tree)
    violations: list[str] = []
    relative_posix = relative.as_posix()
    label_context = _is_label_product_context(relative, tree)
    label_read_context = label_context or any(
        "label" in argument.arg.casefold()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    )
    path_names = _label_path_value_names(
        tree,
        module_aliases=module_aliases,
        symbol_aliases=symbol_aliases,
    )

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for origin in _label_import_origins(node):
                if _is_label_parser_origin(origin):
                    violations.append(
                        f"{relative_posix}:{node.lineno} imports a backend label parser; "
                        "label UI must pass paths/config to ApplicationService."
                    )
                if _is_label_admission_origin(origin):
                    violations.append(
                        f"{relative_posix}:{node.lineno} imports label resource admission; "
                        "label UI must use the public preview command."
                    )
            continue
        if isinstance(node, ast.Call):
            qualified = _label_qualified_name(
                node.func,
                module_aliases=module_aliases,
                symbol_aliases=symbol_aliases,
            )
            if label_read_context and qualified in {"open", "builtins.open"}:
                violations.append(
                    f"{relative_posix}:{node.lineno} uses builtins.open for label UI; "
                    "file reads belong to the admitted backend parser."
                )
            if (
                label_read_context
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _LABEL_PATH_READ_METHODS
                and _is_label_path_expression(
                    node.func.value,
                    path_names=path_names,
                    module_aliases=module_aliases,
                    symbol_aliases=symbol_aliases,
                )
            ):
                violations.append(
                    f"{relative_posix}:{node.lineno} uses Path.{node.func.attr} for label "
                    "UI; file reads belong to the admitted backend parser."
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    name = (
                        child.id
                        if isinstance(child, ast.Name)
                        else child.attr
                        if isinstance(child, ast.Attribute)
                        else ""
                    )
                    if label_context and _is_materialized_label_ui_name(name):
                        violations.append(
                            f"{relative_posix}:{node.lineno} stores a materialized label "
                            "payload; UI state must remain path/config/summary based."
                        )
                        break
    return violations


def _is_label_product_context(relative: Path, tree: ast.Module) -> bool:
    if relative in _LABEL_UI_OWNER_MODULES or "label" in relative.stem.casefold():
        return True
    if any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and "label" in node.name.casefold()
        for node in ast.walk(tree)
    ):
        return True
    return any(
        _is_label_parser_origin(origin) or _is_label_admission_origin(origin)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for origin in _label_import_origins(node)
    )


def _label_import_bindings(
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, str]]:
    module_aliases: dict[str, str] = {}
    symbol_aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                module_aliases[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            for alias in node.names:
                local_name = alias.asname or alias.name
                symbol_aliases[local_name] = ".".join(
                    part for part in (module, alias.name) if part
                )
    assignments = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
        ),
        key=lambda node: (
            int(getattr(node, "lineno", 0)),
            int(getattr(node, "col_offset", 0)),
        ),
    )
    for node in assignments:
        value = node.value
        if value is None:
            continue
        qualified = _label_qualified_name(
            value,
            module_aliases=module_aliases,
            symbol_aliases=symbol_aliases,
        )
        if "." not in qualified:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                symbol_aliases[target.id] = qualified
    return module_aliases, symbol_aliases


def _label_import_origins(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    module = str(node.module or "")
    return [
        ".".join(part for part in (module, alias.name) if part) for alias in node.names
    ]


def _is_label_parser_origin(origin: str) -> bool:
    parts = tuple(str(origin).casefold().split("."))
    if {"label_loader", "label_resource_reader"} & set(parts):
        return True
    if any("label" in part and "parser" in part for part in parts):
        return True
    return "parser" in parts and any("label" in part for part in parts)


def _is_label_admission_origin(origin: str) -> bool:
    return "label_resource_admission" in str(origin).casefold().split(".")


def _label_qualified_name(
    node: ast.AST,
    *,
    module_aliases: dict[str, str],
    symbol_aliases: dict[str, str],
) -> str:
    if isinstance(node, ast.Name):
        return symbol_aliases.get(
            node.id,
            module_aliases.get(node.id, node.id),
        )
    if isinstance(node, ast.Attribute):
        parent = _label_qualified_name(
            node.value,
            module_aliases=module_aliases,
            symbol_aliases=symbol_aliases,
        )
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _label_path_value_names(
    tree: ast.Module,
    *,
    module_aliases: dict[str, str],
    symbol_aliases: dict[str, str],
) -> set[str]:
    path_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None or not _is_label_path_expression(
                value,
                path_names=path_names,
                module_aliases=module_aliases,
                symbol_aliases=symbol_aliases,
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                target_key = _label_expression_key(target)
                if target_key and target_key not in path_names:
                    path_names.add(target_key)
                    changed = True
    return path_names


def _is_label_path_expression(
    node: ast.AST,
    *,
    path_names: set[str],
    module_aliases: dict[str, str],
    symbol_aliases: dict[str, str],
) -> bool:
    expression_key = _label_expression_key(node)
    if expression_key and expression_key in path_names:
        return True
    if isinstance(node, ast.Name):
        return (
            _label_qualified_name(
                node,
                module_aliases=module_aliases,
                symbol_aliases=symbol_aliases,
            )
            == "pathlib.Path"
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_label_path_expression(
            node.left,
            path_names=path_names,
            module_aliases=module_aliases,
            symbol_aliases=symbol_aliases,
        )
    if not isinstance(node, ast.Call):
        return False
    qualified = _label_qualified_name(
        node.func,
        module_aliases=module_aliases,
        symbol_aliases=symbol_aliases,
    )
    if qualified == "pathlib.Path":
        return True
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in _LABEL_PATH_TRANSFORM_METHODS
        and _is_label_path_expression(
            node.func.value,
            path_names=path_names,
            module_aliases=module_aliases,
            symbol_aliases=symbol_aliases,
        )
    )


def _label_expression_key(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _label_expression_key(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _is_materialized_label_ui_name(name: str) -> bool:
    normalized = str(name).strip().casefold()
    if normalized in {"label_data_map", "label_map"}:
        return True
    return "label" in normalized and any(
        token in normalized for token in ("array", "materialized", "payload")
    )


def _class_node(tree: ast.AST | None, class_name: str) -> ast.ClassDef | None:
    if not isinstance(tree, ast.Module):
        return None
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )


def _class_method_node(
    tree: ast.AST | None,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    class_node = _class_node(tree, class_name)
    if class_node is None:
        return None
    return next(
        (
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == method_name
        ),
        None,
    )


def _class_name_collection(
    class_node: ast.ClassDef | None,
    attribute_name: str,
) -> set[str]:
    if class_node is None:
        return set()
    for statement in class_node.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = (
            statement.targets
            if isinstance(statement, ast.Assign)
            else [statement.target]
        )
        if not any(
            isinstance(target, ast.Name) and target.id == attribute_name
            for target in targets
        ):
            continue
        value = statement.value
        if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            return set()
        return {item.id for item in value.elts if isinstance(item, ast.Name)}
    return set()


def _function_call_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> set[str]:
    return {name for _line, name in _function_calls_in_order(function)}


def _resolved_function_call_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    module: ast.Module | None,
) -> set[str]:
    """Resolve direct calls and callable aliases without losing dangerous origins."""
    if function is None:
        return set()

    aliases: dict[str, set[str]] = {}
    import_nodes: list[ast.Import | ast.ImportFrom] = []
    if module is not None:
        import_nodes.extend(
            node
            for node in module.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        )
    import_nodes.extend(
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    for node in import_nodes:
        if isinstance(node, ast.ImportFrom):
            for imported in node.names:
                if imported.name == "*":
                    continue
                local_name = imported.asname or imported.name
                aliases.setdefault(local_name, set()).add(imported.name)
        else:
            for imported in node.names:
                local_name = imported.asname or imported.name.split(".", maxsplit=1)[0]
                aliases.setdefault(local_name, set()).add(imported.name)

    function_returns: dict[str, list[ast.expr]] = {}
    definition_roots: list[ast.AST] = [function]
    if module is not None:
        definition_roots.append(module)
    for root in definition_roots:
        for node in ast.walk(root):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            function_returns.setdefault(node.name, []).extend(
                _function_return_expressions(node)
            )
            aliases.setdefault(node.name, set()).add(node.name)

    assignment_nodes: list[ast.Assign | ast.AnnAssign] = []
    if module is not None:
        assignment_nodes.extend(
            node
            for node in module.body
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
        )
    assignment_nodes.extend(
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
    )
    bindings: list[tuple[str, tuple[ast.expr, ...]]] = []
    container_mutations: list[tuple[str, object, ast.expr]] = []
    for node in assignment_nodes:
        if node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            bindings.extend(_assignment_binding_pairs(target, node.value))
            if isinstance(target, ast.Subscript) and isinstance(
                target.value,
                ast.Name,
            ):
                has_literal_key, key = _literal_container_key(target.slice)
                container_mutations.append(
                    (
                        target.value.id,
                        key if has_literal_key else _DYNAMIC_CALLABLE_CONTAINER_KEY,
                        node.value,
                    )
                )
    for node in ast.walk(function):
        if isinstance(node, ast.NamedExpr):
            bindings.extend(_assignment_binding_pairs(node.target, node.value))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            container_name = node.func.value.id
            if node.func.attr == "update":
                for argument in node.args:
                    if not isinstance(argument, ast.Dict):
                        container_mutations.append(
                            (
                                container_name,
                                _DYNAMIC_CALLABLE_CONTAINER_KEY,
                                argument,
                            )
                        )
                        continue
                    for key_node, value_node in zip(
                        argument.keys,
                        argument.values,
                        strict=True,
                    ):
                        if key_node is None:
                            key = _DYNAMIC_CALLABLE_CONTAINER_KEY
                        else:
                            has_literal_key, literal_key = _literal_container_key(
                                key_node
                            )
                            key = (
                                literal_key
                                if has_literal_key
                                else _DYNAMIC_CALLABLE_CONTAINER_KEY
                            )
                        container_mutations.append((container_name, key, value_node))
                container_mutations.extend(
                    (
                        container_name,
                        keyword.arg
                        if keyword.arg is not None
                        else _DYNAMIC_CALLABLE_CONTAINER_KEY,
                        keyword.value,
                    )
                    for keyword in node.keywords
                )
            elif node.func.attr == "__setitem__" and len(node.args) >= 2:
                has_literal_key, key = _literal_container_key(node.args[0])
                container_mutations.append(
                    (
                        container_name,
                        key if has_literal_key else _DYNAMIC_CALLABLE_CONTAINER_KEY,
                        node.args[1],
                    )
                )

    callable_return_expressions = {
        name: list(return_values) for name, return_values in function_returns.items()
    }
    for target_name, return_value in (
        (target_name, value.body)
        for target_name, values in bindings
        for value in values
        if isinstance(value, ast.Lambda)
    ):
        callable_return_expressions.setdefault(target_name, []).append(return_value)
    factory_returns: dict[str, set[str]] = {}
    container_aliases: dict[str, dict[object, set[str]]] = {}
    changed = True
    while changed:
        changed = False
        for target_name, values in bindings:
            for value in values:
                container_items = _callable_container_items(
                    value,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
                if container_items is None:
                    continue
                known_items = container_aliases.setdefault(target_name, {})
                for key, origins in container_items.items():
                    known_origins = known_items.setdefault(key, set())
                    previous_size = len(known_origins)
                    known_origins.update(origins)
                    changed = changed or len(known_origins) != previous_size
        for container_name, key, value in container_mutations:
            known_items = container_aliases.setdefault(container_name, {})
            known_origins = known_items.setdefault(key, set())
            previous_size = len(known_origins)
            known_origins.update(
                _callable_reference_names(
                    value,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
            )
            changed = changed or len(known_origins) != previous_size

        for factory_name, return_values in callable_return_expressions.items():
            origins = {
                origin
                for return_value in return_values
                for origin in _callable_reference_names(
                    return_value,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
            }
            known_returns = factory_returns.setdefault(factory_name, set())
            previous_size = len(known_returns)
            known_returns.update(origins)
            changed = changed or len(known_returns) != previous_size

        for target_name, values in bindings:
            origins = {
                origin
                for value in values
                for origin in _callable_reference_names(
                    value,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
            }
            known = aliases.setdefault(target_name, set())
            previous_size = len(known)
            known.update(origins)
            changed = changed or len(known) != previous_size

    calls: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            calls.update(
                _callable_reference_names(
                    node.func,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
            )
    return calls


def _function_return_expressions(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.expr]:
    """Return expressions owned by one function, excluding nested callables."""

    class FunctionReturnVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.expressions: list[ast.expr] = []

        def visit_Return(self, node: ast.Return) -> None:
            if node.value is not None:
                self.expressions.append(node.value)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

    visitor = FunctionReturnVisitor()
    for statement in function.body:
        visitor.visit(statement)
    return visitor.expressions


def _assignment_binding_pairs(
    target: ast.expr,
    value: ast.expr,
) -> list[tuple[str, tuple[ast.expr, ...]]]:
    """Pair unpack targets with the callable expressions bound to each target."""
    if isinstance(target, ast.Name):
        return [(target.id, (value,))]
    if isinstance(target, ast.Starred):
        return _assignment_binding_pairs(target.value, value)
    if not isinstance(target, (ast.List, ast.Tuple)):
        return []

    target_items = target.elts
    if not isinstance(value, (ast.List, ast.Tuple)):
        return [(name, (value,)) for name in _assigned_names([target])]

    value_items = value.elts
    starred_indexes = [
        index
        for index, item in enumerate(target_items)
        if isinstance(item, ast.Starred)
    ]
    if not starred_indexes and len(target_items) == len(value_items):
        return [
            pair
            for target_item, value_item in zip(
                target_items,
                value_items,
                strict=True,
            )
            for pair in _assignment_binding_pairs(target_item, value_item)
        ]
    if len(starred_indexes) == 1 and len(value_items) >= len(target_items) - 1:
        starred_index = starred_indexes[0]
        trailing_count = len(target_items) - starred_index - 1
        pairs = [
            pair
            for target_item, value_item in zip(
                target_items[:starred_index],
                value_items[:starred_index],
                strict=True,
            )
            for pair in _assignment_binding_pairs(target_item, value_item)
        ]
        if trailing_count:
            pairs.extend(
                pair
                for target_item, value_item in zip(
                    target_items[-trailing_count:],
                    value_items[-trailing_count:],
                    strict=True,
                )
                for pair in _assignment_binding_pairs(target_item, value_item)
            )
        starred_target = target_items[starred_index]
        starred_values = value_items[
            starred_index : len(value_items) - trailing_count
            if trailing_count
            else len(value_items)
        ]
        pairs.extend(
            (name, tuple(starred_values)) for name in _assigned_names([starred_target])
        )
        return pairs

    conservative_values = tuple(_sequence_leaf_values(value))
    return [(name, conservative_values) for name in _assigned_names([target])]


def _sequence_leaf_values(expression: ast.expr) -> list[ast.expr]:
    if isinstance(expression, (ast.List, ast.Tuple)):
        return [
            leaf for item in expression.elts for leaf in _sequence_leaf_values(item)
        ]
    if isinstance(expression, ast.Starred):
        return _sequence_leaf_values(expression.value)
    return [expression]


def _assigned_names(targets: list[ast.expr]) -> set[str]:
    names: set[str] = set()
    pending = list(targets)
    while pending:
        target = pending.pop()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.List, ast.Tuple)):
            pending.extend(target.elts)
        elif isinstance(target, ast.Starred):
            pending.append(target.value)
    return names


def _callable_reference_names(
    expression: ast.expr,
    aliases: dict[str, set[str]],
    factory_returns: dict[str, set[str]] | None = None,
    container_aliases: dict[str, dict[object, set[str]]] | None = None,
) -> set[str]:
    factory_returns = factory_returns or {}
    container_aliases = container_aliases or {}
    if isinstance(expression, ast.Name):
        known_origins = aliases.get(expression.id)
        return set(known_origins) if known_origins else {expression.id}
    if isinstance(expression, ast.Attribute):
        return {expression.attr}
    if isinstance(expression, ast.NamedExpr):
        return _callable_reference_names(
            expression.value,
            aliases,
            factory_returns,
            container_aliases,
        )
    if isinstance(expression, ast.IfExp):
        return _callable_reference_names(
            expression.body,
            aliases,
            factory_returns,
            container_aliases,
        ) | _callable_reference_names(
            expression.orelse,
            aliases,
            factory_returns,
            container_aliases,
        )
    if isinstance(expression, ast.BoolOp):
        return {
            name
            for value in expression.values
            for name in _callable_reference_names(
                value,
                aliases,
                factory_returns,
                container_aliases,
            )
        }
    if isinstance(expression, ast.Lambda):
        return {
            name
            for node in ast.walk(expression.body)
            if isinstance(node, ast.Call)
            for name in _callable_reference_names(
                node.func,
                aliases,
                factory_returns,
                container_aliases,
            )
        }
    if isinstance(expression, ast.Subscript):
        container_items = _callable_container_items(
            expression.value,
            aliases,
            factory_returns,
            container_aliases,
        )
        if not container_items:
            return {_UNRESOLVED_CALLABLE_ORIGIN}
        has_literal_key, key = _literal_container_key(expression.slice)
        if has_literal_key and key in container_items:
            exact_origins = set(container_items[key])
            exact_origins.update(
                container_items.get(_DYNAMIC_CALLABLE_CONTAINER_KEY, set())
            )
            return exact_origins
        possible_origins = {
            origin for origins in container_items.values() for origin in origins
        }
        if _DYNAMIC_CALLABLE_CONTAINER_KEY in container_items:
            possible_origins.add(_UNRESOLVED_CALLABLE_ORIGIN)
        return possible_origins or {_UNRESOLVED_CALLABLE_ORIGIN}
    if isinstance(expression, ast.Call):
        invoked_names = _callable_reference_names(
            expression.func,
            aliases,
            factory_returns,
            container_aliases,
        )
        if "partial" in invoked_names:
            if not expression.args:
                return {_UNRESOLVED_CALLABLE_ORIGIN}
            return _callable_reference_names(
                expression.args[0],
                aliases,
                factory_returns,
                container_aliases,
            ) or {_UNRESOLVED_CALLABLE_ORIGIN}
        if "getattr" in invoked_names:
            if (
                len(expression.args) >= 2
                and isinstance(expression.args[1], ast.Constant)
                and isinstance(expression.args[1].value, str)
            ):
                return {expression.args[1].value}
            return {_UNRESOLVED_CALLABLE_ORIGIN}
        returned_names = {
            returned_name
            for invoked_name in invoked_names
            for returned_name in factory_returns.get(invoked_name, set())
        }
        return returned_names or {_UNRESOLVED_CALLABLE_ORIGIN}
    return set()


def _callable_container_items(
    expression: ast.expr,
    aliases: dict[str, set[str]],
    factory_returns: dict[str, set[str]],
    container_aliases: dict[str, dict[object, set[str]]],
) -> dict[object, set[str]] | None:
    if isinstance(expression, ast.Name):
        known_items = container_aliases.get(expression.id)
        if known_items is None:
            return None
        return {key: set(origins) for key, origins in known_items.items()}
    if isinstance(expression, ast.Dict):
        result: dict[object, set[str]] = {}
        for key_node, value_node in zip(
            expression.keys,
            expression.values,
            strict=True,
        ):
            if key_node is None:
                key = _DYNAMIC_CALLABLE_CONTAINER_KEY
            else:
                has_literal_key, literal_key = _literal_container_key(key_node)
                key = (
                    literal_key if has_literal_key else _DYNAMIC_CALLABLE_CONTAINER_KEY
                )
            result.setdefault(key, set()).update(
                _callable_reference_names(
                    value_node,
                    aliases,
                    factory_returns,
                    container_aliases,
                )
            )
        return result
    if isinstance(expression, (ast.List, ast.Tuple)):
        return {
            index: _callable_reference_names(
                value,
                aliases,
                factory_returns,
                container_aliases,
            )
            for index, value in enumerate(expression.elts)
        }
    return None


def _literal_container_key(expression: ast.expr) -> tuple[bool, object]:
    try:
        value = ast.literal_eval(expression)
        hash(value)
    except (TypeError, ValueError):
        return False, _DYNAMIC_CALLABLE_CONTAINER_KEY
    return True, value


def _function_calls_in_order(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> list[tuple[int, str]]:
    if function is None:
        return []
    return sorted(
        (
            (node.lineno, _call_name(node.func))
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
        ),
        key=lambda item: item[0],
    )


def check_application_state_module_boundaries(root_dir: Path) -> list[str]:
    """Keep saliency projection and query handling in their focused owners."""
    violations: list[str] = []
    saliency_owner_path = root_dir / SALIENCY_COVERAGE_OWNER
    query_owner_path = root_dir / QUERY_STATE_SERVICE_OWNER
    state_service_path = root_dir / APPLICATION_STATE_SERVICE_MODULE

    saliency_owner_tree = _parse_python_file(saliency_owner_path)
    if saliency_owner_tree is None:
        violations.append(
            f"{SALIENCY_COVERAGE_OWNER} is missing or invalid; saliency coverage "
            "requires one application-owned projector."
        )
    else:
        missing_names = SALIENCY_COVERAGE_PUBLIC_NAMES - _top_level_bound_names(
            saliency_owner_tree
        )
        if missing_names:
            violations.append(
                f"{SALIENCY_COVERAGE_OWNER} does not own: "
                f"{', '.join(sorted(missing_names))}."
            )

    query_owner_tree = _parse_python_file(query_owner_path)
    if query_owner_tree is None:
        violations.append(
            f"{QUERY_STATE_SERVICE_OWNER} is missing or invalid; "
            "QueryStateCommandService requires one focused owner."
        )
    elif "QueryStateCommandService" not in _top_level_bound_names(query_owner_tree):
        violations.append(
            f"{QUERY_STATE_SERVICE_OWNER} does not own QueryStateCommandService."
        )

    state_service_tree = _parse_python_file(state_service_path)
    if state_service_tree is None:
        violations.append(f"{APPLICATION_STATE_SERVICE_MODULE} is missing or invalid.")
    else:
        state_names = _top_level_bound_names(state_service_tree)
        policy_definitions = SALIENCY_COVERAGE_POLICY_DEFINITIONS & state_names
        if policy_definitions:
            violations.append(
                f"{APPLICATION_STATE_SERVICE_MODULE} defines saliency coverage policy "
                f"owned by {SALIENCY_COVERAGE_OWNER}: "
                f"{', '.join(sorted(policy_definitions))}."
            )
        if "QueryStateCommandService" in state_names:
            violations.append(
                f"QueryStateCommandService is owned by {QUERY_STATE_SERVICE_OWNER}; "
                f"{APPLICATION_STATE_SERVICE_MODULE} may only re-export it."
            )

        saliency_compatibility_exports = {
            alias.name
            for node in state_service_tree.body
            if isinstance(node, ast.ImportFrom)
            and _application_module_matches(node.module, "saliency_coverage")
            for alias in node.names
        }
        missing_saliency_exports = (
            SALIENCY_COVERAGE_COMPATIBILITY_NAMES - saliency_compatibility_exports
        )
        if missing_saliency_exports:
            violations.append(
                f"{APPLICATION_STATE_SERVICE_MODULE} must explicitly re-export "
                "compatibility names from saliency_coverage: "
                f"{', '.join(sorted(missing_saliency_exports))}."
            )

        query_compatibility_exported = any(
            isinstance(node, ast.ImportFrom)
            and _application_module_matches(node.module, "query_state_service")
            and any(alias.name == "QueryStateCommandService" for alias in node.names)
            for node in state_service_tree.body
        )
        if not query_compatibility_exported:
            violations.append(
                f"{APPLICATION_STATE_SERVICE_MODULE} must explicitly re-export "
                "QueryStateCommandService from query_state_service."
            )

        for node in ast.walk(state_service_tree):
            if not isinstance(node, ast.Call):
                continue
            called_name = _called_symbol_name(node.func)
            if called_name in SALIENCY_COVERAGE_SNAPSHOT_TYPES:
                violations.append(
                    f"{APPLICATION_STATE_SERVICE_MODULE}:{node.lineno} constructs "
                    f"{called_name}; StateSnapshotService must consume "
                    "SaliencyCoverageProjector output."
                )

    for path, tree in (
        (SALIENCY_COVERAGE_OWNER, saliency_owner_tree),
        (QUERY_STATE_SERVICE_OWNER, query_owner_tree),
        (APPLICATION_STATE_SERVICE_MODULE, state_service_tree),
    ):
        if tree is None:
            continue
        for node in ast.walk(tree):
            violations.extend(
                f"{path}:{getattr(node, 'lineno', 0)} imports {module_name}; "
                "application state modules must remain cold-import safe."
                for module_name in _imported_module_names(node)
                if module_name == "matplotlib" or module_name.startswith("matplotlib.")
            )

    product_root = root_dir / "XBrainLab"
    if not product_root.exists():
        return violations

    for py_file in product_root.rglob("*.py"):
        relative_path = py_file.relative_to(root_dir)
        tree = _parse_python_file(py_file)
        if tree is None:
            continue

        is_state_compatibility = relative_path == APPLICATION_STATE_SERVICE_MODULE
        is_query_owner = relative_path == QUERY_STATE_SERVICE_OWNER
        is_ui = relative_path.parts[:2] == ("XBrainLab", "ui")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                if (
                    "QueryStateCommandService" in imported_names
                    and not is_state_compatibility
                    and not is_query_owner
                    and not _application_module_matches(
                        node.module,
                        "query_state_service",
                    )
                ):
                    violations.append(
                        f"{relative_path}:{node.lineno} imports "
                        "QueryStateCommandService from "
                        f"{node.module or '<relative module>'}; product imports "
                        f"must point to {QUERY_STATE_SERVICE_OWNER}."
                    )

                ui_policy_imports = imported_names & SALIENCY_COVERAGE_PUBLIC_NAMES
                imports_saliency_owner = _application_module_matches(
                    node.module,
                    "saliency_coverage",
                )
                imports_state_compatibility = _application_module_matches(
                    node.module,
                    "state_service",
                )
                if is_ui and (
                    imports_saliency_owner
                    or (ui_policy_imports and imports_state_compatibility)
                ):
                    imported_policy = (
                        imported_names if imports_saliency_owner else ui_policy_imports
                    )
                    violations.append(
                        f"{relative_path}:{node.lineno} imports "
                        f"{', '.join(sorted(imported_policy))}; UI must consume "
                        "published saliency coverage instead of calling its projector."
                    )
            elif isinstance(node, ast.Import):
                violations.extend(
                    f"{relative_path}:{node.lineno} imports {alias.name}; UI must "
                    "consume published saliency coverage instead of calling its "
                    "projector."
                    for alias in node.names
                    if is_ui
                    and _application_module_matches(
                        alias.name,
                        "saliency_coverage",
                    )
                )
            elif is_ui and isinstance(node, ast.Call):
                called_name = _called_symbol_name(node.func)
                if called_name in SALIENCY_COVERAGE_UI_CALL_NAMES:
                    violations.append(
                        f"{relative_path}:{node.lineno} calls {called_name}; UI must "
                        "consume published saliency coverage instead of calling its "
                        "projector."
                    )

    return violations


def _application_module_matches(module: str | None, leaf: str) -> bool:
    module_name = module or ""
    return module_name == leaf or module_name.endswith(f".{leaf}")


def _called_symbol_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _constructs_application_service(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and _called_symbol_name(node.func) == "ApplicationService"
    )


def _imported_module_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        return {node.module or ""}
    return set()


def _top_level_bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            continue
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        names.update(
            child.id
            for target in targets
            for child in ast.walk(target)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        )
    return names


def _is_saliency_provenance_owner_import(module: str | None) -> bool:
    module_name = module or ""
    return module_name == "saliency_provenance" or module_name.endswith(
        ".saliency_provenance"
    )


def check_application_service_ownership_boundaries(root_dir: Path) -> list[str]:
    """Keep service creation/cache ownership at the application runtime boundary."""
    violations: list[str] = []
    product_dir = root_dir / "XBrainLab"
    if product_dir.exists():
        for py_file in product_dir.rglob("*.py"):
            relative_path = py_file.relative_to(root_dir)
            if relative_path in APPLICATION_SERVICE_CACHE_OWNER_FILES:
                continue
            tree = _parse_python_file(py_file)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if _reads_private_application_service_cache(node):
                    violations.append(
                        f"{relative_path}:{getattr(node, 'lineno', 0)} reads the "
                        "private ApplicationService cache; runtime.py is its sole "
                        "lifecycle owner."
                    )
                elif _writes_private_application_service_cache(node):
                    if relative_path == Path("XBrainLab/backend/study.py") and (
                        _declares_application_service_cache_storage(node)
                    ):
                        continue
                    violations.append(
                        f"{relative_path}:{getattr(node, 'lineno', 0)} writes the "
                        "private ApplicationService cache; runtime.py is its sole "
                        "lifecycle owner."
                    )
                elif _constructs_application_service(node):
                    violations.append(
                        f"{relative_path}:{getattr(node, 'lineno', 0)} constructs "
                        "ApplicationService directly; product runtime must use "
                        "get_application_service()."
                    )

    service_path = root_dir / "XBrainLab" / "backend" / "application" / "service.py"
    service_tree = _parse_python_file(service_path)
    if service_tree is not None:
        violations.extend(
            f"{service_path.relative_to(root_dir)}:"
            f"{getattr(node, 'lineno', 0)} calls an adapter's private "
            "_resolve_controller(); ApplicationService must use the typed "
            "adapter port."
            for node in ast.walk(service_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_resolve_controller"
        )
        for class_node in service_tree.body:
            if not (
                isinstance(class_node, ast.ClassDef)
                and class_node.name == "ApplicationService"
            ):
                continue
            violations.extend(
                f"{service_path.relative_to(root_dir)}:{method.lineno} "
                "ApplicationService must not define __new__; runtime.py owns "
                "service creation and the constructor is initialization-only."
                for method in class_node.body
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                and method.name == "__new__"
            )

    study_path = root_dir / "XBrainLab" / "backend" / "study.py"
    study_tree = _parse_python_file(study_path)
    if study_tree is not None:
        violations.extend(
            f"{study_path.relative_to(root_dir)}:"
            f"{getattr(node, 'lineno', 0)} imports the "
            "application runtime; Study must not depend on application runtime."
            for node in ast.walk(study_tree)
            if _imports_application_service_runtime(node)
        )

    pipeline_path = (
        root_dir / "XBrainLab" / "backend" / "application" / "pipeline_stage.py"
    )
    pipeline_tree = _parse_python_file(pipeline_path)
    if pipeline_tree is not None:
        violations.extend(
            f"{pipeline_path.relative_to(root_dir)}:"
            f"{getattr(node, 'lineno', 0)} locates "
            "ApplicationService; pipeline_stage.py must not service-locate "
            "and requires an explicit ApplicationViewPublication."
            for node in ast.walk(pipeline_tree)
            if _imports_application_service_runtime(node)
            or _calls_application_service_locator(node)
        )

    return violations


def check_application_shutdown_lifecycle_ownership(root_dir: Path) -> list[str]:
    """Keep shutdown state and reconciliation out of ``ApplicationService``."""
    service_path = root_dir / "XBrainLab" / "backend" / "application" / "service.py"
    service_tree = _parse_python_file(service_path)
    violations: list[str] = []
    if service_tree is not None:
        relative_path = service_path.relative_to(root_dir)
        for class_node in service_tree.body:
            if not (
                isinstance(class_node, ast.ClassDef)
                and class_node.name == "ApplicationService"
            ):
                continue
            violations.extend(
                f"{relative_path}:{node.lineno} stores shutdown lifecycle state "
                f"'{node.attr}' on ApplicationService; use "
                "ApplicationShutdownLifecycleCoordinator."
                for node in ast.walk(class_node)
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr in APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_ATTRIBUTES
                )
            )
            violations.extend(
                f"{relative_path}:{method.lineno} keeps shutdown reconciliation "
                f"method '{method.name}' on ApplicationService; delegate to "
                "ApplicationShutdownLifecycleCoordinator."
                for method in class_node.body
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                and method.name in APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_METHODS
            )

    runtime_path = root_dir / "XBrainLab" / "backend" / "application" / "runtime.py"
    runtime_tree = _parse_python_file(runtime_path)
    if runtime_tree is not None:
        relative_path = runtime_path.relative_to(root_dir)
        for node in ast.walk(runtime_tree):
            private_attribute: str | None = None
            if (
                isinstance(node, ast.Attribute)
                and node.attr in APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_ATTRIBUTES
            ):
                private_attribute = node.attr
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value
                in APPLICATION_SERVICE_SHUTDOWN_LIFECYCLE_ATTRIBUTES
            ):
                private_attribute = node.args[1].value
            if private_attribute is not None:
                violations.append(
                    f"{relative_path}:{getattr(node, 'lineno', 0)} reads private "
                    "shutdown lifecycle "
                    f"state '{private_attribute}'; use ApplicationService.is_closed."
                )
    return violations


def check_application_controller_boundary(root_dir: Path) -> list[str]:
    """Keep the application package independent of UI controller families."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    if not application_dir.exists():
        return []

    violations: list[str] = []
    adapter_references: set[tuple[Path, int, str]] = set()
    for path in sorted(application_dir.rglob("*.py")):
        tree = _parse_python_file(path)
        if tree is None:
            continue
        relative = path.relative_to(root_dir)
        for node in ast.walk(tree):
            imported_modules = _imported_module_names(node)
            if any(
                "controller" in module_name.split(".")
                or "controller_adapters" in module_name.split(".")
                for module_name in imported_modules
            ):
                violations.append(
                    f"{relative}:{getattr(node, 'lineno', 0)} imports a controller "
                    "module; application composition must use Study-owned ports."
                )

            symbol_name: str | None = None
            if isinstance(node, ast.ClassDef):
                symbol_name = node.name
            elif isinstance(node, ast.Name):
                symbol_name = node.id
            elif isinstance(node, ast.Attribute):
                symbol_name = node.attr
            if symbol_name is not None and symbol_name.endswith("ControllerAdapter"):
                adapter_references.add(
                    (relative, getattr(node, "lineno", 0), symbol_name)
                )

            if (
                isinstance(node, ast.Call)
                and _called_symbol_name(node.func) == "get_controller"
            ):
                violations.append(
                    f"{relative}:{node.lineno} calls get_controller; application "
                    "composition must use an explicit Study-owned port."
                )

    violations.extend(
        f"{relative}:{line} references {name}; controller adapters are forbidden "
        "in the application layer."
        for relative, line, name in sorted(
            adapter_references,
            key=lambda item: (str(item[0]), item[1], item[2]),
        )
    )
    return violations


def check_dataset_product_port_boundary(root_dir: Path) -> list[str]:
    """Keep Dataset product commands on the Study-owned dataset service port."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    if not application_dir.exists():
        return []

    violations: list[str] = []
    for py_file in application_dir.rglob("*.py"):
        relative = py_file.relative_to(root_dir)
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                forbidden = imported_names & {
                    "DatasetController",
                    "DatasetControllerAdapter",
                }
                if forbidden:
                    violations.append(
                        f"{relative}:{node.lineno} imports "
                        f"{', '.join(sorted(forbidden))}; Dataset product commands "
                        "must depend on DatasetProductPort."
                    )
            elif isinstance(node, (ast.ClassDef, ast.Name, ast.Attribute)):
                symbol = (
                    node.name
                    if isinstance(node, ast.ClassDef)
                    else node.id
                    if isinstance(node, ast.Name)
                    else node.attr
                )
                if symbol == "DatasetControllerAdapter":
                    violations.append(
                        f"{relative}:{getattr(node, 'lineno', 0)} references "
                        "DatasetControllerAdapter; the application Dataset family "
                        "must use DatasetProductPort."
                    )
            if not isinstance(node, ast.Call):
                continue
            if (
                _called_symbol_name(node.func) == "get_controller"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "dataset"
            ):
                violations.append(
                    f"{relative}:{node.lineno} resolves Study.get_controller"
                    "('dataset'); Dataset product commands must use the "
                    "Study-owned dataset service port."
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "notify"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "dataset"
            ) or (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Attribute)
                and node.args[0].attr == "dataset"
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "notify"
            ):
                violations.append(
                    f"{relative}:{node.lineno} reaches Dataset observer semantics; "
                    "application business logic must publish CommandResult and "
                    "application view truth instead."
                )
    return violations


def check_preprocess_product_port_boundary(root_dir: Path) -> list[str]:
    """Keep Preprocess product commands on the Study-owned domain service port."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    if not application_dir.exists():
        return []

    forbidden_symbols = {
        "PreprocessController",
        "PreprocessControllerAdapter",
        "_PreprocessControllerPort",
    }
    violations: list[str] = []
    for py_file in application_dir.rglob("*.py"):
        relative = py_file.relative_to(root_dir)
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            imported_modules = _imported_module_names(node)
            if any(
                module_name.endswith("controller.preprocess_controller")
                for module_name in imported_modules
            ):
                violations.append(
                    f"{relative}:{getattr(node, 'lineno', 0)} imports the "
                    "preprocess controller module; Preprocess product commands "
                    "must depend on the Study-owned preprocess service port."
                )
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                forbidden = imported_names & forbidden_symbols
                if forbidden:
                    violations.append(
                        f"{relative}:{node.lineno} imports "
                        f"{', '.join(sorted(forbidden))}; Preprocess product "
                        "commands must depend on the Study-owned preprocess service "
                        "port."
                    )
            elif isinstance(node, (ast.ClassDef, ast.Name, ast.Attribute)):
                symbol = (
                    node.name
                    if isinstance(node, ast.ClassDef)
                    else node.id
                    if isinstance(node, ast.Name)
                    else node.attr
                )
                if symbol in forbidden_symbols:
                    violations.append(
                        f"{relative}:{getattr(node, 'lineno', 0)} references "
                        f"{symbol}; the application Preprocess family must use the "
                        "Study-owned preprocess service port."
                    )
            if not isinstance(node, ast.Call):
                continue
            if (
                _called_symbol_name(node.func) == "get_controller"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "preprocess"
            ):
                violations.append(
                    f"{relative}:{node.lineno} resolves "
                    "Study.get_controller('preprocess'); Preprocess product commands "
                    "must use the Study-owned preprocess service port."
                )

    service_path = application_dir / "service.py"
    service_tree = _parse_python_file(service_path)
    if service_tree is None:
        return violations

    preprocess_assignments: list[tuple[int, ast.AST | None]] = []
    for node in ast.walk(service_tree):
        if isinstance(node, ast.Assign):
            value = node.value
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        else:
            continue
        if any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "preprocess"
            for target in targets
        ):
            preprocess_assignments.append((node.lineno, value))

    if not preprocess_assignments:
        violations.append(
            "XBrainLab/backend/application/service.py does not compose the "
            "Study-owned preprocess service port."
        )
    for line, value in preprocess_assignments:
        if not (
            isinstance(value, ast.Attribute)
            and value.attr == "preprocess_state_service"
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "study"
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "self"
        ):
            violations.append(
                "XBrainLab/backend/application/service.py:"
                f"{line} must compose self.preprocess from the Study-owned "
                "preprocess service port."
            )
    return violations


def check_visualization_product_port_boundary(root_dir: Path) -> list[str]:
    """Keep Visualization commands on a manager-owned domain service port."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    if not application_dir.exists():
        return []

    forbidden_symbols = {
        "VisualizationController",
        "VisualizationControllerAdapter",
        "_VisualizationControllerPort",
    }
    violations: list[str] = []
    for py_file in application_dir.rglob("*.py"):
        relative = py_file.relative_to(root_dir)
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            imported_modules = _imported_module_names(node)
            if any(
                module_name.endswith("controller.visualization_controller")
                for module_name in imported_modules
            ):
                violations.append(
                    f"{relative}:{getattr(node, 'lineno', 0)} imports the "
                    "visualization controller module; Visualization product "
                    "commands must depend on a manager-owned domain port."
                )
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                forbidden = imported_names & forbidden_symbols
                if forbidden:
                    violations.append(
                        f"{relative}:{node.lineno} imports "
                        f"{', '.join(sorted(forbidden))}; Visualization product "
                        "commands must depend on a manager-owned domain port."
                    )
            elif isinstance(node, (ast.ClassDef, ast.Name, ast.Attribute)):
                symbol = (
                    node.name
                    if isinstance(node, ast.ClassDef)
                    else node.id
                    if isinstance(node, ast.Name)
                    else node.attr
                )
                if symbol in forbidden_symbols:
                    violations.append(
                        f"{relative}:{getattr(node, 'lineno', 0)} references "
                        f"{symbol}; the application Visualization family must "
                        "use a manager-owned domain port."
                    )
            if not isinstance(node, ast.Call):
                continue
            if (
                _called_symbol_name(node.func) == "get_controller"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "visualization"
            ):
                violations.append(
                    f"{relative}:{node.lineno} resolves Study.get_controller"
                    "('visualization'); Visualization product commands must use "
                    "the manager-owned domain port."
                )
    return violations


def check_application_publication_lifecycle_port_boundary(
    root_dir: Path,
) -> list[str]:
    """Keep publication orchestration behind application-owned event ports."""
    relative = Path(
        "XBrainLab/backend/application/application_publication_lifecycle.py"
    )
    lifecycle_path = root_dir / relative
    tree = _parse_python_file(lifecycle_path)
    if tree is None:
        return [f"{relative} is missing or invalid."]

    violations: list[str] = []
    adapter_references: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        imported_modules = _imported_module_names(node)
        if any(
            "controller_adapters" in module_name.split(".")
            for module_name in imported_modules
        ):
            violations.append(
                f"{relative}:{getattr(node, 'lineno', 0)} imports "
                "controller_adapters; ApplicationPublicationLifecycle must depend "
                "on application-owned event ports."
            )

        symbol_name: str | None = None
        if isinstance(node, ast.Name):
            symbol_name = node.id
        elif isinstance(node, ast.Attribute):
            symbol_name = node.attr
        if symbol_name is not None and symbol_name.endswith("ControllerAdapter"):
            adapter_references.add((getattr(node, "lineno", 0), symbol_name))

        if isinstance(node, ast.Call) and _call_name(node.func) == "get_controller":
            violations.append(
                f"{relative}:{node.lineno} calls get_controller; publication "
                "orchestration must receive an injected lifecycle event port."
            )

    violations.extend(
        f"{relative}:{line} references {name}; controller adapters belong outside "
        "ApplicationPublicationLifecycle."
        for line, name in sorted(adapter_references)
    )

    lifecycle_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "ApplicationPublicationLifecycle"
        ),
        None,
    )
    initializer = (
        next(
            (
                node
                for node in lifecycle_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "__init__"
            ),
            None,
        )
        if lifecycle_class is not None
        else None
    )
    training_events_parameter = (
        next(
            (
                argument
                for argument in (
                    *initializer.args.posonlyargs,
                    *initializer.args.args,
                    *initializer.args.kwonlyargs,
                )
                if argument.arg == "training_events"
            ),
            None,
        )
        if initializer is not None
        else None
    )
    if training_events_parameter is None or not _annotation_mentions_symbol(
        training_events_parameter.annotation,
        "TrainingLifecycleEventPort",
    ):
        violations.append(
            f"{relative} must inject training_events as TrainingLifecycleEventPort."
        )

    service_relative = Path("XBrainLab/backend/application/service.py")
    service_tree = _parse_python_file(root_dir / service_relative)
    if service_tree is not None:
        lifecycle_constructions = [
            node
            for node in ast.walk(service_tree)
            if isinstance(node, ast.Call)
            and _called_symbol_name(node.func) == "ApplicationPublicationLifecycle"
        ]
        if not lifecycle_constructions or any(
            not any(
                keyword.arg == "training_events" for keyword in construction.keywords
            )
            for construction in lifecycle_constructions
        ):
            violations.append(
                f"{service_relative} must inject training_events at the existing "
                "ApplicationPublicationLifecycle composition root."
            )

    return violations


def _annotation_mentions_symbol(annotation: ast.AST | None, symbol: str) -> bool:
    if annotation is None:
        return False
    return any(
        (isinstance(node, ast.Name) and node.id == symbol)
        or (isinstance(node, ast.Attribute) and node.attr == symbol)
        or (isinstance(node, ast.Constant) and node.value == symbol)
        for node in ast.walk(annotation)
    )


def check_training_runtime_port_boundary(root_dir: Path) -> list[str]:
    """Keep Study.training_manager behind its typed application runtime port."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    if not application_dir.exists():
        return []

    violations: list[str] = []
    for py_file in application_dir.rglob("*.py"):
        relative = py_file.relative_to(root_dir)
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        if relative == TRAINING_RUNTIME_OWNER:
            for node in ast.walk(tree):
                direct_trainer_access = (
                    isinstance(node, ast.Attribute)
                    and node.attr == "trainer"
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr in {"_manager", "training_manager"}
                )
                dynamic_trainer_access = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Attribute)
                    and node.args[0].attr in {"_manager", "training_manager"}
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "trainer"
                )
                if direct_trainer_access or dynamic_trainer_access:
                    violations.append(
                        f"{relative}:{getattr(node, 'lineno', 0)} accesses the "
                        "TrainingManager.trainer field directly; TrainingRuntimePort "
                        "must use one lock-scoped manager accessor."
                    )
            continue
        alias_visitor = _StudyTrainingAliasVisitor(relative)
        alias_visitor.visit(tree)
        violations.extend(alias_visitor.violations)
        for node in ast.walk(tree):
            direct_access = (
                isinstance(node, ast.Attribute) and node.attr == "training_manager"
            )
            getattr_access = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "training_manager"
            )
            if direct_access or getattr_access:
                violations.append(
                    f"{relative}:{getattr(node, 'lineno', 0)} accesses "
                    "Study.training_manager outside TrainingRuntimePort; "
                    "training_runtime.py is the only application runtime owner."
                )
    return violations


class _StudyTrainingAliasVisitor(ast.NodeVisitor):
    """Find Study compatibility aliases without flagging domain model fields."""

    def __init__(self, relative_path: Path) -> None:
        self.relative_path = relative_path
        self.violations: list[str] = []
        self._function_stack: list[str] = []
        self._study_alias_scopes: list[set[str]] = [set()]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self._function_stack.append(node.name)
        aliases = set(self._study_alias_scopes[-1])
        aliases.update(self._function_study_aliases(node))
        self._study_alias_scopes.append(aliases)
        self.generic_visit(node)
        self._study_alias_scopes.pop()
        self._function_stack.pop()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            node.attr in STUDY_TRAINING_COMPATIBILITY_FIELDS
            and self._is_study_root(node.value)
            and not self._legacy_pipeline_exemption()
        ):
            self._record(node, node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr", "delattr"}
            and len(node.args) >= 2
            and self._is_study_root(node.args[0])
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in STUDY_TRAINING_COMPATIBILITY_FIELDS
            and not self._legacy_pipeline_exemption()
        ):
            self._record(node, str(node.args[1].value))
        self.generic_visit(node)

    def _is_study_root(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "study" or node.id in self._study_alias_scopes[-1]
        return isinstance(node, ast.Attribute) and node.attr in {"study", "_study"}

    def _legacy_pipeline_exemption(self) -> bool:
        if (
            self.relative_path
            != Path("XBrainLab/backend/application/pipeline_stage.py")
            or not self._function_stack
        ):
            return False
        return self._function_stack[-1] == "_legacy_study_pipeline_stage"

    def _record(self, node: ast.AST, field_name: str) -> None:
        self.violations.append(
            f"{self.relative_path}:{getattr(node, 'lineno', 0)} accesses "
            f"Study.{field_name} compatibility state outside TrainingRuntimePort."
        )

    @staticmethod
    def _function_study_aliases(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> set[str]:
        aliases: set[str] = set()
        for child in ast.walk(node):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child is not node
            ):
                continue
            if isinstance(child, ast.Assign):
                value = child.value
                targets = child.targets
            elif isinstance(child, ast.AnnAssign):
                value = child.value
                targets = [child.target]
            else:
                continue
            if value is None or not (
                (isinstance(value, ast.Name) and value.id == "study")
                or (
                    isinstance(value, ast.Attribute)
                    and value.attr in {"study", "_study"}
                )
            ):
                continue
            aliases.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )
        return aliases


def check_montage_command_ownership(root_dir: Path) -> list[str]:
    """Keep montage mutation on the ApplicationService/coordinator boundary."""
    violations: list[str] = []
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    analysis_path = application_dir / "analysis_service.py"
    preprocess_path = application_dir / "preprocess_service.py"
    service_path = application_dir / "service.py"

    analysis_tree = _parse_python_file(analysis_path)
    if analysis_tree is not None:
        analysis_class = next(
            (
                node
                for node in analysis_tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == "AnalysisCommandService"
            ),
            None,
        )
        if analysis_class is not None:
            method_names = {
                node.name
                for node in analysis_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "handle_apply_montage" in method_names:
                violations.append(
                    "XBrainLab/backend/application/analysis_service.py owns "
                    "handle_apply_montage; montage mutation belongs to "
                    "ApplicationService and the BIDS montage coordinator."
                )
            constructor = next(
                (
                    node
                    for node in analysis_class.body
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__"
                ),
                None,
            )
            if constructor is not None and any(
                argument.arg == "preprocess"
                for argument in [
                    *constructor.args.posonlyargs,
                    *constructor.args.args,
                    *constructor.args.kwonlyargs,
                ]
            ):
                violations.append(
                    "XBrainLab/backend/application/analysis_service.py depends on "
                    "the preprocess mutation controller; analysis must remain "
                    "read/evaluation/visualization focused."
                )

    preprocess_tree = _parse_python_file(preprocess_path)
    preprocess_handler = None
    if preprocess_tree is not None:
        preprocess_class = next(
            (
                node
                for node in preprocess_tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == "PreprocessCommandService"
            ),
            None,
        )
        if preprocess_class is not None:
            preprocess_handler = next(
                (
                    node
                    for node in preprocess_class.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "handle_apply_montage"
                ),
                None,
            )
    if preprocess_handler is not None:
        violations.append(
            "XBrainLab/backend/application/preprocess_service.py must not own "
            "handle_apply_montage."
        )

    service_tree = _parse_python_file(service_path)
    montage_routes: list[str] = []
    if service_tree is not None:
        lazy_analysis_class = next(
            (
                node
                for node in service_tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == "_LazyAnalysisCommandService"
            ),
            None,
        )
        if lazy_analysis_class is not None:
            lazy_method_names = {
                node.name
                for node in lazy_analysis_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "handle_apply_montage" in lazy_method_names:
                violations.append(
                    "_LazyAnalysisCommandService owns handle_apply_montage; "
                    "montage commands must route directly to ApplicationService."
                )
            lazy_constructor = next(
                (
                    node
                    for node in lazy_analysis_class.body
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__"
                ),
                None,
            )
            if lazy_constructor is not None and any(
                argument.arg == "preprocess"
                for argument in [
                    *lazy_constructor.args.posonlyargs,
                    *lazy_constructor.args.args,
                    *lazy_constructor.args.kwonlyargs,
                ]
            ):
                violations.append(
                    "The lazy analysis wrapper depends on preprocess; montage "
                    "mutation wiring belongs to ApplicationService."
                )

        for node in ast.walk(service_tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                if not (
                    isinstance(key, ast.Attribute)
                    and key.attr == "APPLY_MONTAGE"
                    and isinstance(value, ast.Attribute)
                ):
                    continue
                if value.attr == "handle_apply_montage" and isinstance(
                    value.value, ast.Attribute
                ):
                    montage_routes.append(value.value.attr)
                elif (
                    value.attr == "_handle_apply_montage"
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "self"
                ):
                    montage_routes.append("application_service")
    if montage_routes != ["application_service"]:
        rendered = ", ".join(montage_routes) if montage_routes else "missing"
        violations.append(
            "ApplicationService must route APPLY_MONTAGE exactly once to "
            "one authorized montage handler; current owner(s): "
            f"{rendered}."
        )

    return violations


def check_training_configuration_reset_ownership(root_dir: Path) -> list[str]:
    """Keep configuration writes in the runtime and reset as delegation only."""
    application_dir = root_dir / "XBrainLab" / "backend" / "application"
    owner_path = root_dir / TRAINING_RUNTIME_OWNER
    delegate_path = root_dir / TRAINING_CONFIGURATION_RESET_DELEGATE
    if not application_dir.exists():
        return []

    violations: list[str] = []
    owner_fields: set[str] = set()
    for py_file in application_dir.rglob("*.py"):
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        relative_path = py_file.relative_to(root_dir)
        assigned_fields = {
            target.attr
            for node in ast.walk(tree)
            for target in _assignment_attribute_targets(node)
            if target.attr in TRAINING_CONFIGURATION_RESET_FIELDS
        }
        if relative_path == TRAINING_RUNTIME_OWNER:
            owner_fields.update(assigned_fields)
            continue
        violations.extend(
            (
                f"{relative_path} assigns training configuration field "
                f"{field_name!r}; configuration mutation must be owned only by "
                f"{TRAINING_RUNTIME_OWNER}."
            )
            for field_name in sorted(assigned_fields)
        )

    if not owner_path.exists():
        violations.append(
            f"{TRAINING_RUNTIME_OWNER} is missing; application-level training "
            "configuration requires one runtime owner."
        )
    else:
        missing_fields = TRAINING_CONFIGURATION_RESET_FIELDS - owner_fields
        if missing_fields:
            violations.append(
                f"{TRAINING_RUNTIME_OWNER} does not own configuration mutation "
                f"for: {', '.join(sorted(missing_fields))}."
            )

    delegate_tree = _parse_python_file(delegate_path)
    if delegate_tree is None:
        violations.append(
            f"{TRAINING_CONFIGURATION_RESET_DELEGATE} is missing; reset must "
            "delegate to TrainingRuntimePort.clear_configuration()."
        )
    elif not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "clear_configuration"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "training_runtime"
        for node in ast.walk(delegate_tree)
    ):
        violations.append(
            f"{TRAINING_CONFIGURATION_RESET_DELEGATE} must delegate reset to "
            "training_runtime.clear_configuration()."
        )
    return violations


def _assignment_attribute_targets(node: ast.AST) -> list[ast.Attribute]:
    targets: list[ast.AST]
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    return [
        child
        for target in targets
        for child in ast.walk(target)
        if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store)
    ]


def _parse_python_file(path: Path) -> ast.Module | None:
    if not path.exists():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None


@dataclass(frozen=True)
class _MutableObjectBoundaryUse:
    path: str
    symbol: str
    boundary: str
    form: str
    lineno: int
    col_offset: int
    detail: str

    @property
    def allowlist_key(self) -> tuple[str, str, str, str]:
        return (self.path, self.symbol, self.boundary, self.form)


_MUTABLE_BOUNDARY_LABELS = {
    MUTABLE_BOUNDARY_INCLUDE_OBJECTS: "include_objects use",
    MUTABLE_BOUNDARY_LOCAL_PAYLOAD: "local_payload use",
    MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD: "local_result_payload use",
    MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME: "CommandResult.runtime access",
    MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE: "backend domain object storage",
}

_BACKEND_DOMAIN_OBJECT_NAMES = frozenset(
    {
        "averaged_record",
        "data",
        "data_list",
        "dataset",
        "dataset_generator",
        "datasets",
        "epoch_data",
        "eval_record",
        "friendly_map",
        "loaded_data_list",
        "model_holder",
        "plan",
        "plan_to_plot",
        "plans",
        "pooled_record",
        "preferred_record",
        "preprocessed_data_list",
        "raw_data",
        "real_plan_map",
        "real_plan_opt",
        "record",
        "records",
        "row_map",
        "study",
        "trainer",
        "trainer_map",
        "trainers",
        "training_plan_holders",
    }
)
_BACKEND_DOMAIN_OBJECT_SUFFIXES = (
    "_data_list",
    "_dataset",
    "_datasets",
    "_dataset_generator",
    "_epoch_data",
    "_model_holder",
    "_plan",
    "_plans",
    "_record",
    "_records",
    "_study",
    "_trainer",
    "_trainers",
)
_BACKEND_DOMAIN_RESULT_KEYS = frozenset(
    {
        "averaged_records",
        "dataset_generator",
        "datasets",
        "epoch_data",
        "loaded_data_list",
        "plan",
        "plan_objects",
        "pooled_results",
        "preprocessed_data_list",
        "record",
        "trainer_objects",
    }
)
_BACKEND_DOMAIN_RETURNING_CALLS = frozenset(
    {
        "DatasetGenerator",
        "get_dataset_generator",
        "get_datasets",
        "get_epoch_data",
        "get_formatted_history",
        "get_plans",
        "get_trainer",
        "get_trainers",
        "get_training_plan_holders",
    }
)


def check_training_history_projection_boundary(root_dir: Path) -> list[str]:
    """Keep product training history detached from mutable plan/record objects."""
    violations: list[str] = []

    query_path = root_dir / "XBrainLab/backend/application/query_state_service.py"
    query_tree = _parse_python_file(query_path) if query_path.exists() else None
    if query_tree is not None:
        query_method = _find_class_method(
            query_tree,
            "QueryStateCommandService",
            "handle_query_state",
        )
        if query_method is not None:
            for call in (
                node for node in ast.walk(query_method) if isinstance(node, ast.Call)
            ):
                if _mutable_boundary_call_name(call.func) != "training_history":
                    continue
                include_objects = any(
                    keyword.arg == "include_objects" for keyword in call.keywords
                )
                if call.args or include_objects:
                    violations.append(
                        f"{query_path.relative_to(root_dir)}:{call.lineno} "
                        "training_history product query must not pass "
                        "include_objects or other object-selection arguments"
                    )

    state_path = root_dir / "XBrainLab/backend/application/state_service.py"
    state_tree = _parse_python_file(state_path) if state_path.exists() else None
    if state_tree is not None:
        state_method = _find_class_method(
            state_tree,
            "StateSnapshotService",
            "training_history",
        )
        if state_method is not None:
            parameter_names = {
                argument.arg
                for argument in (
                    *state_method.args.posonlyargs,
                    *state_method.args.args,
                    *state_method.args.kwonlyargs,
                )
            }
            if parameter_names - {"self"}:
                violations.append(
                    f"{state_path.relative_to(root_dir)}:{state_method.lineno} "
                    "StateSnapshotService.training_history must expose one "
                    "detached projection with no object opt-in"
                )
            if not any(
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func)
                == "project_training_history_rows"
                for node in ast.walk(state_method)
            ):
                violations.append(
                    f"{state_path.relative_to(root_dir)}:{state_method.lineno} "
                    "StateSnapshotService.training_history must return the "
                    "detached training-history projection"
                )

    projection_path = root_dir / "XBrainLab/backend/application/training_history.py"
    projection_tree = (
        _parse_python_file(projection_path) if projection_path.exists() else None
    )
    if projection_tree is not None:
        to_dict_method = _find_class_method(
            projection_tree,
            "TrainingHistoryRow",
            "to_dict",
        )
        if to_dict_method is not None:
            projected_keys = {
                key.value
                for node in ast.walk(to_dict_method)
                if isinstance(node, ast.Dict)
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            violations.extend(
                (
                    f"{projection_path.relative_to(root_dir)}:"
                    f"{to_dict_method.lineno} detached training history must "
                    f"not serialize live key {live_key!r}"
                )
                for live_key in ("plan", "record")
                if live_key in projected_keys
            )
            missing_keys = {"identity", "metrics"} - projected_keys
            if missing_keys:
                violations.append(
                    f"{projection_path.relative_to(root_dir)}:"
                    f"{to_dict_method.lineno} detached training history is missing "
                    f"required key(s): {', '.join(sorted(missing_keys))}"
                )

    for relative_path in (
        Path("XBrainLab/ui/panels/training/panel.py"),
        Path("XBrainLab/ui/panels/training/history_table.py"),
    ):
        ui_path = root_dir / relative_path
        ui_tree = _parse_python_file(ui_path) if ui_path.exists() else None
        if ui_tree is None:
            continue
        for node in ast.walk(ui_tree):
            if (
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func) == "QueryStateCommand"
                and _query_state_call_name(node) == "training_history"
                and any(keyword.arg == "include_objects" for keyword in node.keywords)
            ):
                violations.append(
                    f"{relative_path}:{node.lineno} training history UI must not "
                    "pass include_objects"
                )
            if isinstance(node, (ast.Name, ast.Attribute)) and _ast_identifier(
                node
            ) in {
                "current_plotting_record",
                "selection_changed_record",
                "row_map",
            }:
                violations.append(
                    f"{relative_path}:{node.lineno} record-based training history "
                    f"UI state is forbidden: {_ast_identifier(node)}"
                )
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in {"plan", "record"}
            ):
                violations.append(
                    f"{relative_path}:{node.lineno} training history UI must not "
                    f"read live row key {node.slice.value!r}"
                )

    detached_consumer_paths = [
        Path("scripts/dev/run_public_cross_source_training_smoke.py"),
        *sorted((root_dir / "tests" / "integration").rglob("*.py")),
    ]
    for candidate in detached_consumer_paths:
        consumer_path = candidate if candidate.is_absolute() else root_dir / candidate
        consumer_tree = (
            _parse_python_file(consumer_path) if consumer_path.exists() else None
        )
        if consumer_tree is None:
            continue
        relative_path = consumer_path.relative_to(root_dir)
        violations.extend(
            f"{relative_path}:{node.lineno} product validation must read "
            "detached training-history diagnostics, not include_objects"
            for node in ast.walk(consumer_tree)
            if (
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func) == "QueryStateCommand"
                and _query_state_call_name(node) == "training_history"
                and any(keyword.arg == "include_objects" for keyword in node.keywords)
            )
        )

    return violations


def check_dataset_detached_read_boundary(root_dir: Path) -> list[str]:
    """Keep product Dataset readers on detached row and channel projections."""
    violations: list[str] = []
    query_path = root_dir / "XBrainLab/backend/application/query_state_service.py"
    query_tree = _parse_python_file(query_path) if query_path.exists() else None
    if query_tree is not None:
        query_method = _find_class_method(
            query_tree,
            "QueryStateCommandService",
            "handle_query_state",
        )
        data_branch = (
            _find_query_branch(query_method, "data_lists")
            if query_method is not None
            else None
        )
        label_target_branch = (
            _find_query_branch(query_method, "label_import_targets")
            if query_method is not None
            else None
        )
        if data_branch is None:
            violations.append(
                "QueryStateCommandService.handle_query_state is missing the "
                "data_lists detached projection."
            )
        else:
            branch_calls = {
                _mutable_boundary_call_name(node.func)
                for node in ast.walk(data_branch)
                if isinstance(node, ast.Call)
            }
            violations.extend(
                f"data_lists must use DatasetStateService.{required_call}()."
                for required_call in (
                    "get_loaded_data_rows",
                    "get_preprocessed_data_rows",
                )
                if required_call not in branch_calls
            )
            if any(
                isinstance(node, ast.Attribute) and node.attr == "include_objects"
                for node in ast.walk(data_branch)
            ):
                violations.append(
                    "data_lists must not expose an include_objects opt-in."
                )
            forbidden_keys = {
                node.value
                for node in ast.walk(data_branch)
                if isinstance(node, ast.Constant)
                and node.value in {"loaded_data_list", "preprocessed_data_list"}
            }
            if forbidden_keys:
                violations.append(
                    "data_lists must not publish mutable object key(s): "
                    f"{', '.join(sorted(forbidden_keys))}."
                )
        if label_target_branch is None:
            violations.append(
                "QueryStateCommandService.handle_query_state is missing the "
                "label_import_targets detached projection."
            )
        elif not any(
            isinstance(node, ast.Call)
            and _mutable_boundary_call_name(node.func) == "get_label_import_target_rows"
            for node in ast.walk(label_target_branch)
        ):
            violations.append(
                "label_import_targets must use DatasetStateService."
                "get_label_import_target_rows()."
            )

    for relative_path in (
        Path("XBrainLab/ui/components/info_panel_service.py"),
        Path("XBrainLab/ui/main_window.py"),
        Path("XBrainLab/ui/panels/dataset/panel.py"),
        Path("XBrainLab/ui/panels/dataset/sidebar.py"),
    ):
        ui_path = root_dir / relative_path
        ui_tree = _parse_python_file(ui_path) if ui_path.exists() else None
        if ui_tree is None:
            continue
        for node in ast.walk(ui_tree):
            if not (
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func) == "QueryStateCommand"
                and _query_state_call_name(node) == "data_lists"
            ):
                continue
            if any(keyword.arg == "include_objects" for keyword in node.keywords):
                violations.append(
                    f"{relative_path}:{node.lineno} data_lists UI query must not "
                    "request mutable objects."
                )

    panel_path = root_dir / "XBrainLab/ui/panels/dataset/panel.py"
    panel_tree = _parse_python_file(panel_path) if panel_path.exists() else None
    if panel_tree is not None:
        panel_class = next(
            (
                node
                for node in panel_tree.body
                if isinstance(node, ast.ClassDef) and node.name == "DatasetPanel"
            ),
            None,
        )
        if panel_class is not None:
            for node in ast.walk(panel_class):
                if not (
                    isinstance(node, ast.Call)
                    and _mutable_boundary_call_name(node.func) == "setData"
                    and node.args
                    and isinstance(node.args[0], (ast.Name, ast.Attribute))
                    and _ast_identifier(node.args[0]) == "UserRole"
                ):
                    continue
                violations.append(
                    f"{panel_path.relative_to(root_dir)}:{node.lineno} Dataset "
                    "table must store detached row identity, not UserRole objects."
                )

    label_coordinator_path = (
        root_dir / "XBrainLab/ui/panels/dataset/external_label_import_coordinator.py"
    )
    label_coordinator_tree = (
        _parse_python_file(label_coordinator_path)
        if label_coordinator_path.exists()
        else None
    )
    if label_coordinator_tree is not None:
        circular_host_methods = {
            "_build_label_import_plan",
            "_execute_label_import_async",
            "_filter_events_for_import",
            "_get_target_files_for_import",
            "_offer_label_recipe_save",
            "_smart_filter_suggestions_for_import",
            "_target_files_from_table_rows",
            "_target_index_for_filter_suggestion",
        }
        for node in ast.walk(label_coordinator_tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
                and node.func.value.attr == "_host"
                and node.func.attr in circular_host_methods
            ):
                violations.append(
                    f"{label_coordinator_path.relative_to(root_dir)}:{node.lineno} "
                    f"round-trips '{node.func.attr}' through its host; call the "
                    "coordinator-owned workflow method directly."
                )
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "self"
                and node.value.attr == "_host"
                and node.attr == "_last_target_file_indices"
            ) or (
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func) == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "_last_target_file_indices"
            ):
                violations.append(
                    f"{label_coordinator_path.relative_to(root_dir)}:"
                    f"{getattr(node, 'lineno', 0)} stores label target selection on "
                    "the host; ExternalLabelImportCoordinator must own it."
                )
        target_method = _find_class_method(
            label_coordinator_tree,
            "ExternalLabelImportCoordinator",
            "target_files_from_table_rows",
        )
        if target_method is None:
            violations.append(
                "ExternalLabelImportCoordinator is missing detached target resolution."
            )
        else:
            for node in ast.walk(target_method):
                if not isinstance(node, ast.Call):
                    continue
                if _mutable_boundary_call_name(node.func) == "item":
                    violations.append(
                        "ExternalLabelImportCoordinator must not recover live EEG "
                        "objects from Dataset table items."
                    )
                if _mutable_boundary_call_name(node.func) == "data" and any(
                    isinstance(child, ast.Attribute) and child.attr == "UserRole"
                    for child in ast.walk(node)
                ):
                    violations.append(
                        "ExternalLabelImportCoordinator must not read UserRole "
                        "payloads as label targets."
                    )
        query_method = _find_class_method(
            label_coordinator_tree,
            "ExternalLabelImportCoordinator",
            "_query_label_import_targets",
        )
        if query_method is None or not any(
            isinstance(node, ast.Call)
            and _mutable_boundary_call_name(node.func) == "QueryStateCommand"
            and _query_state_call_name(node) == "label_import_targets"
            for node in ast.walk(query_method or ast.Pass())
        ):
            violations.append(
                "ExternalLabelImportCoordinator must resolve label targets through "
                "the label_import_targets command query."
            )

    dataset_actions_path = root_dir / "XBrainLab/ui/panels/dataset/actions.py"
    dataset_actions_tree = (
        _parse_python_file(dataset_actions_path)
        if dataset_actions_path.exists()
        else None
    )
    if dataset_actions_tree is not None:
        handler_class = next(
            (
                node
                for node in dataset_actions_tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == "DatasetActionHandler"
            ),
            None,
        )
        if handler_class is not None:
            violations.extend(
                f"{dataset_actions_path.relative_to(root_dir)}:{node.lineno} "
                "stores external-label target selection on DatasetActionHandler; "
                "ExternalLabelImportCoordinator must be the single owner."
                for node in ast.walk(handler_class)
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr == "_last_target_file_indices"
                )
            )

    channel_path = root_dir / "XBrainLab/ui/dialogs/dataset/channel_selection_dialog.py"
    channel_tree = _parse_python_file(channel_path) if channel_path.exists() else None
    if channel_tree is not None:
        constructor = _find_class_method(
            channel_tree,
            "ChannelSelectionDialog",
            "__init__",
        )
        if constructor is not None:
            argument_names = {
                argument.arg
                for argument in (
                    *constructor.args.posonlyargs,
                    *constructor.args.args,
                    *constructor.args.kwonlyargs,
                )
            }
            if argument_names & {"data", "data_list", "loaded_data_list", "raw_data"}:
                violations.append(
                    "ChannelSelectionDialog must accept detached channel names, "
                    "not loaded EEG objects."
                )

    rereference_path = (
        root_dir / "XBrainLab/ui/dialogs/preprocess/rereference_dialog.py"
    )
    rereference_tree = (
        _parse_python_file(rereference_path) if rereference_path.exists() else None
    )
    if rereference_tree is not None:
        constructor = _find_class_method(
            rereference_tree,
            "RereferenceDialog",
            "__init__",
        )
        if constructor is not None:
            argument_names = {
                argument.arg
                for argument in (
                    *constructor.args.posonlyargs,
                    *constructor.args.args,
                    *constructor.args.kwonlyargs,
                )
            }
            if argument_names & {
                "data",
                "data_list",
                "preprocessed_data",
                "raw_data",
            }:
                violations.append(
                    "RereferenceDialog must accept detached channel names, "
                    "not loaded EEG objects."
                )

    preprocess_render_paths = (
        Path("XBrainLab/ui/panels/preprocess/data_query.py"),
        Path("XBrainLab/ui/panels/preprocess/panel.py"),
        Path("XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py"),
    )
    forbidden_render_calls = {
        "get_loaded_data_list",
        "get_mne",
        "get_preprocessed_data_list",
        "get_sfreq",
        "is_raw",
        "local_result_payload",
        "query_preprocess_render_lists",
    }
    for relative_path in preprocess_render_paths:
        render_path = root_dir / relative_path
        render_tree = _parse_python_file(render_path) if render_path.exists() else None
        if render_tree is None:
            continue
        for node in ast.walk(render_tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _mutable_boundary_call_name(node.func)
            if call_name in forbidden_render_calls:
                violations.append(
                    f"{relative_path}:{node.lineno} Preprocess rendering must not "
                    f"call mutable EEG accessor {call_name}(); use the immutable "
                    "PreprocessRenderPublication."
                )
            if (
                call_name == "QueryStateCommand"
                and _query_state_call_name(node) == "data_lists"
                and any(keyword.arg == "include_objects" for keyword in node.keywords)
            ):
                violations.append(
                    f"{relative_path}:{node.lineno} Preprocess rendering must not "
                    "request mutable data-list objects."
                )
    return violations


def _find_query_branch(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    query_name: str,
) -> ast.If | None:
    for node in ast.walk(method):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        values = {
            child.value
            for child in ast.walk(node.test)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        if query_name in values:
            return node
    return None


def _find_class_method(
    tree: ast.AST,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        return next(
            (
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == method_name
            ),
            None,
        )
    return None


def _query_state_call_name(call: ast.Call) -> str | None:
    if call.args:
        value = _string_constant(call.args[0])
        if value is not None:
            return value
    return next(
        (
            _string_constant(keyword.value)
            for keyword in call.keywords
            if keyword.arg == "query"
        ),
        None,
    )


def _ast_identifier(node: ast.Name | ast.Attribute) -> str:
    return node.id if isinstance(node, ast.Name) else node.attr


def check_dataset_split_publication_boundary(root_dir: Path) -> list[str]:
    """Keep dataset-splitting UI on detached, generation-bound publications."""
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return []

    violations: list[str] = []
    reported: set[tuple[str, int, str]] = set()
    split_ui_paths = {
        Path("XBrainLab/ui/panels/training/sidebar.py"),
        Path("XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py"),
        Path("XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py"),
    }
    inspected_paths = [*sorted(product_dir.rglob("*.py"))]
    capture_path = root_dir / "scripts/dev/capture_ui_polish_surfaces.py"
    if capture_path.exists():
        inspected_paths.append(capture_path)

    def record(relative: str, line: int, kind: str, message: str) -> None:
        key = (relative, line, kind)
        if key in reported:
            return
        reported.add(key)
        violations.append(f"{relative}:{line} {message}")

    for path in inspected_paths:
        tree = _parse_python_file(path)
        if tree is None:
            continue
        relative_path = path.relative_to(root_dir)
        relative = relative_path.as_posix()

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and node.value == "dataset_generation_context"
            ):
                record(
                    relative,
                    node.lineno,
                    "retired_query",
                    "dataset_generation_context is retired; use the typed "
                    "DatasetSplitContext publication.",
                )

            if isinstance(node, ast.Call):
                called_name = _call_name(node.func)
                if called_name == "DataSplittingDialog" and len(node.args) > 1:
                    record(
                        relative,
                        node.lineno,
                        "dialog_controller",
                        "DataSplittingDialog must receive detached keyword context, "
                        "not a controller positional argument.",
                    )
                if called_name == "DataSplittingPreviewDialog" and len(node.args) > 2:
                    record(
                        relative,
                        node.lineno,
                        "preview_live_context",
                        "DataSplittingPreviewDialog must receive detached keyword "
                        "context and preview callbacks.",
                    )

        if relative_path not in split_ui_paths:
            continue

        init_method = (
            _find_class_method(tree, "DataSplittingDialog", "__init__")
            if relative_path
            == Path("XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py")
            else None
        )
        if init_method is not None and any(
            argument.arg == "controller"
            for argument in _function_arguments(init_method)
        ):
            record(
                relative,
                init_method.lineno,
                "controller_parameter",
                "DataSplittingDialog must not accept a controller parameter.",
            )

        boundary_roots: tuple[ast.AST, ...]
        if relative_path == Path("XBrainLab/ui/panels/training/sidebar.py"):
            boundary_roots = tuple(
                method
                for method_name in ("split_data", "_data_splitting_dialog_context")
                if (
                    method := _find_class_method(
                        tree,
                        "TrainingSidebar",
                        method_name,
                    )
                )
                is not None
            )
        else:
            boundary_roots = (tree,)

        for node in (
            candidate
            for boundary_root in boundary_roots
            for candidate in ast.walk(boundary_root)
        ):
            live_name: str | None = None
            if isinstance(node, (ast.Name, ast.Attribute)):
                candidate = _ast_identifier(node)
                if candidate in {"epoch_data", "dataset_generator", "datasets"}:
                    live_name = candidate
                elif candidate == "local_result_payload":
                    record(
                        relative,
                        node.lineno,
                        "local_result_payload",
                        "dataset-splitting UI must not use local_result_payload.",
                    )
            elif isinstance(node, ast.Constant) and node.value in {
                "epoch_data",
                "dataset_generator",
                "datasets",
            }:
                live_name = str(node.value)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name.rsplit(".", 1)[-1] == "local_result_payload":
                        record(
                            relative,
                            node.lineno,
                            "local_result_payload",
                            "dataset-splitting UI must not use local_result_payload.",
                        )
            if live_name is not None:
                record(
                    relative,
                    getattr(node, "lineno", 0),
                    f"live_{live_name}",
                    f"dataset-splitting UI must not access live {live_name}; use "
                    "detached split publications.",
                )

    return sorted(violations)


def check_epoch_dialog_publication_boundary(root_dir: Path) -> list[str]:
    """Keep Time Epoching UI on one detached ApplicationService context."""
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return []

    violations: list[str] = []
    reported: set[tuple[str, int, str]] = set()
    sidebar_path = Path("XBrainLab/ui/panels/preprocess/sidebar.py")
    dialog_path = Path("XBrainLab/ui/dialogs/preprocess/epoching_dialog.py")
    inspected_paths = [*sorted(product_dir.rglob("*.py"))]
    capture_paths = (
        root_dir / "scripts/dev/capture_epoching_dialog.py",
        root_dir / "scripts/dev/capture_ui_polish_surfaces.py",
    )
    inspected_paths.extend(path for path in capture_paths if path.exists())

    def record(relative: str, line: int, kind: str, message: str) -> None:
        key = (relative, line, kind)
        if key in reported:
            return
        reported.add(key)
        violations.append(f"{relative}:{line} {message}")

    for path in inspected_paths:
        tree = _parse_python_file(path)
        if tree is None:
            continue
        relative_path = path.relative_to(root_dir)
        relative = relative_path.as_posix()

        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_preprocessed_data_list_for_epoching"
            ):
                record(
                    relative,
                    node.lineno,
                    "retired_live_query",
                    "_preprocessed_data_list_for_epoching is retired; use the "
                    "typed EpochDialogContext publication.",
                )
            if isinstance(node, ast.Call):
                called_name = _call_name(node.func)
                if called_name == "EpochingDialog" and len(node.args) > 1:
                    record(
                        relative,
                        node.lineno,
                        "positional_live_data",
                        "EpochingDialog must receive detached epoch_context by "
                        "keyword, not a live data positional argument.",
                    )

        if relative_path == dialog_path:
            init_method = _find_class_method(tree, "EpochingDialog", "__init__")
            if init_method is not None and any(
                argument.arg in {"data", "data_list", "preprocessed_data_list"}
                for argument in _function_arguments(init_method)
            ):
                record(
                    relative,
                    init_method.lineno,
                    "live_data_parameter",
                    "EpochingDialog must not accept live EEG data parameters.",
                )
            for node in ast.walk(tree):
                identifier = (
                    _ast_identifier(node)
                    if isinstance(node, (ast.Name, ast.Attribute))
                    else None
                )
                if identifier in {
                    "data_list",
                    "preprocessed_data_list",
                    "build_epoching_context",
                }:
                    record(
                        relative,
                        getattr(node, "lineno", 0),
                        f"live_{identifier}",
                        "EpochingDialog must render the detached epoch_context "
                        "without reading or deriving from live EEG objects.",
                    )

        if relative_path == sidebar_path:
            open_epoching = _find_class_method(
                tree,
                "PreprocessSidebar",
                "open_epoching",
            )
            if open_epoching is None:
                continue
            for node in ast.walk(open_epoching):
                identifier = (
                    _ast_identifier(node)
                    if isinstance(node, (ast.Name, ast.Attribute))
                    else None
                )
                if identifier in {
                    "data_list",
                    "preprocessed_data_list",
                    "local_result_payload",
                }:
                    record(
                        relative,
                        getattr(node, "lineno", 0),
                        f"live_{identifier}",
                        "PreprocessSidebar.open_epoching must use only the typed "
                        "detached EpochDialogContext.",
                    )
                if isinstance(node, ast.keyword) and (
                    node.arg == "include_objects"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is True
                ):
                    record(
                        relative,
                        node.lineno,
                        "include_objects",
                        "PreprocessSidebar.open_epoching must not request live "
                        "application objects.",
                    )

    return sorted(violations)


def check_mutable_object_boundaries(
    root_dir: Path,
    *,
    validate_allowlist: bool = False,
) -> list[str]:
    """Freeze current process-local object crossings without removing them yet."""
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return []

    uses: list[_MutableObjectBoundaryUse] = []
    for py_file in sorted(product_dir.rglob("*.py")):
        tree = _parse_python_file(py_file)
        if tree is None:
            continue
        relative_path = py_file.relative_to(root_dir).as_posix()
        visitor = _MutableObjectBoundaryVisitor(relative_path)
        visitor.visit(tree)
        uses.extend(visitor.uses)

    uses.sort(
        key=lambda use: (
            use.path,
            use.lineno,
            use.col_offset,
            use.boundary,
            use.form,
            use.detail,
        )
    )
    allowed_counts = {
        (debt.path, debt.symbol, debt.boundary, debt.form): debt.allowed_occurrences
        for debt in MUTABLE_OBJECT_BOUNDARY_DEBT_ALLOWLIST
    }
    observed_counts: dict[tuple[str, str, str, str], int] = {}
    violations: list[str] = []
    for use in uses:
        key = use.allowlist_key
        occurrence = observed_counts.get(key, 0) + 1
        observed_counts[key] = occurrence
        if occurrence <= allowed_counts.get(key, 0):
            continue
        label = _MUTABLE_BOUNDARY_LABELS[use.boundary]
        violations.append(
            f"{use.path}:{use.lineno} [{use.symbol}] {label} is not allowlisted: "
            f"{use.detail}"
        )

    if validate_allowlist:
        for debt in MUTABLE_OBJECT_BOUNDARY_DEBT_ALLOWLIST:
            key = (debt.path, debt.symbol, debt.boundary, debt.form)
            observed = observed_counts.get(key, 0)
            if observed == debt.allowed_occurrences:
                continue
            label = _MUTABLE_BOUNDARY_LABELS[debt.boundary]
            violations.append(
                f"{debt.path} [{debt.symbol}] stale {label} allowlist entry "
                f"({debt.form}): expected {debt.allowed_occurrences}, found {observed}"
            )
    return violations


class _MutableObjectBoundaryVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.uses: list[_MutableObjectBoundaryUse] = []
        self._symbol_stack: list[str] = []
        self._handled_token_nodes: set[int] = set()
        self._is_ui = relative_path.startswith("XBrainLab/ui/")

    @property
    def _symbol(self) -> str:
        return ".".join(self._symbol_stack) or "<module>"

    def _record(
        self,
        node: ast.AST,
        boundary: str,
        form: str,
        detail: str,
        *,
        symbol: str | None = None,
    ) -> None:
        self.uses.append(
            _MutableObjectBoundaryUse(
                path=self.relative_path,
                symbol=symbol or self._symbol,
                boundary=boundary,
                form=form,
                lineno=getattr(node, "lineno", 0),
                col_offset=getattr(node, "col_offset", 0),
                detail=detail,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol_stack.append(node.name)
        self.generic_visit(node)
        self._symbol_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        symbol = ".".join([*self._symbol_stack, node.name])
        if node.name == "local_payload":
            self._record(
                node,
                MUTABLE_BOUNDARY_LOCAL_PAYLOAD,
                "definition",
                "defined local_payload",
                symbol=symbol,
            )
        elif node.name == "local_result_payload":
            self._record(
                node,
                MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
                "definition",
                "defined local_result_payload",
                symbol=symbol,
            )
        self._symbol_stack.append(node.name)
        self.generic_visit(node)
        self._symbol_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        self._record_boundary_imports(node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._record_boundary_imports(node)
        self.generic_visit(node)

    def _record_boundary_imports(self, node: ast.Import | ast.ImportFrom) -> None:
        for alias in node.names:
            imported_name = alias.name.rsplit(".", 1)[-1]
            if imported_name == "local_payload":
                boundary = MUTABLE_BOUNDARY_LOCAL_PAYLOAD
            elif imported_name == "local_result_payload":
                boundary = MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD
            else:
                continue
            self._record(
                node,
                boundary,
                "import",
                f"imported {imported_name}",
            )

    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg == "include_objects":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                    "keyword",
                    ast.unparse(node),
                )

        called_name = _mutable_boundary_call_name(node.func)
        if called_name in {"local_payload", "local_result_payload"}:
            boundary = (
                MUTABLE_BOUNDARY_LOCAL_PAYLOAD
                if called_name == "local_payload"
                else MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD
            )
            self._record(node, boundary, "call", ast.unparse(node))
            self._handled_token_nodes.add(id(node.func))
        elif called_name == "getattr" and len(node.args) >= 2:
            attribute_name = _string_constant(node.args[1])
            if attribute_name == "runtime":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME,
                    "getattr",
                    ast.unparse(node),
                )
            elif attribute_name in {"local_payload", "local_result_payload"}:
                boundary = (
                    MUTABLE_BOUNDARY_LOCAL_PAYLOAD
                    if attribute_name == "local_payload"
                    else MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD
                )
                self._record(node, boundary, "getattr", ast.unparse(node))

        if self._is_ui and _is_ui_backend_domain_storage_call(node):
            self._record(
                node,
                MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
                "widget_or_container",
                ast.unparse(node),
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if id(node) not in self._handled_token_nodes:
            if node.attr == "include_objects":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                    "attribute",
                    ast.unparse(node),
                )
            elif node.attr == "local_payload":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_LOCAL_PAYLOAD,
                    "attribute",
                    ast.unparse(node),
                )
            elif node.attr == "local_result_payload":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
                    "attribute",
                    ast.unparse(node),
                )
            elif node.attr == "runtime":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME,
                    "attribute",
                    ast.unparse(node),
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and id(node) not in self._handled_token_nodes:
            if node.id == "include_objects":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                    "name",
                    node.id,
                )
            elif node.id == "local_payload":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_LOCAL_PAYLOAD,
                    "name",
                    node.id,
                )
            elif node.id == "local_result_payload":
                self._record(
                    node,
                    MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
                    "name",
                    node.id,
                )
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        if node.arg == "include_objects":
            self._record(
                node,
                MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                "parameter",
                "parameter include_objects",
            )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id == "include_objects":
            self._record(
                node,
                MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                "field",
                ast.unparse(node),
            )
        self._record_ui_storage_assignment(node, [node.target], node.value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_ui_storage_assignment(node, node.targets, node.value)
        self.generic_visit(node)

    def _record_ui_storage_assignment(
        self,
        node: ast.Assign | ast.AnnAssign,
        targets: list[ast.expr],
        value: ast.expr | None,
    ) -> None:
        if not self._is_ui or value is None:
            return
        if any(
            _is_ui_backend_domain_storage_assignment(target, value)
            for target in targets
        ):
            self._record(
                node,
                MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
                "assignment",
                ast.unparse(node),
            )

    def visit_Constant(self, node: ast.Constant) -> None:
        if node.value == "include_objects":
            self._record(
                node,
                MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
                "literal",
                repr(node.value),
            )
        self.generic_visit(node)


def _mutable_boundary_call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_ui_backend_domain_storage_assignment(
    target: ast.expr,
    value: ast.expr,
) -> bool:
    target_attribute = _self_owned_attribute_name(target)
    if target_attribute is None:
        return False
    if (
        target_attribute.endswith(("application_query", "command_result"))
        and isinstance(value, ast.Name)
        and value.id in {"result", "command_result"}
    ):
        return True
    return _expression_is_backend_domain_object(value)


def _self_owned_attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Subscript):
        return _self_owned_attribute_name(node.value)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _is_ui_backend_domain_storage_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    call_name = node.func.attr
    if call_name == "addItem" and len(node.args) >= 2:
        return _expression_is_backend_domain_object(node.args[1])
    if call_name in {"setData", "setItemData"} and len(node.args) >= 2:
        return any(
            _expression_is_backend_domain_object(argument) for argument in node.args[1:]
        )
    if call_name in {"append", "extend", "insert", "update"}:
        if _self_owned_attribute_name(node.func.value) is None:
            return False
        return any(_expression_is_backend_domain_object(arg) for arg in node.args)
    return False


def _expression_is_backend_domain_object(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return _is_backend_domain_object_name(node.id)
    if isinstance(node, ast.Attribute):
        return _is_backend_domain_object_name(node.attr)
    if isinstance(node, ast.Subscript):
        if _expression_is_backend_domain_object(node.value):
            return True
        return _string_constant(node.slice) in _BACKEND_DOMAIN_RESULT_KEYS
    if isinstance(node, ast.IfExp):
        return _expression_is_backend_domain_object(
            node.body
        ) or _expression_is_backend_domain_object(node.orelse)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(_expression_is_backend_domain_object(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return any(
            value is not None and _expression_is_backend_domain_object(value)
            for value in node.values
        )
    if isinstance(node, ast.DictComp):
        return _expression_is_backend_domain_object(node.value) or any(
            _expression_is_backend_domain_object(generator.iter)
            for generator in node.generators
        )
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return _expression_is_backend_domain_object(node.elt) or any(
            _expression_is_backend_domain_object(generator.iter)
            for generator in node.generators
        )
    if not isinstance(node, ast.Call):
        return False

    call_name = _mutable_boundary_call_name(node.func)
    if call_name in _BACKEND_DOMAIN_RETURNING_CALLS:
        return True
    if call_name in {"dict", "list", "set", "tuple"}:
        return any(_expression_is_backend_domain_object(arg) for arg in node.args)
    if call_name == "get" and node.args:
        return _string_constant(node.args[0]) in _BACKEND_DOMAIN_RESULT_KEYS
    return False


def _is_backend_domain_object_name(name: str) -> bool:
    return name in _BACKEND_DOMAIN_OBJECT_NAMES or name.endswith(
        _BACKEND_DOMAIN_OBJECT_SUFFIXES
    )


def _reads_private_application_service_cache(node: ast.AST) -> bool:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr == "_application_service"
    ):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "_application_service"
    )


def _writes_private_application_service_cache(node: ast.AST) -> bool:
    targets: list[ast.AST]
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        targets = []
    if any(
        isinstance(target, ast.Attribute) and target.attr == "_application_service"
        for root in targets
        for target in ast.walk(root)
    ):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"setattr", "delattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "_application_service"
    )


def _declares_application_service_cache_storage(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Attribute)
        and isinstance(node.target.value, ast.Name)
        and node.target.value.id == "self"
        and node.target.attr == "_application_service"
        and isinstance(node.value, ast.Constant)
        and node.value.value is None
    )


def _imports_application_service_runtime(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(
            alias.name == "XBrainLab.backend.application.runtime"
            for alias in node.names
        )
    if not isinstance(node, ast.ImportFrom):
        return False
    module = node.module or ""
    if module in {
        "runtime",
        "application.runtime",
        "XBrainLab.backend.application.runtime",
    }:
        return True
    return module in {
        "application",
        "XBrainLab.backend.application",
    } and any(alias.name == "get_application_service" for alias in node.names)


def _calls_application_service_locator(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id == "get_application_service")
        or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_application_service"
        )
    )


def check_product_runtime_mock_dependencies(root_dir: Path) -> list[str]:
    """Reject product behavior that branches on unittest.mock objects."""
    violations: list[str] = []
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return violations

    for py_file in product_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            imports_mock = False
            if isinstance(node, ast.ImportFrom):
                imports_mock = node.module == "unittest.mock"
            elif isinstance(node, ast.Import):
                imports_mock = any(
                    alias.name == "unittest.mock" for alias in node.names
                )
            if imports_mock:
                violations.append(
                    f"{py_file.relative_to(root_dir)}:"
                    f"{getattr(node, 'lineno', 0)} imports "
                    "unittest.mock; product contracts must use explicit protocols "
                    "and tests must inject conforming fakes."
                )
    return violations


def check_mapped_real_tool_command_ownership(root_dir: Path) -> list[str]:
    """Keep mapped Real adapters behind the canonical application tool surface."""
    violations: list[str] = []
    canonical_delegate_names = {
        "execute_application_tool_command",
        "execute_real_application_tool",
    }

    for relative_path in MAPPED_REAL_TOOL_FILES:
        path = root_dir / relative_path
        if not path.exists():
            continue
        tree = _parse_python_file(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported_name = alias.name.rsplit(".", 1)[-1]
                    if imported_name == "get_application_service" or (
                        imported_name.endswith("Command") and imported_name != "Command"
                    ):
                        violations.append(
                            f"{relative_path}:{node.lineno} imports {imported_name}; "
                            "application_surface.py exclusively owns mapped command "
                            "translation and service resolution."
                        )
                    if imported_name.startswith("build_") and imported_name.endswith(
                        "_command"
                    ):
                        violations.append(
                            f"{relative_path}:{node.lineno} imports {imported_name}; "
                            "mapped Real adapters must delegate the complete parameter "
                            "translation to the canonical application surface."
                        )

            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if call_name == "get_application_service":
                violations.append(
                    f"{relative_path}:{node.lineno} resolves ApplicationService "
                    "directly; mapped Real adapters must delegate through the "
                    "canonical application surface/runtime."
                )
            elif call_name == "execute":
                violations.append(
                    f"{relative_path}:{node.lineno} calls service.execute() directly; "
                    "application_surface.py owns mapped command execution."
                )
            elif call_name.endswith("Command") and call_name != "Command":
                violations.append(
                    f"{relative_path}:{node.lineno} constructs {call_name}; "
                    "application_surface.py exclusively owns mapped command "
                    "translation."
                )
            elif call_name.startswith("build_") and call_name.endswith("_command"):
                violations.append(
                    f"{relative_path}:{node.lineno} calls {call_name}; mapped Real "
                    "adapters must delegate the complete parameter translation."
                )

        for class_node in (
            node for node in tree.body if isinstance(node, ast.ClassDef)
        ):
            if class_node.name not in CANONICAL_DELEGATING_REAL_TOOL_CLASSES:
                continue
            execute_method = next(
                (
                    node
                    for node in class_node.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "execute"
                ),
                None,
            )
            if execute_method is None:
                continue
            call_names = _function_call_names(execute_method)
            if call_names.isdisjoint(canonical_delegate_names):
                violations.append(
                    f"{relative_path}:{execute_method.lineno} "
                    f"{class_node.name}.execute() does not delegate to the canonical "
                    "application tool surface/runtime."
                )

            for call in (
                node for node in ast.walk(execute_method) if isinstance(node, ast.Call)
            ):
                call_name = _call_name(call.func)
                qualified_call = ast.unparse(call.func)
                if call_name.startswith("normalize_"):
                    violations.append(
                        f"{relative_path}:{call.lineno} {class_node.name}.execute() "
                        f"calls {call_name}; input normalization belongs to "
                        "application_surface.py."
                    )
                if qualified_call.startswith("os.") or call_name == "Path":
                    violations.append(
                        f"{relative_path}:{call.lineno} {class_node.name}.execute() "
                        "performs local path translation; path expansion belongs to "
                        "application_surface.py."
                    )

    stale_test_targets = tuple(
        f"XBrainLab.llm.tools.real.{module_name}.get_application_service"
        for module_name in (
            "preprocess_real",
            "training_real",
        )
    )
    excluded_guard_tests = {
        Path("tests/architecture_compliance.py"),
        Path("tests/unit/test_architecture_compliance.py"),
    }
    tests_root = root_dir / "tests"
    if tests_root.exists():
        for path in tests_root.rglob("*.py"):
            relative_path = path.relative_to(root_dir)
            if relative_path in excluded_guard_tests:
                continue
            tree = _parse_python_file(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(
                    node.value,
                    str,
                ):
                    continue
                if node.value in stale_test_targets:
                    violations.append(
                        f"{relative_path}:{node.lineno} patches {node.value}; "
                        "mapped Real-tool tests must inject the canonical "
                        "ApplicationSurface/runtime boundary."
                    )

    return violations


def check_concrete_llm_tool_result_contracts(root_dir: Path) -> list[str]:
    """Reject concrete assistant tools that expose stringly execute results."""
    violations: list[str] = []
    tools_root = root_dir / "XBrainLab" / "llm" / "tools"
    allowed_markers = ("ToolResult", "UiRequest", "ToolExecutionResult")

    for implementation_dir in (tools_root / "real", tools_root / "mock"):
        if not implementation_dir.exists():
            continue
        for path in implementation_dir.glob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef) or node.name != "execute":
                    continue
                annotation = ast.unparse(node.returns) if node.returns else ""
                if not any(marker in annotation for marker in allowed_markers):
                    violations.append(
                        f"{path.relative_to(root_dir)}:{node.lineno} concrete execute "
                        "must return ToolResult or UiRequest, not an implicit/string result."
                    )
                for child in ast.walk(node):
                    if not isinstance(child, ast.Return):
                        continue
                    if isinstance(child.value, (ast.Constant, ast.JoinedStr)) and (
                        isinstance(child.value, ast.JoinedStr)
                        or isinstance(child.value.value, str)
                    ):
                        violations.append(
                            f"{path.relative_to(root_dir)}:{child.lineno} returns raw "
                            "text from execute; wrap it in ToolResult."
                        )
    return violations


def check_typed_agent_confirmation_boundary(root_dir: Path) -> list[str]:
    """Reject boolean and stringly assistant confirmation product boundaries."""
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return []

    violations: list[str] = []
    for path in product_dir.rglob("*.py"):
        tree = _parse_python_file(path)
        if tree is None:
            continue
        relative = path.relative_to(root_dir)
        reported: set[tuple[int, str]] = set()

        for node in ast.walk(tree):
            signal_name = _boolean_confirmation_signal_name(node)
            if signal_name is not None:
                key = (getattr(node, "lineno", 0), "boolean_signal")
                if key not in reported:
                    reported.add(key)
                    violations.append(
                        f"{relative}:{key[0]} declares confirmation signal "
                        f"{signal_name!r} as pyqtSignal(bool); emit a typed "
                        "AgentConfirmationRequest instead."
                    )

            if _uses_legacy_on_user_confirmed(node):
                key = (getattr(node, "lineno", 0), "legacy_callback")
                if key not in reported:
                    reported.add(key)
                    violations.append(
                        f"{relative}:{key[0]} uses legacy on_user_confirmed; "
                        "consume a correlated AgentConfirmationResolution instead."
                    )

            if isinstance(node, ast.Constant) and node.value == "confirm_action":
                key = (getattr(node, "lineno", 0), "legacy_payload")
                if key not in reported:
                    reported.add(key)
                    violations.append(
                        f"{relative}:{key[0]} uses legacy confirm_action payload; "
                        "emit an AgentConfirmationRequest object instead."
                    )

            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name == "on_user_confirmed":
                continue
            if not _is_confirmation_resolution_handler(node.name):
                continue
            for argument in _function_arguments(node):
                if argument.arg in {"self", "cls"}:
                    continue
                if not _annotation_contains_bool(argument.annotation):
                    continue
                key = (node.lineno, "boolean_handler")
                if key in reported:
                    break
                reported.add(key)
                violations.append(
                    f"{relative}:{node.lineno} confirmation handler {node.name!r} "
                    f"accepts boolean parameter {argument.arg!r}; pass a typed "
                    "AgentConfirmationResolution instead."
                )
                break

    return violations


def check_pending_interaction_compatibility_api(root_dir: Path) -> list[str]:
    """Reject test-only pending-state APIs and direct legacy test access."""
    violations: list[str] = []

    for relative_path in PENDING_INTERACTION_RUNTIME_FILES:
        path = root_dir / relative_path
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in PENDING_INTERACTION_COMPATIBILITY_MEMBERS:
                continue
            violations.append(
                f"{relative_path}:{node.lineno} defines test-only pending "
                f"interaction compatibility API {node.name}(); use "
                "PendingInteractionCoordinator's typed begin/resolve/clear contract."
            )

    test_paths: list[Path] = []
    for relative_root in PENDING_INTERACTION_TEST_ROOTS:
        test_root = root_dir / relative_root
        if test_root.exists():
            test_paths.extend(test_root.rglob("*.py"))
    test_paths.extend(
        root_dir / relative_path
        for relative_path in PENDING_INTERACTION_TEST_FILES
        if (root_dir / relative_path).exists()
    )
    for path in sorted(set(test_paths)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        relative_path = path.relative_to(root_dir)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in PENDING_INTERACTION_COMPATIBILITY_MEMBERS:
                continue
            violations.append(
                f"{relative_path}:{node.lineno} accesses legacy pending field "
                f"{node.attr}; use the controller's PendingInteractionCoordinator "
                "and its typed public contract."
            )

    return violations


def check_agent_controller_lifecycle_aliases(root_dir: Path) -> list[str]:
    """Reject lifecycle state stored on ``LLMController`` compatibility aliases."""
    violations: list[str] = []
    controller_path = root_dir / "XBrainLab" / "llm" / "agent" / "controller.py"
    paths = [controller_path]
    tests_dir = root_dir / "tests"
    if tests_dir.exists():
        paths.extend(sorted(tests_dir.rglob("*.py")))

    for path in paths:
        if not path.exists():
            continue
        tree, syntax_violation = _parse_product_guard_tree(
            path,
            root_dir,
            guard_name="agent controller lifecycle ownership",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None
        visitor = _LegacyAgentControllerLifecycleVisitor(
            inspect_all_self_accesses=path == controller_path
        )
        visitor.visit(tree)
        relative_path = path.relative_to(root_dir)
        violations.extend(
            f"{relative_path}:{line}: legacy LLMController lifecycle alias "
            f"'{attribute}' bypasses its explicit owner"
            for line, attribute in visitor.violations
        )
    return violations


def check_agent_manager_publication_state_ownership(root_dir: Path) -> list[str]:
    """Keep Assistant publication state writable only inside its coordinator."""
    violations: list[str] = []
    manager_path = root_dir / "XBrainLab" / "ui" / "components" / "agent_manager.py"
    paths = [manager_path]
    tests_dir = root_dir / "tests"
    if tests_dir.exists():
        paths.extend(sorted(tests_dir.rglob("*.py")))

    for path in paths:
        if not path.exists():
            continue
        tree = _parse_python_file(path)
        if tree is None:
            continue
        relative_path = path.relative_to(root_dir)
        violations.extend(
            f"{relative_path}:{node.lineno} accesses legacy AgentManager publication "
            f"alias '{node.attr}'; use the publication coordinator contract."
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in LEGACY_AGENT_MANAGER_PUBLICATION_ALIASES
        )

    coordinator_path = (
        root_dir
        / "XBrainLab"
        / "ui"
        / "components"
        / "assistant_application_publication_coordinator.py"
    )
    coordinator_tree = _parse_python_file(coordinator_path)
    if coordinator_tree is not None:
        relative_path = coordinator_path.relative_to(root_dir)
        violations.extend(
            f"{relative_path}:{node.lineno} exposes writable publication state "
            f"'{node.attr}'; keep storage private and expose a read-only snapshot."
            for node in ast.walk(coordinator_tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr in PUBLIC_ASSISTANT_PUBLICATION_STATE_FIELDS
        )
    return violations


class _LegacyAgentControllerLifecycleVisitor(ast.NodeVisitor):
    """Find old controller fields without flagging AgentWorker internals."""

    def __init__(self, *, inspect_all_self_accesses: bool) -> None:
        self._inspect_all_self_accesses = inspect_all_self_accesses
        self._controller_class_depth = 0
        self.violations: list[tuple[int, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_controller = node.name.endswith("Controller")
        if is_controller:
            self._controller_class_depth += 1
        self.generic_visit(node)
        if is_controller:
            self._controller_class_depth -= 1

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            node.attr in LEGACY_AGENT_CONTROLLER_LIFECYCLE_ATTRIBUTES
            and self._is_controller_receiver(node.value)
        ):
            self.violations.append((node.lineno, node.attr))
        self.generic_visit(node)

    def _is_controller_receiver(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            if node.id == "self":
                return (
                    self._inspect_all_self_accesses or self._controller_class_depth > 0
                )
            normalized = node.id.lstrip("_").lower()
            return normalized == "ctrl" or normalized.endswith("controller")
        return isinstance(node, ast.Attribute) and node.attr in {
            "controller",
            "agent_controller",
        }


def check_agent_confirmation_contract_evidence(root_dir: Path) -> list[str]:
    """Require tests to prove typed request/resolution correlation semantics."""
    violations: list[str] = []
    contract_path = root_dir / "XBrainLab" / "llm" / "agent" / "confirmation.py"
    evidence_path = root_dir / AGENT_CONFIRMATION_CONTRACT_EVIDENCE

    if contract_path.exists() and not evidence_path.exists():
        violations.append(
            f"{AGENT_CONFIRMATION_CONTRACT_EVIDENCE} is missing; typed confirmation "
            "requires dedicated correlated request/resolution evidence."
        )

    for relative in LLM_AGENT_CONFIRMATION_EXACT_EVIDENCE_TESTS:
        path = root_dir / relative
        tree = _parse_python_file(path)
        if tree is None:
            continue
        violations.extend(
            f"{relative}:{node.lineno} asserts a legacy confirm_action payload; "
            "assert AgentConfirmationRequest and correlated resolution fields."
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == "confirm_action"
        )

    tree = _parse_python_file(evidence_path)
    if tree is None:
        return violations

    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    if not any(
        _is_contract_classmethod_call(
            call,
            owner="AgentConfirmationRequest",
            method="for_action",
        )
        for call in calls
    ):
        violations.append(
            f"{AGENT_CONFIRMATION_CONTRACT_EVIDENCE} must construct an "
            "AgentConfirmationRequest.for_action() request."
        )
    if not any(
        _is_contract_classmethod_call(
            call,
            owner="AgentConfirmationResolution",
            method="for_request",
        )
        for call in calls
    ):
        violations.append(
            f"{AGENT_CONFIRMATION_CONTRACT_EVIDENCE} must construct an "
            "AgentConfirmationResolution.for_request() resolution."
        )

    assertions = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    asserted_fields = {
        child.attr
        for assertion in assertions
        for child in ast.walk(assertion.test)
        if isinstance(child, ast.Attribute)
        and child.attr in AGENT_CONFIRMATION_CORRELATION_FIELDS
    }
    missing_fields = AGENT_CONFIRMATION_CORRELATION_FIELDS - asserted_fields
    if missing_fields:
        violations.append(
            f"{AGENT_CONFIRMATION_CONTRACT_EVIDENCE} must assert all correlation "
            "fields (request_id, params_fingerprint, publication_generation); "
            f"missing: {', '.join(sorted(missing_fields))}."
        )

    match_assertions = [
        assertion
        for assertion in assertions
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "matches"
            for child in ast.walk(assertion.test)
        )
    ]
    has_matching_evidence = any(
        not isinstance(assertion.test, ast.UnaryOp)
        or not isinstance(assertion.test.op, ast.Not)
        for assertion in match_assertions
    )
    has_stale_evidence = any(
        isinstance(assertion.test, ast.UnaryOp)
        and isinstance(assertion.test.op, ast.Not)
        for assertion in match_assertions
    )
    if not has_matching_evidence or not has_stale_evidence:
        violations.append(
            f"{AGENT_CONFIRMATION_CONTRACT_EVIDENCE} must assert matching and stale "
            "AgentConfirmationResolution.matches() behavior."
        )

    return violations


def check_typed_montage_ui_handoff_boundary(root_dir: Path) -> list[str]:
    """Keep montage decisions on the correlated workflow UI handoff path."""
    violations: list[str] = []
    legacy_path = root_dir / LEGACY_MONTAGE_HANDOFF_FILE
    if legacy_path.exists():
        violations.append(
            f"{LEGACY_MONTAGE_HANDOFF_FILE} restores the legacy montage coordinator; "
            "route montage through WorkflowUiHandoffRequest instead."
        )

    product_dir = root_dir / "XBrainLab"
    if product_dir.exists():
        for path in product_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(root_dir)
            violations.extend(
                f"{relative} injects fake user message {message!r}; resolve the "
                "typed montage handoff without starting another user turn."
                for message in LEGACY_MONTAGE_FAKE_USER_MESSAGES
                if message in source
            )

    manager_path = root_dir / MONTAGE_HANDOFF_MANAGER
    if manager_path.exists():
        manager_source = manager_path.read_text(encoding="utf-8")
        violations.extend(
            f"{MONTAGE_HANDOFF_MANAGER} still owns legacy montage symbol "
            f"{symbol!r}; AgentManager must only resolve typed UI handoffs."
            for symbol in LEGACY_MONTAGE_MANAGER_SYMBOLS
            if symbol in manager_source
        )

    controller_path = root_dir / MONTAGE_HANDOFF_CONTROLLER
    host_path = root_dir / MONTAGE_HANDOFF_HOST
    if controller_path.exists() or host_path.exists() or manager_path.exists():
        controller_source = (
            controller_path.read_text(encoding="utf-8")
            if controller_path.exists()
            else ""
        )
        if not all(
            token in controller_source
            for token in (
                "CommandName.APPLY_MONTAGE",
                "WorkflowUiHandoffRequest.for_decision",
                "suggested_values",
            )
        ):
            violations.append(
                f"{MONTAGE_HANDOFF_CONTROLLER} must publish a correlated "
                "APPLY_MONTAGE WorkflowUiHandoffRequest with suggested values."
            )

        host_source = (
            host_path.read_text(encoding="utf-8") if host_path.exists() else ""
        )
        route_source = root_dir / "XBrainLab/llm/agent/ui_handoff.py"
        route_registry_source = (
            route_source.read_text(encoding="utf-8") if route_source.exists() else ""
        )
        registry_has_montage_route = all(
            token in route_registry_source
            for token in (
                "CommandName.APPLY_MONTAGE",
                "WorkflowUiHandoffRouteIdentity.MONTAGE_SETTINGS_DIALOG",
            )
        )
        host_has_montage_adapter = all(
            token in host_source
            for token in (
                "WorkflowUiHandoffRouteIdentity.MONTAGE_SETTINGS_DIALOG",
                "self._open_montage",
                "open_electrode_layout",
                "self._surface_result",
            )
        )
        if not all((registry_has_montage_route, host_has_montage_adapter)):
            violations.append(
                "The canonical Workflow UI route registry and "
                f"{MONTAGE_HANDOFF_HOST} must route APPLY_MONTAGE to the existing "
                "montage surface and return its typed outcome."
            )

    return violations


def _boolean_confirmation_signal_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Assign):
        value = node.value
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        value = node.value
        targets = [node.target]
    else:
        return None
    if not isinstance(value, ast.Call) or _call_name(value.func) != "pyqtSignal":
        return None
    if not any(_annotation_contains_bool(argument) for argument in value.args):
        return None
    target_names = [
        child.id if isinstance(child, ast.Name) else child.attr
        for target in targets
        for child in ast.walk(target)
        if isinstance(child, (ast.Name, ast.Attribute))
    ]
    return next((name for name in target_names if "confirm" in name.lower()), None)


def _uses_legacy_on_user_confirmed(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name == "on_user_confirmed"
    if isinstance(node, ast.Name):
        return node.id == "on_user_confirmed"
    if isinstance(node, ast.Attribute):
        return node.attr == "on_user_confirmed"
    if isinstance(node, ast.alias):
        return (
            node.name.rsplit(".", 1)[-1] == "on_user_confirmed"
            or node.asname == "on_user_confirmed"
        )
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "on_user_confirmed"
    )


def _is_confirmation_resolution_handler(function_name: str) -> bool:
    return function_name in {
        "confirm",
        "handle_confirmation",
        "handle_user_confirmation",
        "on_user_confirmation_resolved",
        "resolve_confirmation",
    } or function_name.endswith("confirmation_resolved")


def _function_arguments(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.arg]:
    arguments = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        arguments.append(node.args.vararg)
    if node.args.kwarg is not None:
        arguments.append(node.args.kwarg)
    return arguments


def _annotation_contains_bool(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    return any(
        (isinstance(node, ast.Name) and node.id == "bool")
        or (isinstance(node, ast.Attribute) and node.attr == "bool")
        or (isinstance(node, ast.Constant) and node.value == "bool")
        for node in ast.walk(annotation)
    )


def _is_contract_classmethod_call(
    call: ast.Call,
    *,
    owner: str,
    method: str,
) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == method
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == owner
    )


def check_product_runtime_backend_facade_usage(root_dir: Path) -> list[str]:
    """Return product runtime code that still enters backend through BackendFacade."""
    violations: list[str] = []

    for relative_dir in PRODUCT_RUNTIME_BACKEND_FACADE_DIRS:
        product_dir = root_dir / relative_dir
        if not product_dir.exists():
            continue
        for py_file in product_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            visitor = _BackendFacadeRuntimeUsageVisitor()
            visitor.visit(tree)
            violations.extend(
                f"{_repo_relative_posix(py_file, root_dir)}:"
                f"{getattr(node, 'lineno', 0)} uses "
                "BackendFacade in product runtime; route through "
                "ApplicationService / Command API directly."
                for node in visitor.violations
            )
    return violations


def check_llm_direct_study_state_reads(root_dir: Path) -> list[str]:
    """Return LLM product code that infers state from mutable Study fields."""
    violations: list[str] = []
    llm_dir = root_dir / "XBrainLab" / "llm"
    if not llm_dir.exists():
        return violations

    for py_file in llm_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            visitor = _DirectStudyStateReadVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{attr.lineno} reads "
                f"study.{attr.attr}; LLM product stage/tool state must come "
                "from the ApplicationService state snapshot."
                for attr in visitor.violations
            )
    return violations


def check_product_success_backend_facade_tests(root_dir: Path) -> list[str]:
    """Return product-success tests that still use BackendFacade as workflow truth."""
    violations: list[str] = []

    for relative_dir in PRODUCT_SUCCESS_BACKEND_FACADE_TEST_DIRS:
        test_dir = root_dir / relative_dir
        if not test_dir.exists():
            continue
        for py_file in test_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            visitor = _BackendFacadeRuntimeUsageVisitor()
            visitor.visit(tree)
            violations.extend(
                f"{_repo_relative_posix(py_file, root_dir)}:"
                f"{getattr(node, 'lineno', 0)} uses "
                "BackendFacade in product-success evidence; rewrite the test to "
                "exercise ApplicationService / Command API, or move compatibility "
                "coverage into explicit facade-only unit tests."
                for node in visitor.violations
            )
    return violations


def check_backend_facade_test_usage(root_dir: Path) -> list[str]:
    """Return tests that still use the removed BackendFacade compatibility API."""
    violations: list[str] = []
    tests_dir = root_dir / "tests"
    if not tests_dir.exists():
        return violations

    for py_file in tests_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        relative_path = _repo_relative_posix(py_file, root_dir)

        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        visitor = _BackendFacadeRuntimeUsageVisitor()
        visitor.visit(tree)
        if not visitor.violations:
            continue
        violations.extend(
            f"{relative_path}:{getattr(node, 'lineno', 0)} uses BackendFacade "
            "after physical facade removal; keep replacement coverage in "
            "ApplicationService / Command API, focused service, helper, or guard "
            "tests instead."
            for node in visitor.violations
        )
    return violations


def check_product_success_direct_study_state_tests(root_dir: Path) -> list[str]:
    """Return product-success tests that use mutable Study state as success truth."""
    violations: list[str] = []

    for relative_file in PRODUCT_SUCCESS_DIRECT_STUDY_STATE_TEST_FILES:
        py_file = root_dir / relative_file
        if not py_file.exists():
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        visitor = _ProductSuccessStudyStateVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{attr.lineno} reads study.{attr.attr} as "
            "product-success evidence; assert ApplicationService / "
            "QueryStateCommand state or UI-visible state instead."
            for attr in visitor.state_reads
        )
        violations.extend(
            f"{relative_file}:{call.lineno} calls study.{_call_name(call.func)}() "
            "as product-success setup/evidence; use ApplicationService query "
            "diagnostics or a command-owned object source instead."
            for call in visitor.study_method_calls
        )
    return violations


def check_headless_verifier_direct_study_state(root_dir: Path) -> list[str]:
    """Return headless product verifiers that bypass command/query state truth."""
    violations: list[str] = []

    for relative_file in HEADLESS_VERIFIER_STATE_TRUTH_FILES:
        py_file = root_dir / relative_file
        if not py_file.exists():
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        state_visitor = _DirectStudyStateReadVisitor()
        state_visitor.visit(tree)
        violations.extend(
            f"{relative_file.as_posix()}:{attr.lineno} reads "
            f"{_study_state_expression(source, attr)}; headless product "
            "verifiers must query state through ApplicationService / "
            "QueryStateCommand."
            for attr in state_visitor.violations
        )

        method_visitor = _DirectStudyMethodCallVisitor(
            HEADLESS_VERIFIER_DIRECT_STUDY_METHODS
        )
        method_visitor.visit(tree)
        violations.extend(
            f"{relative_file.as_posix()}:{call.lineno} calls "
            f"{_study_state_expression(source, call.func)}; headless product "
            "verifiers must use QueryStateCommand for readiness/status, "
            "TrainCommand for training, and StopTrainingCommand for cancellation."
            for call in method_visitor.violations
        )
    return violations


def check_product_success_controller_lookup_assertions(root_dir: Path) -> list[str]:
    """Return integration tests that bless direct Study controller lookup."""
    violations: list[str] = []

    for relative_dir in PRODUCT_SUCCESS_BACKEND_FACADE_TEST_DIRS:
        test_dir = root_dir / relative_dir
        if not test_dir.exists():
            continue
        for py_file in test_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            visitor = _ProductSuccessControllerLookupAssertionVisitor()
            visitor.visit(tree)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} asserts "
                "study.get_controller() lookup as product-success evidence; "
                "use injected controller wiring, ApplicationService / Command API, "
                "or an explicit assert_not_called boundary instead."
                for call in visitor.violations
            )
    return violations


def check_product_tool_envelope_boundary(root_dir: Path) -> list[str]:
    """Keep tolerant model-output parsing outside product execution and scoring."""

    violations: list[str] = []
    scan_roots = (
        root_dir / "XBrainLab",
        root_dir / "scripts" / "agent" / "evals",
    )
    parser_file = root_dir / "XBrainLab" / "llm" / "agent" / "parser.py"
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.py"):
            if path == parser_file:
                continue
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(root_dir)
            if "CommandParser.parse_diagnostic(" in source:
                violations.append(
                    f"{relative} calls tolerant parse_diagnostic(); tolerant parsing "
                    "is restricted to explicit offline migration/diagnostics."
                )
            if "CommandParser.parse(" in source:
                violations.append(
                    f"{relative} calls ambiguous parse(); product execution and "
                    "strict scoring must consume parse_product() status."
                )

    for relative in STRICT_TOOL_ENVELOPE_ENTRYPOINTS:
        path = root_dir / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        if "CommandParser.parse_diagnostic(" in source and not str(relative).startswith(
            "XBrainLab/"
        ):
            violations.append(
                f"{relative} calls tolerant parse_diagnostic(); strict scoring "
                "must consume parse_product() status."
            )
        if "CommandParser.parse_product(" not in source:
            violations.append(
                f"{relative} does not use the strict parse_product() boundary."
            )
    return violations


def check_dataset_data_interpretation_action_ownership(
    root_dir: Path,
) -> list[str]:
    """Keep Data Interpretation UI orchestration in focused workflow owners."""

    owner_relative = Path(
        "XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py"
    )
    recipe_owner_relative = Path(
        "XBrainLab/ui/panels/dataset/data_interpretation_recipe_reload_coordinator.py"
    )
    actions_relative = Path("XBrainLab/ui/panels/dataset/actions.py")
    owner_path = root_dir / owner_relative
    recipe_owner_path = root_dir / recipe_owner_relative
    actions_path = root_dir / actions_relative
    dataset_root = root_dir / "XBrainLab" / "ui" / "panels" / "dataset"
    command_names = frozenset(
        {
            "ApplyInterpretationCommand",
            "LoadDataCommand",
            "PreviewInterpretationCommand",
            "ReloadInterpretationRecipeCommand",
            "ReviewInterpretationCommand",
            "SaveInterpretationRecipeCommand",
            "ValidateInterpretationCommand",
        }
    )
    facade_methods = (
        "import_data",
        "review_current_import",
        "import_folder_source",
        "import_bids_source",
        "reload_interpretation_recipe",
        "_execute_interpretation_command_async",
        "_interaction_failure_outcome",
        "_save_interpretation_recipe",
        "_recipe_save_block_reason",
    )
    implementation_methods = frozenset(
        {
            "_compatibility_locked_preflight_blocked",
            "_read_interpretation_review",
            "_identity_from_publication",
            "_require_interpretation_identity",
            "_require_review_payload_identity",
            "_continue_reloaded_interpretation_recipe",
            "_continue_reloaded_recipe_preview",
            "_continue_reloaded_recipe_validation",
            "_can_start_interpretation",
            "_run_data_interpretation_import",
            "_continue_data_interpretation_import",
            "_start_interpretation_review_async",
            "_preview_and_validate_interpretation_async",
            "_repreview_interpretation_async",
            "_review_interpretation_for_apply_async",
            "_apply_interpretation_async",
            "_resource_preflight_view",
            "_preview_resource_preflight_outcome",
            "_review_state_from_review_result",
            "_review_state_from_parts",
            "_result_failed",
            "_dialog_label_sources",
            "_interpretation_source_and_choices",
            "_merge_interpretation_choices",
            "_choices_after_label_source_change",
            "_diagnostic_payload",
            "_optional_payload_id",
            "_decision_reason",
        }
    )
    review_state_names = frozenset(
        {"_InterpretationReviewState", "_PublishedInterpretationReview"}
    )
    recipe_reload_methods = frozenset(
        {
            "_continue_reloaded_interpretation_recipe",
            "_continue_reloaded_recipe_preview",
            "_continue_reloaded_recipe_validation",
        }
    )
    violations: list[str] = []

    if not owner_path.exists():
        violations.append(f"{owner_relative} is missing as the sole workflow owner.")
    else:
        owner_tree = _parse_python_file(owner_path)
        if owner_tree is not None:
            owner_classes = {
                node.name for node in owner_tree.body if isinstance(node, ast.ClassDef)
            }
            required_classes = (
                "DataInterpretationActionBindings",
                "DataInterpretationActionCoordinator",
                "DataInterpretationActionHost",
                *sorted(review_state_names),
            )
            violations.extend(
                f"{owner_relative} does not define {required_class}."
                for required_class in required_classes
                if required_class not in owner_classes
            )
            coordinator = next(
                (
                    node
                    for node in owner_tree.body
                    if isinstance(node, ast.ClassDef)
                    and node.name == "DataInterpretationActionCoordinator"
                ),
                None,
            )
            lock_preflight = (
                next(
                    (
                        node
                        for node in coordinator.body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == "_compatibility_locked_preflight_blocked"
                    ),
                    None,
                )
                if coordinator is not None
                else None
            )
            uses_host_compatibility_gate = lock_preflight is not None and any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_compatibility_controller_value"
                for node in ast.walk(lock_preflight)
            )
            if not uses_host_compatibility_gate:
                violations.append(
                    f"{owner_relative} compatibility lock preflight must call the "
                    "host _compatibility_controller_value() gate."
                )

            coordinator_methods = (
                {
                    node.name: node
                    for node in coordinator.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if coordinator is not None
                else {}
            )
            violations.extend(
                f"{owner_relative}:{coordinator_methods[name].lineno} keeps recipe "
                f"reload workflow method {name}; move it to {recipe_owner_relative}."
                for name in sorted(recipe_reload_methods & coordinator_methods.keys())
            )
            constructor = coordinator_methods.get("__init__")
            composes_recipe_owner = constructor is not None and any(
                isinstance(node, ast.Call)
                and _mutable_boundary_call_name(node.func)
                == "DataInterpretationRecipeReloadCoordinator"
                for node in ast.walk(constructor)
            )
            if not composes_recipe_owner:
                violations.append(
                    f"{owner_relative} must compose "
                    "DataInterpretationRecipeReloadCoordinator."
                )

    if not recipe_owner_path.exists():
        violations.append(f"{recipe_owner_relative} is missing as recipe reload owner.")
    else:
        recipe_owner_tree = _parse_python_file(recipe_owner_path)
        recipe_owner_classes = (
            {
                node.name
                for node in recipe_owner_tree.body
                if isinstance(node, ast.ClassDef)
            }
            if recipe_owner_tree is not None
            else set()
        )
        if "DataInterpretationRecipeReloadCoordinator" not in recipe_owner_classes:
            violations.append(
                f"{recipe_owner_relative} does not define "
                "DataInterpretationRecipeReloadCoordinator."
            )

    if dataset_root.exists():
        allowed_command_owners = {
            owner_path: command_names - {"ReloadInterpretationRecipeCommand"},
            recipe_owner_path: frozenset(
                {
                    "PreviewInterpretationCommand",
                    "ReloadInterpretationRecipeCommand",
                    "ValidateInterpretationCommand",
                }
            ),
        }
        for path in dataset_root.rglob("*.py"):
            tree = _parse_python_file(path)
            if tree is None:
                continue
            relative = path.relative_to(root_dir)
            allowed_commands = allowed_command_owners.get(path, frozenset())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == (
                    "XBrainLab.backend.application.commands"
                ):
                    violations.extend(
                        f"{relative}:{node.lineno} imports {alias.name} outside its "
                        "focused Data Interpretation workflow owner."
                        for alias in node.names
                        if alias.name in command_names
                        and alias.name not in allowed_commands
                    )
                if not isinstance(node, ast.Call):
                    continue
                called_name = None
                if isinstance(node.func, ast.Name):
                    called_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called_name = node.func.attr
                if called_name in command_names and called_name not in allowed_commands:
                    violations.append(
                        f"{relative}:{node.lineno} constructs {called_name} outside "
                        "its focused Data Interpretation workflow owner."
                    )

    if not actions_path.exists():
        violations.append(f"{actions_relative} is missing the compatibility facade.")
        return violations
    actions_tree = _parse_python_file(actions_path)
    if actions_tree is None:
        return violations
    violations.extend(
        f"{actions_relative}:{node.lineno} defines {node.name}; review state "
        f"belongs to {owner_relative}."
        for node in actions_tree.body
        if isinstance(node, ast.ClassDef) and node.name in review_state_names
    )

    handler = next(
        (
            node
            for node in actions_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DatasetActionHandler"
        ),
        None,
    )
    if handler is None:
        violations.append(f"{actions_relative} does not define DatasetActionHandler.")
        return violations
    methods = {
        node.name: node
        for node in handler.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    constructor = methods.get("__init__")
    composes_owner = False
    if constructor is not None:
        for node in ast.walk(constructor):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            constructor_name = (
                value.func.id
                if isinstance(value.func, ast.Name)
                else value.func.attr
                if isinstance(value.func, ast.Attribute)
                else None
            )
            if constructor_name != "DataInterpretationActionCoordinator":
                continue
            composes_owner = any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "_data_interpretation"
                for target in targets
            )
            if composes_owner:
                break
    if not composes_owner:
        violations.append(
            f"{actions_relative} must compose DataInterpretationActionCoordinator "
            "as self._data_interpretation."
        )

    for method_name in implementation_methods:
        method = methods.get(method_name)
        if method is not None:
            violations.append(
                f"{actions_relative}:{method.lineno} regrows interpretation workflow "
                f"method {method_name}."
            )

    facade_method_names = frozenset(facade_methods)
    for method_name, method in methods.items():
        if method_name in facade_method_names:
            continue
        owns_extra_delegate = any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
            and node.value.attr == "_data_interpretation"
            for node in ast.walk(method)
        )
        if owns_extra_delegate:
            violations.append(
                f"{actions_relative}:{method.lineno} exposes extra interpretation "
                f"delegate {method_name}; only the nine compatibility facades are allowed."
            )

    for method_name in facade_methods:
        method = methods.get(method_name)
        if method is None:
            violations.append(
                f"{actions_relative} is missing required interpretation facade "
                f"{method_name}."
            )
            continue
        body = list(method.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        call = (
            body[0].value
            if len(body) == 1 and isinstance(body[0], ast.Return)
            else None
        )
        is_thin_delegate = (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == method_name
            and isinstance(call.func.value, ast.Attribute)
            and call.func.value.attr == "_data_interpretation"
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == "self"
        )
        if not is_thin_delegate:
            violations.append(
                f"{actions_relative}:{method.lineno} facade {method_name} must be a "
                "single-call thin delegate to self._data_interpretation."
            )
    return violations


def check_agent_resource_receipt_boundary(root_dir: Path) -> list[str]:
    """Keep resource consent typed, host-owned, and receipt-bound end to end."""

    required_snippets = {
        "XBrainLab/backend/application/resource_preflight.py": (
            "class ResourcePreflightView:",
            "class ResourceConfirmationChallenge:",
        ),
        "XBrainLab/backend/application/resource_receipt.py": (
            "class ResourceReceiptAuthority",
        ),
        "XBrainLab/llm/agent/tool_attempt_coordinator.py": (
            "ResourcePreflightView.from_diagnostics",
            'confirmed["resource_preflight_token"] =',
        ),
        "XBrainLab/llm/tools/application_surface.py": (
            "resource_preflight_token=_optional_str(",
        ),
        "XBrainLab/backend/application/data_interpretation_service.py": (
            "ResourceReceiptAuthority[",
            "self._import_preflight_receipts.consume(",
        ),
        "XBrainLab/backend/application/training_resource_receipt.py": (
            "ResourceReceiptAuthority[",
            "self._authority.consume(",
        ),
        "XBrainLab/ui/panels/training/sidebar.py": (
            "ResourcePreflightView.from_diagnostics",
        ),
        "XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py": (
            "ResourcePreflightView.from_diagnostics",
        ),
    }
    violations: list[str] = []
    for relative, snippets in required_snippets.items():
        path = root_dir / relative
        if not path.exists():
            violations.append(f"{relative} is missing from the receipt boundary.")
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{relative} does not preserve required resource receipt "
            f"contract: {snippet!r}."
            for snippet in snippets
            if snippet not in source
        )

    service_path = (
        root_dir
        / "XBrainLab"
        / "backend"
        / "application"
        / "data_interpretation_service.py"
    )
    if service_path.exists() and "confirmation_is_current" in service_path.read_text(
        encoding="utf-8"
    ):
        violations.append(
            "XBrainLab/backend/application/data_interpretation_service.py "
            "accepts generic tokenless resource confirmation."
        )
    client_paths = (
        "XBrainLab/ui/panels/training/sidebar.py",
        "XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py",
        "XBrainLab/llm/agent/tool_attempt_coordinator.py",
    )
    forbidden_key_reads = (
        '.get("resource_preflight")',
        '.get("confirmation_token")',
        '.get("scope_fingerprint")',
        '.get("requires_confirmation")',
    )
    forbidden_subscript_reads = frozenset(
        {
            "resource_preflight",
            "confirmation_token",
            "scope_fingerprint",
            "requires_confirmation",
        }
    )
    for relative in client_paths:
        path = root_dir / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{relative} parses {snippet} outside ResourcePreflightView."
            for snippet in forbidden_key_reads
            if snippet in source
        )
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript) or not isinstance(
                node.ctx,
                ast.Load,
            ):
                continue
            key = node.slice.value if isinstance(node.slice, ast.Constant) else None
            if key in forbidden_subscript_reads:
                violations.append(
                    f"{relative} reads {key!r} outside ResourcePreflightView."
                )
    return violations


class _BackendFacadeRuntimeUsageVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.AST] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "XBrainLab.backend.facade":
            self.violations.append(node)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "BackendFacade":
            self.violations.append(node)
            return
        self.generic_visit(node)


def check_ui_controller_fallbacks(root_dir: Path) -> list[str]:
    """Return UI branches that silently mutate controllers on missing results."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test_source = ast.get_source_segment(source, node.test) or ""
            if "result" not in test_source or "None" not in test_source:
                continue
            violations.extend(
                (
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"{_call_name(call.func)} directly in {test_source!r}; use "
                    "run_controller_compatibility_call() for mock/compatibility-only fallback."
                )
                for call in _forbidden_fallback_calls(node.body)
            )
    return violations


def _forbidden_fallback_calls(nodes: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in nodes:
        visitor = _ControllerFallbackVisitor()
        visitor.visit(node)
        calls.extend(visitor.violations)
    return calls


def check_ui_controller_render_fallbacks(root_dir: Path) -> list[str]:
    """Return UI query-missing branches that read stale controller render state."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test_source = ast.get_source_segment(source, node.test) or ""
            if "result" not in test_source or "None" not in test_source:
                continue
            violations.extend(
                (
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"controller.{_call_name(call.func)}() directly in "
                    f"{test_source!r}; render fallback reads must go through "
                    "run_controller_compatibility_call() so real Study paths do "
                    "not display stale controller state."
                )
                for call in _forbidden_render_fallback_calls(node.body)
            )
    return violations


def check_training_panel_history_fallback_scope(root_dir: Path) -> list[str]:
    """Keep controller history reads behind the no-runtime compatibility branch."""
    panel_path = root_dir / "XBrainLab" / "ui" / "panels" / "training" / "panel.py"
    if not panel_path.exists():
        return []
    tree = ast.parse(panel_path.read_text(encoding="utf-8"), filename=str(panel_path))
    history_method = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_history_for_render"
        ),
        None,
    )
    if history_method is None:
        return [
            "TrainingPanel._history_for_render is required for query/fallback routing."
        ]

    compatibility_calls = [
        call
        for call in ast.walk(history_method)
        if isinstance(call, ast.Call)
        and _call_name(call.func) == "_compatibility_history_for_render"
    ]
    allowed_calls: set[int] = set()
    for node in history_method.body:
        if not isinstance(node, ast.If) or not _is_result_none_guard(node.test):
            continue
        allowed_calls.update(
            id(call)
            for statement in node.body
            for call in ast.walk(statement)
            if isinstance(call, ast.Call)
            and _call_name(call.func) == "_compatibility_history_for_render"
        )
    return [
        f"{panel_path.relative_to(root_dir)}:{call.lineno} reads controller history "
        "outside the explicit result-is-None compatibility branch."
        for call in compatibility_calls
        if id(call) not in allowed_calls
    ]


def _is_result_none_guard(node: ast.AST) -> bool:
    """Return whether a condition is exactly the no-runtime ``result is None`` gate."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Is):
        return False
    if len(node.comparators) != 1:
        return False
    return (
        isinstance(node.left, ast.Name)
        and node.left.id == "result"
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _forbidden_render_fallback_calls(nodes: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in nodes:
        visitor = _ControllerRenderFallbackVisitor()
        visitor.visit(node)
        calls.extend(visitor.violations)
    return calls


class _ControllerFallbackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if call_name in UI_CONTROLLER_FALLBACK_METHODS:
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ControllerRenderFallbackVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if (
            call_name in UI_CONTROLLER_RENDER_FALLBACK_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


@dataclass(frozen=True)
class _FlowOrigin:
    kind: str
    identity: str
    member: str = ""


@dataclass(frozen=True)
class _CompatibilityGateContract:
    callback_positions: frozenset[int]
    callback_keywords: frozenset[str] = frozenset()


_CONTROLLER_ORIGIN = "controller"
_CONTROLLER_CALLABLE_ORIGIN = "controller_callable"
_LOADER_ORIGIN = "loader"
_LOADER_APPLY_ORIGIN = "loader_apply"
_APPLICATION_SERVICE_ORIGIN = "application_service"
_APPLICATION_EXECUTE_ORIGIN = "application_execute"
_APPLICATION_SERVICE_FACTORY_ORIGIN = "application_service_factory"
_BACKEND_FACADE_ORIGIN = "backend_facade"
_BACKEND_FACADE_FACTORY_ORIGIN = "backend_facade_factory"
_GETATTR_FACTORY_ORIGIN = "getattr_factory"
_CAST_FACTORY_ORIGIN = "cast_factory"
_CONTAINER_ACCESSOR_ORIGIN = "container_accessor"
_STUDY_ORIGIN = "study"
_TRUSTED_COMPATIBILITY_GATE = "run_controller_compatibility_call"
_TRUSTED_COMPATIBILITY_GATE_MODULE = "XBrainLab.ui.application_capabilities"
_TRUSTED_APPLICATION_SERVICE_MODULES = frozenset(
    {
        "XBrainLab.backend.application",
        "XBrainLab.backend.application.runtime",
        "XBrainLab.backend.application.service",
    }
)
_TRUSTED_BACKEND_FACADE_MODULES = frozenset({"XBrainLab.backend.facade"})
_TRUSTED_COMPATIBILITY_GATE_CONTRACT = _CompatibilityGateContract(
    callback_positions=frozenset({1}),
    callback_keywords=frozenset({"callback", "fallback"}),
)


def _parse_product_guard_tree(
    py_file: Path,
    root_dir: Path,
    *,
    guard_name: str,
) -> tuple[ast.Module | None, str | None]:
    """Parse one UI product file and return an explicit fail-closed error."""
    source = py_file.read_text(encoding="utf-8")
    try:
        return ast.parse(source, filename=str(py_file)), None
    except SyntaxError as exc:
        line = int(exc.lineno or 1)
        return (
            None,
            f"{_repo_relative_posix(py_file, root_dir)}:{line} has invalid Python syntax "
            f"({exc.msg}); {guard_name} cannot inspect this product file and "
            "fails closed.",
        )


def _expression_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _expression_key(node.value)
        return f"{owner}.{node.attr}" if owner else None
    if isinstance(node, ast.Subscript):
        owner = _expression_key(node.value)
        item = _static_container_item_key(node.slice)
        if owner is not None and item is not None:
            return f"{owner}[{item}]"
    return None


def _static_container_item_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(
        node.value,
        (str, int, float, bytes, bool, type(None)),
    ):
        return repr(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        prefix = "+" if isinstance(node.op, ast.UAdd) else "-"
        return f"{prefix}{node.operand.value!r}"
    return None


def _is_controller_identifier(name: str) -> bool:
    return name == "controller" or name.endswith("_controller")


def _is_loader_identifier(name: str) -> bool:
    return name in {"loader", "raw_loader", "data_loader"} or name.endswith("_loader")


def _is_application_service_identifier(name: str) -> bool:
    return name in {"application_service", "app_service"} or name.endswith(
        "_application_service"
    )


def _origins_for_identifier(
    name: str, *, identity: str | None = None
) -> set[_FlowOrigin]:
    resolved_identity = identity or name
    if _is_controller_identifier(name):
        return {_FlowOrigin(_CONTROLLER_ORIGIN, resolved_identity)}
    if _is_loader_identifier(name):
        return {_FlowOrigin(_LOADER_ORIGIN, resolved_identity)}
    if _is_application_service_identifier(name):
        return {_FlowOrigin(_APPLICATION_SERVICE_ORIGIN, resolved_identity)}
    if name in {"study", "loaded_study"}:
        return {_FlowOrigin(_STUDY_ORIGIN, resolved_identity)}
    return set()


def _imported_flow_values(tree: ast.AST) -> dict[str, set[_FlowOrigin]]:
    values: dict[str, set[_FlowOrigin]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for alias in node.names:
            bound_name = alias.asname or alias.name
            if node.module in _TRUSTED_APPLICATION_SERVICE_MODULES and alias.name in {
                "ApplicationService",
                "get_application_service",
            }:
                values.setdefault(bound_name, set()).add(
                    _FlowOrigin(
                        _APPLICATION_SERVICE_FACTORY_ORIGIN,
                        f"{node.module}.{alias.name}",
                    )
                )
            elif (
                node.module in _TRUSTED_BACKEND_FACADE_MODULES
                and alias.name == "BackendFacade"
            ):
                values.setdefault(bound_name, set()).add(
                    _FlowOrigin(
                        _BACKEND_FACADE_FACTORY_ORIGIN,
                        f"{node.module}.{alias.name}",
                    )
                )
            elif node.module == "builtins" and alias.name == "getattr":
                values.setdefault(bound_name, set()).add(
                    _FlowOrigin(
                        _GETATTR_FACTORY_ORIGIN,
                        "builtins.getattr",
                    )
                )
            elif node.module == "typing" and alias.name == "cast":
                values.setdefault(bound_name, set()).add(
                    _FlowOrigin(
                        _CAST_FACTORY_ORIGIN,
                        "typing.cast",
                    )
                )
    return values


class _ScopedOriginFlow:
    """Small conservative intraprocedural origin tracker for architecture guards."""

    def __init__(
        self,
        parameters: tuple[str, ...] = (),
        initial_values: dict[str, set[_FlowOrigin]] | None = None,
    ) -> None:
        self.values: dict[str, set[_FlowOrigin]] = {
            key: set(value) for key, value in (initial_values or {}).items()
        }
        self.values.setdefault("getattr", set()).add(
            _FlowOrigin(_GETATTR_FACTORY_ORIGIN, "builtins.getattr")
        )
        self.values.setdefault("cast", set()).add(
            _FlowOrigin(_CAST_FACTORY_ORIGIN, "typing.cast")
        )
        self.container_keys: set[str] = set()
        for parameter in parameters:
            self.values.pop(parameter, None)
            inferred = _origins_for_identifier(parameter)
            if inferred:
                self.values[parameter] = inferred

    def resolve(self, node: ast.AST) -> set[_FlowOrigin]:
        key = _expression_key(node)
        if key is not None and key in self.values:
            return set(self.values[key])

        if isinstance(node, ast.Name):
            return _origins_for_identifier(node.id)
        if isinstance(node, ast.Attribute):
            container_key = _expression_key(node.value)
            if container_key in self.container_keys:
                return {
                    _FlowOrigin(
                        _CONTAINER_ACCESSOR_ORIGIN,
                        container_key,
                        node.attr,
                    )
                }
            base = self.resolve(node.value)
            member_origins = self._member_origins(
                base,
                node.attr,
                expression_identity=key,
            )
            if member_origins:
                return member_origins
            return _origins_for_identifier(node.attr, identity=key)
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            factory_origins = self.resolve(node.func)
            container_accessors = {
                origin
                for origin in factory_origins
                if origin.kind == _CONTAINER_ACCESSOR_ORIGIN
            }
            if container_accessors:
                resolved: set[_FlowOrigin] = set()
                for accessor in container_accessors:
                    if accessor.member in {
                        "get",
                        "pop",
                        "setdefault",
                        "__getitem__",
                    }:
                        if node.args:
                            resolved.update(
                                self._container_item_origins(
                                    accessor.identity,
                                    node.args[0],
                                )
                            )
                        else:
                            resolved.update(self.values.get(accessor.identity, set()))
                    elif accessor.member in {"values", "items", "copy"}:
                        resolved.update(self.values.get(accessor.identity, set()))
                return resolved
            if any(
                origin.kind == _BACKEND_FACADE_FACTORY_ORIGIN
                for origin in factory_origins
            ):
                return {
                    _FlowOrigin(
                        _BACKEND_FACADE_ORIGIN,
                        _expression_key(node.func) or call_name,
                    )
                }
            if any(
                origin.kind == _APPLICATION_SERVICE_FACTORY_ORIGIN
                for origin in factory_origins
            ):
                return {
                    _FlowOrigin(
                        _APPLICATION_SERVICE_ORIGIN,
                        _expression_key(node.func) or call_name,
                    )
                }
            if call_name == "BackendFacade":
                return {_FlowOrigin(_BACKEND_FACADE_ORIGIN, "BackendFacade")}
            if call_name in {"ApplicationService", "get_application_service"}:
                return {
                    _FlowOrigin(
                        _APPLICATION_SERVICE_ORIGIN,
                        call_name,
                    )
                }
            if call_name == "get_controller_for_compatibility_context":
                controller_kind = _constant_string_argument(node, 2)
                if controller_kind:
                    return {
                        _FlowOrigin(
                            _CONTROLLER_ORIGIN,
                            f"compatibility_controller:{controller_kind}",
                        )
                    }
                return {
                    _FlowOrigin(
                        _CONTROLLER_ORIGIN,
                        "compatibility_controller:<dynamic>",
                    )
                }
            invokes_getattr = call_name == "getattr" or any(
                origin.kind == _GETATTR_FACTORY_ORIGIN for origin in factory_origins
            )
            if invokes_getattr and node.args:
                base = self.resolve(node.args[0])
                member = _constant_string_argument(node, 1) or "<dynamic>"
                identity = _expression_key(node.args[0])
                expression_identity = (
                    f"{identity}.{member}"
                    if identity and member != "<dynamic>"
                    else None
                )
                return self._member_origins(
                    base,
                    member,
                    expression_identity=expression_identity,
                ) or _origins_for_identifier(
                    member,
                    identity=expression_identity,
                )
            invokes_cast = call_name == "cast" or any(
                origin.kind == _CAST_FACTORY_ORIGIN for origin in factory_origins
            )
            if invokes_cast and len(node.args) >= 2:
                return self.resolve(node.args[1])
            if call_name == "dict":
                dict_origins: set[_FlowOrigin] = set()
                for argument in node.args:
                    dict_origins.update(self.resolve(argument))
                for keyword in node.keywords:
                    dict_origins.update(self.resolve(keyword.value))
                return dict_origins
            return set()
        if isinstance(node, ast.Subscript):
            return self.resolve(node.value)
        if isinstance(node, ast.IfExp):
            return self.resolve(node.body) | self.resolve(node.orelse)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            collection_origins: set[_FlowOrigin] = set()
            for element in node.elts:
                collection_origins.update(self.resolve(element))
            return collection_origins
        if isinstance(node, ast.Dict):
            origins = set()
            for value in node.values:
                origins.update(self.resolve(value))
            return origins
        if isinstance(node, ast.Starred):
            return self.resolve(node.value)
        return set()

    def bind(self, target: ast.AST, value: ast.AST | None) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(
                value.elts
            ):
                for element, item in zip(target.elts, value.elts, strict=True):
                    self.bind(element, item)
                return
            origins = self.resolve(value) if value is not None else set()
            for element in target.elts:
                self._bind_origins(element, origins)
            return
        origins = self.resolve(value) if value is not None else set()
        self._bind_origins(target, origins)
        self._bind_static_container_items(target, value)
        target_key = _expression_key(target)
        source_key = _expression_key(value) if value is not None else None
        if (
            target_key is not None
            and source_key is not None
            and source_key in self.container_keys
        ):
            self.container_keys.add(target_key)
            prefix = f"{source_key}["
            for key, item_origins in tuple(self.values.items()):
                if key.startswith(prefix):
                    self.values[f"{target_key}{key[len(source_key) :]}"] = set(
                        item_origins
                    )

    def _bind_static_container_items(
        self,
        target: ast.AST,
        value: ast.AST | None,
    ) -> None:
        target_key = _expression_key(target)
        if target_key is None or value is None:
            return
        if isinstance(value, ast.Dict):
            self.container_keys.add(target_key)
            for key_node, item in zip(value.keys, value.values, strict=True):
                if key_node is None:
                    continue
                item_key = _static_container_item_key(key_node)
                if item_key is None:
                    continue
                child_key = f"{target_key}[{item_key}]"
                self.values[child_key] = self.resolve(item)
                self._store_nested_container(child_key, item)
            return
        if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            self.container_keys.add(target_key)
            for index, item in enumerate(value.elts):
                child_key = f"{target_key}[{index!r}]"
                self.values[child_key] = self.resolve(item)
                self._store_nested_container(child_key, item)
            return
        if isinstance(value, ast.Call) and _call_name(value.func) == "dict":
            self.container_keys.add(target_key)
            for keyword in value.keywords:
                if keyword.arg is None:
                    continue
                child_key = f"{target_key}[{keyword.arg!r}]"
                self.values[child_key] = self.resolve(keyword.value)
                self._store_nested_container(child_key, keyword.value)

    def _store_nested_container(self, target_key: str, value: ast.AST) -> None:
        if not isinstance(value, (ast.Dict, ast.Tuple, ast.List, ast.Set)):
            return
        self.container_keys.add(target_key)

    def _container_item_origins(
        self,
        container_key: str,
        item: ast.AST,
    ) -> set[_FlowOrigin]:
        item_key = _static_container_item_key(item)
        if item_key is not None:
            stored_key = f"{container_key}[{item_key}]"
            if stored_key in self.values:
                return set(self.values[stored_key])
        return set(self.values.get(container_key, set()))

    def _bind_origins(
        self,
        target: ast.AST,
        origins: set[_FlowOrigin],
    ) -> None:
        if isinstance(target, ast.Starred):
            self._bind_origins(target.value, origins)
            return
        key = _expression_key(target)
        if key is None:
            return
        inferred = set(origins)
        terminal_name = key.rsplit(".", 1)[-1]
        if not inferred:
            inferred = _origins_for_identifier(terminal_name, identity=key)
        if inferred:
            self.values.setdefault(key, set()).update(inferred)

    @staticmethod
    def _member_origins(
        base: set[_FlowOrigin],
        member: str,
        *,
        expression_identity: str | None,
    ) -> set[_FlowOrigin]:
        resolved: set[_FlowOrigin] = set()
        for origin in base:
            if origin.kind == _CONTROLLER_ORIGIN:
                if member == "study":
                    resolved.add(
                        _FlowOrigin(
                            _STUDY_ORIGIN,
                            expression_identity or f"{origin.identity}.study",
                        )
                    )
                else:
                    resolved.add(
                        _FlowOrigin(
                            _CONTROLLER_CALLABLE_ORIGIN,
                            origin.identity,
                            member,
                        )
                    )
            elif origin.kind == _LOADER_ORIGIN and member in {"apply", "<dynamic>"}:
                resolved.add(
                    _FlowOrigin(
                        _LOADER_APPLY_ORIGIN,
                        origin.identity,
                        member,
                    )
                )
            elif origin.kind == _APPLICATION_SERVICE_ORIGIN and member in {
                "execute",
                "<dynamic>",
            }:
                resolved.add(
                    _FlowOrigin(
                        _APPLICATION_EXECUTE_ORIGIN,
                        origin.identity,
                        member,
                    )
                )
            elif origin.kind == _BACKEND_FACADE_ORIGIN and member == "service":
                resolved.add(
                    _FlowOrigin(
                        _APPLICATION_SERVICE_ORIGIN,
                        expression_identity or "BackendFacade.service",
                    )
                )
        return resolved


def _constant_string_argument(node: ast.Call, position: int) -> str | None:
    if len(node.args) <= position:
        return None
    value = node.args[position]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _function_parameter_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    return tuple(
        argument.arg
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    )


def _function_call_parameter_positions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, int]:
    positional = [*node.args.posonlyargs, *node.args.args]
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    return {argument.arg: index for index, argument in enumerate(positional)}


def _callback_expressions(
    node: ast.Call,
    contract: _CompatibilityGateContract,
) -> tuple[ast.AST, ...]:
    expressions = [
        node.args[index]
        for index in contract.callback_positions
        if index < len(node.args)
    ]
    expressions.extend(
        keyword.value
        for keyword in node.keywords
        if keyword.arg in contract.callback_keywords
    )
    return tuple(expressions)


def _direct_callback_invoker_contracts(
    tree: ast.AST,
) -> dict[str, _CompatibilityGateContract]:
    """Return local callables that demonstrably invoke callback parameters."""
    contracts: dict[str, _CompatibilityGateContract] = {}
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = _function_call_parameter_positions(function)
        keyword_only = {argument.arg for argument in function.args.kwonlyargs}
        directly_invoked = {
            _call_name(call.func)
            for call in ast.walk(function)
            if isinstance(call, ast.Call)
        }
        callback_positions = frozenset(
            position
            for name, position in positional.items()
            if name in directly_invoked
        )
        callback_keywords = frozenset(keyword_only & directly_invoked)
        if callback_positions or callback_keywords:
            contracts[function.name] = _CompatibilityGateContract(
                callback_positions=callback_positions,
                callback_keywords=callback_keywords,
            )
    return contracts


def _looks_like_untrusted_compatibility_gate(call_name: str) -> bool:
    lower_name = call_name.lower()
    return "compatibility" in lower_name or lower_name.endswith("_gate")


def _compatibility_gate_contracts(
    tree: ast.AST,
) -> dict[str, _CompatibilityGateContract]:
    """Infer wrappers only when callback parameters reach the real gate."""
    trusted_gate_names = _trusted_compatibility_gate_names(tree)
    contracts: dict[str, _CompatibilityGateContract] = dict.fromkeys(
        trusted_gate_names,
        _TRUSTED_COMPATIBILITY_GATE_CONTRACT,
    )

    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name not in trusted_gate_names
    ]
    changed = True
    while changed:
        changed = False
        for function in definitions:
            if function.name in contracts:
                continue
            call_positions = _function_call_parameter_positions(function)
            keyword_parameters = {argument.arg for argument in function.args.kwonlyargs}
            forwarded_positions: set[int] = set()
            forwarded_keywords: set[str] = set()
            for call in (
                item for item in ast.walk(function) if isinstance(item, ast.Call)
            ):
                gate_contract = contracts.get(_call_name(call.func))
                if gate_contract is None:
                    continue
                for callback in _callback_expressions(call, gate_contract):
                    if not isinstance(callback, ast.Name):
                        continue
                    if callback.id in call_positions:
                        forwarded_positions.add(call_positions[callback.id])
                    elif callback.id in keyword_parameters:
                        forwarded_keywords.add(callback.id)
            forwarded_names = {
                name
                for name, position in call_positions.items()
                if position in forwarded_positions
            } | forwarded_keywords
            if not forwarded_names:
                continue
            directly_invoked = {
                _call_name(call.func)
                for call in (
                    item for item in ast.walk(function) if isinstance(item, ast.Call)
                )
                if _call_name(call.func) in forwarded_names
            }
            if directly_invoked:
                continue
            contracts[function.name] = _CompatibilityGateContract(
                callback_positions=frozenset(forwarded_positions),
                callback_keywords=frozenset(forwarded_keywords),
            )
            changed = True
    return contracts


def _trusted_compatibility_gate_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    if _trusted_compatibility_gate_is_unshadowed(tree):
        names.add(_TRUSTED_COMPATIBILITY_GATE)

    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.ImportFrom)
            or node.module != _TRUSTED_COMPATIBILITY_GATE_MODULE
        ):
            continue
        for alias in node.names:
            if alias.name != _TRUSTED_COMPATIBILITY_GATE:
                continue
            bound_name = alias.asname or alias.name
            if not _name_has_untrusted_binding(
                tree,
                bound_name,
                trusted_import=node,
            ):
                names.add(bound_name)
    return names


def _name_has_untrusted_binding(
    tree: ast.AST,
    name: str,
    *,
    trusted_import: ast.ImportFrom,
) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == name
        ):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            argument.arg == name
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        ):
            return True
        if (
            isinstance(node, ast.Name)
            and node.id == name
            and isinstance(node.ctx, ast.Store)
        ):
            return True
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) != name:
                    continue
                if node is trusted_import:
                    continue
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return True
    return False


def _trusted_compatibility_gate_is_unshadowed(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == _TRUSTED_COMPATIBILITY_GATE
        ):
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            argument.arg == _TRUSTED_COMPATIBILITY_GATE
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        ):
            return False
        if (
            isinstance(node, ast.Name)
            and node.id == _TRUSTED_COMPATIBILITY_GATE
            and isinstance(node.ctx, ast.Store)
        ):
            return False
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound_name = alias.asname or alias.name
                if (
                    bound_name == _TRUSTED_COMPATIBILITY_GATE
                    and node.module != _TRUSTED_COMPATIBILITY_GATE_MODULE
                ):
                    return False
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name) == _TRUSTED_COMPATIBILITY_GATE:
                    return False
    return True


class _ScopedFlowVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        parameters: tuple[str, ...] = (),
        initial_values: dict[str, set[_FlowOrigin]] | None = None,
    ) -> None:
        self.flow = _ScopedOriginFlow(parameters, initial_values)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.flow.bind(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.flow.bind(node.target, node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.flow.bind(node.target, node.value)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self.flow.bind(node.target, node.iter)
        for statement in (*node.body, *node.orelse):
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        self.flow.bind(node.target, node.iter)
        for statement in (*node.body, *node.orelse):
            self.visit(statement)


def _visit_scope(
    visitor: _ScopedFlowVisitor,
    node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef,
) -> None:
    for statement in node.body:
        visitor.visit(statement)


def _persistent_application_service_values(
    tree: ast.AST,
    *,
    initial_values: dict[str, set[_FlowOrigin]] | None = None,
) -> dict[str, set[_FlowOrigin]]:
    """Resolve ApplicationService objects stored on ``self``/``cls`` fields."""
    persistent: dict[str, set[_FlowOrigin]] = {}
    scopes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for scope in scopes:
        visitor = _ScopedFlowVisitor(
            parameters=_function_parameter_names(scope),
            initial_values={
                **(initial_values or {}),
                **persistent,
            },
        )
        _visit_scope(visitor, scope)
        for key, origins in visitor.flow.values.items():
            if not key.startswith(("self.", "cls.")):
                continue
            service_origins = {
                origin
                for origin in origins
                if origin.kind == _APPLICATION_SERVICE_ORIGIN
            }
            if service_origins:
                persistent.setdefault(key, set()).update(service_origins)
    return persistent


def _controller_call_is_allowlisted(
    origin: _FlowOrigin,
    *,
    function_name: str,
    allowances: tuple[ControllerDirectCallAllowance, ...],
) -> bool:
    return any(
        allowance.function_name == function_name
        and allowance.receiver_identity == origin.identity
        and origin.member in allowance.methods
        for allowance in allowances
    )


class _DirectControllerMutationVisitor(_ScopedFlowVisitor):
    def __init__(
        self,
        *,
        function_name: str,
        allowances: tuple[ControllerDirectCallAllowance, ...] = (),
        gate_contracts: dict[str, _CompatibilityGateContract] | None = None,
        callback_invoker_contracts: (
            dict[str, _CompatibilityGateContract] | None
        ) = None,
        initially_gated: bool = False,
        parameters: tuple[str, ...] = (),
        initial_values: dict[str, set[_FlowOrigin]] | None = None,
    ) -> None:
        super().__init__(
            parameters=parameters,
            initial_values=initial_values,
        )
        self.violations: list[tuple[ast.Call, str]] = []
        self._function_name = function_name
        self._allowances = allowances
        self._gate_contracts = gate_contracts or {}
        self._callback_invoker_contracts = callback_invoker_contracts or {}
        self._gate_depth = int(initially_gated)

    def visit_Call(self, node: ast.Call) -> None:
        callable_origins = {
            origin
            for origin in self.flow.resolve(node.func)
            if origin.kind == _CONTROLLER_CALLABLE_ORIGIN
        }
        if self._gate_depth == 0 and any(
            not _controller_call_is_allowlisted(
                origin,
                function_name=self._function_name,
                allowances=self._allowances,
            )
            for origin in callable_origins
        ):
            member = next(
                (
                    origin.member
                    for origin in callable_origins
                    if not _controller_call_is_allowlisted(
                        origin,
                        function_name=self._function_name,
                        allowances=self._allowances,
                    )
                ),
                _call_name(node.func),
            )
            self.violations.append((node, member))

        contract = self._gate_contracts.get(_call_name(node.func))
        callback_ids = (
            {id(item) for item in _callback_expressions(node, contract)}
            if contract is not None
            else set()
        )
        unsafe_contract = self._callback_invoker_contracts.get(_call_name(node.func))
        if (
            unsafe_contract is None
            and contract is None
            and _looks_like_untrusted_compatibility_gate(_call_name(node.func))
        ):
            unsafe_contract = _TRUSTED_COMPATIBILITY_GATE_CONTRACT
        if self._gate_depth == 0 and unsafe_contract is not None:
            ungated_arguments = _callback_expressions(node, unsafe_contract)
            callback_origins = {
                origin
                for argument in ungated_arguments
                for origin in self.flow.resolve(argument)
                if origin.kind == _CONTROLLER_CALLABLE_ORIGIN
            }
            recorded_members = {
                member for call, member in self.violations if call is node
            }
            self.violations.extend(
                (node, origin.member)
                for origin in callback_origins
                if origin.member not in recorded_members
            )
        self.visit(node.func)
        for argument in node.args:
            if id(argument) in callback_ids:
                self._gate_depth += 1
                self.visit(argument)
                self._gate_depth -= 1
            else:
                self.visit(argument)
        for keyword in node.keywords:
            if id(keyword.value) in callback_ids:
                self._gate_depth += 1
                self.visit(keyword.value)
                self._gate_depth -= 1
            else:
                self.visit(keyword.value)


def check_ui_direct_controller_mutations(root_dir: Path) -> list[str]:
    """Return UI controller mutations outside explicit controller compatibility paths."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        tree, syntax_violation = _parse_product_guard_tree(
            py_file,
            root_dir,
            guard_name="direct-controller architecture guard",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None
        imported_values = _imported_flow_values(tree)
        allowances = UI_CONTROLLER_DIRECT_CALL_ALLOWLIST.get(
            py_file.relative_to(root_dir),
            (),
        )
        gate_contracts = _compatibility_gate_contracts(tree)
        callback_invoker_contracts = _direct_callback_invoker_contracts(tree)
        gated_helper_names = _structurally_gated_helper_names(
            tree,
            _controller_mutation_helper_names(
                tree,
                allowances,
                gate_contracts,
                initial_values=imported_values,
            ),
            gate_contracts=gate_contracts,
        )
        scopes: tuple[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef, ...] = (
            tree,
            *tuple(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
        )
        for node in scopes:
            function_name = (
                node.name if not isinstance(node, ast.Module) else "<module>"
            )
            visitor = _DirectControllerMutationVisitor(
                function_name=function_name,
                allowances=allowances,
                gate_contracts=gate_contracts,
                callback_invoker_contracts=callback_invoker_contracts,
                initially_gated=function_name in gated_helper_names,
                parameters=(
                    _function_parameter_names(node)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else ()
                ),
                initial_values=imported_values,
            )
            _visit_scope(visitor, node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                f"controller.{member}() directly; product UI "
                "mutations must go through ApplicationService, with controller "
                "mutation limited to an explicit "
                "run_controller_compatibility_call() boundary."
                for call, member in visitor.violations
            )
    return violations


def check_ui_legacy_mutation_helper_calls(root_dir: Path) -> list[str]:
    """Return controller-mutation helpers called outside the compatibility gate."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        tree, syntax_violation = _parse_product_guard_tree(
            py_file,
            root_dir,
            guard_name="legacy-mutation-helper architecture guard",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None

        allowances = UI_CONTROLLER_DIRECT_CALL_ALLOWLIST.get(
            py_file.relative_to(root_dir),
            (),
        )
        gate_contracts = _compatibility_gate_contracts(tree)
        helper_names = _controller_mutation_helper_names(
            tree,
            allowances,
            gate_contracts,
        )
        if not helper_names:
            continue

        visitor = _LegacyMutationHelperCallVisitor(
            helper_names,
            gate_contracts=gate_contracts,
        )
        visitor.visit(tree)
        violations.extend(
            f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
            f"{_call_name(call.func)}() outside run_controller_compatibility_call(); "
            "helpers that mutate controllers must remain behind "
            "the explicit mock/compatibility gate."
            for call in visitor.violations
        )
    return violations


def _controller_mutation_helper_names(
    tree: ast.AST,
    allowances: tuple[ControllerDirectCallAllowance, ...] = (),
    gate_contracts: dict[str, _CompatibilityGateContract] | None = None,
    *,
    initial_values: dict[str, set[_FlowOrigin]] | None = None,
) -> set[str]:
    helper_names: set[str] = set()
    contracts = gate_contracts or _compatibility_gate_contracts(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visitor = _DirectControllerMutationVisitor(
            function_name=node.name,
            allowances=allowances,
            gate_contracts=contracts,
            parameters=_function_parameter_names(node),
            initial_values=initial_values,
        )
        _visit_scope(visitor, node)
        if visitor.violations:
            helper_names.add(node.name)
    return helper_names


def _structurally_gated_helper_names(
    tree: ast.AST,
    helper_names: set[str],
    *,
    gate_contracts: dict[str, _CompatibilityGateContract] | None = None,
) -> set[str]:
    if not helper_names:
        return set()
    visitor = _CompatibilityHelperCallAudit(
        helper_names,
        gate_contracts=gate_contracts or _compatibility_gate_contracts(tree),
    )
    visitor.visit(tree)
    return visitor.gated_calls - visitor.ungated_calls


class _CompatibilityHelperCallAudit(ast.NodeVisitor):
    def __init__(
        self,
        helper_names: set[str],
        *,
        gate_contracts: dict[str, _CompatibilityGateContract],
    ) -> None:
        self.helper_names = helper_names
        self.gated_calls: set[str] = set()
        self.ungated_calls: set[str] = set()
        self._gate_contracts = gate_contracts
        self._gate_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in self.helper_names:
            target = self.gated_calls if self._gate_depth else self.ungated_calls
            target.add(call_name)
        contract = self._gate_contracts.get(call_name)
        callback_ids = (
            {id(item) for item in _callback_expressions(node, contract)}
            if contract is not None
            else set()
        )
        self.visit(node.func)
        for argument in node.args:
            self._visit_call_part(argument, id(argument) in callback_ids)
        for keyword in node.keywords:
            self._visit_call_part(
                keyword.value,
                id(keyword.value) in callback_ids,
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in self.helper_names and isinstance(node.ctx, ast.Load):
            target = self.gated_calls if self._gate_depth else self.ungated_calls
            target.add(node.attr)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.helper_names and isinstance(node.ctx, ast.Load):
            target = self.gated_calls if self._gate_depth else self.ungated_calls
            target.add(node.id)

    def _visit_call_part(self, node: ast.AST, gated: bool) -> None:
        if gated:
            self._gate_depth += 1
        self.visit(node)
        if gated:
            self._gate_depth -= 1


class _LegacyMutationHelperCallVisitor(ast.NodeVisitor):
    def __init__(
        self,
        helper_names: set[str],
        *,
        gate_contracts: dict[str, _CompatibilityGateContract],
    ) -> None:
        self.helper_names = helper_names
        self.violations: list[ast.Call] = []
        self._gate_contracts = gate_contracts
        self._legacy_gate_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in self.helper_names and self._legacy_gate_depth == 0:
            self.violations.append(node)
        contract = self._gate_contracts.get(call_name)
        callback_ids = (
            {id(item) for item in _callback_expressions(node, contract)}
            if contract is not None
            else set()
        )
        self.visit(node.func)
        for argument in node.args:
            self._visit_call_part(argument, id(argument) in callback_ids)
        for keyword in node.keywords:
            self._visit_call_part(
                keyword.value,
                id(keyword.value) in callback_ids,
            )

    def _visit_call_part(self, node: ast.AST, gated: bool) -> None:
        if gated:
            self._legacy_gate_depth += 1
        self.visit(node)
        if gated:
            self._legacy_gate_depth -= 1


def check_ui_legacy_fallback_helper_scope(root_dir: Path) -> list[str]:
    """Return direct controller compatibility gates outside explicit legacy helpers."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name in {"__init__.py", "application_capabilities.py"}:
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_explicit_controller_compatibility_helper(node):
                continue
            visitor = _LegacyFallbackGateVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "run_controller_compatibility_call() from a product method; move "
                "mock/compatibility behavior into an explicit private helper that "
                "owns the compatibility gate."
                for call in visitor.violations
            )
    return violations


def _is_explicit_controller_compatibility_helper(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    if not node.name.startswith("_"):
        return False
    visitor = _DirectCompatibilityGateVisitor()
    for statement in node.body:
        visitor.visit(statement)
    return visitor.found


class _DirectCompatibilityGateVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.found = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "run_controller_compatibility_call":
            self.found = True
            return
        self.generic_visit(node)


class _LegacyFallbackGateVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if _is_explicit_controller_compatibility_helper(node):
            return
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if _is_explicit_controller_compatibility_helper(node):
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "run_controller_compatibility_call":
            self.violations.append(node)
            return
        self.generic_visit(node)


def _call_receiver_is_controller(func: ast.expr) -> bool:
    if not isinstance(func, ast.Attribute):
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name):
        return receiver.id == "controller" or receiver.id.endswith("_controller")
    return (
        isinstance(receiver, ast.Attribute)
        and (receiver.attr == "controller" or receiver.attr.endswith("_controller"))
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "self"
    )


def check_ui_direct_backend_service_execute(root_dir: Path) -> list[str]:
    """Return UI code that bypasses the shared command execution helper."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name in {"__init__.py", "application_capabilities.py"}:
            continue
        tree, syntax_violation = _parse_product_guard_tree(
            py_file,
            root_dir,
            guard_name="ApplicationService-execute architecture guard",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None
        imported_values = _imported_flow_values(tree)
        persistent_values = _persistent_application_service_values(
            tree,
            initial_values=imported_values,
        )
        initial_values = {
            **imported_values,
            **persistent_values,
        }
        scopes: tuple[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef, ...] = (
            tree,
            *tuple(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
        )
        for node in scopes:
            visitor = _DirectBackendServiceExecuteVisitor(
                parameters=(
                    _function_parameter_names(node)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else ()
                ),
                initial_values=initial_values,
            )
            _visit_scope(visitor, node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "BackendFacade(...).service.execute() or ApplicationService.execute() "
                "directly; UI command/query execution must go through "
                "execute_application_command() so the shared Study detection, "
                "mock/compatibility boundary, and refresh policy stay centralized."
                for call in visitor.violations
            )
    return violations


class _DirectBackendServiceExecuteVisitor(_ScopedFlowVisitor):
    def __init__(
        self,
        *,
        parameters: tuple[str, ...] = (),
        initial_values: dict[str, set[_FlowOrigin]] | None = None,
    ) -> None:
        super().__init__(
            parameters=parameters,
            initial_values=initial_values,
        )
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if any(
            origin.kind == _APPLICATION_EXECUTE_ORIGIN
            for origin in self.flow.resolve(node.func)
        ):
            self.violations.append(node)
        self.generic_visit(node)


def check_ui_command_execution_suppresses_observer_refresh(root_dir: Path) -> list[str]:
    """Return command helper executions not protected from observer refresh."""
    helper_file = root_dir / "XBrainLab" / "ui" / "application_capabilities.py"
    if not helper_file.exists():
        return []

    source = helper_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(helper_file))
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "execute_application_command":
            continue
        visitor = _CommandExecutionObserverSuppressionVisitor()
        visitor.visit(node)
        violations.extend(
            f"{helper_file.relative_to(root_dir)}:{call.lineno} executes "
            "ApplicationService without suppress_observer_refresh_during_command(); "
            "controller observer events fired inside command handlers must wait "
            "for CommandResult.changed_state refresh."
            for call in visitor.violations
        )
    return violations


class _CommandExecutionObserverSuppressionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []
        self._suppression_depth = 0

    def visit_With(self, node: ast.With) -> None:
        suppresses = any(
            _call_name(item.context_expr.func)
            == "suppress_observer_refresh_during_command"
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
        )
        if suppresses:
            self._suppression_depth += 1
            for statement in node.body:
                self.visit(statement)
            self._suppression_depth -= 1
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            _call_name(node.func) == "execute"
            and _call_invokes_application_service(node)
            and self._suppression_depth == 0
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _call_invokes_application_service(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    receiver = node.func.value
    return (
        isinstance(receiver, ast.Call)
        and _call_name(receiver.func) == "get_application_service"
    )


def check_ui_direct_loader_apply(root_dir: Path) -> list[str]:
    """Return UI code that applies raw loaders outside a compatibility gate."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        tree, syntax_violation = _parse_product_guard_tree(
            py_file,
            root_dir,
            guard_name="direct-loader-apply architecture guard",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None
        imported_values = _imported_flow_values(tree)
        gate_contracts = _compatibility_gate_contracts(tree)
        helper_names = _loader_apply_helper_names(
            tree,
            gate_contracts=gate_contracts,
            initial_values=imported_values,
        )
        gated_helper_names = _structurally_gated_helper_names(
            tree,
            helper_names,
            gate_contracts=gate_contracts,
        )
        scopes: tuple[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef, ...] = (
            tree,
            *tuple(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
        )
        for node in scopes:
            function_name = (
                node.name if not isinstance(node, ast.Module) else "<module>"
            )
            visitor = _DirectLoaderApplyVisitor(
                gate_contracts=gate_contracts,
                initially_gated=function_name in gated_helper_names,
                parameters=(
                    _function_parameter_names(node)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else ()
                ),
                initial_values=imported_values,
            )
            _visit_scope(visitor, node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "loader.apply() directly; isolate raw loader mutation behind a "
                "compatibility loader adapter or ApplicationService command."
                for call in visitor.violations
            )
    return violations


def _loader_apply_helper_names(
    tree: ast.AST,
    *,
    gate_contracts: dict[str, _CompatibilityGateContract] | None = None,
    initial_values: dict[str, set[_FlowOrigin]] | None = None,
) -> set[str]:
    helper_names: set[str] = set()
    contracts = gate_contracts or _compatibility_gate_contracts(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visitor = _DirectLoaderApplyVisitor(
            gate_contracts=contracts,
            parameters=_function_parameter_names(node),
            initial_values=initial_values,
        )
        _visit_scope(visitor, node)
        if visitor.violations:
            helper_names.add(node.name)
    return helper_names


class _DirectLoaderApplyVisitor(_ScopedFlowVisitor):
    def __init__(
        self,
        *,
        gate_contracts: dict[str, _CompatibilityGateContract] | None = None,
        initially_gated: bool = False,
        parameters: tuple[str, ...] = (),
        initial_values: dict[str, set[_FlowOrigin]] | None = None,
    ) -> None:
        super().__init__(
            parameters=parameters,
            initial_values=initial_values,
        )
        self.violations: list[ast.Call] = []
        self._gate_contracts = gate_contracts or {}
        self._gate_depth = int(initially_gated)

    def visit_Call(self, node: ast.Call) -> None:
        is_loader_apply = any(
            origin.kind == _LOADER_APPLY_ORIGIN
            for origin in self.flow.resolve(node.func)
        )
        mentions_study = any(
            _flow_expression_contains_origin(self.flow, argument, _STUDY_ORIGIN)
            for argument in node.args
        ) or any(
            _flow_expression_contains_origin(
                self.flow,
                keyword.value,
                _STUDY_ORIGIN,
            )
            for keyword in node.keywords
        )
        if self._gate_depth == 0 and is_loader_apply and mentions_study:
            self.violations.append(node)

        contract = self._gate_contracts.get(_call_name(node.func))
        callback_ids = (
            {id(item) for item in _callback_expressions(node, contract)}
            if contract is not None
            else set()
        )
        self.visit(node.func)
        for argument in node.args:
            self._visit_call_part(argument, id(argument) in callback_ids)
        for keyword in node.keywords:
            self._visit_call_part(
                keyword.value,
                id(keyword.value) in callback_ids,
            )

    def _visit_call_part(self, node: ast.AST, gated: bool) -> None:
        if gated:
            self._gate_depth += 1
        self.visit(node)
        if gated:
            self._gate_depth -= 1


def _flow_expression_contains_origin(
    flow: _ScopedOriginFlow,
    node: ast.AST,
    kind: str,
) -> bool:
    if any(origin.kind == kind for origin in flow.resolve(node)):
        return True
    return any(
        any(origin.kind == kind for origin in flow.resolve(child))
        for child in ast.walk(node)
        if child is not node
    )


def check_ui_direct_study_state_reads(root_dir: Path) -> list[str]:
    """Return UI code that reads mutable Study state outside legacy helpers."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            visitor = _DirectStudyStateReadVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{attr.lineno} reads "
                f"study.{attr.attr}; product UI render/action state must come "
                "from ApplicationService query/capability results."
                for attr in visitor.violations
            )
    return violations


def check_ui_agent_worker_internal_access(root_dir: Path) -> list[str]:
    """Keep UI code behind queued runtime publications owned by the GUI."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations
    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            for token in UI_AGENT_WORKER_INTERNAL_TOKENS:
                if token not in line:
                    continue
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{line_number} reads {token}; "
                    "UI code must consume the queued assistant runtime publication "
                    "instead of worker or engine internals."
                )
            if ".runtime_snapshot(" in line:
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{line_number} directly reads "
                    "AgentController.runtime_snapshot(); GUI code must consume the "
                    "queued AssistantRuntimeCoordinator snapshot instead."
                )
    return violations


def check_assistant_presentation_ownership(root_dir: Path) -> list[str]:
    """Keep visible responses and turn activity behind one controller contract."""
    violations: list[str] = []
    controller_path = root_dir / "XBrainLab" / "llm" / "agent" / "controller.py"
    if controller_path.exists():
        source = controller_path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            for token in (
                "response_ready.emit",
                "chunk_received.emit",
                "remove_content.emit",
                "request_user_interaction =",
            ):
                if token not in line:
                    continue
                violations.append(
                    f"{controller_path.relative_to(root_dir)}:{line_number} uses "
                    f"{token}; product-visible assistant copy must be published "
                    "only through AssistantResponsePresentation."
                )

    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations
    for py_file in ui_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        if py_file.relative_to(root_dir).as_posix() == "XBrainLab/ui/chat/panel.py":
            for token in (
                "def on_chunk_received",
                "def collapse_agent_message",
                "current_agent_bubble",
            ):
                if token not in source:
                    continue
                violations.append(
                    f"{py_file.relative_to(root_dir)} retains {token}; ChatPanel "
                    "must render completed typed presentations instead of owning "
                    "a legacy streaming transcript."
                )
        for line_number, line in enumerate(source.splitlines(), start=1):
            for token in (
                "response_ready.connect",
                "chunk_received.connect",
                "remove_content.connect",
                "interaction_resolved.connect",
                "generation_started.connect",
                "processing_finished.connect",
                "request_user_interaction.connect",
            ):
                if token not in line:
                    continue
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{line_number} uses {token}; "
                    "the UI must render the typed response publication instead "
                    "of owning a parallel transcript or interaction-copy channel."
                )
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        allowed_transcript_calls: set[int] = set()
        relative_path = py_file.relative_to(root_dir).as_posix()
        if relative_path == "XBrainLab/ui/components/agent_manager.py":
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if function.name != "_render_visible_assistant_response":
                    continue
                allowed_transcript_calls.update(
                    id(node)
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_agent_message"
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_agent_message"
                and id(node) not in allowed_transcript_calls
            ):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} calls "
                    "add_agent_message outside the typed response renderer; "
                    "the UI must not create a parallel assistant transcript."
                )
            call_name = _call_name(node.func)
            if call_name != "AssistantTurnActivity":
                continue
            violations.append(
                f"{py_file.relative_to(root_dir)}:{node.lineno} constructs "
                "AssistantTurnActivity; the controller is the sole "
                "AssistantTurnActivity publisher."
            )
    return violations


def check_assistant_turn_scope_ownership(root_dir: Path) -> list[str]:
    """Keep assistant autonomy request-derived instead of manually mutable."""
    forbidden_tokens = {
        Path("XBrainLab/llm/agent/controller.py"): (
            "def set_execution_mode(",
            "execution_mode_changed =",
            "self._execution_mode",
        ),
        Path("XBrainLab/ui/components/assistant_command_dispatcher.py"): (
            "def set_mode(",
            "mode_requested =",
            '"set_execution_mode"',
        ),
        Path("XBrainLab/ui/components/assistant_runtime_lifecycle.py"): (
            "def set_execution_mode(",
            "def set_mode(",
            "execution_mode:",
        ),
        Path("XBrainLab/ui/components/agent_manager.py"): (
            "_ASSISTANT_IDLE_POLICY_MODE",
            "execution_mode=",
            "self._execution_mode",
            "def _on_execution_mode_changed(",
            "def _sync_execution_mode_ui(",
        ),
        Path("XBrainLab/llm/agent/assembler.py"): (
            "def set_execution_mode(",
            "self._execution_mode",
        ),
    }
    violations: list[str] = []
    for relative_path, tokens in forbidden_tokens.items():
        path = root_dir / relative_path
        if not path.exists():
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for token in tokens:
                if token not in line:
                    continue
                violations.append(
                    f"{relative_path}:{line_number} retains {token}; product "
                    "assistant autonomy must come only from the immutable "
                    "AssistantTurnRequest scope."
                )
    return violations


def check_assistant_runtime_selection_ownership(root_dir: Path) -> list[str]:
    """Keep launch selection and fallback policy in one core resolver."""
    violations: list[str] = []
    owner = root_dir / ASSISTANT_RUNTIME_SELECTION_OWNER
    if owner.exists():
        with contextlib.suppress(SyntaxError):
            ast.parse(owner.read_text(encoding="utf-8"), filename=str(owner))

    config_path = root_dir / "XBrainLab" / "llm" / "core" / "config.py"
    if config_path.exists():
        try:
            config_tree = ast.parse(
                config_path.read_text(encoding="utf-8"),
                filename=str(config_path),
            )
        except SyntaxError:
            config_tree = None
        if config_tree is not None:
            violations.extend(
                (
                    f"{config_path.relative_to(root_dir)}:{node.lineno} defines "
                    "available_local_model_id; runtime fallback policy belongs "
                    "only to AssistantRuntimeLaunchResolver."
                )
                for node in ast.walk(config_tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "available_local_model_id"
            )

    for relative_path in ASSISTANT_RUNTIME_SELECTION_CONSUMERS:
        path = root_dir / relative_path
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = _assistant_runtime_call_name(node)
                if call_name in ASSISTANT_RUNTIME_SELECTION_POLICY_CALLS:
                    violations.append(
                        f"{relative_path}:{node.lineno} calls {call_name}; backend, "
                        "model readiness, and fallback policy belong only to "
                        "AssistantRuntimeLaunchResolver."
                    )
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (
                relative_path == Path("XBrainLab/llm/agent/worker.py")
                and node.name in ASSISTANT_RUNTIME_STARTUP_FUNCTIONS
            ):
                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue
                    if _assistant_runtime_call_name(child) != "load_from_file":
                        continue
                    violations.append(
                        f"{relative_path}:{child.lineno} calls load_from_file during "
                        f"{node.name}; worker startup/switch must consume the exact "
                        "immutable launch spec without rereading settings."
                    )
    return violations


def _assistant_runtime_call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def check_ui_controller_study_get_controller_fallbacks(root_dir: Path) -> list[str]:
    """Return UI code that retrieves controllers through controller.study."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            visitor = _ControllerStudyGetControllerVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                "controller.study.get_controller(); product UI controller wiring "
                "must be injected or command/query-backed."
                for call in visitor.violations
            )
    return violations


def check_ui_direct_study_get_controller_lookups(root_dir: Path) -> list[str]:
    """Return direct Study controller lookup outside central bootstrap wiring."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if (
            py_file.name == "__init__.py"
            or py_file.name in UI_DIRECT_STUDY_CONTROLLER_LOOKUP_ALLOWED_FILES
        ):
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            visitor = _DirectStudyGetControllerLookupVisitor()
            visitor.visit(node)
            violations.extend(
                f"{_repo_relative_posix(py_file, root_dir)}:{call.lineno} calls "
                "study.get_controller(); product UI controller lookup must be "
                "limited to the central bootstrap quarantine for panel "
                "constructor adapters."
                for call in visitor.violations
            )
    return violations


class _DirectStudyStateReadVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Attribute] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr not in UI_DIRECT_STUDY_STATE_ATTRIBUTES:
            self.generic_visit(node)
            return
        if _expression_mentions_study(node.value):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ProductSuccessStudyStateVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.state_reads: list[ast.Attribute] = []
        self.study_method_calls: list[ast.Call] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.ctx, ast.Load)
            and node.attr in UI_DIRECT_STUDY_STATE_ATTRIBUTES
            and _expression_mentions_study(node.value)
        ):
            self.state_reads.append(node)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            _call_name(node.func) in PRODUCT_SUCCESS_DIRECT_STUDY_METHODS
            and isinstance(node.func, ast.Attribute)
            and _expression_mentions_study(node.func.value)
        ):
            self.study_method_calls.append(node)
            return
        self.generic_visit(node)


class _DirectStudyMethodCallVisitor(ast.NodeVisitor):
    def __init__(self, method_names: tuple[str, ...]) -> None:
        self.method_names = method_names
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if (
            _call_name(node.func) in self.method_names
            and isinstance(node.func, ast.Attribute)
            and _expression_mentions_study(node.func.value)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ProductSuccessControllerLookupAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if (
            _call_name(node.func) in PRODUCT_SUCCESS_CONTROLLER_LOOKUP_ASSERTIONS
            and isinstance(node.func, ast.Attribute)
            and _expression_mentions_get_controller(node.func.value)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _ControllerStudyGetControllerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _is_controller_study_get_controller_call(node):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _DirectStudyGetControllerLookupVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _is_study_get_controller_call(node):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _expression_mentions_study(node: ast.AST) -> bool:
    study_names = {"study", "loaded_study"}
    if isinstance(node, ast.Name) and node.id in study_names:
        return True
    if isinstance(node, ast.Attribute) and node.attr == "study":
        return True
    return any(
        (isinstance(child, ast.Name) and child.id in study_names)
        or (isinstance(child, ast.Attribute) and child.attr == "study")
        for child in ast.walk(node)
    )


def _expression_mentions_get_controller(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "get_controller":
        return True
    return any(
        isinstance(child, ast.Attribute) and child.attr == "get_controller"
        for child in ast.walk(node)
    )


def _is_controller_study_get_controller_call(node: ast.Call) -> bool:
    if _call_name(node.func) != "get_controller":
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    return _expression_mentions_controller_study(node.func.value)


def _is_study_get_controller_call(node: ast.Call) -> bool:
    if _call_name(node.func) != "get_controller":
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    receiver = node.func.value
    if isinstance(receiver, ast.Name) and receiver.id == "study":
        return True
    return _expression_mentions_study(receiver)


def _expression_mentions_controller_study(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute) or child.attr != "study":
            continue
        owner = child.value
        if isinstance(owner, ast.Name) and (
            owner.id == "controller" or owner.id.endswith("_controller")
        ):
            return True
        if isinstance(owner, ast.Attribute) and (
            owner.attr == "controller" or owner.attr.endswith("_controller")
        ):
            return True
    return False


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _study_state_expression(source: str, node: ast.AST) -> str:
    expression = ast.get_source_segment(source, node)
    if expression:
        return expression
    attr = getattr(node, "attr", "state")
    return f"study.{attr}"


def _read_poetry_default_dependency_names(pyproject: Path) -> set[str]:
    """Return dependency keys from ``[tool.poetry.dependencies]`` only."""
    deps: set[str] = set()
    in_default_deps = False
    for raw_line in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            in_default_deps = line == "[tool.poetry.dependencies]"
            continue
        if not in_default_deps or "=" not in line:
            continue
        deps.add(line.split("=", 1)[0].strip().strip('"'))
    return deps


def check_ui_post_command_local_refreshes(root_dir: Path) -> list[str]:
    """Return UI code that locally refreshes after service-backed commands."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"{_post_command_refresh_call_name(call)} after "
                    "execute_application_command(); "
                    "service-backed success refresh must go through "
                    "refresh_after_command(), with local refresh limited to "
                    "explicit legacy-result helpers."
                    for call in _post_command_local_refresh_calls(
                        node.body,
                        source,
                        node.name,
                    )
                )
        violations.extend(
            _format_async_command_callback_refresh_violations(
                py_file,
                root_dir,
                tree,
                source,
            )
        )
    return violations


def check_ui_post_command_controller_echoes(root_dir: Path) -> list[str]:
    """Return UI code that re-reads controller echo state after command success."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                violations.extend(
                    f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                    f"controller.{_call_name(call.func)}() after "
                    "execute_application_command(); service-backed success UI "
                    "must trust CommandResult and selected user inputs, with "
                    "controller echo reads limited to explicit controller compatibility "
                    "branches."
                    for call in _post_command_controller_echo_calls(
                        node.body,
                        source,
                    )
                )
    return violations


def check_ui_refresh_false_commands(root_dir: Path) -> list[str]:
    """Return mutating UI commands that suppress command-driven refresh."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "execute_application_command":
                continue
            if not _call_has_refresh_false(node):
                continue
            command_expr = _execute_command_argument(node)
            command_name = _refresh_false_command_name(command_expr)
            if _is_read_only_refresh_false_command(command_expr):
                continue
            violations.append(
                f"{py_file.relative_to(root_dir)}:{node.lineno} calls "
                f"{command_name or 'unknown command'} with refresh=False; only "
                "read/query commands may suppress command-driven UI refresh."
            )
    return violations


def check_ui_capability_gated_controller_readiness(root_dir: Path) -> list[str]:
    """Return UI command gates that consult controller state despite capabilities."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _contains_get_command_capability(node):
                continue
            visitor = _CapabilityGatedControllerReadinessVisitor()
            visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                f"controller.{_call_name(call.func)}() in a capability-gated "
                "command path; controller readiness checks must be limited to an "
                "explicit capability is None branch."
                for call in visitor.violations
            )
    return violations


def check_ui_observer_direct_update_bridges(root_dir: Path) -> list[str]:
    """Return observer bridges that bypass the simple refresh helper."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _observer_bridge_uses_import_finished_simple_refresh(node):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires "
                    "import_finished as a simple refresh event; successful import "
                    "state refresh is owned by data_changed. Use a named callback "
                    "handler for import warnings or event-specific behavior."
                )
                continue
            if _call_name(node.func) != "_create_bridge":
                continue
            if _observer_bridge_uses_direct_update_panel(node):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires observer "
                    "events directly to update_panel(); use _create_refresh_bridge() "
                    "for simple panel refresh (delegating to refresh_from_observer), "
                    "or a named callback handler for event-specific behavior."
                )
                continue
            if (
                py_file.name != "base_panel.py"
                and _observer_bridge_uses_direct_refresh_from_observer(node)
            ):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires simple "
                    "observer refresh through _create_bridge(..., "
                    "refresh_from_observer); use _create_refresh_bridge() instead."
                )
    return violations


def check_ui_observer_handlers_call_refresh_coordinator(root_dir: Path) -> list[str]:
    """Return event-specific observer handlers that skip the refresh coordinator."""
    violations: list[str] = []
    ui_dir = root_dir / "XBrainLab" / "ui"
    if not ui_dir.exists():
        return violations

    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "_create_bridge":
                continue
            event_name = _observer_bridge_event_name(node)
            if event_name not in UI_OBSERVER_REFRESH_EVENTS:
                continue
            handler_name = _observer_bridge_handler_method_name(node)
            if not handler_name:
                continue
            handler = functions.get(handler_name)
            if handler is None:
                continue
            if not _function_calls_refresh_after_observer(handler):
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} wires "
                    f"{event_name!r} to {handler_name}(), but that handler does "
                    "not call refresh_after_observer(); event-specific observer "
                    "handlers may do local side effects, then must delegate shared "
                    "refresh scope to the coordinator."
                )
                continue
            for local_call in _observer_handler_local_render_calls(event_name, handler):
                call_name = _call_name(local_call.func)
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{local_call.lineno} "
                    f"{handler_name}() handles {event_name!r} and calls "
                    f"{call_name}(); local render refresh must stay in "
                    "refresh_after_observer()/refresh_coordinator scope."
                )
    return violations


def _observer_bridge_event_name(call: ast.Call) -> str | None:
    if len(call.args) < 2:
        return None
    event_arg = call.args[1]
    if isinstance(event_arg, ast.Constant) and isinstance(event_arg.value, str):
        return event_arg.value
    return None


def _observer_bridge_handler_method_name(call: ast.Call) -> str | None:
    if len(call.args) < 3:
        return None
    handler_arg = call.args[2]
    if not isinstance(handler_arg, ast.Attribute):
        return None
    if isinstance(handler_arg.value, ast.Name) and handler_arg.value.id == "self":
        return handler_arg.attr
    return None


def _function_calls_refresh_after_observer(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(child, ast.Call)
        and _call_name(child.func) == "refresh_after_observer"
        for child in ast.walk(node)
    )


def _observer_handler_local_render_calls(
    event_name: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        call_name = _call_name(child.func)
        if call_name not in UI_OBSERVER_HANDLER_LOCAL_RENDER_METHODS:
            continue
        if (event_name, call_name) in UI_OBSERVER_HANDLER_LOCAL_RENDER_ALLOWLIST:
            continue
        calls.append(child)
    return calls


def _observer_bridge_uses_import_finished_simple_refresh(call: ast.Call) -> bool:
    call_name = _call_name(call.func)
    if call_name == "_create_refresh_bridge":
        return _call_has_string_arg(call, "import_finished")
    if call_name == "QtObserverBridge":
        return _call_has_string_arg(call, "import_finished")
    return False


def _call_has_string_arg(call: ast.Call, value: str) -> bool:
    return any(
        isinstance(arg, ast.Constant) and arg.value == value for arg in call.args
    )


def _observer_bridge_uses_direct_update_panel(call: ast.Call) -> bool:
    if len(call.args) < 3:
        return False
    handler = call.args[2]
    return isinstance(handler, ast.Attribute) and handler.attr == "update_panel"


def _observer_bridge_uses_direct_refresh_from_observer(call: ast.Call) -> bool:
    if len(call.args) < 3:
        return False
    handler = call.args[2]
    return (
        isinstance(handler, ast.Attribute) and handler.attr == "refresh_from_observer"
    )


def _post_command_local_refresh_calls(
    statements: list[ast.stmt],
    source: str,
    function_name: str = "",
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
) -> list[ast.Call]:
    violations: list[ast.Call] = []
    command_seen = False
    for statement in statements:
        if command_seen:
            visitor = _PostCommandLocalRefreshVisitor(
                source,
                function_name,
                functions=functions,
            )
            visitor.visit(statement)
            violations.extend(visitor.violations)
        violations.extend(
            _post_command_local_refresh_calls(
                _nested_statement_bodies(statement),
                source,
                function_name,
                functions,
            ),
        )
        if _contains_service_backed_command(statement):
            command_seen = True
    return violations


def _post_command_controller_echo_calls(
    statements: list[ast.stmt],
    source: str,
) -> list[ast.Call]:
    violations: list[ast.Call] = []
    command_seen = False
    for statement in statements:
        if command_seen:
            visitor = _PostCommandControllerEchoVisitor(source)
            visitor.visit(statement)
            violations.extend(visitor.violations)
        violations.extend(
            _post_command_controller_echo_calls(
                _nested_statement_bodies(statement),
                source,
            ),
        )
        if _contains_service_backed_command(statement):
            command_seen = True
    return violations


def _format_async_command_callback_refresh_violations(
    py_file: Path,
    root_dir: Path,
    tree: ast.AST,
    source: str,
) -> list[str]:
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) not in UI_SERVICE_COMMAND_ASYNC_METHODS:
            continue
        if _call_has_refresh_false(node):
            continue
        callback_name = _command_async_result_callback_name(node)
        if not callback_name:
            continue
        functions = _command_callback_function_scope(node, parents)
        callback = functions.get(callback_name)
        if callback is None:
            continue
        visitor = _PostCommandLocalRefreshVisitor(
            source,
            callback.name,
            functions=functions,
        )
        for statement in callback.body:
            visitor.visit(statement)
        violations.extend(
            f"{py_file.relative_to(root_dir)}:{call.lineno} async on_result "
            f"{callback_name}() calls {_post_command_refresh_call_name(call)}; "
            "service-backed "
            "async success refresh must go through refresh_after_command(), not "
            "callback-local render refresh."
            for call in visitor.violations
        )
    return violations


def _command_callback_function_scope(
    call: ast.Call,
    parents: dict[ast.AST, ast.AST],
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    enclosing_function: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    enclosing_class: ast.ClassDef | None = None
    enclosing_module: ast.Module | None = None
    current: ast.AST | None = call
    while current is not None:
        current = parents.get(current)
        if enclosing_function is None and isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            enclosing_function = current
        if isinstance(current, ast.ClassDef):
            enclosing_class = current
            break
        if isinstance(current, ast.Module):
            enclosing_module = current
            break

    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    if enclosing_class is not None:
        functions.update(
            {
                node.name: node
                for node in enclosing_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        )
    elif enclosing_module is not None:
        functions.update(
            {
                node.name: node
                for node in enclosing_module.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        )
    if enclosing_function is not None:
        functions.update(
            {
                node.name: node
                for node in ast.walk(enclosing_function)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        )
    return functions


def _command_async_result_callback_name(call: ast.Call) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != "on_result":
            continue
        callback = keyword.value
        if isinstance(callback, ast.Name):
            return callback.id
        if isinstance(callback, ast.Attribute):
            return callback.attr
    return None


def _nested_statement_bodies(statement: ast.stmt) -> list[ast.stmt]:
    bodies: list[ast.stmt] = []
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(statement, field_name, None)
        if isinstance(value, list):
            bodies.extend(node for node in value if isinstance(node, ast.stmt))
    handlers = getattr(statement, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            body = getattr(handler, "body", None)
            if isinstance(body, list):
                bodies.extend(node for node in body if isinstance(node, ast.stmt))
    return bodies


def _contains_service_backed_command(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _call_name(child.func) not in UI_SERVICE_COMMAND_METHODS:
            continue
        if _call_has_refresh_false(child):
            continue
        return True
    return False


def _execute_command_argument(node: ast.Call) -> ast.AST | None:
    if len(node.args) >= 2:
        return node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "command":
            return keyword.value
    return None


def _refresh_false_command_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_read_only_refresh_false_command(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    call_name = _call_name(node.func)
    if call_name in UI_REFRESH_FALSE_READ_ONLY_COMMANDS:
        return True
    return call_name == "SaliencyCommand" and not node.args and not node.keywords


def _contains_get_command_capability(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and _call_name(child.func) == "get_command_capability"
        for child in ast.walk(node)
    )


def _call_has_refresh_false(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg != "refresh":
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
            return True
    return False


class _PostCommandLocalRefreshVisitor(ast.NodeVisitor):
    def __init__(
        self,
        source: str,
        function_name: str = "",
        *,
        functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    ) -> None:
        self.source = source
        self.function_name = function_name
        self.functions = functions or {}
        self._visited_functions: set[str] = {function_name} if function_name else set()
        self.violations: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_missing_result_guard(node.test):
            if not _is_command_result_refresh_helper(self.function_name):
                for statement in node.body:
                    self.visit(statement)
            for statement in node.orelse:
                self.visit(statement)
            return
        if _is_failure_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if (
            call_name in UI_POST_COMMAND_LOCAL_REFRESH_METHODS
            or call_name in UI_POST_COMMAND_PUBLICATION_RENDER_METHODS
            or _publication_control_mutation_name(node) is not None
            or _publication_render_getattr_name(node) is not None
        ):
            self.violations.append(node)
            return
        method_name = _self_method_call_name(node)
        if method_name is not None and method_name not in self._visited_functions:
            target = self.functions.get(method_name)
            if target is not None:
                self._visited_functions.add(method_name)
                for statement in target.body:
                    self.visit(statement)
        self.generic_visit(node)


def _self_method_call_name(node: ast.Call) -> str | None:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "self":
        return None
    return func.attr


def _publication_control_mutation_name(node: ast.Call) -> str | None:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in UI_POST_COMMAND_PUBLICATION_CONTROL_MUTATORS:
        return None
    receiver = func.value
    if not isinstance(receiver, ast.Attribute):
        return None
    if not isinstance(receiver.value, ast.Name) or receiver.value.id != "self":
        return None
    if receiver.attr not in UI_POST_COMMAND_PUBLICATION_CONTROL_NAMES:
        return None
    return f"{receiver.attr}.{func.attr}"


def _publication_render_getattr_name(node: ast.Call) -> str | None:
    if _call_name(node.func) != "getattr" or len(node.args) < 2:
        return None
    method_name = node.args[1]
    if not isinstance(method_name, ast.Constant) or not isinstance(
        method_name.value,
        str,
    ):
        return None
    if method_name.value not in UI_POST_COMMAND_PUBLICATION_RENDER_METHODS:
        return None
    return method_name.value


def _post_command_refresh_call_name(node: ast.Call) -> str:
    return (
        _publication_control_mutation_name(node)
        or _publication_render_getattr_name(node)
        or _call_name(node.func)
    )


class _PostCommandControllerEchoVisitor(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.violations: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_missing_result_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        if _is_failure_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if (
            call_name in UI_POST_COMMAND_CONTROLLER_ECHO_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


class _CapabilityGatedControllerReadinessVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in UI_CONTROLLER_FALLBACK_WRAPPERS:
            return
        if (
            call_name in UI_CAPABILITY_GATED_CONTROLLER_READINESS_METHODS
            and _call_receiver_is_controller(node.func)
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)


def _is_failure_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Attribute):
        return node.attr == "failed"
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_is_failure_guard(value) for value in node.values)
    return False


def _is_missing_result_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Compare):
        return _is_none_failure_compare(node)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_is_missing_result_guard(value) for value in node.values)
    return False


def _is_missing_capability_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.Compare):
        return _is_capability_none_compare(node)
    if isinstance(node, ast.BoolOp):
        return any(_is_missing_capability_guard(value) for value in node.values)
    return False


def _is_command_result_refresh_helper(function_name: str) -> bool:
    return function_name.endswith("_after_command_result")


def _is_none_failure_compare(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    left_is_none = isinstance(node.left, ast.Constant) and node.left.value is None
    right_is_none = (
        isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )
    if not (left_is_none or right_is_none):
        return False
    return isinstance(node.ops[0], (ast.Is, ast.Eq))


def _is_capability_none_compare(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Is, ast.Eq)):
        return False

    left = node.left
    right = node.comparators[0]
    return (
        _is_capability_reference(left)
        and isinstance(right, ast.Constant)
        and right.value is None
    ) or (
        isinstance(left, ast.Constant)
        and left.value is None
        and _is_capability_reference(right)
    )


def _is_capability_reference(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return "capability" in node.id
    return isinstance(node, ast.Attribute) and "capability" in node.attr


def check_primary_panel_product_bootstrap_boundary(root_dir: Path) -> list[str]:
    """Keep primary product-panel construction off controller bundles."""
    violations: list[str] = []
    main_window_path = root_dir / "XBrainLab/ui/main_window.py"
    main_window_tree = _parse_python_file(main_window_path)
    if main_window_tree is None:
        return ["XBrainLab/ui/main_window.py is missing or invalid"]

    panel_specs = {
        panel_name: [
            node
            for node in ast.walk(main_window_tree)
            if isinstance(node, ast.Call)
            and _call_name(node.func) == "_PanelSpec"
            and _panel_spec_attr(node) == panel_name
        ]
        for panel_name in (
            "dataset_panel",
            "preprocess_panel",
            "training_panel",
        )
    }
    for panel_name, label in (
        ("dataset_panel", "Dataset"),
        ("preprocess_panel", "Preprocess"),
        ("training_panel", "Training"),
    ):
        specs = panel_specs[panel_name]
        if len(specs) != 1:
            violations.append(f"MainWindow must define exactly one {label} panel spec")
            continue
        controller_names = _panel_spec_controller_names(specs[0])
        if not isinstance(controller_names, ast.Tuple) or controller_names.elts:
            violations.append(
                f"{label} panel spec must have no controller requirements"
            )

    if (
        any(
            isinstance(node, ast.Attribute) and node.attr == "_workflow_controllers"
            for node in ast.walk(main_window_tree)
        )
        or any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and "controller_compatibility_bootstrap" in (ast.unparse(node) or "")
            for node in ast.walk(main_window_tree)
        )
        or any(
            isinstance(node, ast.Call)
            and (
                _call_name(node.func) == "get_controller"
                or "compatibility" in _call_name(node.func)
                or "bootstrap" in _call_name(node.func)
            )
            for node in ast.walk(main_window_tree)
        )
    ):
        violations.append(
            "MainWindow must not retain or resolve a workflow controller bundle"
        )

    init_panels = _find_class_method(main_window_tree, "MainWindow", "init_panels")
    if init_panels is None:
        violations.append("MainWindow has no init_panels method")
    elif any(
        isinstance(node, ast.Call)
        and (
            "compatibility" in _call_name(node.func)
            or "bootstrap" in _call_name(node.func)
        )
        for node in ast.walk(init_panels)
    ):
        violations.append(
            "MainWindow init_panels must defer compatibility bootstrap to Training"
        )

    materialize = _find_class_method(
        main_window_tree,
        "MainWindow",
        "_materialize_panel",
    )
    if materialize is None:
        violations.append("MainWindow has no _materialize_panel method")
    else:
        for panel_name, label in (
            ("dataset_panel", "Dataset"),
            ("preprocess_panel", "Preprocess"),
        ):
            branch = _find_panel_materialization_branch(materialize, panel_name)
            branch_nodes = (
                [child for statement in branch.body for child in ast.walk(statement)]
                if branch is not None
                else []
            )
            runtime_names = {
                target.id
                for node in branch_nodes
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _call_name(node.value.func) == "application_ui_runtime"
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            panel_call = next(
                (
                    node
                    for node in branch_nodes
                    if isinstance(node, ast.Call)
                    and _call_name(node.func)
                    in {"DatasetPanel", "PreprocessPanel", "resolved_panel_class"}
                ),
                None,
            )
            panel_keywords = (
                {
                    keyword.arg: keyword.value
                    for keyword in panel_call.keywords
                    if keyword.arg is not None
                }
                if panel_call is not None
                else {}
            )
            publication_value = panel_keywords.get("publication_port")
            if not (
                isinstance(publication_value, ast.Name)
                and publication_value.id in runtime_names
            ):
                violations.append(
                    f"MainWindow {label} product construction must inject "
                    "publication_port"
                )
            parent_value = panel_keywords.get("parent")
            if not (isinstance(parent_value, ast.Name) and parent_value.id == "self"):
                violations.append(
                    f"MainWindow {label} product construction must inject parent"
                )
            if panel_call is not None and panel_call.args:
                violations.append(
                    f"MainWindow {label} product construction passes positional "
                    "controller arguments"
                )
            if any(
                isinstance(node, ast.Attribute) and node.attr == "_workflow_controllers"
                for node in branch_nodes
            ) or any(
                isinstance(node, ast.Call)
                and (
                    _call_name(node.func) == "get_controller"
                    or "compatibility" in _call_name(node.func)
                    or "bootstrap" in _call_name(node.func)
                )
                for node in branch_nodes
            ):
                violations.append(
                    f"MainWindow {label} product construction accesses the "
                    "compatibility controller bundle"
                )
            broad_keywords = sorted(
                name
                for name in panel_keywords
                if name == "controller" or name.endswith("_controller")
            )
            if broad_keywords:
                violations.append(
                    f"MainWindow {label} product construction injects broad "
                    "controller ports: " + ", ".join(broad_keywords)
                )

        training_branch = _find_panel_materialization_branch(
            materialize,
            "training_panel",
        )
        training_nodes = (
            [
                child
                for statement in training_branch.body
                for child in ast.walk(statement)
            ]
            if training_branch is not None
            else []
        )
        runtime_names = {
            target.id
            for node in training_nodes
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _call_name(node.value.func) == "application_ui_runtime"
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        panel_call = next(
            (
                node
                for node in training_nodes
                if isinstance(node, ast.Call)
                and _call_name(node.func) in {"TrainingPanel", "resolved_panel_class"}
            ),
            None,
        )
        panel_keywords = (
            {
                keyword.arg: keyword.value
                for keyword in panel_call.keywords
                if keyword.arg is not None
            }
            if panel_call is not None
            else {}
        )
        for port_name in ("query_port", "publication_port", "action_port"):
            value = panel_keywords.get(port_name)
            if not (isinstance(value, ast.Name) and value.id in runtime_names):
                violations.append(
                    f"MainWindow Training product construction must inject {port_name}"
                )
        transient_value = panel_keywords.get("transient_port")
        if not (
            isinstance(transient_value, ast.Call)
            and _call_name(transient_value.func) == "training_transient_ui_port"
        ):
            violations.append(
                "MainWindow Training product construction must inject transient_port"
            )
        if panel_call is not None and panel_call.args:
            violations.append(
                "MainWindow Training product construction passes positional "
                "controller arguments"
            )
        broad_keywords = sorted(
            name
            for name in panel_keywords
            if name == "controller" or name.endswith("_controller")
        )
        if broad_keywords:
            violations.append(
                "MainWindow Training product construction injects broad controller "
                "ports: " + ", ".join(broad_keywords)
            )

    for panel_name, class_name, label in (
        ("dataset", "DatasetPanel", "DatasetPanel"),
        ("preprocess", "PreprocessPanel", "PreprocessPanel"),
        ("training", "TrainingPanel", "TrainingPanel"),
    ):
        panel_path = root_dir / f"XBrainLab/ui/panels/{panel_name}/panel.py"
        panel_tree = _parse_python_file(panel_path)
        initializer = (
            _find_class_method(panel_tree, class_name, "__init__")
            if panel_tree is not None
            else None
        )
        if initializer is None:
            violations.append(f"{label} has no explicit constructor")
            continue
        compatibility_calls = [
            node
            for node in ast.walk(initializer)
            if isinstance(node, ast.Call)
            and _call_name(node.func) == "get_controller_for_compatibility_context"
        ]
        for call in compatibility_calls:
            compatibility_gated = any(
                isinstance(candidate, ast.If)
                and call in ast.walk(candidate)
                and (
                    _test_compares_name_to_none(
                        candidate.test,
                        "publication_port",
                    )
                    or (
                        label == "TrainingPanel"
                        and any(
                            isinstance(test_node, ast.Attribute)
                            and test_node.attr == "_typed_port_mode"
                            for test_node in ast.walk(candidate.test)
                        )
                    )
                )
                for candidate in ast.walk(initializer)
            )
            if not compatibility_gated:
                violations.append(
                    f"{label} compatibility lookup must be gated by "
                    "publication_port is None"
                )
                break

    return violations


def _test_compares_name_to_none(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(candidate, ast.Compare)
        and len(candidate.ops) == 1
        and isinstance(candidate.ops[0], (ast.Is, ast.Eq))
        and len(candidate.comparators) == 1
        and (
            (
                isinstance(candidate.left, ast.Name)
                and candidate.left.id == name
                and isinstance(candidate.comparators[0], ast.Constant)
                and candidate.comparators[0].value is None
            )
            or (
                isinstance(candidate.left, ast.Constant)
                and candidate.left.value is None
                and isinstance(candidate.comparators[0], ast.Name)
                and candidate.comparators[0].id == name
            )
        )
        for candidate in ast.walk(node)
    )


def check_primary_ui_publication_refresh_boundary(root_dir: Path) -> list[str]:
    """Protect primary workflow panels from split product refresh truth."""
    violations = _check_application_publication_render_ledger(root_dir)
    panels_root = root_dir / "XBrainLab/ui/panels"
    for candidate in sorted(panels_root.rglob("*.py")):
        tree = _parse_python_file(candidate)
        if tree is None:
            continue
        violations.extend(
            f"{candidate.relative_to(root_dir)}:{node.lineno} retains "
            f"command-result refresh helper {node.name}"
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "after_command_result" in node.name
        )

    panel_specs = {
        "dataset": "DatasetPanel",
        "preprocess": "PreprocessPanel",
        "training": "TrainingPanel",
    }
    for panel_name, class_name in panel_specs.items():
        panel_path = root_dir / f"XBrainLab/ui/panels/{panel_name}/panel.py"
        tree = _parse_python_file(panel_path)
        if tree is None:
            violations.append(
                f"{panel_path.relative_to(root_dir)} is missing or invalid"
            )
            continue
        panel_class = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == class_name
            ),
            None,
        )
        if panel_class is None:
            violations.append(f"{panel_path.relative_to(root_dir)} has no {class_name}")
            continue

        initializer = _find_class_method(tree, class_name, "__init__")
        parameters = (
            {
                argument.arg: argument
                for argument in (
                    *initializer.args.posonlyargs,
                    *initializer.args.args,
                    *initializer.args.kwonlyargs,
                )
            }
            if initializer is not None
            else {}
        )
        publication_parameter = parameters.get("publication_port")
        expected_publication_port = (
            "TrainingPublicationPort"
            if class_name == "TrainingPanel"
            else "ApplicationViewPublicationPort"
        )
        if publication_parameter is None or (
            expected_publication_port
            not in _annotation_class_names(publication_parameter.annotation)
        ):
            violations.append(
                f"{class_name} must declare publication_port: "
                f"{expected_publication_port}"
            )

        setup = _find_class_method(tree, class_name, "_setup_bridges")
        publication_branch = (
            next(
                (
                    statement
                    for statement in setup.body
                    if isinstance(statement, ast.If)
                    and any(
                        isinstance(candidate, ast.Attribute)
                        and candidate.attr
                        == (
                            "_typed_port_mode"
                            if class_name == "TrainingPanel"
                            else "_publication_port"
                        )
                        for candidate in ast.walk(statement.test)
                    )
                ),
                None,
            )
            if setup is not None
            else None
        )
        if publication_branch is None:
            violations.append(
                f"{class_name} has no publication-first compatibility boundary"
            )
        else:
            bridge_events = {
                _annotation_terminal_name(call.args[1])
                or _string_constant(call.args[1])
                or ""
                for call in ast.walk(publication_branch)
                if isinstance(call, ast.Call)
                and _call_name(call.func) == "_create_bridge"
                and len(call.args) > 1
            }
            allowed_events = {"APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT"}
            if class_name == "TrainingPanel":
                allowed_events.update(
                    {"training_updated", "TRAINING_PROGRESS_UPDATED_EVENT"}
                )
            if "APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT" not in bridge_events:
                violations.append(
                    f"{class_name} does not subscribe to application publication"
                )
            unexpected_events = sorted(bridge_events - allowed_events)
            if unexpected_events:
                violations.append(
                    f"{class_name} product branch subscribes to state observer(s): "
                    + ", ".join(unexpected_events)
                )
            if not any(
                isinstance(node, ast.Return) for node in publication_branch.body
            ):
                violations.append(
                    f"{class_name} publication branch does not exclude compatibility "
                    "controller observers"
                )

        handler = _find_class_method(
            tree,
            class_name,
            "_on_application_view_publication_changed",
        )
        if not _method_calls_application_render_ledger(handler, "queue"):
            violations.append(
                f"{class_name} has no monotonic publication revision gate"
            )
            violations.append(f"{class_name} has no queued publication refresh")
        cleanup = _find_class_method(tree, class_name, "cleanup")
        if not _method_calls_application_render_ledger(cleanup, "cleanup"):
            violations.append(
                f"{class_name} cleanup does not cancel publication retries"
            )

    capabilities_path = root_dir / "XBrainLab/ui/application_capabilities.py"
    capabilities_tree = _parse_python_file(capabilities_path)
    if capabilities_tree is None:
        violations.append(
            "XBrainLab/ui/application_capabilities.py is missing or invalid"
        )
    else:
        forbidden_refresh_calls = {
            "begin_command_refresh_suppression",
            "complete_command_refresh_suppression",
            "end_command_refresh_suppression",
            "refresh_after_command",
            "refresh_after_serialized_command",
            "suppress_observer_refresh_during_command",
        }
        used_forbidden = sorted(
            {
                _call_name(node.func)
                for node in ast.walk(capabilities_tree)
                if isinstance(node, ast.Call)
                and _call_name(node.func) in forbidden_refresh_calls
            }
        )
        imported_forbidden = sorted(
            {
                alias.name
                for node in ast.walk(capabilities_tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
                if alias.name in forbidden_refresh_calls
            }
        )
        if used_forbidden or imported_forbidden:
            violations.append(
                "application_capabilities reintroduces command-result refresh: "
                + ", ".join(sorted({*used_forbidden, *imported_forbidden}))
            )
        async_helper = next(
            (
                node
                for node in capabilities_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "execute_application_command_async"
            ),
            None,
        )
        runner_calls = (
            [
                node
                for node in ast.walk(async_helper)
                if isinstance(node, ast.Call)
                and _call_name(node.func) == "QtApplicationCommandRunner"
            ]
            if async_helper is not None
            else []
        )
        if not runner_calls or any(
            not any(
                keyword.arg == "refresh"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
                for keyword in call.keywords
            )
            for call in runner_calls
        ):
            violations.append(
                "async application commands must disable command-result refresh"
            )

    refresh_path = root_dir / "XBrainLab/ui/refresh_coordinator.py"
    refresh_tree = _parse_python_file(refresh_path)
    guarded_functions = {
        "refresh_after_command",
        "refresh_after_observer",
        "complete_command_refresh_suppression",
        "suppress_observer_refresh_during_command",
        "begin_command_refresh_suppression",
        "end_command_refresh_suppression",
    }
    if refresh_tree is None:
        violations.append("XBrainLab/ui/refresh_coordinator.py is missing or invalid")
    else:
        functions = {
            node.name: node
            for node in refresh_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name in sorted(guarded_functions):
            function = functions.get(function_name)
            if function is None or not any(
                isinstance(node, ast.Call)
                and _call_name(node.func) == "_has_revisioned_application_context"
                for node in ast.walk(function)
            ):
                violations.append(
                    f"refresh_coordinator.{function_name} has no real Study guard"
                )

    agent_manager_path = root_dir / "XBrainLab/ui/components/agent_manager.py"
    agent_manager_tree = _parse_python_file(agent_manager_path)
    if agent_manager_tree is not None:
        forbidden_agent_refresh = {
            "begin_command_refresh_suppression",
            "complete_command_refresh_suppression",
            "end_command_refresh_suppression",
            "refresh_after_command",
            "refresh_after_serialized_command",
            "suppress_observer_refresh_during_command",
        }
        used_forbidden = {
            _call_name(node.func)
            for node in ast.walk(agent_manager_tree)
            if isinstance(node, ast.Call)
            and _call_name(node.func) in forbidden_agent_refresh
        }
        imported_forbidden = {
            alias.name
            for node in ast.walk(agent_manager_tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name in forbidden_agent_refresh
        }
        if used_forbidden or imported_forbidden:
            violations.append(
                "AgentManager must not own application refresh suppression or "
                "command-result refresh; revisioned application publication is "
                "the product refresh truth: "
                + ", ".join(sorted({*used_forbidden, *imported_forbidden}))
            )
        forbidden_delivery_calls = {
            "acknowledge_view_publication_delivery",
            "reject_view_publication_delivery",
        }
        used_delivery_calls = {
            _call_name(node.func)
            for node in ast.walk(agent_manager_tree)
            if isinstance(node, ast.Call)
            and _call_name(node.func) in forbidden_delivery_calls
        }
        application_bridge_owns_acknowledgement = any(
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Attribute)
                and target.attr == "_application_publication_bridge"
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
            and isinstance(node.value, ast.Call)
            and any(
                keyword.arg == "require_slot_acknowledgement"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.value.keywords
            )
            for node in ast.walk(agent_manager_tree)
        )
        if used_delivery_calls or application_bridge_owns_acknowledgement:
            details = sorted(used_delivery_calls)
            if application_bridge_owns_acknowledgement:
                details.append("require_slot_acknowledgement=True")
            violations.append(
                "AgentManager must not acknowledge or reject global application "
                "publication delivery; DesktopApplicationPublicationRenderer is "
                "the sole desktop acknowledgement owner: " + ", ".join(details)
            )
    return violations


def _method_calls_application_render_ledger(
    method: ast.FunctionDef | ast.AsyncFunctionDef | None,
    method_name: str,
) -> bool:
    return bool(
        method is not None
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "_application_render_ledger"
            for node in ast.walk(method)
        )
    )


def _check_application_publication_render_ledger(root_dir: Path) -> list[str]:
    """Require one bounded queued-render implementation for panel consumers."""
    helper_path = root_dir / "XBrainLab/ui/application_publication_renderer.py"
    tree = _parse_python_file(helper_path)
    if tree is None:
        return [
            "XBrainLab/ui/application_publication_renderer.py is missing or invalid"
        ]
    ledger_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "ApplicationPublicationRenderLedger"
        ),
        None,
    )
    if ledger_class is None:
        return ["ApplicationPublicationRenderLedger is missing"]

    violations: list[str] = []
    queue = _find_class_method(
        tree,
        "ApplicationPublicationRenderLedger",
        "queue",
    )
    if queue is None or not any(
        isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.LtE) for operator in node.ops)
        and any(
            isinstance(candidate, ast.Attribute)
            and candidate.attr == "_last_rendered_revision"
            for candidate in ast.walk(node)
        )
        for node in ast.walk(queue or ast.Pass())
    ):
        violations.append("ApplicationPublicationRenderLedger has no revision gate")

    failed_attempt = _find_class_method(
        tree,
        "ApplicationPublicationRenderLedger",
        "_record_failed_attempt",
    )
    retry_interval = _find_class_method(
        tree,
        "ApplicationPublicationRenderLedger",
        "_retry_interval",
    )
    bounded_retry = bool(
        failed_attempt is not None
        and any(
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "_attempts"
            and isinstance(node.op, ast.Add)
            for node in ast.walk(failed_attempt)
        )
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "start"
            and any(
                isinstance(candidate, ast.Call)
                and isinstance(candidate.func, ast.Attribute)
                and candidate.func.attr == "_retry_interval"
                for candidate in ast.walk(node)
            )
            for node in ast.walk(failed_attempt)
        )
        and retry_interval is not None
        and any(
            isinstance(node, ast.Compare)
            and any(isinstance(operator, ast.GtE) for operator in node.ops)
            and any(
                isinstance(candidate, ast.Name)
                and candidate.id == "PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS"
                for candidate in ast.walk(node)
            )
            for node in ast.walk(retry_interval)
        )
        and all(
            any(
                isinstance(node, ast.Name) and node.id == interval_name
                for node in ast.walk(retry_interval)
            )
            for interval_name in (
                "PANEL_PUBLICATION_RENDER_RETRY_INTERVAL_MS",
                "PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS",
            )
        )
    )
    if not bounded_retry:
        violations.append(
            "ApplicationPublicationRenderLedger has no bounded delayed retry"
        )

    cleanup = _find_class_method(
        tree,
        "ApplicationPublicationRenderLedger",
        "cleanup",
    )
    if cleanup is None or not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "stop"
        for node in ast.walk(cleanup or ast.Pass())
    ):
        violations.append(
            "ApplicationPublicationRenderLedger cleanup does not stop its timer"
        )
    return violations


def check_evaluation_publication_refresh_boundary(root_dir: Path) -> list[str]:
    """Protect Evaluation's narrow publication-owned UI boundary."""
    violations: list[str] = []
    panel_path = root_dir / "XBrainLab/ui/panels/evaluation/panel.py"
    main_window_path = root_dir / "XBrainLab/ui/main_window.py"
    refresh_path = root_dir / "XBrainLab/ui/refresh_coordinator.py"

    panel_source = panel_path.read_text(encoding="utf-8")
    panel_tree = ast.parse(panel_source)
    evaluation_class = next(
        (
            node
            for node in panel_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "EvaluationPanel"
        ),
        None,
    )
    if evaluation_class is None:
        return ["XBrainLab/ui/panels/evaluation/panel.py has no EvaluationPanel"]

    initializer = next(
        (
            node
            for node in evaluation_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__init__"
        ),
        None,
    )
    expected_ports = {
        "query_port": "EvaluationQueryPort",
        "publication_port": "ApplicationPublicationSubscriptionPort",
        "action_port": "EvaluationActionPort",
    }
    if initializer is None:
        violations.append("EvaluationPanel has no explicit typed constructor")
    else:
        parameters = {
            parameter.arg: parameter
            for parameter in (
                *initializer.args.posonlyargs,
                *initializer.args.args,
                *initializer.args.kwonlyargs,
            )
        }
        broad_parameters = sorted(
            name
            for name in parameters
            if "controller" in name or name == "application_runtime"
        )
        if initializer.args.vararg is not None:
            broad_parameters.append(f"*{initializer.args.vararg.arg}")
        if initializer.args.kwarg is not None:
            broad_parameters.append(f"**{initializer.args.kwarg.arg}")
        if broad_parameters:
            violations.append(
                "EvaluationPanel constructor accepts broad parameters: "
                + ", ".join(broad_parameters)
            )
        for parameter_name, annotation_name in expected_ports.items():
            parameter = parameters.get(parameter_name)
            annotation_names = (
                _annotation_class_names(parameter.annotation)
                if parameter is not None
                else set()
            )
            if annotation_name not in annotation_names:
                violations.append(
                    "EvaluationPanel must declare narrow port "
                    f"{parameter_name}: {annotation_name}"
                )

    for node in ast.walk(evaluation_class):
        if isinstance(node, ast.Attribute) and node.attr.endswith("_controller"):
            violations.append(
                f"EvaluationPanel stores broad controller attribute {node.attr}"
            )
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in {"get_controller", "_create_refresh_bridge"}:
            violations.append(
                f"EvaluationPanel uses forbidden controller refresh path {call_name}()"
            )
        if call_name == "_create_bridge":
            event_arg = node.args[1] if len(node.args) > 1 else None
            if not (
                isinstance(event_arg, ast.Name)
                and event_arg.id == "APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT"
            ):
                violations.append(
                    "EvaluationPanel subscribes to a non-application publication event"
                )

    revision_gate = any(
        isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.LtE) for operator in node.ops)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "revision"
        and any(
            isinstance(comparator, ast.Attribute)
            and comparator.attr == "_last_application_revision"
            for comparator in node.comparators
        )
        for node in ast.walk(evaluation_class)
    )
    if not revision_gate:
        violations.append("EvaluationPanel has no monotonic application revision gate")
    publication_handler = _find_class_method(
        panel_tree,
        "EvaluationPanel",
        "_on_application_view_publication_changed",
    )
    if not _method_calls_application_render_ledger(publication_handler, "queue"):
        violations.append(
            "EvaluationPanel has no queued application publication ledger"
        )
    evaluation_cleanup = _find_class_method(
        panel_tree,
        "EvaluationPanel",
        "cleanup",
    )
    if not _method_calls_application_render_ledger(evaluation_cleanup, "cleanup"):
        violations.append("EvaluationPanel cleanup does not cancel publication retries")

    main_window_tree = ast.parse(main_window_path.read_text(encoding="utf-8"))
    evaluation_specs = [
        node
        for node in ast.walk(main_window_tree)
        if isinstance(node, ast.Call)
        and _call_name(node.func) == "_PanelSpec"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "evaluation_panel"
    ]
    if len(evaluation_specs) != 1:
        violations.append("MainWindow must define exactly one Evaluation panel spec")
    else:
        spec = evaluation_specs[0]
        controller_names = spec.args[4] if len(spec.args) > 4 else None
        if not isinstance(controller_names, ast.Tuple) or controller_names.elts:
            violations.append(
                "MainWindow Evaluation panel spec must have no controller requirements"
            )

    materialize_method = _find_class_method(
        main_window_tree,
        "MainWindow",
        "_materialize_panel",
    )
    evaluation_branch = (
        _find_panel_materialization_branch(
            materialize_method,
            "evaluation_panel",
        )
        if materialize_method is not None
        else None
    )
    branch_nodes = (
        [child for statement in evaluation_branch.body for child in ast.walk(statement)]
        if evaluation_branch is not None
        else []
    )
    runtime_names = {
        target.id
        for node in branch_nodes
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and _call_name(node.value.func) == "application_ui_runtime"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    panel_call = next(
        (
            node
            for node in branch_nodes
            if isinstance(node, ast.Call)
            and _call_name(node.func) in {"EvaluationPanel", "resolved_panel_class"}
        ),
        None,
    )
    panel_keywords = (
        {
            keyword.arg: keyword.value
            for keyword in panel_call.keywords
            if keyword.arg is not None
        }
        if panel_call is not None
        else {}
    )
    for port_name in expected_ports:
        port_value = panel_keywords.get(port_name)
        if not (isinstance(port_value, ast.Name) and port_value.id in runtime_names):
            violations.append(
                f"MainWindow Evaluation construction must inject {port_name}"
            )
    parent_value = panel_keywords.get("parent")
    if not (isinstance(parent_value, ast.Name) and parent_value.id == "self"):
        violations.append("MainWindow Evaluation construction must inject parent")
    if panel_call is not None and panel_call.args:
        violations.append(
            "MainWindow Evaluation construction must not pass positional ports"
        )
    violations.extend(
        (f"MainWindow Evaluation construction injects broad {broad_name}")
        for broad_name in ("controller", "controllers", "application_runtime")
        if broad_name in panel_keywords
    )

    refresh_tree = ast.parse(refresh_path.read_text(encoding="utf-8"))
    panel_names_function = next(
        (
            node
            for node in refresh_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_panel_names_for"
        ),
        None,
    )
    if panel_names_function is None:
        violations.append("refresh_coordinator has no command-result panel router")
    else:
        appends_evaluation = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "evaluation_panel"
            for node in ast.walk(panel_names_function)
        )
        excludes_unknown_evaluation = any(
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "panel_name"
            and len(node.ops) == 1
            and len(node.comparators) == 1
            and (
                (
                    isinstance(node.ops[0], ast.NotEq)
                    and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == "evaluation_panel"
                )
                or (
                    isinstance(node.ops[0], ast.NotIn)
                    and isinstance(
                        node.comparators[0],
                        (ast.Set, ast.Tuple, ast.List),
                    )
                    and any(
                        isinstance(element, ast.Constant)
                        and element.value == "evaluation_panel"
                        for element in node.comparators[0].elts
                    )
                )
            )
            for node in ast.walk(panel_names_function)
        )
        if appends_evaluation or not excludes_unknown_evaluation:
            violations.append("Generic command-result refresh must exclude Evaluation")

    return violations


def check_visualization_publication_refresh_boundary(root_dir: Path) -> list[str]:
    """Protect Visualization's narrow publication-owned UI boundary."""
    violations: list[str] = []
    panel_path = root_dir / "XBrainLab/ui/panels/visualization/panel.py"
    main_window_path = root_dir / "XBrainLab/ui/main_window.py"
    refresh_path = root_dir / "XBrainLab/ui/refresh_coordinator.py"

    panel_tree = _parse_python_file(panel_path)
    if panel_tree is None:
        return ["XBrainLab/ui/panels/visualization/panel.py is missing or invalid"]
    visualization_class = next(
        (
            node
            for node in panel_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "VisualizationPanel"
        ),
        None,
    )
    if visualization_class is None:
        return ["XBrainLab/ui/panels/visualization/panel.py has no VisualizationPanel"]

    initializer = next(
        (
            node
            for node in visualization_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__init__"
        ),
        None,
    )
    expected_ports = {
        "query_port": "VisualizationQueryPort",
        "publication_port": "VisualizationPublicationPort",
        "action_port": "VisualizationActionPort",
    }
    if initializer is None:
        violations.append("VisualizationPanel has no explicit typed constructor")
    else:
        parameters = {
            parameter.arg: parameter
            for parameter in (
                *initializer.args.posonlyargs,
                *initializer.args.args,
                *initializer.args.kwonlyargs,
            )
        }
        broad_parameters = sorted(
            name
            for name in parameters
            if "controller" in name or name == "application_runtime"
        )
        if initializer.args.vararg is not None:
            broad_parameters.append(f"*{initializer.args.vararg.arg}")
        if initializer.args.kwarg is not None:
            broad_parameters.append(f"**{initializer.args.kwarg.arg}")
        if broad_parameters:
            violations.append(
                "VisualizationPanel accepts broad constructor parameter(s): "
                + ", ".join(broad_parameters)
            )
        for parameter_name, annotation_name in expected_ports.items():
            parameter = parameters.get(parameter_name)
            annotation_names = (
                _annotation_class_names(parameter.annotation)
                if parameter is not None
                else set()
            )
            if annotation_name not in annotation_names:
                violations.append(
                    "VisualizationPanel must declare narrow port "
                    f"{parameter_name}: {annotation_name}"
                )

    for node in ast.walk(visualization_class):
        if isinstance(node, ast.Attribute) and (
            node.attr == "controller" or node.attr.endswith("_controller")
        ):
            violations.append(
                f"VisualizationPanel stores broad controller attribute {node.attr}"
            )
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in {
            "get_controller",
            "_create_refresh_bridge",
            "refresh_after_observer",
        }:
            violations.append(
                f"VisualizationPanel uses forbidden refresh path {call_name}()"
            )
        if call_name != "_create_bridge":
            continue
        event_arg = (
            node.args[1]
            if len(node.args) > 1
            else next(
                (
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg in {"event", "event_name"}
                ),
                None,
            )
        )
        event_name = (
            _annotation_terminal_name(event_arg) if event_arg is not None else ""
        )
        if event_name != "APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT":
            violations.append(
                "VisualizationPanel subscribes to a non-application publication event"
            )

    publication_handler = next(
        (
            node
            for node in visualization_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_on_application_view_publication_changed"
        ),
        None,
    )
    revision_gate = bool(
        publication_handler is not None
        and any(
            isinstance(node, ast.Compare)
            and any(isinstance(operator, ast.LtE) for operator in node.ops)
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "revision"
            and any(
                isinstance(comparator, ast.Attribute)
                and comparator.attr == "_last_application_revision"
                for comparator in node.comparators
            )
            for node in ast.walk(publication_handler)
        )
    )
    if not revision_gate:
        violations.append(
            "VisualizationPanel has no monotonic application revision gate"
        )

    if not _method_calls_application_render_ledger(publication_handler, "queue"):
        violations.append(
            "VisualizationPanel has no queued application publication refresh"
        )
    visualization_cleanup = _find_class_method(
        panel_tree,
        "VisualizationPanel",
        "cleanup",
    )
    if not _method_calls_application_render_ledger(
        visualization_cleanup,
        "cleanup",
    ):
        violations.append(
            "VisualizationPanel cleanup does not cancel publication retries"
        )
    if publication_handler is not None and any(
        isinstance(node, ast.Call) and _call_name(node.func) == "update_panel"
        for node in ast.walk(publication_handler)
    ):
        violations.append(
            "VisualizationPanel publication handler must not refresh inline"
        )

    main_window_tree = _parse_python_file(main_window_path)
    if main_window_tree is None:
        violations.append("XBrainLab/ui/main_window.py is missing or invalid")
    else:
        visualization_specs = [
            node
            for node in ast.walk(main_window_tree)
            if isinstance(node, ast.Call)
            and _call_name(node.func) == "_PanelSpec"
            and _panel_spec_attr(node) == "visualization_panel"
        ]
        if len(visualization_specs) != 1:
            violations.append(
                "MainWindow must define exactly one Visualization panel spec"
            )
        else:
            controller_names = _panel_spec_controller_names(visualization_specs[0])
            if not isinstance(controller_names, ast.Tuple) or controller_names.elts:
                violations.append(
                    "MainWindow Visualization panel spec must have no "
                    "controller requirements"
                )

        materialize_method = _find_class_method(
            main_window_tree,
            "MainWindow",
            "_materialize_panel",
        )
        visualization_branch = (
            _find_panel_materialization_branch(
                materialize_method,
                "visualization_panel",
            )
            if materialize_method is not None
            else None
        )
        branch_nodes = (
            [
                child
                for statement in visualization_branch.body
                for child in ast.walk(statement)
            ]
            if visualization_branch is not None
            else []
        )
        runtime_names = {
            target.id
            for node in branch_nodes
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _call_name(node.value.func) == "application_ui_runtime"
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        panel_call = next(
            (
                node
                for node in branch_nodes
                if isinstance(node, ast.Call)
                and _call_name(node.func)
                in {
                    "VisualizationPanel",
                    "resolved_panel_class",
                }
            ),
            None,
        )
        panel_keywords = (
            {
                keyword.arg: keyword.value
                for keyword in panel_call.keywords
                if keyword.arg is not None
            }
            if panel_call is not None
            else {}
        )
        for port_name in expected_ports:
            port_value = panel_keywords.get(port_name)
            if not (
                isinstance(port_value, ast.Name) and port_value.id in runtime_names
            ):
                violations.append(
                    f"MainWindow Visualization construction must inject {port_name}"
                )
        violations.extend(
            (f"MainWindow Visualization construction injects broad {broad_name}")
            for broad_name in ("controller", "controllers", "application_runtime")
            if broad_name in panel_keywords
        )

    refresh_tree = _parse_python_file(refresh_path)
    if refresh_tree is None:
        violations.append("XBrainLab/ui/refresh_coordinator.py is missing or invalid")
    else:
        panel_names_function = next(
            (
                node
                for node in refresh_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_panel_names_for"
            ),
            None,
        )
        changed_state_routes_visualization = (
            panel_names_function is None
            or _function_routes_to_panel(
                panel_names_function,
                "visualization_panel",
            )
            or not _function_excludes_panel_for_unknown_state(
                panel_names_function,
                "visualization_panel",
            )
        )
        if changed_state_routes_visualization:
            violations.append(
                "refresh_coordinator changed-state refresh must exclude Visualization"
            )

        observer_function = next(
            (
                node
                for node in refresh_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_panel_names_for_observer_event"
            ),
            None,
        )
        observer_routes_visualization = (
            observer_function is None
            or _function_routes_to_panel(
                observer_function,
                "visualization_panel",
            )
            or _observer_router_has_unowned_return(observer_function)
            or _named_mapping_contains_panel(
                refresh_tree,
                "_OBSERVER_EVENT_REFRESH_ROUTES",
                "visualization_panel",
            )
            or _named_mapping_contains_panel(
                refresh_tree,
                "_OBSERVER_EVENT_PANEL_OVERRIDES",
                "visualization_panel",
            )
        )
        if observer_routes_visualization:
            violations.append(
                "refresh_coordinator observer refresh must exclude Visualization"
            )

    return violations


def _panel_spec_attr(call: ast.Call) -> str | None:
    if call.args:
        return _string_constant(call.args[0])
    return next(
        (
            _string_constant(keyword.value)
            for keyword in call.keywords
            if keyword.arg == "attr"
        ),
        None,
    )


def _panel_spec_controller_names(call: ast.Call) -> ast.AST | None:
    if len(call.args) > 4:
        return call.args[4]
    return next(
        (
            keyword.value
            for keyword in call.keywords
            if keyword.arg == "controller_names"
        ),
        None,
    )


def _find_panel_materialization_branch(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    panel_name: str,
) -> ast.If | None:
    candidates = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Constant) and candidate.value == panel_name
            for candidate in ast.walk(node.test)
        )
        and any(
            isinstance(candidate, ast.Attribute) and candidate.attr == "attr"
            for candidate in ast.walk(node.test)
        )
    ]
    return next(
        (
            candidate
            for candidate in candidates
            if any(
                isinstance(node, ast.Call)
                and (
                    _call_name(node.func) == "resolved_panel_class"
                    or _call_name(node.func).endswith("Panel")
                )
                for statement in candidate.body
                for node in ast.walk(statement)
            )
        ),
        candidates[0] if candidates else None,
    )


def _function_routes_to_panel(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    panel_name: str,
) -> bool:
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"append", "extend", "insert"}
            and any(
                _positive_panel_literal(argument, panel_name) for argument in node.args
            )
        ):
            return True
        if (
            isinstance(node, ast.Return)
            and node.value is not None
            and _positive_panel_literal(node.value, panel_name)
        ):
            return True
    return False


def _positive_panel_literal(node: ast.AST, panel_name: str) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == panel_name
    if isinstance(node, ast.Compare):
        return False
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return _positive_panel_literal(node.elt, panel_name)
    if isinstance(node, ast.DictComp):
        return _positive_panel_literal(
            node.key,
            panel_name,
        ) or _positive_panel_literal(node.value, panel_name)
    return any(
        _positive_panel_literal(child, panel_name)
        for child in ast.iter_child_nodes(node)
    )


def _function_excludes_panel_for_unknown_state(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    panel_name: str,
) -> bool:
    return any(
        isinstance(node, ast.Compare)
        and any(isinstance(operator, (ast.NotEq, ast.NotIn)) for operator in node.ops)
        and any(
            isinstance(candidate, ast.Constant) and candidate.value == panel_name
            for comparator in node.comparators
            for candidate in ast.walk(comparator)
        )
        for node in ast.walk(function)
    )


def _observer_router_has_unowned_return(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = node.value
        if isinstance(value, ast.Call) and _call_name(value.func) == "_panel_names_for":
            continue
        if (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id == "_OBSERVER_EVENT_PANEL_OVERRIDES"
        ):
            continue
        return True
    return False


def _named_mapping_contains_panel(
    tree: ast.Module,
    mapping_name: str,
    panel_name: str,
) -> bool:
    for node in tree.body:
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == mapping_name
                for target in node.targets
            )
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == mapping_name
        ):
            value = node.value
        if value is not None and any(
            isinstance(candidate, ast.Constant) and candidate.value == panel_name
            for candidate in ast.walk(value)
        ):
            return True
    return False


def test_repository_architecture_compliance():
    """Pytest entry point for the repo architecture compliance gate."""
    root_dir = Path(__file__).resolve().parents[1]
    assert check_architecture(str(root_dir)) == 0


if __name__ == "__main__":
    sys.exit(check_architecture(os.getcwd()))
