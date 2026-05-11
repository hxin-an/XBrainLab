"""Headless automation adapter for the ApplicationService command API.

The adapter intentionally stays thin: it validates JSON-shaped payloads,
constructs typed command objects, and lets ApplicationService enforce
capability, confirmation, and runtime behavior.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from .capabilities import CommandCapability
from .commands import (
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    Command,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    MetadataUpdate,
    NewSessionCommand,
    PreprocessCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from .data_interpretation_choice_schema import data_interpretation_choices_schema
from .results import _serialize
from .service import ApplicationService


@dataclass(frozen=True)
class AutomationCommandSpec:
    """Serializable command schema suitable for CLI or MCP tool wrapping."""

    name: str
    taxonomy: str
    description: str
    input_schema: dict[str, Any]
    capability: dict[str, Any] | None = None
    legacy_compatibility: bool = False
    primary_workflow: bool = True
    preferred_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class AutomationExecution:
    """Result envelope for one automation payload."""

    accepted: bool
    command_name: str | None
    verification: dict[str, Any]
    autonomy: dict[str, Any]
    capability: dict[str, Any] | None
    result: dict[str, Any] | None
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


class AutomationPayloadError(ValueError):
    """Raised when an automation payload cannot form a typed command."""


COMMAND_TYPES: dict[CommandName, type[Any]] = {
    CommandName.SCAN_SOURCE: ScanSourceCommand,
    CommandName.PREVIEW_INTERPRETATION: PreviewInterpretationCommand,
    CommandName.VALIDATE_INTERPRETATION: ValidateInterpretationCommand,
    CommandName.APPLY_INTERPRETATION: ApplyInterpretationCommand,
    CommandName.SAVE_INTERPRETATION_RECIPE: SaveInterpretationRecipeCommand,
    CommandName.RELOAD_INTERPRETATION_RECIPE: ReloadInterpretationRecipeCommand,
    CommandName.LOAD_DATA: LoadDataCommand,
    CommandName.ATTACH_LABELS: AttachLabelsCommand,
    CommandName.IMPORT_LABELS: ImportLabelsCommand,
    CommandName.UPDATE_METADATA: UpdateMetadataCommand,
    CommandName.APPLY_SMART_PARSE: ApplySmartParseCommand,
    CommandName.REMOVE_FILES: RemoveFilesCommand,
    CommandName.PREPROCESS: PreprocessCommand,
    CommandName.CREATE_EPOCH: CreateEpochCommand,
    CommandName.GENERATE_DATASET: GenerateDatasetCommand,
    CommandName.CLEAR_DATASETS: ClearDatasetsCommand,
    CommandName.CONFIGURE_TRAINING: ConfigureTrainingCommand,
    CommandName.TRAIN: TrainCommand,
    CommandName.STOP_TRAINING: StopTrainingCommand,
    CommandName.CLEAR_TRAINING_HISTORY: ClearTrainingHistoryCommand,
    CommandName.EVALUATE: EvaluateCommand,
    CommandName.VISUALIZE: VisualizeCommand,
    CommandName.SALIENCY: SaliencyCommand,
    CommandName.APPLY_MONTAGE: ApplyMontageCommand,
    CommandName.QUERY_STATE: QueryStateCommand,
    CommandName.RESET_PREPROCESS: ResetPreprocessCommand,
    CommandName.RESET_SESSION: ResetSessionCommand,
    CommandName.NEW_SESSION: NewSessionCommand,
}

COMMAND_TAXONOMY: dict[CommandName, str] = {
    CommandName.SCAN_SOURCE: "data_interpretation",
    CommandName.PREVIEW_INTERPRETATION: "data_interpretation",
    CommandName.VALIDATE_INTERPRETATION: "data_interpretation",
    CommandName.APPLY_INTERPRETATION: "data_interpretation",
    CommandName.SAVE_INTERPRETATION_RECIPE: "data_interpretation",
    CommandName.RELOAD_INTERPRETATION_RECIPE: "data_interpretation",
    CommandName.LOAD_DATA: "legacy_data_compatibility",
    CommandName.ATTACH_LABELS: "legacy_data_compatibility",
    CommandName.IMPORT_LABELS: "legacy_data_compatibility",
    CommandName.UPDATE_METADATA: "metadata_resolution",
    CommandName.APPLY_SMART_PARSE: "metadata_resolution",
    CommandName.REMOVE_FILES: "metadata_resolution",
    CommandName.PREPROCESS: "data_transform",
    CommandName.CREATE_EPOCH: "data_transform",
    CommandName.GENERATE_DATASET: "experiment_setup",
    CommandName.CLEAR_DATASETS: "lifecycle_destructive",
    CommandName.CONFIGURE_TRAINING: "experiment_setup",
    CommandName.TRAIN: "execution",
    CommandName.STOP_TRAINING: "execution_control",
    CommandName.CLEAR_TRAINING_HISTORY: "lifecycle_destructive",
    CommandName.EVALUATE: "query",
    CommandName.VISUALIZE: "query",
    CommandName.SALIENCY: "query",
    CommandName.APPLY_MONTAGE: "data_transform",
    CommandName.QUERY_STATE: "query",
    CommandName.RESET_PREPROCESS: "lifecycle_destructive",
    CommandName.RESET_SESSION: "lifecycle_destructive",
    CommandName.NEW_SESSION: "lifecycle_destructive",
}

LEGACY_COMPATIBILITY_COMMANDS: frozenset[CommandName] = frozenset(
    {
        CommandName.LOAD_DATA,
        CommandName.ATTACH_LABELS,
        CommandName.IMPORT_LABELS,
    }
)

LEGACY_PREFERRED_COMMANDS: tuple[str, ...] = (
    CommandName.SCAN_SOURCE.value,
    CommandName.PREVIEW_INTERPRETATION.value,
    CommandName.VALIDATE_INTERPRETATION.value,
    CommandName.APPLY_INTERPRETATION.value,
    CommandName.SAVE_INTERPRETATION_RECIPE.value,
)

LEGACY_COMMAND_DESCRIPTIONS: dict[CommandName, str] = {
    CommandName.LOAD_DATA: (
        "Legacy compatibility: directly load raw EEG files. Prefer Data "
        "Interpretation scan_source -> preview_interpretation -> "
        "validate_interpretation -> apply_interpretation for new imports."
    ),
    CommandName.ATTACH_LABELS: (
        "Legacy compatibility: attach label files to already-loaded raw data. "
        "Prefer Data Interpretation label/event carrier preview, validation, "
        "apply, and recipe trace for new imports."
    ),
    CommandName.IMPORT_LABELS: (
        "Legacy compatibility: apply an explicit post-load label import plan. "
        "Prefer Data Interpretation label/event carrier review and recipe flow "
        "for new imports."
    ),
}


def command_specs(
    service: ApplicationService | None = None,
) -> list[AutomationCommandSpec]:
    """Return all command schemas with optional live capability policy."""
    capabilities = service.get_capabilities() if service is not None else None
    specs: list[AutomationCommandSpec] = []
    for command_name in CommandName:
        command_type = COMMAND_TYPES[command_name]
        capability = (
            capabilities.get(command_name).to_dict()
            if capabilities is not None
            else None
        )
        specs.append(
            AutomationCommandSpec(
                name=command_name.value,
                taxonomy=COMMAND_TAXONOMY[command_name],
                description=_command_description(command_name, command_type),
                input_schema=_command_input_schema(command_type),
                capability=capability,
                legacy_compatibility=_is_legacy_compatibility(command_name),
                primary_workflow=not _is_legacy_compatibility(command_name),
                preferred_commands=_preferred_commands(command_name),
            )
        )
    return specs


def mcp_tool_specs(
    service: ApplicationService | None = None,
) -> list[dict[str, Any]]:
    """Return MCP-shaped tool specs backed by the same command schemas."""
    return [
        {
            "name": spec.name,
            "title": _tool_title(spec.name),
            "description": spec.description,
            "inputSchema": spec.input_schema,
            "outputSchema": _automation_execution_output_schema(),
            "x_xbrainlab": {
                "taxonomy": spec.taxonomy,
                "capability": spec.capability,
                "execution": _execution_metadata(spec.capability),
                "legacy_compatibility": spec.legacy_compatibility,
                "primary_workflow": spec.primary_workflow,
                "preferred_commands": list(spec.preferred_commands),
            },
        }
        for spec in command_specs(service)
    ]


def build_command_from_payload(payload: dict[str, Any]) -> Command:
    """Build a typed command object from a JSON-shaped automation payload."""
    if not isinstance(payload, dict):
        raise AutomationPayloadError("Payload must be an object.")

    command_value = payload.get("command_name", payload.get("command"))
    if not isinstance(command_value, str) or not command_value:
        raise AutomationPayloadError("Payload must include command or command_name.")

    try:
        command_name = CommandName(command_value)
    except ValueError as exc:
        raise AutomationPayloadError(f"Unsupported command: {command_value}") from exc

    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise AutomationPayloadError("Payload arguments must be an object.")

    return _construct_command(command_name, arguments)


def execute_automation_payload(
    service: ApplicationService,
    payload: dict[str, Any],
) -> AutomationExecution:
    """Execute one automation payload through ApplicationService."""
    state_before = service.get_state()
    command_name = _payload_command_name(payload)
    capability = _capability_for_payload(service, command_name)
    verification: dict[str, Any] = {
        "schema_valid": False,
        "capability_enabled": capability.enabled if capability else False,
        "confirmation_required": _confirmation_required(capability),
        "reasons": capability.reasons if capability else [],
    }

    try:
        command = build_command_from_payload(payload)
    except AutomationPayloadError as exc:
        verification["error"] = str(exc)
        return AutomationExecution(
            accepted=False,
            command_name=command_name.value if command_name else None,
            verification=verification,
            autonomy=_autonomy_dict(capability),
            capability=capability.to_dict() if capability else None,
            result=None,
            state=state_before.to_dict(),
        )

    verification["schema_valid"] = True
    result = service.execute(command)
    return AutomationExecution(
        accepted=True,
        command_name=command_name.value if command_name else result.command_name,
        verification=verification,
        autonomy=_autonomy_dict(capability),
        capability=capability.to_dict() if capability else None,
        result=result.to_dict(),
        state=result.state.to_dict(),
    )


def _construct_command(command_name: CommandName, arguments: dict[str, Any]) -> Command:
    command_type = COMMAND_TYPES[command_name]
    ui_only = _ui_only_command_fields(command_name)
    requested_ui_only = sorted(set(arguments) & ui_only)
    if requested_ui_only:
        raise AutomationPayloadError(
            f"{command_name.value} received UI-only arguments: "
            f"{', '.join(requested_ui_only)}"
        )
    field_map = {field.name: field for field in fields(command_type)}
    unknown = sorted(set(arguments) - set(field_map))
    if unknown:
        raise AutomationPayloadError(
            f"{command_name.value} received unsupported arguments: {', '.join(unknown)}"
        )

    missing = [
        name
        for name, field_info in field_map.items()
        if field_info.default is MISSING
        and field_info.default_factory is MISSING
        and name not in arguments
    ]
    if missing:
        raise AutomationPayloadError(
            f"{command_name.value} missing required arguments: {', '.join(missing)}"
        )

    values: dict[str, Any] = {}
    for name, value in arguments.items():
        values[name] = _coerce_value(name, value)
    return command_type(**values)


def _coerce_value(name: str, value: Any) -> Any:
    if name == "plan" and isinstance(value, dict):
        return LabelImportPlan(**value)
    if name == "updates" and isinstance(value, list):
        return [
            MetadataUpdate(**item) if isinstance(item, dict) else item for item in value
        ]
    return value


def _command_input_schema(command_type: type[Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    type_hints = get_type_hints(command_type)
    for field_info in fields(command_type):
        if _field_hidden_from_automation(command_type, field_info.name):
            continue
        annotation = type_hints.get(field_info.name, field_info.type)
        properties[field_info.name] = _command_field_schema(
            command_type,
            field_info.name,
            annotation,
        )
        if field_info.default is MISSING and field_info.default_factory is MISSING:
            required.append(field_info.name)
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _ui_only_command_fields(command_name: CommandName) -> frozenset[str]:
    if command_name in {CommandName.EVALUATE, CommandName.VISUALIZE}:
        return frozenset({"include_objects"})
    return frozenset()


def _field_hidden_from_automation(command_type: type[Any], field_name: str) -> bool:
    return (
        command_type in {EvaluateCommand, VisualizeCommand}
        and field_name == "include_objects"
    )


def _command_field_schema(
    command_type: type[Any],
    field_name: str,
    annotation: Any,
) -> dict[str, Any]:
    if command_type is PreviewInterpretationCommand and field_name == "choices":
        return data_interpretation_choices_schema()
    return _json_schema_for_type(annotation)


def _json_schema_for_type(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {list, tuple, set}:
        item_type = args[0] if args else Any
        return {"type": "array", "items": _json_schema_for_type(item_type)}
    if origin is dict:
        return {"type": "object"}
    if origin in {UnionType, Union}:
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            schema = _json_schema_for_type(non_none[0])
            schema["nullable"] = True
            return schema
        return {"anyOf": [_json_schema_for_type(item) for item in non_none]}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {"type": "string", "enum": [item.value for item in annotation]}
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _command_input_schema(annotation)
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    return {"type": "object"}


def _command_description(command_name: CommandName, command_type: type[Any]) -> str:
    if command_name in LEGACY_COMMAND_DESCRIPTIONS:
        return LEGACY_COMMAND_DESCRIPTIONS[command_name]
    return (command_type.__doc__ or "").strip().splitlines()[0]


def _tool_title(name: str) -> str:
    return name.replace("_", " ").title()


def _is_legacy_compatibility(command_name: CommandName) -> bool:
    return command_name in LEGACY_COMPATIBILITY_COMMANDS


def _preferred_commands(command_name: CommandName) -> tuple[str, ...]:
    if _is_legacy_compatibility(command_name):
        return LEGACY_PREFERRED_COMMANDS
    return ()


def _execution_metadata(capability: dict[str, Any] | None) -> dict[str, Any]:
    if capability is None:
        return {
            "long_running": False,
            "destructive": False,
            "confirmation_required": False,
            "requires_confirmation": False,
            "decision_boundary": None,
            "requires_http_job": False,
            "supported_job_transports": [],
        }
    long_running = bool(capability.get("long_running", False))
    return {
        "long_running": long_running,
        "destructive": bool(capability.get("destructive", False)),
        "confirmation_required": bool(capability.get("confirmation_required", False)),
        "requires_confirmation": bool(capability.get("requires_confirmation", False))
        or bool(capability.get("confirmation_required", False)),
        "decision_boundary": capability.get("decision_boundary"),
        "requires_http_job": long_running,
        "supported_job_transports": ["http"] if long_running else [],
    }


def _automation_execution_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "accepted": {"type": "boolean"},
            "command_name": {"type": "string", "nullable": True},
            "verification": {"type": "object"},
            "autonomy": {"type": "object"},
            "capability": {"type": "object", "nullable": True},
            "result": {"type": "object", "nullable": True},
            "state": {"type": "object"},
            "adapter": {"type": "object"},
        },
        "required": [
            "accepted",
            "command_name",
            "verification",
            "autonomy",
            "capability",
            "result",
            "state",
        ],
    }


def _payload_command_name(payload: dict[str, Any]) -> CommandName | None:
    value = payload.get("command_name", payload.get("command"))
    if not isinstance(value, str) or not value:
        return None
    try:
        return CommandName(value)
    except ValueError:
        return None


def _capability_for_payload(
    service: ApplicationService,
    command_name: CommandName | None,
) -> CommandCapability | None:
    if command_name is None:
        return None
    return service.get_capabilities().get(command_name)


def _confirmation_required(capability: CommandCapability | None) -> bool:
    if capability is None:
        return False
    return capability.confirmation_required or capability.requires_confirmation


def _autonomy_dict(capability: CommandCapability | None) -> dict[str, Any]:
    if capability is None:
        return {}
    return {
        "can_auto_execute": capability.can_auto_execute,
        "requires_confirmation": capability.requires_confirmation,
        "confirmation_required": capability.confirmation_required,
        "decision_boundary": capability.decision_boundary,
        "continue_allowed_after_success": capability.continue_allowed_after_success,
        "retry_limit": capability.retry_limit,
        "stop_after_success": capability.stop_after_success,
        "blocks_downstream_until_confirmed": (
            capability.blocks_downstream_until_confirmed
        ),
    }
