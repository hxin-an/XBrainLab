"""Verification layer for validating proposed tool calls.

Provides safety checks between the LLM output parser and the tool
execution engine, including structure validation, confidence gating,
and parameter-level semantic validation via pluggable strategies.
"""

from __future__ import annotations

import logging
import math
import ntpath
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, NamedTuple

from XBrainLab.backend.training.input_contract import (
    TrainingInputContractError,
    normalize_non_negative_integer,
    normalize_positive_integer,
    normalize_training_input,
)
from XBrainLab.llm.tools.application_surface import (
    AuthoritativeConfirmationParameter,
    UserProvidedTrainingOutputDir,
    start_training_confirmation_truth,
)
from XBrainLab.llm.tools.authorized_paths import (
    AuthorizedPathError,
    authorize_existing_path,
)
from XBrainLab.llm.tools.result_contract import redact_public_text

logger = logging.getLogger(__name__)


class VerificationResult(NamedTuple):
    """Result of a tool-call verification check.

    Attributes:
        is_valid: Whether the tool call passed all verification checks.
        error_message: Human-readable reason for rejection, or ``None``
            if the call is valid.

    """

    is_valid: bool
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Validator Strategy interface + built-in strategies
# ---------------------------------------------------------------------------


class ValidatorStrategy(ABC):
    """Abstract base for parameter-level validation strategies."""

    @abstractmethod
    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        """Validate parameters for a tool call.

        Args:
            name: Tool name.
            params: Tool parameters dict.

        Returns:
            ``VerificationResult`` with ``is_valid=True`` if OK.

        """


class FrequencyRangeValidator(ValidatorStrategy):
    """Reject bandpass where low_freq >= high_freq or non-positive."""

    TOOLS: ClassVar[set[str]] = {
        "apply_bandpass_filter",
        "apply_standard_preprocess",
    }

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        if name not in self.TOOLS:
            return VerificationResult(is_valid=True)

        # Determine parameter names (standard_preprocess uses l_freq/h_freq)
        if name == "apply_standard_preprocess":
            lo, hi = params.get("l_freq"), params.get("h_freq")
        else:
            lo, hi = params.get("low_freq"), params.get("high_freq")

        if lo is not None and hi is not None:
            try:
                lo, hi = float(lo), float(hi)
            except (TypeError, ValueError):
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Frequency values must be numeric, got {lo!r} and {hi!r}"
                    ),
                )
            if lo <= 0 or hi <= 0:
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Frequencies must be positive, got low={lo}, high={hi}"
                    ),
                )
            if lo >= hi:
                return VerificationResult(
                    is_valid=False,
                    error_message=f"low_freq ({lo}) must be < high_freq ({hi})",
                )
        return VerificationResult(is_valid=True)


class TrainingParamValidator(ValidatorStrategy):
    """Enforce the assistant training-input contract before execution."""

    TOOLS: ClassVar[set[str]] = {"configure_training"}

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        if name not in self.TOOLS:
            return VerificationResult(is_valid=True)

        try:
            normalize_training_input(params)
            if "repeat" in params:
                normalize_positive_integer("repeat", params["repeat"])
            if "save_checkpoints_every" in params:
                normalize_non_negative_integer(
                    "save_checkpoints_every",
                    params["save_checkpoints_every"],
                )
        except TrainingInputContractError as exc:
            return VerificationResult(
                is_valid=False,
                error_message=redact_public_text(
                    object.__getattribute__(exc, "public_message")
                ),
            )
        return VerificationResult(is_valid=True)


class ToolSchemaValidator(ValidatorStrategy):
    """Validate tool parameters against the registered JSON-like schema."""

    def __init__(self, tool_schemas: dict[str, dict[str, Any]]):
        self.tool_schemas = tool_schemas

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        schema = self.tool_schemas.get(name)
        if schema is None:
            return VerificationResult(
                is_valid=False,
                error_message=f"Tool is not registered: {name}",
            )

        missing_result = self._validate_required(name, params, schema)
        if not missing_result.is_valid:
            return missing_result

        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return VerificationResult(is_valid=True)

        for param_name, value in params.items():
            property_schema = properties.get(param_name)
            if not isinstance(property_schema, dict):
                if self._host_authorized_parameter(name, param_name, value):
                    continue
                if not self._additional_properties_allowed(schema):
                    return VerificationResult(
                        is_valid=False,
                        error_message=(f"Unknown parameter for {name}: {param_name}"),
                    )
                continue

            result = self._validate_value(param_name, value, property_schema)
            if not result.is_valid:
                return result

        return VerificationResult(is_valid=True)

    @staticmethod
    def _host_authorized_parameter(
        tool_name: str,
        param_name: str,
        value: Any,
    ) -> bool:
        if (
            tool_name == "configure_training"
            and param_name == "output_dir"
            and isinstance(value, UserProvidedTrainingOutputDir)
        ):
            return True
        return bool(
            tool_name == "start_training"
            and param_name in {"output_directory", "checkpoint_policy"}
            and isinstance(value, AuthoritativeConfirmationParameter)
        )

    @staticmethod
    def _validate_required(
        name: str,
        params: dict[str, Any],
        schema: dict[str, Any],
    ) -> VerificationResult:
        required = schema.get("required", [])
        if not isinstance(required, list):
            return VerificationResult(is_valid=True)
        missing = [field for field in required if field not in params]
        if missing:
            return VerificationResult(
                is_valid=False,
                error_message=(
                    f"Missing required parameter(s) for {name}: "
                    f"{', '.join(str(field) for field in missing)}"
                ),
            )
        return VerificationResult(is_valid=True)

    @classmethod
    def _validate_value(
        cls,
        param_name: str,
        value: Any,
        property_schema: dict[str, Any],
    ) -> VerificationResult:
        enum_values = property_schema.get("enum")
        if isinstance(enum_values, list) and not _json_enum_matches(
            value,
            enum_values,
        ):
            return VerificationResult(
                is_valid=False,
                error_message=(
                    f"{param_name} must be one of {enum_values}, got {value!r}"
                ),
            )

        expected_type = property_schema.get("type")
        type_result = cls._validate_type(param_name, value, expected_type)
        if not type_result.is_valid:
            return type_result

        bounds_result = cls._validate_numeric_bounds(
            param_name,
            value,
            property_schema,
        )
        if not bounds_result.is_valid:
            return bounds_result

        if isinstance(value, dict):
            nested_result = cls._validate_object(param_name, value, property_schema)
            if not nested_result.is_valid:
                return nested_result

        if isinstance(value, list):
            item_schema = property_schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    item_result = cls._validate_value(
                        f"{param_name}[{index}]",
                        item,
                        item_schema,
                    )
                    if not item_result.is_valid:
                        return item_result

        return VerificationResult(is_valid=True)

    @classmethod
    def _validate_object(
        cls,
        param_name: str,
        value: dict[str, Any],
        property_schema: dict[str, Any],
    ) -> VerificationResult:
        required = property_schema.get("required", [])
        if isinstance(required, list):
            missing = [field for field in required if field not in value]
            if missing:
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Missing required parameter(s) for {param_name}: "
                        f"{', '.join(str(field) for field in missing)}"
                    ),
                )

        nested_properties = property_schema.get("properties", {})
        if not isinstance(nested_properties, dict):
            return VerificationResult(is_valid=True)

        for key, nested_value in value.items():
            nested_schema = nested_properties.get(key)
            if not isinstance(nested_schema, dict):
                additional = property_schema.get("additionalProperties")
                if isinstance(additional, dict):
                    extra_result = cls._validate_value(
                        f"{param_name}.{key}",
                        nested_value,
                        additional,
                    )
                    if not extra_result.is_valid:
                        return extra_result
                    continue
                if not cls._additional_properties_allowed(property_schema):
                    return VerificationResult(
                        is_valid=False,
                        error_message=(f"Unknown parameter for {param_name}: {key}"),
                    )
                continue
            result = cls._validate_value(
                f"{param_name}.{key}",
                nested_value,
                nested_schema,
            )
            if not result.is_valid:
                return result
        return VerificationResult(is_valid=True)

    @staticmethod
    def _additional_properties_allowed(schema: dict[str, Any]) -> bool:
        additional = schema.get("additionalProperties")
        if isinstance(additional, bool):
            return additional
        if isinstance(additional, dict):
            return True
        return not isinstance(schema.get("properties"), dict)

    @staticmethod
    def _validate_type(
        param_name: str,
        value: Any,
        expected_type: Any,
    ) -> VerificationResult:
        if expected_type is None:
            return VerificationResult(is_valid=True)

        expected = (
            [str(item) for item in expected_type]
            if isinstance(expected_type, list)
            else [str(expected_type)]
        )
        if any(_json_type_matches(value, item) for item in expected):
            return VerificationResult(is_valid=True)
        return VerificationResult(
            is_valid=False,
            error_message=(
                f"{param_name} must be {', '.join(expected)}, "
                f"got {type(value).__name__}"
            ),
        )

    @staticmethod
    def _validate_numeric_bounds(
        param_name: str,
        value: Any,
        property_schema: dict[str, Any],
    ) -> VerificationResult:
        comparisons = (
            ("minimum", lambda number, limit: number >= limit, ">="),
            ("exclusiveMinimum", lambda number, limit: number > limit, ">"),
            ("maximum", lambda number, limit: number <= limit, "<="),
            ("exclusiveMaximum", lambda number, limit: number < limit, "<"),
        )
        configured = [item for item in comparisons if item[0] in property_schema]
        if not configured:
            return VerificationResult(is_valid=True)
        if isinstance(value, bool):
            return VerificationResult(
                is_valid=False,
                error_message=f"{param_name} must be numeric, got bool",
            )
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return VerificationResult(
                is_valid=False,
                error_message=f"{param_name} must be numeric, got {value!r}",
            )
        if not math.isfinite(numeric):
            return VerificationResult(
                is_valid=False,
                error_message=f"{param_name} must be finite, got {value!r}",
            )
        for key, predicate, operator in configured:
            try:
                limit = float(property_schema[key])
            except (TypeError, ValueError, OverflowError):
                continue
            if not predicate(numeric, limit):
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"{param_name} must be {operator} {property_schema[key]}, "
                        f"got {value!r}"
                    ),
                )
        return VerificationResult(is_valid=True)


_PathValueKind = Literal["scalar", "sequence", "mapping_keys", "mapping_values"]
_PathCheck = Literal["existence", "provenance", "placeholder"]
_PlaceholderError = Literal["required_path", "remap_target", "label_mapping"]


@dataclass(frozen=True)
class _PathFieldPolicy:
    """Declarative verification policy for one path-bearing schema field."""

    location: tuple[str, ...]
    value_kind: _PathValueKind = "scalar"
    check_existence: bool = False
    check_provenance: bool = True
    check_placeholder: bool = True
    require_absolute: bool = False
    provenance_absolute_only: bool = False
    provenance_user_turn_only: bool = False
    label: str = "path"
    placeholder_error: _PlaceholderError = "required_path"


_PATH_FIELD_POLICY: dict[str, tuple[_PathFieldPolicy, ...]] = {
    "list_files": (
        _PathFieldPolicy(
            ("directory",),
            check_existence=True,
            label="directory",
        ),
    ),
    "scan_source": (
        _PathFieldPolicy(
            ("source_path",),
            check_existence=True,
            require_absolute=True,
            label="source path",
        ),
        _PathFieldPolicy(
            ("label_sources",),
            value_kind="sequence",
            label="label source path",
        ),
    ),
    "preview_interpretation": (
        _PathFieldPolicy(
            ("choices", "selected_eeg_files"),
            value_kind="sequence",
            provenance_absolute_only=True,
            label="file path",
        ),
        _PathFieldPolicy(
            ("choices", "label_sources"),
            value_kind="sequence",
            label="label source path",
        ),
        _PathFieldPolicy(
            ("choices", "required_label_carriers"),
            value_kind="sequence",
            provenance_absolute_only=True,
            label="label carrier path",
        ),
        _PathFieldPolicy(
            ("choices", "excluded_label_carriers"),
            value_kind="sequence",
            provenance_absolute_only=True,
            label="label carrier path",
        ),
        _PathFieldPolicy(
            ("choices", "eeg_file_remap"),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
        _PathFieldPolicy(
            ("choices", "eeg_file_remap"),
            value_kind="mapping_values",
            provenance_absolute_only=True,
            placeholder_error="remap_target",
        ),
        _PathFieldPolicy(
            ("choices", "label_carrier_remap"),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
        _PathFieldPolicy(
            ("choices", "label_carrier_remap"),
            value_kind="mapping_values",
            provenance_absolute_only=True,
            placeholder_error="remap_target",
        ),
        _PathFieldPolicy(
            ("choices", "label_carrier_choices"),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
        _PathFieldPolicy(
            ("choices", "label_carrier_choices", "*", "target_file"),
            provenance_absolute_only=True,
            label="target file",
        ),
        _PathFieldPolicy(
            ("choices", "run_event_mappings"),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
        _PathFieldPolicy(
            ("choices", "metadata_overrides"),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
    ),
    "save_interpretation_recipe": (
        _PathFieldPolicy(("recipe_path",), label="recipe path"),
    ),
    "reload_interpretation_recipe": (
        _PathFieldPolicy(
            ("recipe_path",),
            check_existence=True,
            require_absolute=True,
            label="recipe path",
        ),
    ),
    "load_data": (
        _PathFieldPolicy(
            ("paths",),
            value_kind="sequence",
            check_existence=True,
            label="file path",
        ),
    ),
    "attach_labels": (
        _PathFieldPolicy(
            ("mapping",),
            value_kind="mapping_keys",
            check_placeholder=False,
            provenance_absolute_only=True,
        ),
        _PathFieldPolicy(
            ("mapping",),
            value_kind="mapping_values",
            provenance_absolute_only=True,
            placeholder_error="label_mapping",
        ),
    ),
    "configure_training": (
        _PathFieldPolicy(
            ("output_dir",),
            require_absolute=True,
            provenance_user_turn_only=True,
            label="training output directory",
        ),
    ),
}


def _configured_path_values(
    name: str,
    params: dict[str, Any],
    *,
    check: _PathCheck,
) -> tuple[tuple[_PathFieldPolicy, str], ...]:
    configured: list[tuple[_PathFieldPolicy, str]] = []
    for policy in _PATH_FIELD_POLICY.get(name, ()):
        if not _path_check_enabled(policy, check):
            continue
        for value in _path_field_values(params, policy):
            if (
                check == "provenance"
                and policy.provenance_absolute_only
                and not _is_absolute_user_path(value)
            ):
                continue
            configured.append((policy, value))
    return tuple(configured)


def _path_check_enabled(policy: _PathFieldPolicy, check: _PathCheck) -> bool:
    if check == "existence":
        return policy.check_existence
    if check == "provenance":
        return policy.check_provenance
    return policy.check_placeholder


def _path_field_values(
    params: dict[str, Any],
    policy: _PathFieldPolicy,
) -> tuple[str, ...]:
    nodes: list[Any] = [params]
    for segment in policy.location:
        next_nodes: list[Any] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if segment == "*":
                next_nodes.extend(node.values())
            elif segment in node:
                next_nodes.append(node[segment])
        nodes = next_nodes

    values: list[str] = []
    for node in nodes:
        if policy.value_kind == "scalar" and isinstance(node, str):
            values.append(node)
        elif policy.value_kind == "sequence" and isinstance(node, list):
            values.extend(item for item in node if isinstance(item, str))
        elif policy.value_kind == "mapping_keys" and isinstance(node, dict):
            values.extend(str(key) for key in node)
        elif policy.value_kind == "mapping_values" and isinstance(node, dict):
            values.extend(item for item in node.values() if isinstance(item, str))
    return tuple(values)


def _is_absolute_user_path(value: str) -> bool:
    text = value.strip().strip("\"'")
    return os.path.isabs(text) or bool(re.match(r"^[A-Za-z]:[\\/]", text))


class PathExistsValidator(ValidatorStrategy):
    """Reject configured input paths that do not exist."""

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        for _policy, path in _configured_path_values(
            name,
            params,
            check="existence",
        ):
            if path and not os.path.exists(path):
                return VerificationResult(
                    is_valid=False,
                    error_message=f"Path does not exist: {path}",
                )
        return VerificationResult(is_valid=True)


class PathProvenanceVerifier:
    """Authorize file paths only from the user turn or selected backend roots."""

    def validate(
        self,
        name: str,
        params: dict[str, Any],
        *,
        latest_user_text: str,
        state: dict[str, Any] | None,
    ) -> VerificationResult:
        requested_paths = _configured_path_values(
            name,
            params,
            check="provenance",
        )
        if not requested_paths:
            self._apply_host_authorization(name, params, state=state)
            return VerificationResult(is_valid=True)

        exact_paths, root_paths = self._approved_paths(latest_user_text, state)
        for policy, requested_path in requested_paths:
            requested = requested_path.strip()
            if not requested:
                continue
            if self._user_text_contains_path(requested, latest_user_text):
                if name in {
                    "list_files",
                    "load_data",
                } and not self._authorize_input_path(
                    name,
                    params,
                    requested,
                    requested,
                ):
                    return self._rejection()
                continue
            if policy.provenance_user_turn_only:
                return self._rejection()
            canonical = self._canonical_path(requested)
            if canonical is None:
                return self._rejection()
            exact_root = exact_paths.get(canonical)
            if exact_root is not None:
                if name in {
                    "list_files",
                    "load_data",
                } and not self._authorize_input_path(
                    name,
                    params,
                    requested,
                    exact_root,
                ):
                    return self._rejection()
                continue
            authorized_root = next(
                (
                    raw_root
                    for root, raw_root in root_paths.items()
                    if self._is_lexically_within(canonical, root)
                ),
                None,
            )
            if authorized_root is not None:
                try:
                    authorized = authorize_existing_path(
                        requested,
                        authorized_root=authorized_root,
                        expected_kind="directory" if name == "list_files" else None,
                    )
                except AuthorizedPathError:
                    return self._rejection()
                self._store_authorized_input(name, params, requested, authorized)
                continue
            return self._rejection()
        self._apply_host_authorization(name, params, state=state)
        return VerificationResult(is_valid=True)

    @staticmethod
    def _apply_host_authorization(
        name: str,
        params: dict[str, Any],
        *,
        state: dict[str, Any] | None,
    ) -> None:
        if name == "configure_training":
            output_dir = params.get("output_dir")
            if isinstance(output_dir, str) and not isinstance(
                output_dir,
                UserProvidedTrainingOutputDir,
            ):
                params["output_dir"] = UserProvidedTrainingOutputDir(output_dir)
            return
        if name != "start_training":
            return

        truth = start_training_confirmation_truth(state)
        if truth is None:
            return
        params.pop("output_directory", None)
        params.pop("checkpoint_policy", None)
        params.update(truth.as_host_parameters())

    @classmethod
    def _user_text_contains_path(cls, path: str, text: str) -> bool:
        candidate = path.strip().strip("\"'")
        if not _is_absolute_user_path(candidate):
            return False
        if re.match(r"^[A-Za-z]:[\\/]", candidate):
            candidate = candidate.casefold()
            text = text.casefold()
        for match in re.finditer(re.escape(candidate), text):
            before = text[match.start() - 1] if match.start() else ""
            after = text[match.end()] if match.end() < len(text) else ""
            before_ok = not before or before.isspace() or before in "`'\"([{=:"
            after_ok = not after or after.isspace() or after in "`'\",;)]}.?!:"
            if before_ok and after_ok:
                return True
        return False

    @staticmethod
    def _rejection() -> VerificationResult:
        return VerificationResult(
            is_valid=False,
            error_message=(
                "The requested path was not provided in this turn or selected "
                "by the current data workflow. Choose a file or folder in the "
                "app, or paste the exact path."
            ),
        )

    @classmethod
    def _approved_paths(
        cls,
        latest_user_text: str,
        state: dict[str, Any] | None,
    ) -> tuple[
        dict[tuple[str, str], str],
        dict[tuple[str, str], str],
    ]:
        exact: dict[tuple[str, str], str] = {}
        roots: dict[tuple[str, str], str] = {}

        for user_path in cls._paths_from_user_text(latest_user_text):
            canonical = cls._canonical_path(user_path)
            if canonical is None:
                continue
            exact[canonical] = user_path
            if os.path.isdir(user_path):
                roots[canonical] = user_path

        if not isinstance(state, dict):
            return exact, roots
        interpretation = state.get("interpretation")
        if isinstance(interpretation, dict):
            source_path = interpretation.get("source_path")
            source_kind = str(interpretation.get("source_kind") or "").lower()
            cls._add_selected_path(
                source_path,
                exact,
                roots,
                root_hint=source_kind in {"bids", "folder"},
            )
            cls._add_selected_path(
                interpretation.get("recipe_path"),
                exact,
                roots,
            )
            for key in ("label_sources", "label_carriers"):
                values = interpretation.get(key)
                if isinstance(values, list):
                    for value in values:
                        cls._add_selected_path(value, exact, roots)

        for section_name in ("raw", "preprocessed"):
            section = state.get(section_name)
            if not isinstance(section, dict):
                continue
            files = section.get("files")
            if isinstance(files, list):
                for value in files:
                    cls._add_selected_path(value, exact, roots)
        return exact, roots

    @classmethod
    def _add_selected_path(
        cls,
        value: Any,
        exact: dict[tuple[str, str], str],
        roots: dict[tuple[str, str], str],
        *,
        root_hint: bool = False,
    ) -> None:
        if not isinstance(value, str):
            return
        canonical = cls._canonical_path(value)
        if canonical is None:
            return
        exact[canonical] = value
        if root_hint or os.path.isdir(value):
            roots[canonical] = value

    @classmethod
    def _paths_from_user_text(cls, text: str) -> tuple[str, ...]:
        paths: list[str] = []
        occupied: list[tuple[int, int]] = []
        quoted = re.compile(
            r"(?P<quote>[`\"'])(?P<path>(?:[A-Za-z]:[\\/]|/).*?)(?P=quote)"
        )
        for match in quoted.finditer(text):
            candidate = match.group("path").strip()
            if _is_absolute_user_path(candidate):
                paths.append(candidate)
                occupied.append(match.span())

        unquoted = re.compile(
            r"(?<![:\w])(?:[A-Za-z]:[\\/][^\s,;`\"']+|/(?!/)[^\s,;`\"']+)"
        )
        for match in unquoted.finditer(text):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            candidate = match.group(0).rstrip(".?!:;)]}")
            if _is_absolute_user_path(candidate):
                paths.append(candidate)
        return tuple(dict.fromkeys(paths))

    @classmethod
    def _canonical_path(cls, value: str) -> tuple[str, str] | None:
        text = value.strip().strip("\"'")
        if not _is_absolute_user_path(text):
            return None
        if re.match(r"^[A-Za-z]:[\\/]", text):
            return "windows", ntpath.normcase(ntpath.normpath(text))
        return "posix", os.path.normpath(os.path.abspath(text))

    @staticmethod
    def _authorize_input_path(
        name: str,
        params: dict[str, Any],
        requested: str,
        authorized_root: str,
    ) -> bool:
        try:
            authorized = authorize_existing_path(
                requested,
                authorized_root=authorized_root,
                expected_kind="directory" if name == "list_files" else None,
            )
        except AuthorizedPathError:
            return False
        return PathProvenanceVerifier._store_authorized_input(
            name,
            params,
            requested,
            authorized,
        )

    @staticmethod
    def _store_authorized_input(
        name: str,
        params: dict[str, Any],
        requested: str,
        authorized: str,
    ) -> bool:
        if name == "list_files":
            params["directory"] = authorized
            return True
        if name != "load_data":
            return True
        paths = params.get("paths")
        if not isinstance(paths, list):
            return False
        replaced = False
        for index, item in enumerate(paths):
            if isinstance(item, str) and item.strip() == requested:
                paths[index] = authorized
                replaced = True
        return replaced

    @staticmethod
    def _is_lexically_within(
        candidate: tuple[str, str],
        root: tuple[str, str],
    ) -> bool:
        """Prefilter roots before the final filesystem-identity check."""
        if candidate[0] != root[0]:
            return False
        path_module = ntpath if candidate[0] == "windows" else os.path
        try:
            return path_module.commonpath((candidate[1], root[1])) == root[1]
        except ValueError:
            return False


class PlaceholderArgumentValidator(ValidatorStrategy):
    """Reject tool calls where the model invented a placeholder path."""

    PLACEHOLDER_MARKERS: ClassVar[tuple[str, ...]] = (
        "/path/to/",
        "/path/with/",
        "path_to_",
        "<path",
        "{path",
        "your/eeg",
        "your_eeg",
        "please provide",
        "provide the absolute path",
        "path/to/your",
        "your/recipe",
        "placeholder",
        "replace_with",
        "replace/",
        "missing saved",
        "current replacement",
        "replacement eeg file path",
        "replacement label",
        "path/name",
    )
    PLACEHOLDER_EXACT: ClassVar[set[str]] = {
        "",
        "empty",
        "path",
        "path_to_dataset",
        "path_to_eeg_dataset",
        "path_to_recipe.json",
    }

    def validate(self, name: str, params: dict[str, Any]) -> VerificationResult:
        for policy, path in _configured_path_values(
            name,
            params,
            check="placeholder",
        ):
            if self._looks_like_placeholder_path(path):
                return self._placeholder_rejection(policy, path)
            text = path.strip().strip("\"'")
            if policy.require_absolute and text and not _is_absolute_user_path(text):
                return VerificationResult(
                    is_valid=False,
                    error_message=(
                        f"Required {policy.label} must be an actual absolute path "
                        f"provided by the user, got relative path {text!r}."
                    ),
                )

        return VerificationResult(is_valid=True)

    @staticmethod
    def _placeholder_rejection(
        policy: _PathFieldPolicy,
        placeholder: str,
    ) -> VerificationResult:
        if policy.placeholder_error == "remap_target":
            message = (
                "Required remap target is missing. Provide the saved recipe item "
                "and current replacement remap target, got placeholder "
                f"{placeholder!r}."
            )
        elif policy.placeholder_error == "label_mapping":
            message = (
                "Label mapping must use actual paths provided by the user, got "
                f"placeholder {placeholder!r}."
            )
        else:
            message = (
                f"Required {policy.label} must be an actual path provided by the "
                f"user, got placeholder {placeholder!r}."
            )
        return VerificationResult(is_valid=False, error_message=message)

    @classmethod
    def _looks_like_placeholder_path(cls, value: str) -> bool:
        text = value.strip().strip("\"'").lower()
        if text in cls.PLACEHOLDER_EXACT:
            return True
        return any(marker in text for marker in cls.PLACEHOLDER_MARKERS)


# Default validators applied to every tool call
DEFAULT_VALIDATORS: list[ValidatorStrategy] = [
    FrequencyRangeValidator(),
    TrainingParamValidator(),
    PlaceholderArgumentValidator(),
    PathExistsValidator(),
]


def _json_type_matches(value: Any, expected_type: str) -> bool:
    """Return whether a Python value matches a JSON-schema primitive type."""
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "null":
        return value is None
    return True


def _json_enum_matches(value: Any, enum_values: list[Any]) -> bool:
    """Return whether a value matches an enum, accepting case variants."""
    if value in enum_values:
        return True
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            isinstance(item, str) and item.lower() == lowered for item in enum_values
        )
    return False


class VerificationLayer:
    """Safety guard between LLM output and tool execution.

    Validates the structure of proposed tool calls, optionally gates
    execution based on a confidence threshold, and runs pluggable
    ``ValidatorStrategy`` checks against tool parameters.

    Attributes:
        confidence_threshold: Minimum confidence score (0.0-1.0) required
            for a tool call to pass verification.
        validators: List of ``ValidatorStrategy`` instances to run on
            each tool call after structure/confidence checks pass.

    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        validators: list[ValidatorStrategy] | None = None,
        tool_schemas: dict[str, dict[str, Any]] | None = None,
    ):
        """Initializes the VerificationLayer.

        Args:
            confidence_threshold: Minimum confidence score required for a
                tool call to be considered valid. Defaults to ``0.5``.
            validators: Optional list of ``ValidatorStrategy``
                instances.  Defaults to :data:`DEFAULT_VALIDATORS`.
            tool_schemas: Optional registered tool schemas used to validate
                required fields, JSON-like parameter types, enums, and
                unknown tool names before execution.

        """
        self.confidence_threshold = confidence_threshold
        self.validators: list[ValidatorStrategy] = []
        if tool_schemas is not None:
            self.validators.append(ToolSchemaValidator(tool_schemas))
        self.validators.extend(
            validators if validators is not None else list(DEFAULT_VALIDATORS)
        )

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict],
        confidence: float | None = None,
    ) -> VerificationResult:
        """Verifies a proposed tool call before execution.

        Checks structural validity (correct tuple format and types),
        optionally rejects calls whose confidence falls below the
        configured threshold, and then runs all registered
        ``ValidatorStrategy`` checks.

        Args:
            tool_call: A ``(tool_name, parameters)`` tuple representing
                the proposed tool invocation.
            confidence: Optional confidence score in the range 0.0-1.0.
                If provided and below ``confidence_threshold``, the call
                is rejected.

        Returns:
            A ``VerificationResult`` indicating whether the call is valid.

        """
        # 1. Structure Check
        if not isinstance(tool_call, tuple) or len(tool_call) != 2:
            return VerificationResult(
                is_valid=False,
                error_message="Tool call must be a tuple of (name, params)",
            )

        name, params = tool_call
        if not isinstance(name, str) or not isinstance(params, dict):
            return VerificationResult(
                is_valid=False,
                error_message="Tool call elements must be (str, dict)",
            )

        # 2. Confidence Gating
        if confidence is not None and confidence < self.confidence_threshold:
            return VerificationResult(
                is_valid=False,
                error_message=(
                    f"Confidence too low ({confidence:.2f} < "
                    f"{self.confidence_threshold})"
                ),
            )

        # 3. Parameter Validation Strategies
        for validator in self.validators:
            result = validator.validate(name, params)
            if not result.is_valid:
                safe_error = redact_public_text(
                    result.error_message or "Tool parameters did not pass validation."
                )
                logger.warning(
                    "Validator %s rejected %s: %s",
                    type(validator).__name__,
                    redact_public_text(name),
                    redact_public_text(safe_error),
                )
                return VerificationResult(False, safe_error)

        return VerificationResult(is_valid=True)
