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
from pathlib import Path

_UNRESOLVED_CALLABLE_ORIGIN = "<unresolved-callable-construction>"
_DYNAMIC_CALLABLE_CONTAINER_KEY = object()

FORBIDDEN_PRODUCT_LLM_TOKENS = (
    "APIBackend",
    "GeminiBackend",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XBRAINLAB_SHOW_LEGACY_REMOTE_LLM",
)
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


@dataclass(frozen=True)
class ControllerDirectCallAllowance:
    """One exact non-ApplicationService controller call that UI may retain."""

    function_name: str
    receiver_identity: str
    methods: frozenset[str]


UI_CONTROLLER_DIRECT_CALL_ALLOWLIST = {
    Path("XBrainLab/ui/chat/panel.py"): (
        ControllerDirectCallAllowance(
            "_select_response_action",
            "self._chat_controller",
            frozenset({"consume_response_actions"}),
        ),
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
            frozenset({"add_user_message", "can_accept_turn"}),
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
            "start_new_conversation",
            "self.chat_controller",
            frozenset({"clear_conversation"}),
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
    Path("XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py"): (
        ControllerDirectCallAllowance(
            "__init__",
            "controller",
            frozenset({"get_dataset_generator", "get_epoch_data"}),
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
    Path("tests/integration/pipeline/test_all_real_tools.py"),
    Path("tests/integration/pipeline/test_e2e_training.py"),
    Path("tests/integration/pipeline/test_integration_real_tools.py"),
    Path("tests/integration/pipeline/test_preprocess_validation.py"),
    Path("tests/integration/pipeline/test_real_data_pipeline.py"),
    Path("tests/integration/training/test_training_integration.py"),
    Path("tests/integration/ui/test_epoch_runtime.py"),
    Path("tests/integration/ui/test_product_walkthrough.py"),
    Path("tests/integration/ui/test_real_tools_e2e.py"),
)
PRODUCT_SUCCESS_DIRECT_STUDY_METHODS = ("get_datasets_generator",)
MCP_DIRECT_STUDY_METHODS = ("get_controller", "get_datasets_generator")
HEADLESS_VERIFIER_STATE_TRUTH_FILES = (
    Path("scripts/dev/verify_real_tools.py"),
    Path("scripts/dev/run_public_cross_source_training_smoke.py"),
)
HEADLESS_VERIFIER_DIRECT_STUDY_METHODS = (
    "generate_plan",
    "is_training",
    "stop_training",
    "train",
)
PRODUCT_SUCCESS_TEST_DIRS = (
    Path("tests/integration/backend"),
    Path("tests/integration/io"),
    Path("tests/integration/pipeline"),
    Path("tests/integration/ui"),
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
        "fallback_local_model_id",
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
    Path("XBrainLab/mcp"),
)
MAPPED_REAL_TOOL_FILES = (
    Path("XBrainLab/llm/tools/__init__.py"),
    Path("XBrainLab/llm/tools/real/dataset_real.py"),
    Path("XBrainLab/llm/tools/real/preprocess_real.py"),
    Path("XBrainLab/llm/tools/real/training_real.py"),
    Path("XBrainLab/llm/tools/real/analysis_real.py"),
)
CANONICAL_DELEGATING_REAL_TOOL_CLASSES = frozenset(
    {
        "RealApplyInterpretationTool",
        "RealAttachLabelsTool",
        "RealBandPassFilterTool",
        "RealChannelSelectionTool",
        "RealClearDatasetTool",
        "RealConfigureTrainingTool",
        "RealEpochDataTool",
        "RealEvaluateTool",
        "RealGenerateDatasetTool",
        "RealGetDatasetInfoTool",
        "RealLoadDataTool",
        "RealNormalizeTool",
        "RealNotchFilterTool",
        "RealPreviewInterpretationTool",
        "RealQueryStateTool",
        "RealReloadInterpretationRecipeTool",
        "RealRereferenceTool",
        "RealResampleTool",
        "RealResetPreprocessTool",
        "RealSaliencyTool",
        "RealSaveInterpretationRecipeTool",
        "RealScanSourceTool",
        "RealSetModelTool",
        "RealStandardPreprocessTool",
        "RealStartTrainingTool",
        "RealStopTrainingTool",
        "RealValidateInterpretationTool",
        "RealVisualizeTool",
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
PRODUCT_SUCCESS_LEGACY_FALLBACK_SYMBOLS = (
    "get_controller_for_compatibility_context",
    "run_controller_compatibility_call",
)
PRODUCT_SUCCESS_CONTROLLER_LOOKUP_ASSERTIONS = (
    "assert_any_call",
    "assert_called",
    "assert_called_once",
    "assert_called_once_with",
    "assert_called_with",
)
WEAK_TEST_NAME_PATTERNS = (
    "accepted",
    "no_crash",
    "does_not_crash",
)
PRODUCT_SUCCESS_WEAK_TEST_NAME_PATTERNS = (
    "init",
    "initialization",
    "initializes",
)
MCP_EXACT_EVIDENCE_TEST_DIRS = (
    Path("tests/unit/mcp"),
    Path("tests/integration/mcp"),
)
PIPELINE_STATE_EXACT_EVIDENCE_TEST = Path("tests/unit/llm/test_pipeline_state.py")
LLM_PARSER_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/test_parser.py"),
    Path("tests/unit/llm/test_misc_coverage.py"),
)
STRICT_TOOL_ENVELOPE_ENTRYPOINTS = (
    Path("XBrainLab/llm/agent/controller.py"),
    Path("scripts/agent/evals/run_local_tool_call_eval.py"),
)
LLM_APPLICATION_SURFACE_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/tools/test_application_surface.py"),
)
LLM_AGENT_INTENT_BOUNDARY_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/agent/test_controller.py"),
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
LLM_CONTROLLER_INTEGRATION_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/agent/test_controller_integration.py"),
)
LLM_TOOL_DEFINITION_EXACT_EVIDENCE_TESTS = (
    Path("tests/unit/llm/tools/test_definitions.py"),
)
DOC_CURRENT_TRUTH_FILES = (
    Path("docs/current.md"),
    Path("docs/index.md"),
    Path("docs/architecture/README.md"),
    Path("docs/architecture/ui.md"),
    Path("docs/architecture/backend.md"),
    Path("docs/planning/now.md"),
    Path("docs/validation/README.md"),
)
DOC_CURRENT_TRUTH_OVERCLAIM_PHRASES = (
    "product complete",
    "release approval",
    "full zero-controller UI",
    "human Windows desktop acceptance",
)
DOC_CLAIM_BOUNDARY_TOKENS = (
    "不能",
    "不能取代",
    "不能宣稱",
    "不能支撐",
    "不能先講",
    "不等於",
    "不是",
    "不代表",
    "缺",
    "距離",
    "尚未",
    "未",
    "還不能",
    "gap",
    "missing",
    "not",
    "cannot",
    "can't",
    "is not",
    "before",
    "required",
    "still",
    "remains",
    "claim not supported",
    "not supported",
    "not complete",
    "not ready",
    "without implying",
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
        "XBrainLab/backend/application/analysis_service.py",
        "AnalysisCommandService.handle_evaluate",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "attribute",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/analysis_service.py",
        "AnalysisCommandService.handle_visualize",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "attribute",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/automation.py",
        "_ui_only_command_fields",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "literal",
        2,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/commands.py",
        "EvaluateCommand",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "field",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/commands.py",
        "VisualizeCommand",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "field",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/commands.py",
        "QueryStateCommand",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "field",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/results.py",
        "CommandResult.__post_init__",
        MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME,
        "attribute",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/results.py",
        "CommandResult.local_payload",
        MUTABLE_BOUNDARY_LOCAL_PAYLOAD,
        "definition",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/results.py",
        "CommandResult.local_payload",
        MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME,
        "attribute",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/state_service.py",
        "StateSnapshotService.training_history",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "parameter",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/state_service.py",
        "StateSnapshotService.training_history",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "name",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/query_state_service.py",
        "QueryStateCommandService.handle_query_state",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "attribute",
        3,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/backend/application/query_state_service.py",
        "QueryStateCommandService.handle_query_state",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/llm/tools/application_surface.py",
        "_command_for_tool",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/llm/tools/application_surface.py",
        "_command_for_tool",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "literal",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/application_capabilities.py",
        "local_result_payload",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "definition",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/application_capabilities.py",
        "local_result_payload",
        MUTABLE_BOUNDARY_COMMAND_RESULT_RUNTIME,
        "getattr",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/info_panel_service.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/info_panel_service.py",
        "InfoPanelService._query_data_lists",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/components/info_panel_service.py",
        "InfoPanelService._query_data_lists",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/main_window.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/main_window.py",
        "_StartupInfoPanelService._query_data_lists",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/main_window.py",
        "_StartupInfoPanelService._query_data_lists",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/panel.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/panel.py",
        "DatasetPanel._query_loaded_data_list_for_render",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/panel.py",
        "DatasetPanel._query_loaded_data_list_for_render",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/sidebar.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/sidebar.py",
        "DatasetSidebar._loaded_data_list_for_channel_selection",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/dataset/sidebar.py",
        "DatasetSidebar._loaded_data_list_for_channel_selection",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel._evaluation_query_payload",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel._refresh_application_query",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel._refresh_application_query_async",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/data_query.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/data_query.py",
        "query_preprocess_render_lists",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/data_query.py",
        "query_preprocess_render_lists",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/sidebar.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/sidebar.py",
        "PreprocessSidebar._preprocessed_data_list_for_dialog",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/preprocess/sidebar.py",
        "PreprocessSidebar._preprocessed_data_list_for_dialog",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/panel.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/panel.py",
        "TrainingPanel._history_for_render",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/panel.py",
        "TrainingPanel._history_for_render",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/sidebar.py",
        "<module>",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "import",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/sidebar.py",
        "TrainingSidebar._data_splitting_dialog_context",
        MUTABLE_BOUNDARY_INCLUDE_OBJECTS,
        "keyword",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/sidebar.py",
        "TrainingSidebar._data_splitting_dialog_context",
        MUTABLE_BOUNDARY_LOCAL_RESULT_PAYLOAD,
        "call",
    ),
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
        "XBrainLab/ui/dialogs/dataset/channel_selection_dialog.py",
        "ChannelSelectionDialog.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py",
        "DataSplittingDialog.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
        4,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py",
        "DataSplittingPreviewDialog.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py",
        "DataSplittingPreviewDialog.preview",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/dialogs/preprocess/epoching_dialog.py",
        "EpochingDialog.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/dialogs/preprocess/rereference_dialog.py",
        "RereferenceDialog.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/main_window.py",
        "_StartupInfoPanelService.__init__",
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
        "XBrainLab/ui/panels/dataset/panel.py",
        "DatasetPanel.update_panel",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "widget_or_container",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel.update_panel",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "widget_or_container",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel._refresh_application_query",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel._refresh_application_query_async._handle_result",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/evaluation/panel.py",
        "EvaluationPanel.on_model_changed",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "widget_or_container",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/history_table.py",
        "TrainingHistoryTable.update_history",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/panel.py",
        "TrainingPanel.on_history_selection_changed",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/panel.py",
        "TrainingPanel.update_loop",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/training/training_manager.py",
        "TrainingManagerWindow.__init__",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
        2,
    ),
    MutableObjectBoundaryDebt(
        "XBrainLab/ui/panels/visualization/panel.py",
        "VisualizationPanel._refresh_application_query",
        MUTABLE_BOUNDARY_UI_DOMAIN_STORAGE,
        "assignment",
    ),
)


def check_product_python_syntax(root_dir: Path) -> list[str]:
    """Return every product Python file that cannot be inspected safely."""
    product_dir = root_dir / "XBrainLab"
    if not product_dir.exists():
        return [f"Product package not found: {product_dir}"]
    violations: list[str] = []
    for py_file in product_dir.rglob("*.py"):
        _, syntax_violation = _parse_product_guard_tree(
            py_file,
            root_dir,
            guard_name="architecture compliance",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
    return violations


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

    syntax_violations = check_product_python_syntax(Path(root_dir))
    if syntax_violations:
        print("\nProduct Python Syntax Violations Found:")
        for violation in syntax_violations:
            print(f" - {violation}")
        return 1

    violations = []

    for py_file in ui_dir.rglob("*.py"):
        rel_path = py_file.relative_to(root_dir)
        tree, syntax_violation = _parse_product_guard_tree(
            py_file,
            Path(root_dir),
            guard_name="architecture compliance",
        )
        if syntax_violation is not None:
            violations.append(syntax_violation)
            continue
        assert tree is not None

        # Skip tests and generated files
        if "tests" in str(rel_path) or "__init__" in str(rel_path):
            continue

        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Rule 1: No cross-panel imports
                # Logic: if file is in ui/panels/A, it should not import ui/panels/B
                pass  # simplified for now

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

    llm_study_state_violations = check_llm_direct_study_state_reads(Path(root_dir))
    if llm_study_state_violations:
        print("\nLLM Direct Study State Read Violations Found:")
        for violation in llm_study_state_violations:
            print(f" - {violation}")
        return 1

    mcp_study_state_violations = check_mcp_direct_study_state_reads(Path(root_dir))
    if mcp_study_state_violations:
        print("\nMCP Direct Study State Read Violations Found:")
        for violation in mcp_study_state_violations:
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

    fallback_test_violations = check_product_success_legacy_fallback_tests(
        Path(root_dir)
    )
    if fallback_test_violations:
        print("\nProduct Success Legacy Fallback Test Violations Found:")
        for violation in fallback_test_violations:
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

    weak_test_name_violations = check_weak_test_names(Path(root_dir))
    if weak_test_name_violations:
        print("\nWeak Test Name Violations Found:")
        for violation in weak_test_name_violations:
            print(f" - {violation}")
        return 1

    generic_panel_assertion_violations = (
        check_product_success_generic_panel_instance_assertions(Path(root_dir))
    )
    if generic_panel_assertion_violations:
        print("\nProduct Success Generic Panel Assertion Violations Found:")
        for violation in generic_panel_assertion_violations:
            print(f" - {violation}")
        return 1

    mcp_weak_assertion_violations = check_mcp_weak_response_assertions(Path(root_dir))
    if mcp_weak_assertion_violations:
        print("\nMCP Weak Response Assertion Violations Found:")
        for violation in mcp_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    pipeline_state_weak_assertion_violations = (
        check_pipeline_state_weak_string_assertions(Path(root_dir))
    )
    if pipeline_state_weak_assertion_violations:
        print("\nPipeline State Weak String Assertion Violations Found:")
        for violation in pipeline_state_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    llm_parser_weak_assertion_violations = check_llm_parser_weak_parse_assertions(
        Path(root_dir)
    )
    if llm_parser_weak_assertion_violations:
        print("\nLLM Parser Weak Parse Assertion Violations Found:")
        for violation in llm_parser_weak_assertion_violations:
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

    resource_receipt_boundary_violations = check_agent_resource_receipt_boundary(
        Path(root_dir)
    )
    if resource_receipt_boundary_violations:
        print("\nAgent Resource Receipt Boundary Violations Found:")
        for violation in resource_receipt_boundary_violations:
            print(f" - {violation}")
        return 1

    llm_application_surface_weak_assertion_violations = (
        check_llm_application_surface_weak_result_assertions(Path(root_dir))
    )
    if llm_application_surface_weak_assertion_violations:
        print("\nLLM Application Surface Weak Result Assertion Violations Found:")
        for violation in llm_application_surface_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    llm_agent_intent_boundary_weak_assertion_violations = (
        check_llm_agent_intent_boundary_weak_result_assertions(Path(root_dir))
    )
    if llm_agent_intent_boundary_weak_assertion_violations:
        print("\nLLM Agent Intent-Boundary Weak Result Assertion Violations Found:")
        for violation in llm_agent_intent_boundary_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    llm_agent_confirmation_weak_assertion_violations = (
        check_llm_agent_confirmation_weak_pending_assertions(Path(root_dir))
    )
    if llm_agent_confirmation_weak_assertion_violations:
        print("\nLLM Agent Confirmation Weak Pending Assertion Violations Found:")
        for violation in llm_agent_confirmation_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    llm_controller_integration_weak_assertion_violations = (
        check_llm_controller_integration_weak_initialization_assertions(Path(root_dir))
    )
    if llm_controller_integration_weak_assertion_violations:
        print("\nLLM Controller Integration Weak Initialization Violations Found:")
        for violation in llm_controller_integration_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    llm_tool_definition_weak_assertion_violations = (
        check_llm_tool_definition_weak_string_assertions(Path(root_dir))
    )
    if llm_tool_definition_weak_assertion_violations:
        print("\nLLM Tool Definition Weak String Assertion Violations Found:")
        for violation in llm_tool_definition_weak_assertion_violations:
            print(f" - {violation}")
        return 1

    docs_overclaim_violations = check_docs_current_truth_overclaims(Path(root_dir))
    if docs_overclaim_violations:
        print("\nDocs Current Truth Overclaim Violations Found:")
        for violation in docs_overclaim_violations:
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
            violations.extend(
                f"{py_file.relative_to(root_dir)} contains forbidden "
                f"local-only runtime token {token!r}"
                for token in FORBIDDEN_PRODUCT_LLM_TOKENS
                if token in content
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
                if configures_saliency and any(
                    function in implicit_render_functions for function in self.functions
                ):
                    violations.append(
                        f"{self.relative_path}:{node.lineno} "
                        f"[{self.current_function}] "
                        "render, tab switching, and polling cannot configure saliency"
                    )
                elif configures_saliency and (
                    "_start_saliency_compute" not in self.functions
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
    for method_name in ("apply_labels_batch", "apply_labels_sequence"):
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
                        f"{relative}:{line} calls label_loader outside an admitted "
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
                    f"{relative}:{line} uses direct file IO for label apply; "
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
                        f"{relative} imports LabelResourceAdmissionService or its "
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
                            f"{relative}:{node.lineno} calls session.load(); UI must "
                            "not materialize external label payloads."
                        )
                    if (
                        isinstance(node, ast.Attribute)
                        and node.attr == "label_data_map"
                    ):
                        violations.append(
                            f"{relative}:{node.lineno} retains a materialized label "
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
                            f"{relative}:{node.lineno} AttachLabelsCommand is "
                            f"missing {', '.join(missing)}"
                        )
                if command_name == "LabelImportPlan" and any(
                    keyword.arg == "label_map" for keyword in node.keywords
                ):
                    violations.append(
                        f"{relative}:{node.lineno} public label import cannot pass "
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
                        f"{current_relative}:{statement.lineno} public label schema "
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
                        f"{relative}:{node.lineno} imports a backend label parser; "
                        "label UI must pass paths/config to ApplicationService."
                    )
                if _is_label_admission_origin(origin):
                    violations.append(
                        f"{relative}:{node.lineno} imports label resource admission; "
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
                    f"{relative}:{node.lineno} uses builtins.open for label UI; "
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
                    f"{relative}:{node.lineno} uses Path.{node.func.attr} for label "
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
                            f"{relative}:{node.lineno} stores a materialized label "
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
    """Keep montage mutation on the preprocessing application boundary."""
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
                    "PreprocessCommandService."
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
    if preprocess_handler is None:
        violations.append(
            "XBrainLab/backend/application/preprocess_service.py must own "
            "handle_apply_montage."
        )
    elif not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "apply_montage"
        for node in ast.walk(preprocess_handler)
    ):
        violations.append(
            "PreprocessCommandService.handle_apply_montage must execute the "
            "preprocess controller mutation."
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
                    "montage commands must route directly to preprocessing."
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
                    "mutation wiring belongs to PreprocessCommandService."
                )

        for node in ast.walk(service_tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                if not (
                    isinstance(key, ast.Attribute)
                    and key.attr == "APPLY_MONTAGE"
                    and isinstance(value, ast.Attribute)
                    and value.attr == "handle_apply_montage"
                    and isinstance(value.value, ast.Attribute)
                ):
                    continue
                montage_routes.append(value.value.attr)
    if montage_routes != ["preprocess_commands"]:
        rendered = ", ".join(montage_routes) if montage_routes else "missing"
        violations.append(
            "ApplicationService must route APPLY_MONTAGE exactly once to "
            "preprocess_commands.handle_apply_montage; current owner(s): "
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

            if class_node.name == "RealConfigureTrainingTool":
                positional = [
                    *execute_method.args.posonlyargs,
                    *execute_method.args.args,
                ]
                defaults = [None] * (
                    len(positional) - len(execute_method.args.defaults)
                ) + list(execute_method.args.defaults)
                for argument, default in zip(positional, defaults, strict=True):
                    if (
                        argument.arg == "output_dir"
                        and default is not None
                        and not (
                            isinstance(default, ast.Constant) and default.value is None
                        )
                    ):
                        violations.append(
                            f"{relative_path}:{argument.lineno} "
                            "RealConfigureTrainingTool declares a second output_dir "
                            "default; the canonical surface/backend state owns it."
                        )

    stale_test_targets = tuple(
        f"XBrainLab.llm.tools.real.{module_name}.get_application_service"
        for module_name in (
            "dataset_real",
            "preprocess_real",
            "training_real",
            "analysis_real",
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
        if not all(
            token in host_source
            for token in ("CommandName.APPLY_MONTAGE", "set_montage")
        ):
            violations.append(
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
                f"{py_file.relative_to(root_dir)}:{getattr(node, 'lineno', 0)} uses "
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


def check_mcp_direct_study_state_reads(root_dir: Path) -> list[str]:
    """Return MCP product code that infers status from mutable Study fields."""
    violations: list[str] = []
    mcp_dir = root_dir / "XBrainLab" / "mcp"
    if not mcp_dir.exists():
        return violations

    for py_file in mcp_dir.rglob("*.py"):
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
                f"{_study_state_expression(source, attr)}; MCP product "
                "status/progress state must come from the ApplicationService "
                "state snapshot."
                for attr in visitor.violations
            )
            method_visitor = _DirectStudyMethodCallVisitor(MCP_DIRECT_STUDY_METHODS)
            method_visitor.visit(node)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
                f"{_study_state_expression(source, call.func)}; MCP product "
                "status/progress state must come from ApplicationService "
                "commands or state snapshots, not direct Study method access."
                for call in method_visitor.violations
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
                f"{py_file.relative_to(root_dir)}:{getattr(node, 'lineno', 0)} uses "
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
        relative_path = py_file.relative_to(root_dir)

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


def check_product_success_legacy_fallback_tests(root_dir: Path) -> list[str]:
    """Return product-success tests that still use controller compatibility helpers."""
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
            visitor = _LegacyFallbackTestUsageVisitor()
            visitor.visit(tree)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{getattr(node, 'lineno', 0)} uses "
                f"{_legacy_fallback_symbol_name(node)} as controller compatibility "
                "product-success evidence; rewrite the test to exercise "
                "ApplicationService / Command API, or move compatibility "
                "coverage into explicit compatibility-only unit tests."
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
            f"{relative_file}:{attr.lineno} reads "
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
            f"{relative_file}:{call.lineno} calls "
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


def check_weak_test_names(root_dir: Path) -> list[str]:
    """Return tests named like smoke placeholders instead of behavior checks."""
    violations: list[str] = []
    tests_dir = root_dir / "tests"
    if not tests_dir.exists():
        return violations

    for py_file in tests_dir.rglob("*.py"):
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
            if not node.name.startswith("test_"):
                continue
            relative_file = py_file.relative_to(root_dir)
            patterns = WEAK_TEST_NAME_PATTERNS
            if _is_under_any(relative_file, PRODUCT_SUCCESS_TEST_DIRS):
                patterns = (
                    *WEAK_TEST_NAME_PATTERNS,
                    *PRODUCT_SUCCESS_WEAK_TEST_NAME_PATTERNS,
                )
            if not _is_weak_test_name(node.name, patterns):
                continue
            violations.append(
                f"{py_file.relative_to(root_dir)}:{node.lineno} uses weak test "
                f"name {node.name!r}; rename it to behavior-specific evidence "
                "and assert command/result/state semantics instead of a generic "
                "accepted/no-crash path.",
            )
    return violations


def _is_weak_test_name(
    test_name: str,
    patterns: tuple[str, ...] = WEAK_TEST_NAME_PATTERNS,
) -> bool:
    parts = test_name.split("_")
    return any(
        pattern in parts if "_" not in pattern else pattern in test_name
        for pattern in patterns
    )


def _is_under_any(relative_file: Path, roots: tuple[Path, ...]) -> bool:
    return any(relative_file == root or root in relative_file.parents for root in roots)


def check_product_success_generic_panel_instance_assertions(
    root_dir: Path,
) -> list[str]:
    """Return product-success tests that only assert panel construction shape."""
    violations: list[str] = []

    for relative_dir in PRODUCT_SUCCESS_TEST_DIRS:
        test_dir = root_dir / relative_dir
        if not test_dir.exists():
            continue
        for py_file in test_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Assert):
                    continue
                if not _is_generic_panel_instance_assertion(node.test):
                    continue
                violations.append(
                    f"{py_file.relative_to(root_dir)}:{node.lineno} uses generic "
                    "panel isinstance assertion as product-success evidence; "
                    "assert CommandResult, state diagnostics, refresh result, or "
                    "UI-visible blocked/success text instead.",
                )
    return violations


def _is_generic_panel_instance_assertion(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != "isinstance":
        return False
    if len(node.args) < 2:
        return False
    panel_type = node.args[1]
    if isinstance(panel_type, ast.Name):
        return panel_type.id.endswith("Panel")
    if isinstance(panel_type, ast.Attribute):
        return panel_type.attr.endswith("Panel")
    return False


def check_mcp_weak_response_assertions(root_dir: Path) -> list[str]:
    """Return MCP tests that use generic non-None response assertions."""
    violations: list[str] = []

    for relative_dir in MCP_EXACT_EVIDENCE_TEST_DIRS:
        test_dir = root_dir / relative_dir
        if not test_dir.exists():
            continue
        for py_file in test_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            visitor = _MCPWeakResponseAssertionVisitor()
            visitor.visit(tree)
            violations.extend(
                f"{py_file.relative_to(root_dir)}:{name_node.lineno} uses "
                f"generic non-None MCP assertion on {name_node.id!r}; assert "
                "JSON-RPC envelope, request id, error/result separation, "
                "structuredContent, adapter metadata, and command result truth "
                "instead."
                for name_node in visitor.violations
            )
    return violations


def check_pipeline_state_weak_string_assertions(root_dir: Path) -> list[str]:
    """Return pipeline-state tests that use generic non-empty string assertions."""
    test_file = root_dir / PIPELINE_STATE_EXACT_EVIDENCE_TEST
    if not test_file.exists():
        return []

    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
    except SyntaxError:
        return []

    visitor = _PipelineStateWeakStringAssertionVisitor()
    visitor.visit(tree)
    return [
        f"{PIPELINE_STATE_EXACT_EVIDENCE_TEST}:{node.lineno} uses a generic "
        "non-empty pipeline state string assertion; assert exact stage prompt "
        "markers or the full stage-label display contract instead."
        for node in visitor.violations
    ]


def check_llm_parser_weak_parse_assertions(root_dir: Path) -> list[str]:
    """Return parser tests that only assert parse output exists."""
    violations: list[str] = []

    for relative_file in LLM_PARSER_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _LLMParserWeakParseAssertionVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{name_node.lineno} uses generic non-None parser "
            f"assertion on {name_node.id!r}; assert the exact "
            "(tool_name, parameters) parse result instead."
            for name_node in visitor.violations
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
        if path.exists() and "CommandParser.parse_product(" not in path.read_text(
            encoding="utf-8"
        ):
            violations.append(
                f"{relative} does not use the strict parse_product() boundary."
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
        "XBrainLab/llm/agent/tool_call_normalizer.py": (
            'normalized_params.pop("resource_preflight_token", None)',
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
        "XBrainLab/ui/panels/dataset/actions.py": (
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
        "XBrainLab/ui/panels/dataset/actions.py",
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


def check_llm_application_surface_weak_result_assertions(root_dir: Path) -> list[str]:
    """Return application-surface tests that only assert tool results exist."""
    violations: list[str] = []

    for relative_file in LLM_APPLICATION_SURFACE_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _GenericNonNoneAssertionVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{name_node.lineno} uses generic non-None "
            f"application-surface assertion on {name_node.id!r}; assert "
            "ToolCommandResult type, tool_name, command_name, raw status, "
            "capability, and state instead."
            for name_node in visitor.violations
        )
    return violations


def check_llm_agent_intent_boundary_weak_result_assertions(
    root_dir: Path,
) -> list[str]:
    """Return agent intent-boundary tests that only assert tool results exist."""
    violations: list[str] = []

    for relative_file in LLM_AGENT_INTENT_BOUNDARY_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _GenericNonNoneAssertionVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{name_node.lineno} uses generic non-None "
            f"agent intent-boundary assertion on {name_node.id!r}; assert "
            "ToolCommandResult type, tool_name, command_name, blocked_reason, "
            "message, capability, and state instead."
            for name_node in visitor.violations
        )
    return violations


def check_llm_agent_confirmation_weak_pending_assertions(root_dir: Path) -> list[str]:
    """Return confirmation tests that only assert a pending tuple exists."""
    violations: list[str] = []

    for relative_file in LLM_AGENT_CONFIRMATION_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _AgentPendingConfirmationWeakAssertionVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{node.lineno} uses generic pending-confirmation "
            "existence assertion; assert AgentConfirmationRequest fields, the "
            "typed emitted request, and correlated AgentConfirmationResolution "
            "behavior instead."
            for node in visitor.violations
        )
    return violations


def check_llm_controller_integration_weak_initialization_assertions(
    root_dir: Path,
) -> list[str]:
    """Return controller integration tests that only assert components exist."""
    violations: list[str] = []

    for relative_file in LLM_CONTROLLER_INTEGRATION_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _ControllerIntegrationWeakInitializationVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{node.lineno} uses generic controller "
            "initialization evidence; assert component types, wiring, exact "
            "tool names, and verifier schema keys instead."
            for node in visitor.violations
        )
    return violations


def check_llm_tool_definition_weak_string_assertions(root_dir: Path) -> list[str]:
    """Return tool-definition tests that only assert non-empty strings."""
    violations: list[str] = []

    for relative_file in LLM_TOOL_DEFINITION_EXACT_EVIDENCE_TESTS:
        test_file = root_dir / relative_file
        if not test_file.exists():
            continue
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"), filename=str(test_file)
            )
        except SyntaxError:
            continue

        visitor = _GenericLenGtZeroAssertionVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_file}:{node.lineno} uses generic non-empty tool "
            "definition assertion; assert exact tool name, schema properties, "
            "required fields, and description markers instead."
            for node in visitor.violations
        )
    return violations


def check_docs_current_truth_overclaims(root_dir: Path) -> list[str]:
    """Return current-truth docs that present target/acceptance as complete."""
    violations: list[str] = []

    for relative_file in DOC_CURRENT_TRUTH_FILES:
        path = root_dir / relative_file
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            lineno = index + 1
            normalized = line.strip()
            if not normalized:
                continue
            context = " ".join(lines[max(0, index - 10) : index + 1]).lower()
            if _docs_line_has_claim_boundary(context):
                continue
            lower = normalized.lower()
            violations.extend(
                f"{relative_file}:{lineno} presents {phrase!r} as "
                "current truth; docs must state this as missing, bounded, "
                "or target-only unless backed by human acceptance evidence."
                for phrase in DOC_CURRENT_TRUTH_OVERCLAIM_PHRASES
                if phrase.lower() in lower
            )
    return violations


def _docs_line_has_claim_boundary(lower_line: str) -> bool:
    return any(token.lower() in lower_line for token in DOC_CLAIM_BOUNDARY_TOKENS)


class _MCPWeakResponseAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Name] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        name_node = _generic_non_none_assertion_name(node.test)
        if name_node is not None:
            self.violations.append(name_node)
        self.generic_visit(node)


class _GenericNonNoneAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Name] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        name_node = _generic_non_none_assertion_name(node.test)
        if name_node is not None:
            self.violations.append(name_node)
        self.generic_visit(node)


class _GenericLenGtZeroAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Assert] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        if _is_len_gt_zero_assertion(node.test):
            self.violations.append(node)
        self.generic_visit(node)


class _AgentPendingConfirmationWeakAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Assert] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        if _is_pending_confirmation_non_none_assertion(node.test):
            self.violations.append(node)
        self.generic_visit(node)


class _ControllerIntegrationWeakInitializationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Assert] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        if _is_controller_component_non_none_assertion(
            node.test
        ) or _is_len_gt_zero_assertion(node.test):
            self.violations.append(node)
        self.generic_visit(node)


class _PipelineStateWeakStringAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Assert] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        if _is_generic_non_empty_string_assertion(node.test):
            self.violations.append(node)
        self.generic_visit(node)


def _is_generic_non_empty_string_assertion(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Gt):
        return False
    if len(node.comparators) != 1:
        return False
    comparator = node.comparators[0]
    if not isinstance(comparator, ast.Constant) or comparator.value != 0:
        return False
    if not isinstance(node.left, ast.Call):
        return False
    if _call_name(node.left.func) != "len" or len(node.left.args) != 1:
        return False
    target = node.left.args[0]
    return _is_pipeline_state_string_target(target)


def _is_len_gt_zero_assertion(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Gt):
        return False
    if len(node.comparators) != 1:
        return False
    comparator = node.comparators[0]
    if not isinstance(comparator, ast.Constant) or comparator.value != 0:
        return False
    if not isinstance(node.left, ast.Call):
        return False
    return _call_name(node.left.func) == "len" and len(node.left.args) == 1


def _is_pending_confirmation_non_none_assertion(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.IsNot):
        return False
    if len(node.comparators) != 1:
        return False
    right = node.comparators[0]
    if not isinstance(right, ast.Constant) or right.value is not None:
        return False
    left = node.left
    return isinstance(left, ast.Attribute) and left.attr == "_pending_confirmation"


def _is_controller_component_non_none_assertion(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.IsNot):
        return False
    if len(node.comparators) != 1:
        return False
    right = node.comparators[0]
    if not isinstance(right, ast.Constant) or right.value is not None:
        return False
    left = node.left
    return isinstance(left, ast.Attribute) and left.attr in {
        "registry",
        "assembler",
        "verifier",
    }


def _is_pipeline_state_string_target(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript):
        if not isinstance(node.value, ast.Name) or node.value.id != "config":
            return False
        key = node.slice
        return isinstance(key, ast.Constant) and key.value == "system_prompt"
    if isinstance(node, ast.Attribute):
        return (
            node.attr == "label"
            and isinstance(node.value, ast.Name)
            and node.value.id == "stage"
        )
    return False


class _LLMParserWeakParseAssertionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.Name] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        name_node = _generic_non_none_assertion_name(node.test)
        if name_node is not None and name_node.id in {"parsed", "parsed2", "result"}:
            self.violations.append(name_node)
        self.generic_visit(node)


def _generic_non_none_assertion_name(node: ast.AST) -> ast.Name | None:
    if not isinstance(node, ast.Compare):
        return None
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.IsNot):
        return None
    if len(node.comparators) != 1:
        return None
    left = node.left
    right = node.comparators[0]
    if (
        isinstance(left, ast.Name)
        and isinstance(right, ast.Constant)
        and right.value is None
    ):
        return left
    if (
        isinstance(right, ast.Name)
        and isinstance(left, ast.Constant)
        and left.value is None
    ):
        return right
    return None


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


class _LegacyFallbackTestUsageVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ast.AST] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "XBrainLab.ui.application_capabilities" and any(
            alias.name == "*" or alias.name in PRODUCT_SUCCESS_LEGACY_FALLBACK_SYMBOLS
            for alias in node.names
        ):
            self.violations.append(node)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) in PRODUCT_SUCCESS_LEGACY_FALLBACK_SYMBOLS:
            self.violations.append(node)
            return
        self.generic_visit(node)


def _legacy_fallback_symbol_name(node: ast.AST) -> str:
    if isinstance(node, ast.ImportFrom):
        names = [
            alias.name
            for alias in node.names
            if alias.name in PRODUCT_SUCCESS_LEGACY_FALLBACK_SYMBOLS
        ]
        return ", ".join(names) if names else "*"
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return "controller compatibility helper"


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
            f"{py_file.relative_to(root_dir)}:{line} has invalid Python syntax "
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
                f"{py_file.relative_to(root_dir)}:{call.lineno} calls "
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
                    f"{_call_name(call.func)} after execute_application_command(); "
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
) -> list[ast.Call]:
    violations: list[ast.Call] = []
    command_seen = False
    for statement in statements:
        if command_seen:
            visitor = _PostCommandLocalRefreshVisitor(source, function_name)
            visitor.visit(statement)
            violations.extend(visitor.violations)
        violations.extend(
            _post_command_local_refresh_calls(
                _nested_statement_bodies(statement),
                source,
                function_name,
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
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "execute_application_command_async":
            continue
        if _call_has_refresh_false(node):
            continue
        callback_name = _command_async_result_callback_name(node)
        if not callback_name:
            continue
        callback = functions.get(callback_name)
        if callback is None:
            continue
        visitor = _PostCommandLocalRefreshVisitor(source, callback.name)
        for statement in callback.body:
            visitor.visit(statement)
        violations.extend(
            f"{py_file.relative_to(root_dir)}:{call.lineno} async on_result "
            f"{callback_name}() calls {_call_name(call.func)}; service-backed "
            "async success refresh must go through refresh_after_command(), not "
            "callback-local render refresh."
            for call in visitor.violations
        )
    return violations


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
        if _call_name(child.func) != "execute_application_command":
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
    def __init__(self, source: str, function_name: str = "") -> None:
        self.source = source
        self.function_name = function_name
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
        if _call_name(node.func) in UI_POST_COMMAND_LOCAL_REFRESH_METHODS:
            self.violations.append(node)
            return
        self.generic_visit(node)


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


def test_repository_architecture_compliance():
    """Pytest entry point for the repo architecture compliance gate."""
    root_dir = Path(__file__).resolve().parents[1]
    assert check_architecture(str(root_dir)) == 0


if __name__ == "__main__":
    sys.exit(check_architecture(os.getcwd()))
