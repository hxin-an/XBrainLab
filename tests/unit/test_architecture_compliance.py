import ast
from pathlib import Path

from tests import architecture_compliance
from tests.architecture_compliance import (
    check_agent_confirmation_contract_evidence,
    check_agent_resource_receipt_boundary,
    check_application_service_ownership_boundaries,
    check_assistant_presentation_ownership,
    check_assistant_runtime_selection_ownership,
    check_assistant_turn_scope_ownership,
    check_backend_facade_test_usage,
    check_backend_llm_imports,
    check_concrete_llm_tool_result_contracts,
    check_docs_current_truth_overclaims,
    check_headless_verifier_direct_study_state,
    check_llm_agent_confirmation_weak_pending_assertions,
    check_llm_agent_intent_boundary_weak_result_assertions,
    check_llm_application_surface_weak_result_assertions,
    check_llm_controller_integration_weak_initialization_assertions,
    check_llm_direct_study_state_reads,
    check_llm_parser_weak_parse_assertions,
    check_llm_tool_definition_weak_string_assertions,
    check_mapped_real_tool_command_ownership,
    check_mcp_direct_study_state_reads,
    check_mcp_weak_response_assertions,
    check_montage_command_ownership,
    check_pending_interaction_compatibility_api,
    check_pipeline_state_weak_string_assertions,
    check_product_runtime_backend_facade_usage,
    check_product_runtime_mock_dependencies,
    check_product_success_backend_facade_tests,
    check_product_success_controller_lookup_assertions,
    check_product_success_direct_study_state_tests,
    check_product_success_generic_panel_instance_assertions,
    check_product_success_legacy_fallback_tests,
    check_product_tool_envelope_boundary,
    check_training_configuration_reset_ownership,
    check_training_runtime_port_boundary,
    check_typed_agent_confirmation_boundary,
    check_typed_montage_ui_handoff_boundary,
    check_ui_agent_worker_internal_access,
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
    check_visualization_saliency_publication_boundary,
    check_weak_test_names,
)


def _write_backend_file(root: Path, source: str) -> None:
    path = root / "XBrainLab" / "backend" / "study.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def _write_product_file(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _write_confirmation_evidence(root: Path, source: str) -> None:
    _write_product_file(
        root,
        "tests/unit/llm/agent/test_confirmation.py",
        source,
    )


def test_mapped_real_tool_command_ownership_rejects_parallel_translation(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/real/dataset_real.py",
        """
from XBrainLab.backend.application import LoadDataCommand, get_application_service
from XBrainLab.llm.tools.application_surface import build_load_data_command

class RealLoadDataTool:
    def execute(self, study, paths=None):
        expanded = []
        for path in paths or []:
            if os.path.isdir(path):
                expanded.extend(os.listdir(path))
        command = build_load_data_command({"paths": expanded})
        return get_application_service(study).execute(
            LoadDataCommand(paths=command.paths)
        )
""",
    )

    violations = check_mapped_real_tool_command_ownership(tmp_path)

    assert any("imports LoadDataCommand" in item for item in violations)
    assert any("imports get_application_service" in item for item in violations)
    assert any("calls service.execute() directly" in item for item in violations)
    assert any("performs local path translation" in item for item in violations)
    assert any("does not delegate" in item for item in violations)


def test_mapped_real_tool_command_ownership_accepts_canonical_delegation_and_direct_ui(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/real/dataset_real.py",
        """
from XBrainLab.llm.tools import execute_real_application_tool

class RealLoadDataTool:
    def execute(self, study, paths=None):
        return execute_real_application_tool(
            study,
            "load_data",
            {"paths": paths},
        )

class RealListFilesTool:
    def execute(self, study, directory=None):
        return os.listdir(directory)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/real/preprocess_real.py",
        """
class RealSetMontageTool:
    def execute(self, study, montage_name=None):
        return UiRequest(montage_name)
""",
    )

    assert check_mapped_real_tool_command_ownership(tmp_path) == []


def test_mapped_real_tool_command_ownership_rejects_output_dir_default_and_normalizer(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/real/training_real.py",
        """
from XBrainLab.llm.tools import execute_real_application_tool

class RealConfigureTrainingTool:
    def execute(self, study, output_dir="./output", repeat=1):
        normalized_repeat = normalize_positive_integer("repeat", repeat)
        return execute_real_application_tool(
            study,
            "configure_training",
            {"output_dir": output_dir, "repeat": normalized_repeat},
        )
""",
    )

    violations = check_mapped_real_tool_command_ownership(tmp_path)

    assert any("calls normalize_positive_integer" in item for item in violations)
    assert any("second output_dir default" in item for item in violations)


def test_mapped_real_tool_command_ownership_rejects_stale_service_patch(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "tests/unit/llm/test_stale_real_tool.py",
        """
from unittest.mock import patch

def test_old_adapter_service_ownership():
    with patch(
        "XBrainLab.llm.tools.real.dataset_real.get_application_service",
    ):
        pass
""",
    )

    violations = check_mapped_real_tool_command_ownership(tmp_path)

    assert len(violations) == 1
    assert "mapped Real-tool tests must inject the canonical" in violations[0]


def test_training_runtime_port_boundary_rejects_direct_manager_access(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        "def read(study):\n    return study.training_manager.trainer\n",
    )

    violations = check_training_runtime_port_boundary(tmp_path)

    assert len(violations) == 1
    assert "outside TrainingRuntimePort" in violations[0]


def test_training_runtime_port_boundary_rejects_study_compatibility_aliases(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
def read(self, study):
    active = self.study
    first = study.trainer
    second = getattr(self._study, "model_holder", None)
    active.training_option = None
    setattr(self.study, "saliency_params", {})
    return first, second
""",
    )

    violations = check_training_runtime_port_boundary(tmp_path)

    assert len(violations) == 4
    assert all("compatibility state" in item for item in violations)
    assert any("Study.trainer" in item for item in violations)
    assert any("Study.model_holder" in item for item in violations)
    assert any("Study.training_option" in item for item in violations)
    assert any("Study.saliency_params" in item for item in violations)


def test_training_runtime_port_boundary_accepts_domain_fields_and_exact_legacy(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/state_read_models.py",
        """
def read(plan, context, snapshot):
    return plan.model_holder, context.training_option, snapshot.trainer
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/pipeline_stage.py",
        """
def _legacy_study_pipeline_stage(study):
    return getattr(study, "trainer", None)
""",
    )

    assert check_training_runtime_port_boundary(tmp_path) == []


def test_training_runtime_port_boundary_limits_pipeline_stage_legacy_exemption(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/pipeline_stage.py",
        """
def _legacy_study_pipeline_stage(study):
    return getattr(study, "trainer", None)

def read_runtime_state(study):
    return getattr(study, "trainer", None)
""",
    )

    violations = check_training_runtime_port_boundary(tmp_path)

    assert len(violations) == 1
    assert "pipeline_stage.py" in violations[0]
    assert "Study.trainer compatibility state" in violations[0]


def test_training_runtime_port_boundary_rejects_owner_trainer_field_access(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_runtime.py",
        "def read(study):\n    return study.training_manager.trainer\n",
    )

    violations = check_training_runtime_port_boundary(tmp_path)

    assert len(violations) == 1
    assert "TrainingManager.trainer field directly" in violations[0]


def test_training_runtime_port_boundary_accepts_owner_manager_accessors(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_runtime.py",
        """
def read(self):
    return (
        self._manager.has_trainer(),
        self._manager.get_training_terminal_outcome(),
    )
""",
    )

    assert check_training_runtime_port_boundary(tmp_path) == []


def test_training_runtime_port_boundary_rejects_pipeline_transaction_manager_access(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/pipeline_transaction.py",
        """
def capture(study):
    direct = study.training_manager
    dynamic = getattr(study, "training_manager")
    return direct, dynamic
""",
    )

    violations = check_training_runtime_port_boundary(tmp_path)

    assert len(violations) == 2
    assert all("pipeline_transaction.py" in item for item in violations)
    assert all("outside TrainingRuntimePort" in item for item in violations)


def test_training_runtime_port_boundary_accepts_injected_transaction_runtime(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/pipeline_transaction.py",
        """
from typing import Protocol

class PipelineInvalidationRuntimePort(Protocol):
    def begin_raw_replacement(self) -> object: ...
    def begin_downstream_replacement(self) -> object: ...
    def commit_pipeline_invalidation(self, expected: object) -> bool: ...

class PipelineStateTransaction:
    def __init__(self, training_runtime: PipelineInvalidationRuntimePort) -> None:
        self._training_runtime = training_runtime

    def begin_raw_replacement(self) -> object:
        return self._training_runtime.begin_raw_replacement()

    def begin_downstream_replacement(self) -> object:
        return self._training_runtime.begin_downstream_replacement()

    def commit_pipeline_invalidation(self, expected: object) -> bool:
        return self._training_runtime.commit_pipeline_invalidation(expected)
""",
    )

    assert check_training_runtime_port_boundary(tmp_path) == []


def test_current_training_runtime_port_boundary_is_clean() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_training_runtime_port_boundary(root) == []


def test_label_resource_guard_rejects_ui_loader_and_pathless_llm_command(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/dialogs/dataset/import_label_dialog.py",
        """from XBrainLab.backend.load_data.label_loader import load_label_file

def preview(path):
    return load_label_file(path)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/application_surface.py",
        """def command(mapping):
    return AttachLabelsCommand(mapping=mapping)
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any(
        "import_label_dialog.py" in item and "label_loader" in item
        for item in violations
    )
    assert any(
        "application_surface.py" in item and "label_paths" in item
        for item in violations
    )


def test_label_resource_guard_rejects_ui_admission_session_and_materialized_cache(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/dialogs/dataset/import_label_dialog.py",
        """from XBrainLab.backend.application.label_resource_admission import LabelResourceAdmissionService

class ImportLabelDialog:
    def __init__(self):
        self.label_data_map = {}
        self.resources = LabelResourceAdmissionService(command_name="ui")

    def preview(self, spec):
        session = self.resources.admit([spec], confirmed=False, token=None)
        self.label_data_map[spec.path] = session.load(spec.path)
""",
    )
    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any("LabelResourceAdmissionService" in item for item in violations)
    assert any("session.load" in item for item in violations)
    assert any("materialized label payload" in item for item in violations)


def test_label_resource_guard_resolves_aliased_ui_io_parser_and_admission(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/dialogs/dataset/import_label_dialog.py",
        """import builtins as runtime_io
import pathlib as paths
from XBrainLab.backend.application.label_resource_admission import LabelResourceAdmissionService as ResourceGate
from XBrainLab.backend.load_data import label_loader as external_parser
from XBrainLab.backend.load_data import label_parser as alternate_parser

class ImportLabelDialog:
    def preview(self, selected):
        source = paths.Path(selected)
        with runtime_io.open(selected, "rb") as handle:
            handle.read(1)
        source.read_bytes()
        external_parser.load_label_file(selected)
        alternate_parser.parse_labels(selected)
        resources = ResourceGate(command_name="ui")
        session = resources.admit([], confirmed=False, token=None)
        self.materialized_labels = session.load(selected)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/dataset/actions.py",
        """from XBrainLab.backend.load_data import label_parser as parser_api

def preview(selected):
    return parser_api.parse_labels(selected)
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any("builtins.open" in item for item in violations)
    assert any("Path.read_bytes" in item for item in violations)
    assert any("label parser" in item for item in violations)
    assert any("actions.py" in item and "label parser" in item for item in violations)
    assert any("label resource admission" in item for item in violations)
    assert any("materialized label payload" in item for item in violations)


def test_label_resource_guard_allows_qfiledialog_paths_and_public_commands(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/dialogs/dataset/import_label_dialog.py",
        """from pathlib import Path as UserPath
from PyQt6.QtWidgets import QFileDialog
from XBrainLab.backend.application.commands import LabelImportPlan, PreviewLabelImportCommand

def choose(parent):
    selected, _ = QFileDialog.getOpenFileNames(parent, "Labels")
    normalized = [str(UserPath(path).expanduser()) for path in selected]
    preview = PreviewLabelImportCommand(label_paths=normalized)
    plan = LabelImportPlan(label_paths=normalized, label_configs={})
    return preview, plan
""",
    )

    assert (
        architecture_compliance.check_label_resource_admission_boundary(tmp_path) == []
    )


def test_label_resource_guard_rejects_payload_fields_in_public_schemas(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/commands.py",
        """from dataclasses import dataclass

@dataclass
class LabelImportPlan:
    label_map: dict

@dataclass
class PreviewLabelImportCommand:
    label_array: list
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/results.py",
        """from dataclasses import dataclass

@dataclass
class PreviewLabelImportResult:
    payload: bytes
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/label_import_preview.py",
        """def _preview_summary():
    return {"materialized_payload": [1, 2]}
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any("LabelImportPlan.label_map" in item for item in violations)
    assert any("PreviewLabelImportCommand.label_array" in item for item in violations)
    assert any("PreviewLabelImportResult.payload" in item for item in violations)
    assert any("result field 'materialized_payload'" in item for item in violations)


def test_label_resource_guard_catches_attribute_path_reads_in_any_ui_or_llm_module(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/reviewer_repro.py",
        """from pathlib import Path as SourcePath

class Reader:
    def __init__(self, label_path):
        self.source = SourcePath(label_path)

    def read(self):
        return self.source.read_text(encoding="utf-8")
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/reviewer_tool.py",
        """import pathlib as filesystem

class ToolReader:
    def __init__(self, external_label_path):
        self.location = filesystem.Path(external_label_path)

    def read(self):
        with self.location.open("rb") as handle:
            return handle.read()
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any(
        "reviewer_repro.py" in item and "Path.read_text" in item for item in violations
    )
    assert any(
        "reviewer_tool.py" in item and "Path.open" in item for item in violations
    )


def test_label_resource_guard_recurses_through_public_label_schema_dataclasses(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/commands.py",
        """from dataclasses import dataclass

@dataclass
class ReviewBody:
    label_values: list[int]

@dataclass
class GenericImportCommand:
    body: ReviewBody
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/results.py",
        """from dataclasses import dataclass

@dataclass
class EncodedValues:
    payload: bytes

@dataclass
class ExternalLabelReviewResult:
    details: EncodedValues
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/label_review_contract.py",
        """from dataclasses import dataclass
import numpy as np

@dataclass
class ToolInput:
    labels: np.ndarray

@dataclass
class ExternalLabelTool:
    request: ToolInput
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any(
        "GenericImportCommand" in item and "ReviewBody.label_values" in item
        for item in violations
    )
    assert any(
        "ExternalLabelReviewResult" in item and "EncodedValues.payload" in item
        for item in violations
    )
    assert any(
        "ExternalLabelTool" in item and "ToolInput.labels" in item
        for item in violations
    )


def test_label_resource_guard_resolves_quoted_forward_reference_annotations(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/quoted_label_contract.py",
        """from dataclasses import dataclass
from numpy import ndarray as Array
from typing import Annotated

@dataclass
class QuotedModuleType:
    labels: "np.ndarray"

@dataclass
class QuotedImportedAlias:
    labels: "Array"

@dataclass
class AnnotatedQuotedType:
    labels: Annotated["np.ndarray", "runtime metadata"]
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any("QuotedModuleType.labels" in item for item in violations)
    assert any("QuotedImportedAlias.labels" in item for item in violations)
    assert any("AnnotatedQuotedType.labels" in item for item in violations)


def test_label_resource_guard_ignores_literal_and_annotated_metadata_strings(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/safe_label_metadata_contract.py",
        """from dataclasses import dataclass
from typing import Annotated, Literal

@dataclass
class SafeLabelMetadata:
    label_kind: Literal["np.ndarray"]
    labels: Annotated[str, "np.ndarray"]
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert not any("SafeLabelMetadata" in item for item in violations)


def test_label_resource_guard_covers_all_product_schema_roots_and_command_aliases(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/public_review_contract.py",
        """from dataclasses import dataclass

@dataclass
class PublicReviewState:
    label_values: list[int]
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/shared_review_contract.py",
        """from dataclasses import dataclass

@dataclass
class LabelRows:
    label_values: tuple[str, ...]

""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/public_review_contract.py",
        """from dataclasses import dataclass
from XBrainLab.llm.agent.shared_review_contract import LabelRows as ReviewRows

@dataclass
class AgentReviewRequest:
    body: ReviewRows
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/tools/application_review_contract.py",
        """from dataclasses import dataclass

@dataclass
class MaterializedReviewBody:
    payload: bytes

@dataclass
class ExternalLabelApplicationToolRequest:
    review: MaterializedReviewBody
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/external_label_contract.py",
        """from dataclasses import dataclass

@dataclass
class ApplicationLabelRows:
    label_values: list[str]

@dataclass
class ExternalLabelCommandEnvelope:
    request: ApplicationLabelRows
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/attach_labels.py",
        """from XBrainLab.backend.application.commands import AttachLabelsCommand as Attach

def build(mapping, paths):
    return Attach(mapping=mapping, label_paths=paths)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/attach_labels.py",
        """from XBrainLab.backend.application.commands import AttachLabelsCommand as Attach

def build(mapping, paths):
    return Attach(mapping=mapping, label_paths=paths)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/assigned_attach_labels.py",
        """from XBrainLab.backend.application.commands import AttachLabelsCommand

Attach = AttachLabelsCommand

def build(mapping, paths):
    return Attach(mapping=mapping, label_paths=paths)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/module_assigned_attach_labels.py",
        """from XBrainLab.backend.application import commands

Attach = commands.AttachLabelsCommand

def build(mapping, paths):
    return Attach(mapping=mapping, label_paths=paths)
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any(
        "public_review_contract.py" in item and "label_values" in item
        for item in violations
    )
    assert any(
        "AgentReviewRequest" in item and "LabelRows.label_values" in item
        for item in violations
    )
    assert any(
        "ExternalLabelApplicationToolRequest" in item
        and "MaterializedReviewBody.payload" in item
        for item in violations
    )
    assert any(
        "ExternalLabelCommandEnvelope" in item
        and "ApplicationLabelRows.label_values" in item
        for item in violations
    )
    assert any(
        "attach_labels.py" in item
        and "resource_preflight_confirmed" in item
        and "resource_preflight_token" in item
        for item in violations
    )
    assert any(
        "ui/components/attach_labels.py" in item
        and "resource_preflight_confirmed" in item
        and "resource_preflight_token" in item
        for item in violations
    )
    assert any(
        "assigned_attach_labels.py" in item
        and "resource_preflight_confirmed" in item
        and "resource_preflight_token" in item
        for item in violations
    )
    assert any(
        "module_assigned_attach_labels.py" in item
        and "resource_preflight_confirmed" in item
        and "resource_preflight_token" in item
        for item in violations
    )


def test_label_resource_guard_keeps_qfiledialog_path_selection_clean_in_any_ui_module(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/external_label_picker.py",
        """from pathlib import Path as UserPath
from PyQt6.QtWidgets import QFileDialog
from XBrainLab.backend.application.commands import PreviewLabelImportCommand

class ExternalLabelPicker:
    def choose(self, parent):
        selected, _ = QFileDialog.getOpenFileNames(parent, "Labels")
        paths = [str(UserPath(path).expanduser()) for path in selected]
        return PreviewLabelImportCommand(label_paths=paths)
""",
    )

    assert (
        architecture_compliance.check_label_resource_admission_boundary(tmp_path) == []
    )


def test_label_resource_guard_rejects_unbounded_data_interpretation_apply(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/data_interpretation_apply.py",
        """from pathlib import Path

from XBrainLab.backend.load_data.label_loader import load_label_file

def apply(path):
    raw_rows = Path(path).read_text(encoding="utf-8")
    return raw_rows, load_label_file(path)
""",
    )

    violations = architecture_compliance.check_label_resource_admission_boundary(
        tmp_path
    )

    assert any(
        "data_interpretation_apply.py" in item and "admitted parser owner" in item
        for item in violations
    )
    assert any(
        "data_interpretation_apply.py" in item and "direct file IO" in item
        for item in violations
    )


def test_repository_label_resource_admission_boundary_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]

    assert architecture_compliance.check_label_resource_admission_boundary(root) == []


def test_typed_confirmation_guard_rejects_boolean_signal_callback_and_payload(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/legacy_confirmation.py",
        """
class LegacyConfirmationBridge:
    confirmation_resolved = pyqtSignal(bool)

    def on_user_confirmed(self, approved: bool) -> None:
        self.request_user_interaction.emit(
            "confirm_action",
            {"approved": approved},
        )
""",
    )

    violations = check_typed_agent_confirmation_boundary(tmp_path)

    assert len(violations) == 3
    assert any("pyqtSignal(bool)" in item for item in violations)
    assert any("on_user_confirmed" in item for item in violations)
    assert any("confirm_action" in item for item in violations)


def test_typed_confirmation_guard_rejects_renamed_boolean_handler(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        """
class AssistantRuntimeLifecycle:
    def confirm(self, approved: bool) -> None:
        self._dispatcher.confirm(approved)
""",
    )

    violations = check_typed_agent_confirmation_boundary(tmp_path)

    assert len(violations) == 1
    assert "boolean parameter" in violations[0]
    assert "AgentConfirmationResolution" in violations[0]


def test_typed_confirmation_guard_allows_correlated_request_resolution_boundary(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        """
class AssistantRuntimeLifecycle:
    confirmation_requested = pyqtSignal(object)

    def confirm(self, resolution: AgentConfirmationResolution) -> None:
        if not isinstance(resolution, AgentConfirmationResolution):
            raise TypeError("typed confirmation required")
        self._dispatcher.confirm(resolution)
""",
    )

    assert check_typed_agent_confirmation_boundary(tmp_path) == []


def test_pending_interaction_guard_rejects_compatibility_api_and_legacy_test_access(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
class Controller:
    @property
    def _pending_confirmation(self):
        return None

    @_pending_confirmation.setter
    def _pending_confirmation(self, decision):
        self._pending = decision
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/pending_interaction.py",
        """
class PendingInteractionCoordinator:
    def replace_confirmation_for_compatibility(self, decision, request):
        self._confirmation = (decision, request)
""",
    )
    _write_product_file(
        tmp_path,
        "tests/unit/llm/agent/test_controller.py",
        """
def test_pending(ctrl):
    ctrl._pending_confirmation = decision
    assert ctrl._pending_confirmation is decision
""",
    )

    violations = check_pending_interaction_compatibility_api(tmp_path)

    assert len(violations) == 5
    assert any("_pending_confirmation" in item for item in violations)
    assert any("replace_confirmation_for_compatibility" in item for item in violations)
    assert sum("test_controller.py" in item for item in violations) == 2


def test_pending_interaction_guard_allows_typed_session_contract(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
class Controller:
    @property
    def pending_interactions(self):
        return self._pending_interactions
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/pending_interaction.py",
        """
class PendingInteractionCoordinator:
    def begin_confirmation(self, decision, request):
        self._confirmation = (decision, request)
""",
    )
    _write_product_file(
        tmp_path,
        "tests/unit/llm/agent/test_controller.py",
        """
def test_pending(ctrl):
    session = ctrl.pending_interactions
    session.begin_confirmation(decision, request)
    assert session.confirmation.decision is decision
""",
    )

    assert check_pending_interaction_compatibility_api(tmp_path) == []


def test_product_pending_interaction_contract_has_no_compatibility_api() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_pending_interaction_compatibility_api(root) == []


def test_confirmation_evidence_guard_rejects_legacy_uncorrelated_payload(
    tmp_path: Path,
) -> None:
    _write_confirmation_evidence(
        tmp_path,
        """
def test_confirmation_required_pauses_execution(ctrl):
    assert ctrl._pending_confirmation == ("clear_dataset", {}, [])
    ctrl.request_user_interaction.emit.assert_called_once_with(
        "confirm_action",
        {"tool_name": "clear_dataset", "params": {}},
    )
""",
    )

    violations = check_agent_confirmation_contract_evidence(tmp_path)

    assert any("legacy confirm_action payload" in item for item in violations)
    assert any("AgentConfirmationRequest.for_action" in item for item in violations)
    assert any("AgentConfirmationResolution.for_request" in item for item in violations)
    assert any("correlation fields" in item for item in violations)
    assert any("matching and stale" in item for item in violations)


def test_confirmation_evidence_guard_allows_typed_correlated_contract(
    tmp_path: Path,
) -> None:
    _write_confirmation_evidence(
        tmp_path,
        """
def test_confirmation_resolution_is_correlated():
    request = AgentConfirmationRequest.for_action(
        command_name="clear_dataset",
        params={},
        action_label="Clear dataset",
        description="Clear loaded data.",
        destructive=True,
        publication_generation=4,
        request_id="confirmation-1",
    )
    resolution = AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )
    stale = AgentConfirmationResolution(
        request_id="confirmation-old",
        command_name=request.command_name,
        params_fingerprint=request.params_fingerprint,
        publication_generation=request.publication_generation,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )

    assert resolution.matches(request)
    assert not stale.matches(request)
    assert resolution.request_id == request.request_id
    assert resolution.params_fingerprint == request.params_fingerprint
    assert resolution.publication_generation == request.publication_generation
""",
    )

    assert check_agent_confirmation_contract_evidence(tmp_path) == []


def test_product_confirmation_boundary_and_evidence_are_typed() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_typed_agent_confirmation_boundary(root) == []
    assert check_agent_confirmation_contract_evidence(root) == []


def test_montage_handoff_guard_rejects_legacy_coordinator_and_fake_user_turn(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/montage_interaction_coordinator.py",
        "class MontageInteractionCoordinator: pass\n",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/agent_manager.py",
        """
def open_montage_picker_dialog(self):
    self.handle_user_input("Montage Confirmed.")
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
def request_montage(self):
    return WorkflowUiHandoffRequest.for_decision(
        CommandName.APPLY_MONTAGE,
        suggested_values=(),
    )
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/workflow_ui_handoff_host.py",
        """
def open_surface(self, command_name):
    if command_name is CommandName.APPLY_MONTAGE:
        return self.visualization_panel.control_sidebar.set_montage()
""",
    )

    violations = check_typed_montage_ui_handoff_boundary(tmp_path)

    assert any("legacy montage coordinator" in item for item in violations)
    assert any("fake user message" in item for item in violations)
    assert any("open_montage_picker_dialog" in item for item in violations)


def test_product_montage_decision_uses_typed_ui_handoff() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_typed_montage_ui_handoff_boundary(root) == []


def test_product_tool_envelope_guard_rejects_tolerant_product_and_eval_parsers(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        "commands = CommandParser.parse(model_output)\n",
    )
    _write_product_file(
        tmp_path,
        "scripts/agent/evals/run_local_tool_call_eval.py",
        "commands = CommandParser.parse_diagnostic(model_output)\n",
    )

    violations = check_product_tool_envelope_boundary(tmp_path)

    assert len(violations) == 4
    assert any("ambiguous parse()" in item for item in violations)
    assert any("tolerant parse_diagnostic()" in item for item in violations)
    assert (
        sum("does not use the strict parse_product()" in item for item in violations)
        == 2
    )


def test_product_tool_envelope_guard_accepts_strict_execution_and_scorer(
    tmp_path: Path,
) -> None:
    strict_source = "result = CommandParser.parse_product(model_output)\n"
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        strict_source,
    )
    _write_product_file(
        tmp_path,
        "scripts/agent/evals/run_local_tool_call_eval.py",
        strict_source,
    )

    assert check_product_tool_envelope_boundary(tmp_path) == []


def test_agent_resource_receipt_guard_rejects_tokenless_adapter_contract(
    tmp_path: Path,
) -> None:
    files = {
        "XBrainLab/backend/application/resource_preflight.py": (
            "class ResourcePreflightView:\n    pass\n"
        ),
        "XBrainLab/backend/application/resource_receipt.py": "pass\n",
        "XBrainLab/llm/agent/tool_call_normalizer.py": "normalized_params = {}\n",
        "XBrainLab/llm/agent/tool_attempt_coordinator.py": (
            'payload.get("confirmation_token")\n'
        ),
        "XBrainLab/llm/tools/application_surface.py": "confirmed = True\n",
        "XBrainLab/llm/tools/real/dataset_real.py": "confirmed = True\n",
        "XBrainLab/backend/application/data_interpretation_service.py": (
            "confirmation_is_current = resource_preflight_confirmed\n"
        ),
        "XBrainLab/backend/application/training_resource_receipt.py": "pass\n",
        "XBrainLab/ui/panels/training/sidebar.py": (
            'diagnostics.get("resource_preflight")\n'
        ),
        "XBrainLab/ui/panels/dataset/actions.py": (
            'payload.get("scope_fingerprint")\ntoken = payload["confirmation_token"]\n'
        ),
    }
    for relative, source in files.items():
        _write_product_file(tmp_path, relative, source)

    violations = check_agent_resource_receipt_boundary(tmp_path)

    assert len(violations) >= 12
    assert any("generic tokenless" in violation for violation in violations)
    assert any("application_surface.py" in violation for violation in violations)
    assert any("outside ResourcePreflightView" in violation for violation in violations)
    assert any("reads 'confirmation_token'" in violation for violation in violations)


def test_product_agent_resource_receipt_boundary_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_agent_resource_receipt_boundary(root) == []


def test_backend_llm_import_guard_rejects_reverse_dependency(tmp_path: Path) -> None:
    _write_backend_file(
        tmp_path,
        """
from XBrainLab.llm.pipeline_state import PipelineStage

def stage():
    from XBrainLab.llm.pipeline_state import compute_pipeline_stage
    return compute_pipeline_stage
""",
    )

    violations = check_backend_llm_imports(tmp_path)

    assert len(violations) == 2
    assert all("backend contracts must not depend" in item for item in violations)


def test_product_runtime_mock_guard_rejects_test_object_branching(
    tmp_path: Path,
) -> None:
    path = tmp_path / "XBrainLab" / "ui" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from unittest.mock import Mock

def available(value):
    return not isinstance(value, Mock)
""",
        encoding="utf-8",
    )

    violations = check_product_runtime_mock_dependencies(tmp_path)

    assert len(violations) == 1
    assert "explicit protocols" in violations[0]


def test_product_runtime_mock_guard_allows_protocol_fake_without_mock_import(
    tmp_path: Path,
) -> None:
    path = tmp_path / "XBrainLab" / "ui" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from typing import Protocol

class RuntimeContext(Protocol):
    def is_available(self) -> bool: ...
""",
        encoding="utf-8",
    )

    assert check_product_runtime_mock_dependencies(tmp_path) == []


def test_concrete_llm_tool_result_guard_rejects_string_contract(tmp_path: Path) -> None:
    path = tmp_path / "XBrainLab" / "llm" / "tools" / "real" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
class DemoTool:
    def execute(self, study, **kwargs) -> str:
        return f"Loaded {study}"
""",
        encoding="utf-8",
    )

    violations = check_concrete_llm_tool_result_contracts(tmp_path)

    assert len(violations) == 2
    assert "must return ToolResult or UiRequest" in violations[0]
    assert "wrap it in ToolResult" in violations[1]


def test_concrete_llm_tool_result_guard_allows_typed_contract(tmp_path: Path) -> None:
    path = tmp_path / "XBrainLab" / "llm" / "tools" / "mock" / "demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
class DemoTool:
    def execute(self, study, **kwargs) -> ToolResult:
        return ToolResult(True, "Loaded")
""",
        encoding="utf-8",
    )

    assert check_concrete_llm_tool_result_contracts(tmp_path) == []


def test_backend_llm_import_guard_allows_backend_stage_contract(tmp_path: Path) -> None:
    _write_backend_file(
        tmp_path,
        """
from XBrainLab.backend.application.pipeline_stage import PipelineStage
""",
    )

    assert check_backend_llm_imports(tmp_path) == []


def test_backend_package_has_no_llm_reverse_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_backend_llm_imports(root) == []


def test_application_service_cache_guard_rejects_product_reads(tmp_path: Path) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/demo/sidebar.py",
        """
def cached_service(study):
    direct = study._application_service
    located = getattr(study, "_application_service", None)
    return direct or located
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert len(violations) == 2
    assert all("private ApplicationService cache" in item for item in violations)


def test_application_service_cache_guard_allows_runtime_owner(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/runtime.py",
        """
def cached_service(study, service):
    cached = getattr(study, "_application_service", None)
    study._application_service = service
    return cached
""",
    )

    assert check_application_service_ownership_boundaries(tmp_path) == []


def test_application_service_guard_rejects_constructor_cache_ownership(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
class ApplicationService:
    def __new__(cls, study):
        cached = getattr(study, "_application_service", None)
        study._application_service = cached
        return super().__new__(cls)
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert any("private ApplicationService cache" in item for item in violations)
    assert any(
        "writes the private ApplicationService cache" in item for item in violations
    )
    assert any("must not define __new__" in item for item in violations)


def test_application_service_guard_rejects_product_direct_construction(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/demo.py",
        """
from XBrainLab.backend.application import ApplicationService

def build(study):
    return ApplicationService(study)
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert len(violations) == 1
    assert "constructs ApplicationService directly" in violations[0]
    assert "get_application_service" in violations[0]


def test_application_service_guard_rejects_study_runtime_dependency(
    tmp_path: Path,
) -> None:
    _write_backend_file(
        tmp_path,
        """
from .application.runtime import get_application_service
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert len(violations) == 1
    assert "Study must not depend on application runtime" in violations[0]


def test_application_service_guard_rejects_pipeline_stage_service_locator(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/pipeline_stage.py",
        """
from .runtime import get_application_service

def stage(study):
    return get_application_service(study).get_view_publication()
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert violations
    assert all("pipeline_stage.py" in item for item in violations)
    assert any("must not service-locate" in item for item in violations)


def test_application_service_guard_rejects_private_adapter_resolution(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
class ApplicationService:
    def defer_notifications(self):
        return self.visualization._resolve_controller()
""",
    )

    violations = check_application_service_ownership_boundaries(tmp_path)

    assert any(
        "must use the typed adapter port" in violation for violation in violations
    )


def test_product_application_service_ownership_boundaries_are_clean() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_application_service_ownership_boundaries(root) == []


def test_montage_command_guard_rejects_analysis_owned_mutation(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/analysis_service.py",
        """
class AnalysisCommandService:
    def __init__(self, *, preprocess):
        self.preprocess = preprocess

    def handle_apply_montage(self, command):
        self.preprocess.apply_montage(command.channels, command.positions)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/preprocess_service.py",
        """
class PreprocessCommandService:
    pass
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
class _LazyAnalysisCommandService:
    def __init__(self, *, preprocess):
        self.preprocess = preprocess

    def handle_apply_montage(self, command):
        return self._service().handle_apply_montage(command)

def handlers(self):
    return {
        CommandName.APPLY_MONTAGE: self.analysis.handle_apply_montage,
    }
""",
    )

    violations = check_montage_command_ownership(tmp_path)

    assert any(
        "analysis_service.py owns handle_apply_montage" in item for item in violations
    )
    assert any(
        "depends on the preprocess mutation controller" in item for item in violations
    )
    assert any("preprocess_service.py must own" in item for item in violations)
    assert any(
        "_LazyAnalysisCommandService owns handle_apply_montage" in item
        for item in violations
    )
    assert any(
        "lazy analysis wrapper depends on preprocess" in item for item in violations
    )
    assert any("current owner(s): analysis" in item for item in violations)


def test_product_montage_command_has_one_preprocess_owner() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_montage_command_ownership(root) == []


def test_training_configuration_reset_guard_rejects_second_mutation_owner(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_runtime.py",
        """
def clear(manager):
    manager.model_holder = None
    manager.training_option = None
    manager.saliency_params = None
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_configuration_reset.py",
        """
class TrainingConfigurationResetService:
    def clear(self):
        self.training_runtime.clear_configuration()
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
def clear_again(manager):
    manager.model_holder = None
""",
    )

    violations = check_training_configuration_reset_ownership(tmp_path)

    assert len(violations) == 1
    assert "service.py" in violations[0]
    assert "model_holder" in violations[0]
    assert "owned only" in violations[0]


def test_training_configuration_reset_guard_requires_runtime_delegation(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_runtime.py",
        """
def clear(manager):
    manager.model_holder = None
    manager.training_option = None
    manager.saliency_params = None
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_configuration_reset.py",
        """
class TrainingConfigurationResetService:
    def clear(self):
        self.training.notify("config_changed")
""",
    )

    violations = check_training_configuration_reset_ownership(tmp_path)

    assert len(violations) == 1
    assert "training_runtime.clear_configuration()" in violations[0]


def test_training_configuration_reset_guard_accepts_runtime_owned_mutation(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_runtime.py",
        """
def clear(manager):
    manager.model_holder = None
    manager.training_option = None
    manager.saliency_params = None
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/training_configuration_reset.py",
        """
class TrainingConfigurationResetService:
    def clear(self):
        self.training_runtime.clear_configuration()
""",
    )

    assert check_training_configuration_reset_ownership(tmp_path) == []


def test_product_training_configuration_reset_has_one_mutation_owner() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_training_configuration_reset_ownership(root) == []


def test_agent_coordinators_are_constructor_owned_without_lazy_fallback():
    root = Path(__file__).resolve().parents[2]
    controller_path = root / "XBrainLab" / "llm" / "agent" / "controller.py"
    controller_source = controller_path.read_text(encoding="utf-8")
    controller_tree = ast.parse(controller_source, filename=str(controller_path))
    coordinator_source = (
        root / "XBrainLab" / "llm" / "agent" / "tool_execution_coordinator.py"
    ).read_text(encoding="utf-8")
    attempt_source = (
        root / "XBrainLab" / "llm" / "agent" / "tool_attempt_coordinator.py"
    ).read_text(encoding="utf-8")
    attempt_tree = ast.parse(
        attempt_source,
        filename=str(
            root / "XBrainLab" / "llm" / "agent" / "tool_attempt_coordinator.py"
        ),
    )

    controller_class = next(
        node
        for node in controller_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LLMController"
    )
    constructor = next(
        node
        for node in controller_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    constructor_attributes = {
        target.attr
        for node in ast.walk(constructor)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    }
    lazy_methods = {
        node.name
        for node in controller_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_tool_attempts", "_tool_executions"}
    }
    coordinator_getattrs = [
        node
        for node in ast.walk(controller_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
        and "coordinator" in node.args[1].value
    ]

    assert {
        "_tool_attempt_coordinator",
        "_tool_execution_coordinator",
    } <= constructor_attributes
    assert lazy_methods == set()
    assert coordinator_getattrs == []
    assert "return self._tool_attempt_coordinator.evaluate" in controller_source
    assert "context=tool_context" in controller_source
    assert "_tool_autonomy" not in controller_source
    assert "_application_state_payload" not in controller_source
    assert "get_tool_availability" not in controller_source
    assert "_handle_verification_failure" not in controller_source
    assert "_verification_failure_message" not in controller_source
    assert "context: ToolAvailabilityContext" in coordinator_source
    assert "_get_tool_attempt_context" not in coordinator_source
    attempt_class = next(
        node
        for node in attempt_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ToolAttemptCoordinator"
    )
    context_reads = {
        method.name: sum(
            1
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "context_for"
        )
        for method in attempt_class.body
        if isinstance(method, ast.FunctionDef)
        and method.name in {"evaluate", "evaluate_host_deterministic_continuation"}
    }
    assert context_reads == {
        "evaluate": 1,
        "evaluate_host_deterministic_continuation": 1,
    }
    assert "result=self._verification_result(" in attempt_source


def test_agent_existing_ui_handoff_preserves_typed_terminal_outcomes():
    root = Path(__file__).resolve().parents[2]
    manager_path = root / "XBrainLab" / "ui" / "components" / "agent_manager.py"
    manager_tree = ast.parse(
        manager_path.read_text(encoding="utf-8"),
        filename=str(manager_path),
    )
    handoff_functions = [
        node
        for node in ast.walk(manager_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "handle_workflow_ui_handoff",
            "_handle_workflow_ui_handoff_terminal",
            "_forward_workflow_ui_handoff_resolution",
        }
    ]
    runtime_calls = {
        node.func.attr
        for function in handoff_functions
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_assistant_runtime"
    }
    routed_inference = [
        node
        for function in handoff_functions
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute) and node.attr == "routed"
    ]

    assert runtime_calls == {"resolve_ui_handoff"}
    assert routed_inference == []


def test_assistant_presentation_guard_rejects_raw_ui_channels(tmp_path: Path) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        "self.response_ready.emit('Assistant', text)\n",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/agent_manager.py",
        (
            "controller.chunk_received.connect(panel.on_chunk_received)\n"
            "controller.interaction_resolved.connect(render_interaction)\n"
            "controller.generation_started.connect(mark_processing)\n"
            "controller.processing_finished.connect(clear_processing)\n"
            "controller.request_user_interaction.connect(route_raw_payload)\n"
            "chat_controller.add_agent_message('parallel transcript')\n"
        ),
    )

    violations = check_assistant_presentation_ownership(tmp_path)

    assert any("response_ready.emit" in item for item in violations)
    assert any("chunk_received.connect" in item for item in violations)
    assert any("interaction_resolved.connect" in item for item in violations)
    assert any("generation_started.connect" in item for item in violations)
    assert any("processing_finished.connect" in item for item in violations)
    assert any("request_user_interaction.connect" in item for item in violations)
    assert any("add_agent_message" in item for item in violations)


def test_assistant_presentation_guard_rejects_ui_owned_activity(tmp_path: Path) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/agent_manager.py",
        "activity = AssistantTurnActivity(phase=phase)\n",
    )

    violations = check_assistant_presentation_ownership(tmp_path)

    assert len(violations) == 1
    assert "controller is the sole AssistantTurnActivity publisher" in violations[0]


def test_assistant_presentation_guard_rejects_legacy_chat_streaming_api(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/chat/panel.py",
        (
            "class ChatPanel:\n"
            "    current_agent_bubble = None\n"
            "    def on_chunk_received(self, text): pass\n"
            "    def collapse_agent_message(self, text): pass\n"
        ),
    )

    violations = check_assistant_presentation_ownership(tmp_path)

    assert len(violations) == 3
    assert all("legacy streaming transcript" in item for item in violations)


def test_product_assistant_presentation_has_one_semantic_owner() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_assistant_presentation_ownership(root) == []


def test_assistant_turn_scope_guard_rejects_manual_product_mode_transport(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
class LLMController:
    execution_mode_changed = signal()
    def set_execution_mode(self, mode):
        self._execution_mode = mode
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_command_dispatcher.py",
        """
class AssistantCommandDispatcher:
    mode_requested = signal()
    def set_mode(self, mode):
        return self._emit_or_call("set_execution_mode", mode)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        """
class AssistantRuntimeLifecycle:
    def set_execution_mode(self, mode):
        self.runtime.set_mode(mode)
    def set_mode(self, mode):
        self.runtime.set_mode(mode)
    def activate(self, config, execution_mode: str):
        return self.runtime.activate(config)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/agent_manager.py",
        """
_ASSISTANT_IDLE_POLICY_MODE = "ask"
class AgentManager:
    def configure(self, mode):
        self._execution_mode = mode
        self.lifecycle.activate(self.config, execution_mode=mode)
    def _on_execution_mode_changed(self, mode):
        self._execution_mode = mode
    def _sync_execution_mode_ui(self):
        return self._execution_mode
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/assembler.py",
        """
class ContextAssembler:
    def set_execution_mode(self, mode):
        self._execution_mode = mode
""",
    )

    violations = check_assistant_turn_scope_ownership(tmp_path)

    assert len(violations) == 18
    assert sum("controller.py" in item for item in violations) == 3
    assert sum("assistant_command_dispatcher.py" in item for item in violations) == 3
    assert sum("assistant_runtime_lifecycle.py" in item for item in violations) == 3
    assert sum("agent_manager.py" in item for item in violations) == 7
    assert sum("assembler.py" in item for item in violations) == 2
    assert all("immutable AssistantTurnRequest scope" in item for item in violations)


def test_product_assistant_autonomy_has_no_manual_mode_transport() -> None:
    root = Path(__file__).resolve().parents[2]

    assert check_assistant_turn_scope_ownership(root) == []


def test_agent_manager_runtime_lifecycle_has_one_focused_owner():
    root = Path(__file__).resolve().parents[2]
    manager_path = root / "XBrainLab" / "ui" / "components" / "agent_manager.py"
    lifecycle_path = (
        root / "XBrainLab" / "ui" / "components" / "assistant_runtime_lifecycle.py"
    )
    manager_tree = ast.parse(
        manager_path.read_text(encoding="utf-8"),
        filename=str(manager_path),
    )
    lifecycle_tree = ast.parse(
        lifecycle_path.read_text(encoding="utf-8"),
        filename=str(lifecycle_path),
    )
    manager = next(
        node
        for node in manager_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AgentManager"
    )
    lifecycle = next(
        node
        for node in lifecycle_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AssistantRuntimeLifecycle"
    )
    manager_methods = {
        node.name for node in manager.body if isinstance(node, ast.FunctionDef)
    }
    lifecycle_methods = {
        node.name for node in lifecycle.body if isinstance(node, ast.FunctionDef)
    }
    manager_assignments = {
        target.attr
        for node in ast.walk(manager)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    }

    assert {
        "_load_runtime_config",
        "_assistant_runtime_start_status",
        "_handle_local_runtime_first_run_choice",
        "_on_agent_runtime_state_changed",
    }.isdisjoint(manager_methods)
    assert {"agent_controller", "agent_initialized", "_agent_dispatcher"}.isdisjoint(
        manager_assignments
    )
    assert {
        "load_config",
        "apply_first_run_choice",
        "activate",
        "start",
        "switch_model",
        "close",
    } <= lifecycle_methods


def test_ui_and_agent_never_rebuild_publication_from_separate_state_reads():
    root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for package in (root / "XBrainLab" / "ui", root / "XBrainLab" / "llm"):
        for path in package.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(
                    node.func,
                    ast.Attribute,
                ):
                    continue
                if node.func.attr in {"get_state", "get_capabilities"}:
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno}: "
                        f"{node.func.attr}() bypasses atomic view publication"
                    )

    assert violations == [], (
        "UI and agent product code must read get_view_publication() instead of "
        "reconstructing workflow truth from separate reads:\n" + "\n".join(violations)
    )


def test_ui_and_llm_publication_consumers_use_effective_capabilities():
    root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for package in (root / "XBrainLab" / "ui", root / "XBrainLab" / "llm"):
        for path in package.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            publication_names = _application_view_publication_names(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute) or node.attr != "capabilities":
                    continue
                if _is_application_view_reference(node.value, publication_names):
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno}: "
                        "read effective_capabilities instead of publication.capabilities"
                    )

    assert violations == [], (
        "UI and LLM consumers must apply stale/fail-closed publication policy:\n"
        + "\n".join(violations)
    )


def test_publication_capability_guard_detects_direct_and_aliased_reads():
    tree = ast.parse(
        """
view = service.get_view_publication()
alias = view
unsafe = view.capabilities
also_unsafe = alias.capabilities
safe = view.effective_capabilities
"""
    )

    publication_names = _application_view_publication_names(tree)
    direct_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "capabilities"
        and _is_application_view_reference(node.value, publication_names)
    ]

    assert publication_names == {"view", "alias"}
    assert len(direct_reads) == 2


def _application_view_publication_names(tree: ast.AST) -> set[str]:
    """Return local names proven to carry an ApplicationViewPublication."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]:
                if argument.annotation is not None and (
                    "ApplicationViewPublication" in ast.unparse(argument.annotation)
                ):
                    names.add(argument.arg)
        if isinstance(node, ast.Assign) and _calls_view_publication(node.value):
            names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and _calls_view_publication(node.value)
        ):
            names.add(node.target.id)

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in names:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    return names


def _calls_view_publication(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_view_publication"
    )


def _is_application_view_reference(node: ast.AST, names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names or "publication" in node.id.lower()
    if isinstance(node, ast.Call):
        return _calls_view_publication(node)
    return isinstance(node, ast.Attribute) and "publication" in node.attr.lower()


def _write_ui_file(root, source: str) -> None:
    path = root / "XBrainLab" / "ui" / "panels" / "demo" / "sidebar.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def test_ui_agent_worker_internal_guard_flags_engine_access(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def current_model(agent_controller):
    return agent_controller.worker.engine.config.model_name
""",
    )

    violations = check_ui_agent_worker_internal_access(tmp_path)

    assert len(violations) == 2
    assert all("queued assistant runtime publication" in item for item in violations)


def test_ui_agent_worker_internal_guard_rejects_cross_thread_runtime_snapshot(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def current_model(agent_controller):
    return agent_controller.runtime_snapshot().get("model_name")
""",
    )

    violations = check_ui_agent_worker_internal_access(tmp_path)

    assert len(violations) == 1
    assert "AssistantRuntimeCoordinator" in violations[0]


def test_assistant_runtime_selection_guard_rejects_duplicate_runtime_policy(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/worker.py",
        """
def initialize_agent(self):
    config = LLMConfig.load_from_file()
    selection = LLMConfig.assistant_runtime_selection_from(config)
    return config.available_local_model_id(selection.model_id)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
def set_model(self, model_id):
    if model_id in LLMConfig.allowed_local_model_ids():
        self.sig_reinit.emit(model_id)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        """
def readiness(config):
    return config.local_backend_status_message(config.model_name)
""",
    )

    violations = check_assistant_runtime_selection_ownership(tmp_path)

    assert any("worker.py" in item and "load_from_file" in item for item in violations)
    assert any(
        "worker.py" in item and "assistant_runtime_selection_from" in item
        for item in violations
    )
    assert any(
        "worker.py" in item and "available_local_model_id" in item
        for item in violations
    )
    assert any(
        "controller.py" in item and "allowed_local_model_ids" in item
        for item in violations
    )
    assert any(
        "assistant_runtime_lifecycle.py" in item
        and "local_backend_status_message" in item
        for item in violations
    )


def test_assistant_runtime_selection_guard_accepts_spec_consumers_and_one_owner(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/core/runtime_selection.py",
        """
def resolve(config):
    if config.local_backend_ready(config.model_name):
        return config.local_backend_status_message(config.model_name)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        """
def activate(self, config):
    resolution = self._resolver.resolve(config)
    self._dispatcher.initialize(resolution.launch_spec)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/controller.py",
        """
def set_model(self, launch_spec):
    self.sig_reinit.emit(launch_spec)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/llm/agent/worker.py",
        """
def initialize_agent(self, launch_spec):
    config = launch_spec.build_config()
""",
    )

    assert check_assistant_runtime_selection_ownership(tmp_path) == []


def _write_llm_file(root, source: str) -> None:
    path = root / "XBrainLab" / "llm" / "pipeline_state.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def _write_mcp_file(root, source: str) -> None:
    path = root / "XBrainLab" / "mcp" / "http_server.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def _write_headless_verifier_file(root, source: str) -> None:
    path = root / "scripts" / "dev" / "verify_real_tools.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def _write_public_training_smoke_file(root, source: str) -> None:
    path = root / "scripts" / "dev" / "run_public_cross_source_training_smoke.py"
    path.parent.mkdir(parents=True, exist_ok=True)
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


def test_weak_test_name_guard_flags_product_initialization_names(tmp_path):
    path = tmp_path / "tests" / "integration" / "pipeline" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_visualization_panel_initialization():
    pass


def test_evaluation_panel_init():
    pass
""",
        encoding="utf-8",
    )

    violations = check_weak_test_names(tmp_path)

    assert len(violations) == 2
    assert "test_visualization_panel_initialization" in violations[0]
    assert "command/result/state semantics" in violations[0]
    assert "test_evaluation_panel_init" in violations[1]


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


def test_product_success_panel_instance_guard_flags_generic_assertion(tmp_path):
    path = tmp_path / "tests" / "integration" / "pipeline" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_visualization_panel_uses_command_state(qtbot):
    panel = VisualizationPanel(parent=parent)
    assert isinstance(panel, VisualizationPanel)
""",
        encoding="utf-8",
    )

    violations = check_product_success_generic_panel_instance_assertions(tmp_path)

    assert len(violations) == 1
    assert "generic panel isinstance assertion" in violations[0]
    assert "CommandResult" in violations[0]


def test_product_success_panel_instance_guard_allows_ui_visible_evidence(tmp_path):
    path = tmp_path / "tests" / "integration" / "pipeline" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_visualization_panel_uses_command_state(qtbot):
    panel = VisualizationPanel(parent=parent)
    panel.update_panel()
    assert panel.last_application_query.failed
    assert panel.last_application_query.message == "Create epochs first."
""",
        encoding="utf-8",
    )

    assert check_product_success_generic_panel_instance_assertions(tmp_path) == []


def test_mcp_weak_response_assertion_guard_flags_non_none_response(tmp_path):
    path = tmp_path / "tests" / "unit" / "mcp" / "test_server.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_mcp_response_exists(server):
    response = server.handle_message({"method": "tools/list", "id": 1})
    assert response is not None
""",
        encoding="utf-8",
    )

    violations = check_mcp_weak_response_assertions(tmp_path)

    assert len(violations) == 1
    assert "generic non-None MCP assertion" in violations[0]
    assert "JSON-RPC envelope" in violations[0]


def test_mcp_weak_response_assertion_guard_allows_exact_protocol_shape(tmp_path):
    path = tmp_path / "tests" / "integration" / "mcp" / "test_stdio_server.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_mcp_response_shape(server):
    response = server.handle_message({"method": "tools/list", "id": 1})
    assert isinstance(response, dict), response
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" not in response
    assert response["result"]["tools"][0]["name"] == "scan_source"
""",
        encoding="utf-8",
    )

    assert check_mcp_weak_response_assertions(tmp_path) == []


def test_pipeline_state_weak_string_guard_flags_generic_non_empty_assertions(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "test_pipeline_state.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_every_config_has_tools_and_system_prompt():
    for stage, config in STAGE_CONFIG.items():
        assert len(config["system_prompt"]) > 0


def test_every_stage_has_label():
    for stage in PipelineStage:
        assert len(stage.label) > 0
""",
        encoding="utf-8",
    )

    violations = check_pipeline_state_weak_string_assertions(tmp_path)

    assert len(violations) == 2
    assert "generic non-empty pipeline state string assertion" in violations[0]
    assert "exact stage prompt markers" in violations[0]
    assert "stage-label display contract" in violations[1]


def test_pipeline_state_weak_string_guard_allows_exact_contracts(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "test_pipeline_state.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_every_system_prompt_matches_stage_contract():
    for stage, markers in EXPECTED_STAGE_PROMPT_MARKERS.items():
        prompt = STAGE_CONFIG[stage]["system_prompt"]
        assert prompt.startswith("You are XBrainLab Assistant"), stage
        assert "### What you should do" in prompt, stage
        for marker in markers:
            assert marker in prompt, f"{stage}: missing prompt marker {marker!r}"


def test_every_stage_label_matches_display_contract():
    assert {stage: stage.label for stage in PipelineStage} == EXPECTED_STAGE_LABELS
""",
        encoding="utf-8",
    )

    assert check_pipeline_state_weak_string_assertions(tmp_path) == []


def test_llm_parser_weak_parse_guard_flags_generic_non_none_assertion(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "test_parser.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_valid_json_command():
    parsed = CommandParser.parse(text)
    assert parsed is not None
    cmd, params = parsed[0]
    assert cmd == "load_data"


def test_parse_arguments_alias():
    result = CommandParser.parse(text)
    assert result is not None
""",
        encoding="utf-8",
    )
    misc_path = tmp_path / "tests" / "unit" / "llm" / "test_misc_coverage.py"
    misc_path.write_text(
        """
def test_parse_returns_commands():
    result = CommandParser.parse(text)
    assert result is not None
""",
        encoding="utf-8",
    )

    violations = check_llm_parser_weak_parse_assertions(tmp_path)

    assert len(violations) == 3
    assert "generic non-None parser assertion" in violations[0]
    assert "exact (tool_name, parameters) parse result" in violations[0]
    assert "test_misc_coverage.py" in violations[2]


def test_llm_parser_weak_parse_guard_allows_exact_parse_results(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "test_parser.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_valid_json_command():
    parsed = CommandParser.parse(text)
    assert parsed == [("load_data", {"file_paths": ["/data/A.gdf"]})]


def test_no_json_block():
    result = CommandParser.parse(text)
    assert result is None
""",
        encoding="utf-8",
    )

    assert check_llm_parser_weak_parse_assertions(tmp_path) == []


def test_llm_application_surface_result_guard_flags_generic_non_none_assertion(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "llm" / "tools" / "test_application_surface.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_scan_source_routes_to_command_surface():
    result = execute_application_tool_command(study, "scan_source", params)
    assert result is not None
    assert result.command_name == "scan_source"
""",
        encoding="utf-8",
    )

    violations = check_llm_application_surface_weak_result_assertions(tmp_path)

    assert len(violations) == 1
    assert "generic non-None application-surface assertion" in violations[0]
    assert "ToolCommandResult" in violations[0]


def test_llm_application_surface_result_guard_allows_exact_result_contract(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "llm" / "tools" / "test_application_surface.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_scan_source_routes_to_command_surface():
    result = execute_application_tool_command(study, "scan_source", params)
    assert isinstance(result, ToolCommandResult), result
    assert result.tool_name == "scan_source"
    assert result.command_name == "scan_source"
    assert result.raw_result["status"] == "ok"
    assert result.capability["command_name"] == "scan_source"
    assert result.state["interpretation"]["has_scan_result"] is True
""",
        encoding="utf-8",
    )

    assert check_llm_application_surface_weak_result_assertions(tmp_path) == []


def test_llm_agent_intent_boundary_guard_flags_generic_non_none_assertion(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "llm" / "agent" / "test_controller.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_requested_intent_boundary_reads_application_policy(ctrl):
    result = ctrl._check_requested_intent_boundary("set_model")
    assert result is not None
    assert result.command_name == "train"
""",
        encoding="utf-8",
    )

    violations = check_llm_agent_intent_boundary_weak_result_assertions(tmp_path)

    assert len(violations) == 1
    assert "generic non-None agent intent-boundary assertion" in violations[0]
    assert "ToolCommandResult" in violations[0]


def test_llm_agent_intent_boundary_guard_allows_exact_result_contract(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "llm" / "agent" / "test_controller.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_requested_intent_boundary_reads_application_policy(ctrl):
    result = ctrl._check_requested_intent_boundary("set_model")
    assert isinstance(result, ToolCommandResult), result
    assert result.tool_name == "set_model"
    assert result.command_name == "train"
    assert result.blocked_reason == "Generate datasets before training"
    assert result.message == "Requested workflow step 'train' is not available: Generate datasets before training"
    assert result.capability["command_name"] == "train"
    assert result.state["pipeline_stage"] == "empty"
""",
        encoding="utf-8",
    )

    assert check_llm_agent_intent_boundary_weak_result_assertions(tmp_path) == []


def test_llm_tool_definition_guard_flags_generic_non_empty_assertions(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "tools" / "test_definitions.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_has_name(tool_cls):
    assert len(tool_cls.name.fget(None)) > 0


def test_has_description(tool_cls):
    desc = tool_cls.description.fget(None)
    assert len(desc) > 0
""",
        encoding="utf-8",
    )

    violations = check_llm_tool_definition_weak_string_assertions(tmp_path)

    assert len(violations) == 2
    assert "generic non-empty tool definition assertion" in violations[0]
    assert "exact tool name" in violations[0]


def test_llm_tool_definition_guard_allows_exact_contract_assertions(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "tools" / "test_definitions.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_tool_contract(tool_cls):
    assert _property_value(tool_cls.name) == EXPECTED_TOOL_CONTRACTS[tool_cls]["name"]
    assert tuple(params["properties"].keys()) == EXPECTED_TOOL_CONTRACTS[tool_cls]["properties"]
    assert tuple(params["required"]) == EXPECTED_TOOL_CONTRACTS[tool_cls]["required"]
""",
        encoding="utf-8",
    )

    assert check_llm_tool_definition_weak_string_assertions(tmp_path) == []


def test_llm_agent_confirmation_guard_flags_generic_pending_assertion(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "agent" / "test_controller.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_confirmation_required_pauses_execution(ctrl):
    ctrl._process_tool_calls([("clear_dataset", {})], "{}")
    assert ctrl._pending_confirmation is not None
    assert ctrl._pending_confirmation[0] == "clear_dataset"
""",
        encoding="utf-8",
    )

    violations = check_llm_agent_confirmation_weak_pending_assertions(tmp_path)

    assert len(violations) == 1
    assert "generic pending-confirmation existence assertion" in violations[0]
    assert "AgentConfirmationRequest fields" in violations[0]


def test_llm_agent_confirmation_guard_allows_typed_correlated_contract(tmp_path):
    path = tmp_path / "tests" / "unit" / "llm" / "agent" / "test_controller.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_confirmation_required_pauses_execution(ctrl):
    ctrl._process_tool_calls([("clear_dataset", {})], "{}")
    request = ctrl.pending_interactions.confirmation_request
    assert isinstance(request, AgentConfirmationRequest)
    assert request.command_name == "clear_dataset"
    assert request.publication_generation == 4
    ctrl.confirmation_requested.emit.assert_called_once_with(request)
    resolution = AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )
    assert resolution.matches(request)
    ctrl.on_user_confirmation_resolved(resolution)
""",
        encoding="utf-8",
    )

    assert check_llm_agent_confirmation_weak_pending_assertions(tmp_path) == []


def test_llm_controller_integration_guard_flags_generic_initialization(
    tmp_path,
):
    path = (
        tmp_path
        / "tests"
        / "unit"
        / "llm"
        / "agent"
        / ("test_controller_integration.py")
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_controller_initialization(qapp):
    controller = LLMController(study)
    assert controller.registry is not None
    assert controller.assembler is not None
    assert controller.verifier is not None
    assert len(controller.registry.get_all_tools()) > 0
""",
        encoding="utf-8",
    )

    violations = check_llm_controller_integration_weak_initialization_assertions(
        tmp_path
    )

    assert len(violations) == 4
    assert "generic controller initialization evidence" in violations[0]
    assert "exact tool names" in violations[0]


def test_llm_controller_integration_guard_allows_exact_contract(tmp_path):
    path = (
        tmp_path
        / "tests"
        / "unit"
        / "llm"
        / "agent"
        / ("test_controller_integration.py")
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """
def test_controller_initialization(qapp):
    controller = LLMController(study)
    assert isinstance(controller.registry, ToolRegistry)
    assert isinstance(controller.assembler, ContextAssembler)
    assert isinstance(controller.verifier, VerificationLayer)
    assert tuple(tool.name for tool in controller.registry.get_all_tools()) == EXPECTED_CONTROLLER_TOOL_NAMES
""",
        encoding="utf-8",
    )

    assert (
        check_llm_controller_integration_weak_initialization_assertions(tmp_path) == []
    )


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
from XBrainLab.ui.application_capabilities import run_controller_compatibility_call


def test_product_action():
    run_controller_compatibility_call(widget, lambda: controller.start_training())
""",
        encoding="utf-8",
    )

    violations = check_product_success_legacy_fallback_tests(tmp_path)

    assert len(violations) == 2
    assert "tests/integration/ui/test_demo.py" in violations[0]
    assert "controller compatibility product-success evidence" in violations[0]


def test_product_success_legacy_fallback_test_guard_flags_controller_lookup(
    tmp_path,
):
    path = tmp_path / "tests" / "integration" / "backend" / "test_demo.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.ui import application_capabilities


def test_product_action(study):
    return application_capabilities.get_controller_for_compatibility_context(
        widget,
        study,
        "training",
    )
""",
        encoding="utf-8",
    )

    violations = check_product_success_legacy_fallback_tests(tmp_path)

    assert len(violations) == 1
    assert "get_controller_for_compatibility_context" in violations[0]


def test_product_success_legacy_fallback_test_guard_allows_unit_compatibility_test(
    tmp_path,
):
    path = tmp_path / "tests" / "unit" / "ui" / "test_legacy_compat.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
from XBrainLab.ui.application_capabilities import run_controller_compatibility_call


def test_legacy_compat():
    return run_controller_compatibility_call(object(), lambda: "legacy-ok")
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


def test_headless_verifier_state_guard_flags_direct_study_truth(tmp_path):
    _write_headless_verifier_file(
        tmp_path,
        """
def verify(study):
    if study.loaded_data_list:
        return len(study.datasets)
    study.generate_plan()
    if study.is_training():
        study.stop_training()
    study.train(interact=False)
    return 0
""",
    )

    violations = check_headless_verifier_direct_study_state(tmp_path)

    assert len(violations) == 6
    assert "study.loaded_data_list" in violations[0]
    assert "QueryStateCommand" in violations[0]
    assert "study.datasets" in violations[1]
    assert "study.generate_plan" in violations[2]
    assert "TrainCommand" in violations[2]
    assert "study.is_training" in violations[3]
    assert "StopTrainingCommand" in violations[3]
    assert "study.stop_training" in violations[4]
    assert "study.train" in violations[5]


def test_headless_verifier_state_guard_allows_command_query_truth(tmp_path):
    _write_headless_verifier_file(
        tmp_path,
        """
from XBrainLab.backend.application import (
    QueryStateCommand,
    StopTrainingCommand,
    get_application_service,
)


def verify(study):
    service = get_application_service(study)
    state = service.execute(QueryStateCommand(query="state"))
    if state.failed:
        raise RuntimeError(state.message)
    service.execute(StopTrainingCommand())
""",
    )

    assert check_headless_verifier_direct_study_state(tmp_path) == []


def test_headless_verifier_state_guard_scans_public_training_smoke(tmp_path):
    _write_public_training_smoke_file(
        tmp_path,
        """
def run_fixture_smoke(study):
    dataset_count = len(study.datasets)
    trainer = study.trainer
    study.train(interact=False)
    return dataset_count, trainer
""",
    )

    violations = check_headless_verifier_direct_study_state(tmp_path)

    assert len(violations) == 3
    assert "scripts/dev/run_public_cross_source_training_smoke.py" in violations[0]
    assert "study.datasets" in violations[0]
    assert "study.trainer" in violations[1]
    assert "study.train" in violations[2]


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


def test_direct_backend_service_execute_guard_resolves_stored_and_bound_aliases(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def run(self, study, command):
    service = get_application_service(study)
    stored_service = service
    execute_command = stored_service.execute
    execute_command(command)

    facade = BackendFacade(study)
    facade_service = facade.service
    facade_service.execute(command)

class StoredService:
    def __init__(self, study):
        self._service = ApplicationService(study)

    def run(self, command):
        execute = self._service.execute
        execute(command)
""",
    )

    violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(violations) == 3
    assert all("execute_application_command" in item for item in violations)


def test_direct_backend_service_execute_guard_resolves_import_aliases_and_containers(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
from XBrainLab.backend.application import (
    ApplicationService as ServiceFactory,
    get_application_service as resolve_service,
)

def run(self, study, command):
    services = {"primary": ServiceFactory(study)}
    execute_primary = services["primary"].execute
    execute_primary(command)

    (secondary_service,) = (resolve_service(study),)
    secondary_service.execute(command)
""",
    )

    violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(violations) == 2
    assert all("execute_application_command" in item for item in violations)


def test_direct_backend_service_execute_guard_does_not_trust_symbol_from_fake_module(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
from fake_runtime import ApplicationService as ServiceFactory

def run(self, study, command):
    return ServiceFactory(study).execute(command)
""",
    )

    assert check_ui_direct_backend_service_execute(tmp_path) == []


def test_direct_backend_service_execute_guard_respects_import_alias_shadowing(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
from XBrainLab.backend.application import ApplicationService as ServiceFactory

def run(self, ServiceFactory, study, command):
    return ServiceFactory(study).execute(command)
""",
    )

    assert check_ui_direct_backend_service_execute(tmp_path) == []


def test_origin_guards_resolve_aliased_getattr_calls(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self, loader, study, command):
    read_attribute = getattr

    mutate = read_attribute(self.dataset_controller, "update_metadata")
    mutate(0, subject="S01")

    apply_loader = read_attribute(loader, "apply")
    apply_loader(self.controller.study, force_update=True)

    service = get_application_service(study)
    execute_command = read_attribute(service, "execute")
    execute_command(command)
""",
    )

    controller_violations = check_ui_direct_controller_mutations(tmp_path)
    loader_violations = check_ui_direct_loader_apply(tmp_path)
    service_violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(controller_violations) == 1
    assert "controller.update_metadata" in controller_violations[0]
    assert len(loader_violations) == 1
    assert "loader.apply" in loader_violations[0]
    assert len(service_violations) == 1
    assert "execute_application_command" in service_violations[0]


def test_origin_guards_resolve_imported_getattr_and_cast_aliases(tmp_path):
    _write_ui_file(
        tmp_path,
        """
from builtins import getattr as read_attribute
from typing import cast as typed_cast

def run(self, loader, study, command):
    controller_alias = typed_cast(object, self.dataset_controller)
    mutate = read_attribute(controller_alias, "update_metadata")
    mutate(0, subject="S01")

    loader_alias = typed_cast(object, loader)
    read_attribute(loader_alias, "apply")(
        self.controller.study,
        force_update=True,
    )

    service = typed_cast(object, get_application_service(study))
    read_attribute(service, "execute")(command)
""",
    )

    controller_violations = check_ui_direct_controller_mutations(tmp_path)
    loader_violations = check_ui_direct_loader_apply(tmp_path)
    service_violations = check_ui_direct_backend_service_execute(tmp_path)

    assert len(controller_violations) == 1
    assert "controller.update_metadata" in controller_violations[0]
    assert len(loader_violations) == 1
    assert "loader.apply" in loader_violations[0]
    assert len(service_violations) == 1
    assert "execute_application_command" in service_violations[0]


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
    self._update_panel_after_command_result(result)
""",
    )

    assert check_ui_post_command_local_refreshes(tmp_path) == []


def test_post_command_refresh_guard_flags_async_result_local_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    def _handle_result(result):
        if result.failed:
            return
        self.update_info()

    execute_application_command_async(
        self,
        SomeCommand(),
        on_result=_handle_result,
    )
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "_handle_result" in violations[0]
    assert "async" in violations[0]


def test_post_command_refresh_guard_flags_async_method_callback_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    execute_application_command_async(
        self,
        SomeCommand(),
        on_result=self._handle_result,
    )

def _handle_result(self, result):
    if result.failed:
        return
    self.mark_refresh_dirty()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "_handle_result" in violations[0]
    assert "mark_refresh_dirty" in violations[0]


def test_post_command_refresh_guard_allows_async_read_only_query_refresh_false(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    def _handle_result(result):
        self.update_info()

    execute_application_command_async(
        self,
        QueryStateCommand(query="state"),
        on_result=_handle_result,
        refresh=False,
    )
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
        run_controller_compatibility_call(
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
        run_controller_compatibility_call(
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
        self._run_preprocess_compatibility_call(
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
    assert "run_controller_compatibility_call" in violations[0]


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
    assert "run_controller_compatibility_call" in violations[0]


def test_controller_render_fallback_guard_allows_explicit_legacy_wrapper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_panel(self):
    result = execute_application_command(self, QueryStateCommand(), refresh=False)
    if result is None:
        rows = run_controller_compatibility_call(
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
        ok, running = run_controller_compatibility_call(
            self,
            lambda: self.controller.is_training(),
        )
        if ok and running:
            return
    execute_application_command(self, TrainCommand())
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_capability_readiness_guard_allows_local_compatibility_value_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
    if scan_capability is None:
        available, is_locked = self._compatibility_controller_value(
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


def test_observer_handler_refresh_guard_flags_local_render_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "training_stopped",
        self._on_training_stopped,
    )

def _on_training_stopped(self):
    self.update_loop()
    refresh_after_observer(self, event_name="training_stopped")
""",
    )

    violations = check_ui_observer_handlers_call_refresh_coordinator(tmp_path)

    assert len(violations) == 1
    assert "_on_training_stopped" in violations[0]
    assert "local render refresh" in violations[0]


def test_observer_handler_refresh_guard_allows_training_updated_live_tick(tmp_path):
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
    assert "compatibility loader adapter" in violations[0]


def test_direct_loader_apply_guard_resolves_alias_getattr_and_attribute_chain(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def apply_loaders(self, loader):
    alias = loader
    apply_alias = getattr(alias, "apply")
    apply_alias(self.controller.study, force_update=True)
    self.adapters.data_loader.apply(self.controller.study, force_update=True)
""",
    )

    violations = check_ui_direct_loader_apply(tmp_path)

    assert len(violations) == 2
    assert all("loader.apply" in item for item in violations)


def test_direct_loader_apply_guard_resolves_destructuring_and_container_aliases(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def apply_loaders(self, loader):
    loaders = {"selected": loader}
    loaders["selected"].apply(self.controller.study, force_update=True)

    (loader_alias,) = (loader,)
    apply_alias = loader_alias.apply
    apply_alias(self.controller.study, force_update=True)
""",
    )

    violations = check_ui_direct_loader_apply(tmp_path)

    assert len(violations) == 2
    assert all("loader.apply" in item for item in violations)


def test_direct_loader_apply_guard_rejects_named_legacy_adapter_without_gate(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _apply_legacy_loader(self, loader):
    loader.apply(self.controller.study, force_update=True)
""",
    )

    violations = check_ui_direct_loader_apply(tmp_path)

    assert len(violations) == 1
    assert "loader.apply" in violations[0]


def test_direct_loader_apply_guard_allows_structurally_gated_adapter(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def apply_loader(self, loader):
    return run_controller_compatibility_call(
        self,
        lambda: self._apply_loader_for_test_double(loader),
    )

def _apply_loader_for_test_double(self, loader):
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


def test_training_sidebar_direct_controller_calls_are_compatibility_gated():
    root = Path(__file__).resolve().parents[2]

    violations = [
        violation
        for violation in check_ui_direct_controller_mutations(root)
        if "XBrainLab/ui/panels/training/sidebar.py" in violation
    ]

    assert violations == []


def test_direct_controller_mutation_guard_resolves_alias_chain_getattr_and_bound_alias(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def mutate(self):
    nested = self.context.dataset_controller
    alias = nested
    bound_mutation = alias.update_metadata
    bound_mutation(0, subject="S01")

    dynamic_controller = getattr(self.context, "dataset_controller")
    dynamic_mutation = getattr(dynamic_controller, "update_metadata")
    dynamic_mutation(1, subject="S02")

    self.context.dataset_controller.update_metadata(2, subject="S03")
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 3
    assert all("update_metadata" in item for item in violations)


def test_direct_controller_mutation_guard_resolves_containers_destructuring_and_callbacks(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def mutate(self, selected_key):
    controllers = {"dataset": self.dataset_controller}
    controllers[selected_key].update_metadata(0, subject="S01")

    (preprocess_alias,) = (self.preprocess_controller,)
    preprocess_alias.apply_filter(1.0, 40.0, [50.0])

    callback = self.training_controller.start_training
    fake_gate(self, callback)

def fake_gate(owner, callback):
    return callback()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 3
    assert any("update_metadata" in item for item in violations)
    assert any("apply_filter" in item for item in violations)
    assert any("start_training" in item for item in violations)


def test_direct_controller_mutation_guard_resolves_dict_constructor_container(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def mutate(self):
    controllers = dict(active=self.dataset_controller)
    controllers["active"].update_metadata(0, subject="S01")
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.update_metadata" in violations[0]


def test_direct_controller_mutation_guard_resolves_mapping_access_and_iteration(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def mutate(self, selected_key):
    controllers = {"active": self.dataset_controller}
    controllers.get(selected_key).update_metadata(0, subject="S01")

    for controller_alias in controllers.values():
        controller_alias.reset()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 2
    assert any("update_metadata" in item for item in violations)
    assert any("reset" in item for item in violations)


def test_direct_controller_mutation_guard_keeps_static_safe_container_item_clean(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def refresh(self):
    targets = {
        "backend": self.dataset_controller,
        "presentation": self.history_table,
    }
    targets["presentation"].clearContents()
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


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
    run_controller_compatibility_call(
        self,
        lambda: self.controller.start_training(),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_allows_trusted_gate_import_alias(tmp_path):
    _write_ui_file(
        tmp_path,
        """
from XBrainLab.ui.application_capabilities import (
    run_controller_compatibility_call as compatibility_gate,
)

def run(self):
    return compatibility_gate(
        self,
        lambda: self.controller.start_training(),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_rejects_untrusted_gate_alias_with_bound_callback(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
from fake_runtime import fake_gate as compatibility_gate

def run(self):
    callback = self.controller.start_training
    return compatibility_gate(self, callback)
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.start_training" in violations[0]


def test_direct_controller_mutation_guard_rejects_rebound_trusted_import_alias(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
from XBrainLab.ui.application_capabilities import (
    run_controller_compatibility_call as compatibility_gate,
)

compatibility_gate = fake_gate

def run(self):
    return compatibility_gate(
        self,
        lambda: self.controller.start_training(),
    )
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.start_training" in violations[0]


def test_direct_controller_mutation_guard_allows_named_legacy_wrapper_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_preprocess_compatibility_call(
        "Filtering Blocked",
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )

def _run_preprocess_compatibility_call(self, title, callback):
    return run_controller_compatibility_call(self, callback)
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_rejects_reserved_wrapper_without_real_gate(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_preprocess_compatibility_call(
        "Filtering Blocked",
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )

def _run_preprocess_compatibility_call(self, title, callback):
    return callback()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.apply_filter" in violations[0]


def test_direct_controller_mutation_guard_rejects_shadowed_compatibility_gate(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    return run_controller_compatibility_call(
        self,
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )

def run_controller_compatibility_call(owner, callback):
    return callback()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.apply_filter" in violations[0]


def test_direct_controller_mutation_guard_rejects_rebound_compatibility_gate(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
run_controller_compatibility_call = fake_gate

def run(self):
    return run_controller_compatibility_call(
        self,
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.apply_filter" in violations[0]


def test_direct_controller_mutation_allowlist_is_bound_to_expected_receiver(
    tmp_path,
):
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/chat/panel.py",
        """
def _select_response_action(self, presentation_id):
    return self.training_controller.consume_response_actions(presentation_id)
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.consume_response_actions" in violations[0]


def test_direct_controller_mutation_allowlist_accepts_exact_receiver_and_callsite(
    tmp_path,
):
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/chat/panel.py",
        """
def _select_response_action(self, presentation_id):
    return self._chat_controller.consume_response_actions(presentation_id)
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_allowlist_rejects_wrong_callsite(tmp_path):
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/chat/panel.py",
        """
def forged_callsite(self, presentation_id):
    return self._chat_controller.consume_response_actions(presentation_id)
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.consume_response_actions" in violations[0]


def test_direct_controller_mutation_guard_rejects_named_fallback_helper_without_gate(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def _run_metadata_update_fallback(self, controller):
    controller.update_metadata(0, subject="S01")
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.update_metadata" in violations[0]


def test_direct_controller_mutation_guard_rejects_unknown_controller_method(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def apply_new_backend_mutation(self):
    self.dataset_controller.rewrite_pipeline_state()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.rewrite_pipeline_state" in violations[0]


def test_legacy_mutation_helper_guard_flags_unwrapped_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_legacy_label_import()

def _run_legacy_label_import(self):
    self.controller.apply_labels_sequence([], [], None, None)
""",
    )

    violations = check_ui_legacy_mutation_helper_calls(tmp_path)

    assert len(violations) == 1
    assert "_run_legacy_label_import" in violations[0]
    assert "run_controller_compatibility_call" in violations[0]


def test_legacy_mutation_helper_guard_allows_wrapped_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    run_controller_compatibility_call(
        self,
        lambda: self._run_legacy_label_import(),
    )

def _run_legacy_label_import(self):
    self.controller.apply_labels_sequence([], [], None, None)
""",
    )

    assert check_ui_legacy_mutation_helper_calls(tmp_path) == []


def test_legacy_fallback_scope_guard_flags_product_method_gate(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    return run_controller_compatibility_call(
        self,
        lambda: self.controller.get_loaded_data_list(),
    )
""",
    )

    violations = check_ui_legacy_fallback_helper_scope(tmp_path)

    assert len(violations) == 1
    assert "run_controller_compatibility_call" in violations[0]
    assert "explicit private helper" in violations[0]


def test_legacy_fallback_scope_guard_allows_named_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    return self._legacy_loaded_rows()

def _legacy_loaded_rows(self):
    return run_controller_compatibility_call(
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


def test_ui_architecture_guards_fail_closed_on_product_syntax_error(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def broken(:
    pass
""",
    )

    guard_results = (
        check_ui_direct_controller_mutations(tmp_path),
        check_ui_direct_backend_service_execute(tmp_path),
        check_ui_direct_loader_apply(tmp_path),
    )

    for violations in guard_results:
        assert len(violations) == 1
        assert "invalid Python syntax" in violations[0]

    assert architecture_compliance.check_architecture(str(tmp_path)) == 1


def test_product_syntax_guard_fails_closed_outside_ui(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def valid_panel():
    return None
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/broken.py",
        """
def broken(:
    pass
""",
    )

    violations = architecture_compliance.check_product_python_syntax(tmp_path)

    assert len(violations) == 1
    assert "XBrainLab/backend/broken.py" in violations[0]
    assert "invalid Python syntax" in violations[0]
    assert architecture_compliance.check_architecture(str(tmp_path)) == 1


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


def test_direct_study_state_guard_rejects_named_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_montage_channels(self):
    epoch_data = self.study.epoch_data
    return epoch_data.get_mne().ch_names
""",
    )

    violations = check_ui_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "study.epoch_data" in violations[0]


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


def test_llm_direct_study_state_guard_rejects_named_legacy_stage_helper(tmp_path):
    _write_llm_file(
        tmp_path,
        """
def _legacy_study_pipeline_stage(study):
    if study.loaded_data_list:
        return "data_loaded"
    return "empty"
""",
    )

    violations = check_llm_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "study.loaded_data_list" in violations[0]


def test_mcp_direct_study_state_guard_flags_service_study_progress_read(tmp_path):
    _write_mcp_file(
        tmp_path,
        """
def _training_progress_message(service):
    trainer = service.study.trainer
    if trainer is not None:
        return trainer.get_progress_text()
    return "Training is not running."
""",
    )

    violations = check_mcp_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "service.study.trainer" in violations[0]
    assert "ApplicationService state snapshot" in violations[0]


def test_mcp_direct_study_state_guard_rejects_named_legacy_helper(tmp_path):
    _write_mcp_file(
        tmp_path,
        """
def _legacy_training_progress_message(service):
    trainer = service.study.trainer
    if trainer is not None:
        return trainer.get_progress_text()
    return "Training is not running."
""",
    )

    violations = check_mcp_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "service.study.trainer" in violations[0]


def test_mcp_direct_study_state_guard_flags_service_study_controller_lookup(
    tmp_path,
):
    _write_mcp_file(
        tmp_path,
        """
def _training_progress_message(service):
    controller = service.study.get_controller("training")
    return controller.get_progress_text()
""",
    )

    violations = check_mcp_direct_study_state_reads(tmp_path)

    assert len(violations) == 1
    assert "service.study.get_controller" in violations[0]
    assert "ApplicationService" in violations[0]


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
    assert "must be injected or command/query-backed" in violations[0]


def test_controller_study_get_controller_guard_flags_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_training_controller_for_bridges(self):
    return run_controller_compatibility_call(
        self,
        lambda: self.controller.study.get_controller("training"),
    )
""",
    )

    violations = check_ui_controller_study_get_controller_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "controller.study.get_controller" in violations[0]
    assert "must be injected or command/query-backed" in violations[0]


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
    assert "central bootstrap quarantine" in violations[0]


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


def test_direct_study_get_controller_guard_rejects_named_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _legacy_controller_from_parent(self, parent):
    return parent.study.get_controller("dataset")
""",
    )

    violations = check_ui_direct_study_get_controller_lookups(tmp_path)

    assert len(violations) == 1
    assert "study.get_controller" in violations[0]


def test_mutable_object_boundary_guard_reports_exact_new_product_violations(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/new_boundary.py",
        """from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.ui.application_capabilities import local_result_payload

class NewBoundaryPanel:
    def load(self, result, record):
        QueryStateCommand(query="data_lists", include_objects=True)
        local_result_payload(result)
        result.local_payload
        result.runtime
        getattr(result, "runtime", {})
        self.current_record = record
""",
    )

    violations = architecture_compliance.check_mutable_object_boundaries(tmp_path)

    assert violations == [
        "XBrainLab/ui/panels/new_boundary.py:2 [<module>] "
        "local_result_payload use is not allowlisted: imported local_result_payload",
        "XBrainLab/ui/panels/new_boundary.py:6 [NewBoundaryPanel.load] "
        "include_objects use is not allowlisted: "
        "QueryStateCommand(query='data_lists', include_objects=True)",
        "XBrainLab/ui/panels/new_boundary.py:7 [NewBoundaryPanel.load] "
        "local_result_payload use is not allowlisted: local_result_payload(result)",
        "XBrainLab/ui/panels/new_boundary.py:8 [NewBoundaryPanel.load] "
        "local_payload use is not allowlisted: result.local_payload",
        "XBrainLab/ui/panels/new_boundary.py:9 [NewBoundaryPanel.load] "
        "CommandResult.runtime access is not allowlisted: result.runtime",
        "XBrainLab/ui/panels/new_boundary.py:10 [NewBoundaryPanel.load] "
        "CommandResult.runtime access is not allowlisted: "
        "getattr(result, 'runtime', {})",
        "XBrainLab/ui/panels/new_boundary.py:11 [NewBoundaryPanel.load] "
        "backend domain object storage is not allowlisted: "
        "self.current_record = record",
    ]


def test_mutable_object_boundary_guard_allows_exact_existing_debt_symbol(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/dataset/panel.py",
        """class DatasetPanel:
    def _query_loaded_data_list_for_render(self):
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
        )
        return local_result_payload(result)
""",
    )

    assert architecture_compliance.check_mutable_object_boundaries(tmp_path) == []


def test_mutable_object_boundary_guard_rejects_growth_inside_allowlisted_symbol(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/dataset/panel.py",
        """class DatasetPanel:
    def _query_loaded_data_list_for_render(self):
        first = QueryStateCommand(query="data_lists", include_objects=True)
        second = QueryStateCommand(query="training_history", include_objects=True)
        return first, second
""",
    )

    violations = architecture_compliance.check_mutable_object_boundaries(tmp_path)

    assert violations == [
        "XBrainLab/ui/panels/dataset/panel.py:4 "
        "[DatasetPanel._query_loaded_data_list_for_render] "
        "include_objects use is not allowlisted: "
        "QueryStateCommand(query='training_history', include_objects=True)",
    ]


def test_repository_mutable_object_boundary_debt_is_fully_enumerated() -> None:
    root_dir = Path(__file__).resolve().parents[2]

    assert (
        architecture_compliance.check_mutable_object_boundaries(
            root_dir,
            validate_allowlist=True,
        )
        == []
    )


def test_visualization_saliency_publication_guard_flags_exact_lifecycle_drift(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/panel.py",
        """class VisualizationPanel:
    def on_update(self):
        self._start_saliency_compute()

    def _poll_saliency_status(self, result):
        self.last_application_query = result
        return VisualizeCommand(include_objects=True)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py",
        """from XBrainLab.backend.application.state_service import saliency_method_coverage

def coverage(record):
    return saliency_method_coverage(record, "Gradient")
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py",
        """from XBrainLab.backend.application.state_service import saliency_label_items_from_epoch
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 7
    assert any("on_update" in item and "explicit button" in item for item in violations)
    assert any(
        "_poll_saliency_status" in item and "QueryStateCommand" in item
        for item in violations
    )
    assert any(
        "_poll_saliency_status" in item and "include_objects" in item
        for item in violations
    )
    assert any(
        "_poll_saliency_status" in item and "CommandResult" in item
        for item in violations
    )
    assert sum("state_service" in item for item in violations) == 2
    assert sum("calls coverage projector" in item for item in violations) == 1


def test_visualization_saliency_publication_guard_allows_snapshot_injection(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/panel.py",
        """class VisualizationPanel:
    def _compute_saliency_from_action_bar(self):
        return self._start_saliency_compute()

    def _poll_saliency_status(self):
        return execute_application_command_async(self, QueryStateCommand())

    def _accept_application_publication(self, result):
        self._application_publication_state = result.state
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py",
        """class BaseSaliencyView:
    def set_saliency_coverage(self, coverage):
        self._saliency_coverage = coverage
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py",
        """class Saliency3DPlotWidget:
    def set_saliency_coverage(self, coverage):
        self._saliency_coverage = coverage
""",
    )

    assert check_visualization_saliency_publication_boundary(tmp_path) == []


def test_visualization_saliency_guard_rejects_deferred_layout_timer(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py",
        """from PyQt6.QtCore import QTimer

class BaseSaliencyView:
    def resizeEvent(self, event):
        QTimer.singleShot(0, self._fit_current_figure)
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 1
    assert "QTimer.singleShot" in violations[0]
    assert "deterministic Qt layout" in violations[0]


def test_visualization_saliency_guard_covers_every_saliency_view(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py",
        """from PyQt6.QtCore import QTimer

def render_later(render):
    QTimer.singleShot(100, render)
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/saliency_views/map_view.py",
        """def render_now(app):
    app.processEvents()
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 2
    assert any("QTimer.singleShot" in item for item in violations)
    assert any("nested Qt events" in item for item in violations)


def test_visualization_saliency_publication_guard_rejects_mutable_query_payloads(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/panel.py",
        """class VisualizationPanel:
    def refresh(self, result):
        command = VisualizeCommand(
            include_objects=True,
            include_averaged_records=True,
        )
        return local_result_payload(result).get("trainer_objects"), command
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 4
    assert any("include_objects=True" in item for item in violations)
    assert any("include_averaged_records=True" in item for item in violations)
    assert any("local_result_payload" in item for item in violations)
    assert any("trainer_objects" in item for item in violations)


def test_visualization_saliency_publication_guard_rejects_settings_mutation(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/control_sidebar.py",
        """class ControlSidebar:
    def set_saliency(self, params):
        return execute_application_command_async(
            self,
            SaliencyCommand(params=params),
        )
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 1
    assert "set_saliency" in violations[0]
    assert "Compute/Recompute" in violations[0]


def test_visualization_publication_guard_rejects_live_training_objects(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/control_sidebar.py",
        """class ControlSidebar:
    def export(self):
        return self.controller.get_trainers()
""",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/model_summary.py",
        """class ModelSummary:
    def __init__(self, trainers):
        self.trainers = trainers

    def summarize(self, trainer, plan):
        plans = trainer.get_plans()
        record = plan.get_eval_record()
        dataset = record.get_dataset()
        return plans, record, dataset
""",
    )

    violations = check_visualization_saliency_publication_boundary(tmp_path)

    assert len(violations) == 5
    assert any("get_trainers" in item for item in violations)
    assert any("get_plans" in item for item in violations)
    assert any("get_eval_record" in item for item in violations)
    assert any("get_dataset" in item for item in violations)
    assert any("self.trainers" in item for item in violations)


def test_visualization_publication_guard_allows_typed_identity_storage(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/panel.py",
        """class VisualizationPanel:
    def accept_publication(self, publication):
        self._plan_items = publication.plan_items
        self._run_items = publication.run_items
        self._selected_plan_id = publication.selected_plan_id
        self._selected_run_id = publication.selected_run_id
""",
    )

    assert check_visualization_saliency_publication_boundary(tmp_path) == []
