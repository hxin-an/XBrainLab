"""Verification layer for validating proposed tool calls.

Provides safety checks between the LLM output parser and the tool
execution engine, including structure validation, confidence gating,
and parameter-level semantic validation via pluggable strategies.
"""

from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, NamedTuple

from XBrainLab.llm.tools.application_surface import (
    AuthoritativeConfirmationParameter,
    UserProvidedTrainingOutputDir,
    start_training_confirmation_truth,
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


DIRECT_PARAMETER_TOOLS = frozenset(
    {
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
    }
)
_DECIMAL_NUMBER_PATTERN = r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\w.])"


def collect_direct_parameter_reply_evidence(
    tool_name: str,
    verified_parameters: tuple[tuple[str, Any], ...],
    unassigned_bandpass_cutoff: float | int | None,
    latest_user_text: str,
) -> tuple[tuple[tuple[str, Any], ...], float | int | None] | None:
    """Collect bounded user evidence for one already-admitted direct action.

    The receipt supplies the action identity.  This function never chooses an
    action, trusts model values, or changes capability/execution policy.
    ``None`` is a fail-closed clear-and-restart result.
    """
    if tool_name not in DIRECT_PARAMETER_TOOLS:
        return None
    text = unicodedata.normalize("NFKC", latest_user_text).strip()
    if (
        not text
        or len(text) > 256
        or not _is_direct_parameter_value_reply(tool_name, text)
    ):
        return None
    verified = dict(verified_parameters)
    values = [
        _positive_arabic_decimal(match.group(0))
        for match in re.finditer(_DECIMAL_NUMBER_PATTERN, text)
    ]
    if tool_name == "apply_bandpass_filter":
        if not values or any(value is None for value in values):
            return None
        if verified:
            if (
                len(verified) != 1
                or unassigned_bandpass_cutoff is not None
                or len(values) != 1
            ):
                return None
            remaining = next(
                field for field in ("low_freq", "high_freq") if field not in verified
            )
            verified[remaining] = values[0]
            return (
                tuple((field, verified[field]) for field in ("low_freq", "high_freq")),
                None,
            )
        if len(values) == 1:
            value = values[0]
            if value is None:
                return None
            if unassigned_bandpass_cutoff is None:
                return (), value
            values = [unassigned_bandpass_cutoff, value]
        if len(values) != 2:
            return None
        numeric_values = [value for value in values if value is not None]
        if len(numeric_values) != len(values):
            return None
        low, high = sorted(numeric_values)
        return (
            (
                (("low_freq", low), ("high_freq", high)),
                None,
            )
            if low < high
            else None
        )
    if verified or unassigned_bandpass_cutoff is not None:
        return None
    if tool_name in {"apply_notch_filter", "resample_data"}:
        field = "freq" if tool_name == "apply_notch_filter" else "rate"
        value = values[0] if len(values) == 1 else None
        if value is None or not _clarification_reply_contains_number(value, text):
            return None
        return ((field, value),), None
    if tool_name == "normalize_data":
        methods = [
            method
            for method, pattern in {
                "z-score": r"\bz[\s-]*score\b",
                "min-max": r"\bmin[\s-]*max\b",
            }.items()
            if re.search(pattern, text, re.IGNORECASE)
        ]
        return ((("method", methods[0]),), None) if len(methods) == 1 else None
    method = text.rstrip(".。!").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", method):
        return None
    return (("method", method),), None


def is_explicit_tool_input_cancel(text: str) -> bool:
    """Recognize only a standalone receipt cancellation token."""
    return bool(
        re.fullmatch(
            r"\s*(?:cancel|never\s+mind|取消|算了)\s*[.!。\uff01]?\s*",
            unicodedata.normalize("NFKC", text),
            re.IGNORECASE,
        )
    )


def _is_direct_parameter_value_reply(tool_name: str, text: str) -> bool:
    """Accept only a bounded value shape, never an action or intent sentence."""
    stripped = text.strip().rstrip(".。!\uff01")
    if tool_name in {"apply_notch_filter", "resample_data"}:
        return bool(
            re.fullmatch(
                rf"{_DECIMAL_NUMBER_PATTERN}(?:\s*(?:hz|赫茲))?",
                stripped,
                re.IGNORECASE,
            )
        )
    if tool_name == "apply_bandpass_filter":
        return bool(
            re.fullmatch(
                rf"{_DECIMAL_NUMBER_PATTERN}(?:\s*(?:hz|赫茲))?"
                rf"(?:\s+{_DECIMAL_NUMBER_PATTERN}(?:\s*(?:hz|赫茲))?"
                rf"|\s*(?:,|;|/|:|=|~|-|\u2013|\u2014|and|to)\s*"
                rf"{_DECIMAL_NUMBER_PATTERN}(?:\s*(?:hz|赫茲))?)?",
                stripped,
                re.IGNORECASE,
            )
        )
    if tool_name == "normalize_data":
        return bool(
            re.fullmatch(r"(?:z[\s-]*score|min[\s-]*max)", stripped, re.IGNORECASE)
        )
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", stripped))


def _positive_arabic_decimal(value: str) -> float | int | None:
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        return None
    if not decimal.is_finite() or decimal <= 0:
        return None
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return float(decimal)


def verify_direct_parameter_origins(
    tool_name: str,
    params: dict[str, Any],
    latest_user_text: str,
) -> VerificationResult:
    """Verify direct preprocessing values against the latest user request.

    The model may select one published preprocessing action, but it may not
    supply that action's required values from defaults, examples, or earlier
    context.  This check deliberately verifies value provenance only; it does
    not infer intent or select a different action.
    """
    if tool_name not in DIRECT_PARAMETER_TOOLS:
        return VerificationResult(True)

    text = unicodedata.normalize("NFKC", latest_user_text).strip()
    if tool_name == "apply_bandpass_filter":
        return _verify_bandpass_origins(params, text)
    if tool_name == "apply_notch_filter":
        return _verify_single_numeric_origin(
            params.get("freq"), text, "What notch frequency should I use?"
        )
    if tool_name == "resample_data":
        return _verify_single_numeric_origin(
            params.get("rate"), text, "What resampling rate should I use?"
        )
    if tool_name == "normalize_data":
        return _verify_method_origin(
            params.get("method"),
            text,
            aliases={
                "zscore": r"z[\s-]*score",
                "minmax": r"min[\s-]*max",
            },
            question="Which normalization method should I use: z-score or min-max?",
        )
    return _verify_reference_origin(params.get("method"), text)


def verified_direct_parameter_origin_values(
    tool_name: str,
    params: dict[str, Any],
    latest_user_text: str,
) -> tuple[tuple[str, Any], ...]:
    """Return only direct parameter values proven by the current user text."""
    if tool_name != "apply_bandpass_filter":
        return ()
    text = unicodedata.normalize("NFKC", latest_user_text).strip()
    low_verified, high_verified = _bandpass_origin_matches(params, text)
    verified: list[tuple[str, Any]] = []
    if low_verified:
        verified.append(("low_freq", params.get("low_freq")))
    if high_verified:
        verified.append(("high_freq", params.get("high_freq")))
    return tuple(verified)


def _clarification_reply_contains_number(value: Any, text: str) -> bool:
    numeric_matches = tuple(re.finditer(_DECIMAL_NUMBER_PATTERN, text))
    for match in numeric_matches:
        if not _numbers_equal(value, match.group(0)):
            continue
        suffix = text[match.end() : match.end() + 8]
        if re.match(r"\s*(?:hz|赫茲)\b", suffix, re.IGNORECASE):
            return True
    stripped = text.strip().rstrip(".。!\uff01")
    return bool(
        re.fullmatch(_DECIMAL_NUMBER_PATTERN, stripped)
        and _numbers_equal(value, stripped)
    )


def _verify_bandpass_origins(
    params: dict[str, Any],
    text: str,
) -> VerificationResult:
    low_verified, high_verified = _bandpass_origin_matches(params, text)
    if low_verified and high_verified:
        return VerificationResult(True)
    if high_verified and not low_verified:
        return VerificationResult(
            False,
            "What low cutoff frequency should I use for the bandpass filter?",
        )
    if low_verified and not high_verified:
        return VerificationResult(
            False,
            "What high cutoff frequency should I use for the bandpass filter?",
        )
    return VerificationResult(
        False,
        "What low and high cutoff frequencies should I use for the bandpass filter?",
    )


def _bandpass_origin_matches(params: dict[str, Any], text: str) -> tuple[bool, bool]:
    """Return cutoffs proven only by Arabic-decimal membership."""
    low = params.get("low_freq")
    high = params.get("high_freq")
    values = tuple(re.finditer(_DECIMAL_NUMBER_PATTERN, text))
    return (
        any(_numbers_equal(low, value.group(0)) for value in values),
        any(_numbers_equal(high, value.group(0)) for value in values),
    )


def _verify_single_numeric_origin(
    value: Any,
    text: str,
    question: str,
) -> VerificationResult:
    if any(
        _numbers_equal(value, match.group(0))
        for match in re.finditer(_DECIMAL_NUMBER_PATTERN, text)
    ):
        return VerificationResult(True)
    return VerificationResult(False, question)


def _verify_method_origin(
    value: Any,
    text: str,
    *,
    aliases: dict[str, str],
    question: str,
) -> VerificationResult:
    normalized_value = _normalized_method(value)
    alias_pattern = aliases.get(normalized_value)
    if alias_pattern is None:
        return VerificationResult(False, question)
    alias = re.compile(alias_pattern, re.IGNORECASE)
    if alias.search(text):
        return VerificationResult(True)
    return VerificationResult(False, question)


def _verify_reference_origin(
    value: Any,
    text: str,
) -> VerificationResult:
    question = "What EEG reference method should I use?"
    if not isinstance(value, str) or not value.strip():
        return VerificationResult(False, question)
    escaped_words = [re.escape(part) for part in re.findall(r"\w+", value)]
    if not escaped_words:
        return VerificationResult(False, question)
    method = r"[\s_-]*".join(escaped_words)
    if re.search(rf"\b{method}\b", text, re.IGNORECASE):
        return VerificationResult(True)
    return VerificationResult(False, question)


def _numbers_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _normalized_method(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


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


def _is_absolute_user_path(value: str) -> bool:
    text = value.strip().strip("\"'")
    return os.path.isabs(text) or bool(re.match(r"^[A-Za-z]:[\\/]", text))


class PathProvenanceVerifier:
    """Preserve training host parameters without authorizing model file access."""

    def validate(
        self,
        name: str,
        params: dict[str, Any],
        *,
        latest_user_text: str,
        state: dict[str, Any] | None,
    ) -> VerificationResult:
        if name == "configure_training":
            output_dir = params.get("output_dir")
            if (
                isinstance(output_dir, str)
                and output_dir.strip()
                and not self._user_text_contains_path(
                    output_dir.strip(), latest_user_text
                )
            ):
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
        path = params.get("output_dir") if name == "configure_training" else None
        if not isinstance(path, str):
            return VerificationResult(is_valid=True)
        if self._looks_like_placeholder_path(path):
            return VerificationResult(
                is_valid=False,
                error_message=(
                    "Required training output directory must be an actual path "
                    f"provided by the user, got placeholder {path!r}."
                ),
            )
        text = path.strip().strip("\"'")
        if text and not _is_absolute_user_path(text):
            return VerificationResult(
                is_valid=False,
                error_message=(
                    "Required training output directory must be an actual "
                    "absolute path "
                    f"provided by the user, got relative path {text!r}."
                ),
            )
        return VerificationResult(is_valid=True)

    @classmethod
    def _looks_like_placeholder_path(cls, value: str) -> bool:
        text = value.strip().strip("\"'").lower()
        if text in cls.PLACEHOLDER_EXACT:
            return True
        return any(marker in text for marker in cls.PLACEHOLDER_MARKERS)


# Default validators applied to every tool call
DEFAULT_VALIDATORS: list[ValidatorStrategy] = [
    FrequencyRangeValidator(),
    PlaceholderArgumentValidator(),
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
