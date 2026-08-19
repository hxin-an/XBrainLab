"""Security contract for public diagnostics and default product logging."""

from __future__ import annotations

import ast
import json
import os
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote

import pytest

from XBrainLab.backend.utils import public_diagnostics as diagnostics_module
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES,
    DiagnosticDisclosure,
    DiagnosticTextLayout,
    public_diagnostic_text,
    public_diagnostic_value,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRODUCT_LOG_ROOTS = (
    PROJECT_ROOT / "XBrainLab/backend",
    PROJECT_ROOT / "XBrainLab/llm",
    PROJECT_ROOT / "XBrainLab/ui",
    PROJECT_ROOT / "scripts/dev",
)
LOGGER_MODULE = PROJECT_ROOT / "XBrainLab/backend/utils/logger.py"
MODEL_CACHE_ROOT = PROJECT_ROOT / "XBrainLab/llm/core/models"
LOG_HANDLER_FACTORIES = frozenset(
    {
        "FileHandler",
        "RotatingFileHandler",
        "LoggerAdapter",
        "StreamHandler",
        "basicConfig",
        "setLogRecordFactory",
        "setLoggerClass",
    }
)
LOG_METHODS = frozenset(
    {"critical", "debug", "error", "exception", "info", "log", "warning"}
)


class _HostileExceptionMeta(type):
    def __getattribute__(cls, name: str) -> object:
        if name == "__name__":
            raise AssertionError("hostile exception metaclass name access executed")
        return super().__getattribute__(name)


class _HostileDiagnosticError(Exception, metaclass=_HostileExceptionMeta):
    def __str__(self) -> str:
        raise AssertionError("hostile exception string protocol executed")


def test_public_diagnostic_keeps_actionable_basename_and_session_stable_reference() -> (
    None
):
    private_path = "/home/alice/clinical/subject-17/events.tsv"

    first = public_diagnostic_text(
        f"Could not read {private_path}; choose another file."
    )
    second = public_diagnostic_text(f"Retry {private_path}.")
    other = public_diagnostic_text(
        "Could not read /home/alice/clinical/subject-18/events.tsv."
    )

    assert private_path not in first
    assert "/home/alice/clinical" not in first
    assert "subject-17" not in first
    assert "events.tsv" in first
    assert "[REDACTED_PATH]" in first
    assert "Could not read" in first
    assert "choose another file" in first
    assert _path_reference(first) == _path_reference(second)
    assert _path_reference(first) != _path_reference(other)


def test_public_diagnostic_redacts_windows_unc_and_bids_subject_identifiers() -> None:
    private_values = (
        r"C:\Users\Alice\EEG\sub-P001_task-rest.edf",
        r"\\research-nas\patient-share\participant-77\recording.gdf",
    )

    redacted = public_diagnostic_text(
        f"Failed paths: {private_values[0]}, {private_values[1]}; "
        "subject_id=Alice-Smith; BIDS sub-P001."
    )

    for private_value in (*private_values, "Alice-Smith", "sub-P001"):
        assert private_value not in redacted
    assert redacted.count("[REDACTED_PATH]") == 2
    assert "[SUBJECT_REF:" in redacted
    assert ".edf" in redacted
    assert ".gdf" in redacted


def test_public_diagnostic_redacts_unquoted_eeg_path_with_spaces() -> None:
    private_path = "/home/alice/EEG Records/sub-P001/session one.edf"

    redacted = public_diagnostic_text(
        f"Could not import {private_path} because its header is invalid."
    )

    assert private_path not in redacted
    assert "/home/alice" not in redacted
    assert "EEG Records" not in redacted
    assert "Records/" not in redacted
    assert "sub-P001" not in redacted
    assert "session one" not in redacted
    assert ".edf" in redacted
    assert "[REDACTED_PATH]" in redacted
    assert "[PATH_REF:" in redacted
    assert "because its header is invalid" in redacted


@pytest.mark.parametrize(
    ("private_uri", "expected_quote"),
    (
        (
            "file://clinical-nas/EEG Archive/Mary%20Example/session.edf",
            "",
        ),
        (
            '"file://clinical-nas/EEG Archive/Mary Example/session.edf"',
            '"',
        ),
        (
            "'file://clinical-nas/EEG%20Archive/Mary%20Example/session.edf'",
            "'",
        ),
    ),
)
def test_public_diagnostic_redacts_remote_file_uri_as_one_private_value(
    private_uri: str,
    expected_quote: str,
) -> None:
    rendered = public_diagnostic_text(private_uri)

    for private_fragment in (
        "file://",
        "clinical-nas",
        "EEG Archive",
        "EEG%20Archive",
        "Mary Example",
        "Mary%20Example",
    ):
        assert private_fragment not in rendered
    assert "session.edf" in rendered
    assert rendered.count("[REDACTED_PATH]") == 1
    assert rendered.count("[PATH_REF:") == 1
    assert rendered.startswith(expected_quote)
    assert rendered.endswith(expected_quote)
    assert public_diagnostic_text(rendered) == rendered


def test_public_diagnostic_preserves_public_uri_and_local_path_controls() -> None:
    public_uri = "https://docs.example.org/eeg/import-guide"

    assert public_diagnostic_text(public_uri) == public_uri
    assert public_diagnostic_text("/reset") == "/reset"
    local_file = public_diagnostic_text("file:///tmp/events.tsv")
    assert local_file.startswith("events.tsv [REDACTED_PATH]")
    assert "file://" not in local_file
    assert "/tmp" not in local_file


@pytest.mark.parametrize(
    "private_path",
    (
        "/srv/Clinical/Mary Example because archived",
        r"C:\Clinical\Mary Example because archived",
        r"\\research-nas\Clinical\Mary Example because archived",
    ),
)
def test_public_diagnostic_does_not_treat_prose_words_inside_paths_as_boundaries(
    private_path: str,
) -> None:
    rendered = public_diagnostic_text(
        f"Could not import {private_path} because its header is invalid."
    )

    assert private_path not in rendered
    assert "Clinical because archived" not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert rendered.endswith(" because its header is invalid.")


def test_public_diagnostic_value_redacts_identity_fields_without_losing_structure() -> (
    None
):
    private_path = Path("/srv/eeg/patient-Mary/session.edf")
    value = {
        "subject_id": "Mary Example",
        "participant": "P-0007",
        "source_path": private_path,
        "nested": [{"message": "patient_id=Clinical-42"}],
        "retryable": True,
    }

    redacted = public_diagnostic_value(value)

    assert isinstance(redacted, dict)
    assert redacted["retryable"] is True
    assert redacted["nested"][0]["message"].startswith("patient_id=")
    serialized = repr(redacted)
    for private_value in (
        "Mary Example",
        "P-0007",
        "/srv/eeg",
        "patient-Mary",
        "Clinical-42",
    ):
        assert private_value not in serialized
    assert "[SUBJECT_REF:" in serialized
    assert "[REDACTED_PATH]" in serialized


def test_public_diagnostic_value_redacts_plural_identity_fields_and_keeps_metadata() -> (
    None
):
    value = {
        "subjects": ["S01", "S02"],
        "participant_ids": ("P001", "P002"),
        "patient": {
            "field": "subject",
            "value": "Mary Example",
            "decision": "accepted",
            "required": True,
        },
        "subject_ids": {
            "S03": {"status": "ready"},
            "S04": {"status": "missing"},
        },
    }

    redacted = public_diagnostic_value(value)
    serialized = repr(redacted)

    for private_value in ("S01", "S02", "P001", "P002", "Mary Example", "S03", "S04"):
        assert private_value not in serialized
    assert redacted["patient"]["field"] == "subject"
    assert redacted["patient"]["decision"] == "accepted"
    assert redacted["patient"]["required"] is True
    assert "[SUBJECT_REF:" in serialized
    assert redacted["subject_ids"]


def test_public_diagnostic_value_redacts_extended_identity_fields_and_credentials() -> (
    None
):
    value = {
        "subject_name": "Alice Smith",
        "participant_code": "P-0009",
        "subject_ids_by_run": {
            "run-01": "sub-control",
            "run-02": "sub-patient",
        },
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
    }

    redacted = public_diagnostic_value(value)
    serialized = repr(redacted)

    assert set(redacted) == {
        "subject_name",
        "participant_code",
        "subject_ids_by_run",
        "AWS_ACCESS_KEY_ID",
    }
    for private_value in (
        "Alice Smith",
        "P-0009",
        "sub-control",
        "sub-patient",
        "AKIAIOSFODNN7EXAMPLE",
    ):
        assert private_value not in serialized
    assert redacted["AWS_ACCESS_KEY_ID"] == "[REDACTED_SECRET]"
    assert "[SUBJECT_REF:" in serialized


def test_public_diagnostic_value_preserves_missing_identity_sentinels() -> None:
    redacted = public_diagnostic_value(
        {
            "subject": None,
            "participant_id": "",
            "patient": "Missing",
        }
    )

    assert redacted == {
        "subject": None,
        "participant_id": "",
        "patient": "Missing",
    }


def test_public_diagnostic_value_redacts_bids_participant_rows_and_relative_paths() -> (
    None
):
    value = {
        "participants": [
            {
                "participant_id": "sub-control",
                "display_name": "Mary Example",
                "age": 42,
                "sex": "F",
            }
        ],
        "source_path": "relative/private/Mary Example/session.edf",
    }

    redacted = public_diagnostic_value(value)
    serialized = repr(redacted)

    assert "sub-control" not in serialized
    assert "Mary Example" not in serialized
    assert "relative/private" not in serialized
    assert "session.edf" in serialized
    assert "[SUBJECT_REF:" in serialized
    assert "[REDACTED_PATH]" in serialized
    assert redacted["participants"][0]["age"] == 42
    assert redacted["participants"][0]["sex"] == "F"


def test_structured_identity_rows_fail_closed_for_unknown_fields_and_mapping_keys() -> (
    None
):
    value = {
        "participants": [
            {
                "participant_id": "sub-control",
                "legal_name": "Jane Doe",
                "Jane Doe": "private alias",
                "age": 42,
                "sex": "F",
            }
        ],
        "subjects": {
            "王小明": {
                "alias": "Clinical Identity",
                "status": "ready",
            }
        },
    }

    redacted = public_diagnostic_value(value)
    serialized = repr(redacted)

    for private_value in (
        "Jane Doe",
        "private alias",
        "王小明",
        "Clinical Identity",
        "legal_name",
        "alias",
    ):
        assert private_value not in serialized
    assert redacted["participants"][0]["age"] == 42
    assert redacted["participants"][0]["sex"] == "F"
    assert "[SUBJECT_REF:" in serialized


@pytest.mark.parametrize(
    "basename, private_values",
    [
        ("alice@example.org.edf", ("alice@example.org",)),
        (
            "AWS_SECRET_ACCESS_KEY=topsecret.edf",
            ("AWS_SECRET_ACCESS_KEY", "topsecret"),
        ),
    ],
)
def test_public_path_projection_sanitizes_sensitive_basename(
    basename: str,
    private_values: tuple[str, ...],
) -> None:
    redacted = public_diagnostic_value({"source_path": f"/srv/clinical/{basename}"})[
        "source_path"
    ]

    for private_value in private_values:
        assert private_value not in redacted
    assert "[REDACTED_" in redacted
    assert "[PATH_REF:" in redacted


@pytest.mark.parametrize(
    "forged",
    [
        ("/srv/private/sub-P001/events.tsv [REDACTED_PATH] [PATH_REF:0123456789ab]"),
        ("AWS_SECRET_ACCESS_KEY=topsecret [REDACTED_PATH] [PATH_REF:0123456789ab]"),
    ],
)
def test_public_path_projection_rejects_forged_reference_markers(forged: str) -> None:
    redacted = public_diagnostic_value({"source_path": forged})["source_path"]

    assert forged not in redacted
    assert "/srv/private" not in redacted
    assert "sub-P001" not in redacted
    assert "topsecret" not in redacted
    assert "[REDACTED_PATH]" in redacted
    assert "[PATH_REF:" in redacted


@pytest.mark.parametrize(
    "private_path, private_fragments",
    [
        (
            "/srv/private/%73ub-P001/Jane%20Doe.edf",
            ("%73ub-P001", "sub-P001", "Jane%20Doe", "Jane Doe"),
        ),
        (
            r"C:\private\%4Dary%20Example\patient%2D77.gdf",
            ("%4Dary%20Example", "Mary Example", "patient%2D77", "patient-77"),
        ),
    ],
)
def test_percent_encoded_private_path_projection_is_safe_and_idempotent(
    private_path: str,
    private_fragments: tuple[str, ...],
) -> None:
    first = public_diagnostic_value({"source_path": private_path})
    second = public_diagnostic_value(first)

    assert first == second
    serialized = repr(first)
    for private_fragment in private_fragments:
        assert private_fragment not in serialized
    assert "[REDACTED_PATH]" in serialized
    assert "[PATH_REF:" in serialized


@pytest.mark.parametrize(
    ("encoded", "private_fragments", "expected_marker"),
    [
        (
            "%2Fsrv%2Fclinical%2FMary%20Example%2Fsession.edf",
            ("/srv/clinical", "Mary Example"),
            "[REDACTED_PATH]",
        ),
        (
            "%252Fsrv%252Fclinical%252Fsub-P001%252Fsession.edf",
            ("/srv/clinical", "sub-P001"),
            "[REDACTED_PATH]",
        ),
        (
            "%25252Fsrv%25252Fclinical%25252Fsub-P001%25252Fsession.edf",
            ("/srv/clinical", "sub-P001"),
            "[REDACTED_PATH]",
        ),
        (
            "subject_id%3DMary%20Example",
            ("Mary Example",),
            "[SUBJECT_REF:",
        ),
        (
            "subject%255Fid%253DMary%2520Example",
            ("Mary Example",),
            "[SUBJECT_REF:",
        ),
        (
            "subject%25255Fid%25253DMary%252520Example",
            ("Mary Example",),
            "[SUBJECT_REF:",
        ),
        (
            "api%5Fkey%3Ds3cr3tvalue",
            ("s3cr3tvalue",),
            "[REDACTED_SECRET]",
        ),
        (
            "api%255Fkey%253Ds3cr3tvalue",
            ("s3cr3tvalue",),
            "[REDACTED_SECRET]",
        ),
        (
            "api%25255Fkey%25253Ds3cr3tvalue",
            ("s3cr3tvalue",),
            "[REDACTED_SECRET]",
        ),
        (
            "pass%2500word%253Dnul-secret",
            ("nul-secret",),
            "[REDACTED_SECRET]",
        ),
        (
            "api%5Fkey=correct horse battery staple",
            ("correct", "horse", "battery", "staple"),
            "[REDACTED_SECRET]",
        ),
        (
            "subject%5Fid=Mary Example",
            ("Mary Example",),
            "[SUBJECT_REF:",
        ),
        (
            "-----BEGIN%20PRIVATE%20KEY-----%0Aprivate-material"
            "%0A-----END%20PRIVATE%20KEY-----",
            ("private-material", "BEGIN PRIVATE KEY", "END PRIVATE KEY"),
            "[REDACTED_SECRET]",
        ),
        (
            "api%" + ("25" * 512) + "5Fkey=deep private secret",
            ("deep", "private", "secret"),
            "[REDACTED_SECRET]",
        ),
        (
            "alice%40clinical.example",
            ("alice@clinical.example",),
            "[REDACTED_EMAIL]",
        ),
    ],
)
def test_percent_encoded_sensitive_text_fails_closed(
    encoded: str,
    private_fragments: tuple[str, ...],
    expected_marker: str,
) -> None:
    rendered = public_diagnostic_text(f"Diagnostic: {encoded}")

    assert encoded not in rendered
    decoded_twice = unquote(unquote(encoded))
    for private_fragment in private_fragments:
        assert private_fragment not in rendered
    assert decoded_twice not in rendered
    assert expected_marker in rendered
    assert public_diagnostic_text(rendered) == rendered


def test_percent_encoded_non_sensitive_status_is_preserved() -> None:
    messages = (
        "Import status%3Dok; continue.",
        "Import status%25253Dok; continue.",
        "Import status%5Fcode=ok; continue.",
        "Import status%" + ("25" * 512) + "5Fcode=ok; continue.",
    )

    assert [public_diagnostic_text(message) for message in messages] == list(messages)


@pytest.mark.parametrize(
    ("private_path", "private_fragments"),
    [
        (
            "users/Alice/eeg/session.edf",
            ("users/Alice",),
        ),
        (
            "eeg_data/file.gdf",
            ("eeg_data", "file.gdf"),
        ),
        (
            "/home/alice/Clinical Records/Mary Example.",
            ("/home/alice", "Clinical Records", "Mary Example"),
        ),
        (
            r"C:\Users\Alice\Clinical Records\Mary Example.",
            (r"C:\Users\Alice", "Clinical Records", "Mary Example"),
        ),
    ],
)
def test_relative_and_sentence_final_private_paths_fail_closed(
    private_path: str,
    private_fragments: tuple[str, ...],
) -> None:
    rendered = public_diagnostic_text(f"Could not open {private_path}")

    for private_fragment in private_fragments:
        assert private_fragment not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert public_diagnostic_text(rendered) == rendered


def test_public_diagnostic_redacts_common_secret_forms_and_multiword_values() -> None:
    raw = (
        "AWS_SECRET_ACCESS_KEY=aws-secret-value; "
        "Authorization: Basic dXNlcjpwYXNz; "
        "password=correct horse battery staple; retry after updating credentials."
    )

    redacted = public_diagnostic_text(raw)

    for private_value in (
        "aws-secret-value",
        "dXNlcjpwYXNz",
        "correct",
        "horse",
        "battery",
        "staple",
    ):
        assert private_value not in redacted
    assert redacted.count("[REDACTED_SECRET]") == 3
    assert "retry after updating credentials." in redacted


@pytest.mark.parametrize(
    "raw, private_values, preserved",
    [
        (
            "password=\ncorrect horse battery staple\nRetry after review.",
            ("correct", "horse", "battery", "staple"),
            "Retry after review.",
        ),
        (
            "private_key:\n  first-private-line\n  second-private-line\nContinue.",
            ("first-private-line", "second-private-line"),
            "Continue.",
        ),
        (
            "-----BEGIN PRIVATE KEY-----\nprivate-material\n"
            "-----END PRIVATE KEY-----\nContinue.",
            ("private-material", "BEGIN PRIVATE KEY", "END PRIVATE KEY"),
            "Continue.",
        ),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nrsa-private-material\n"
            "-----END RSA PRIVATE KEY-----",
            ("rsa-private-material", "BEGIN RSA PRIVATE KEY", "END RSA PRIVATE KEY"),
            "",
        ),
    ],
)
def test_public_diagnostic_redacts_multiline_assignments_and_private_key_blocks(
    raw: str,
    private_values: tuple[str, ...],
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(raw)

    for private_value in private_values:
        assert private_value not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert preserved in redacted
    assert public_diagnostic_text(redacted) == redacted


def test_public_diagnostic_redacts_url_digest_and_aws_credentials() -> None:
    raw = (
        "Fetch https://alice:supersecret@example.org/model; "
        'Authorization: Digest username="alice", realm="private", '
        'response="deadbeef"; AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE.'
    )

    redacted = public_diagnostic_text(raw)

    for private_value in (
        "alice:supersecret",
        'username="alice"',
        'realm="private"',
        'response="deadbeef"',
        "AKIAIOSFODNN7EXAMPLE",
    ):
        assert private_value not in redacted
    assert "https://" in redacted
    assert "example.org/model" in redacted
    assert redacted.count("[REDACTED_SECRET]") >= 3


def test_public_diagnostic_redacts_generic_uri_and_aws_signature_credentials() -> None:
    raw = (
        "Fetch ftp://alice:supersecret@127.0.0.1/model; "
        "request https://example.org/object?"
        "X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2Fdate"
        "&X-Amz-Signature=deadbeef; "
        "Authorization: AWS4-HMAC-SHA256 "
        "Credential=AKIAIOSFODNN7EXAMPLE/date, "
        "SignedHeaders=host, Signature=cafebabe."
    )

    redacted = public_diagnostic_text(raw)

    for private_value in (
        "alice:supersecret",
        "AKIAIOSFODNN7EXAMPLE",
        "deadbeef",
        "cafebabe",
    ):
        assert private_value not in redacted
    assert "ftp://" not in redacted
    assert "127.0.0.1/model" not in redacted
    assert "[REDACTED_PATH]" in redacted
    assert redacted.count("[REDACTED_SECRET]") >= 3


def test_public_diagnostic_secret_assignment_preserves_next_instruction() -> None:
    redacted = public_diagnostic_text(
        "password=correct horse battery staple. Retry with another account."
    )

    for private_value in ("correct", "horse", "battery", "staple"):
        assert private_value not in redacted
    assert "Retry with another account." in redacted


@pytest.mark.parametrize(
    "instruction",
    [
        "retry with another account.",
        "2 attempts remain.",
        "請重新登入。",
    ],
)
def test_public_diagnostic_secret_assignment_preserves_any_next_sentence(
    instruction: str,
) -> None:
    redacted = public_diagnostic_text(
        f"password=correct horse battery staple. {instruction}"
    )

    assert "correct horse battery staple" not in redacted
    assert instruction in redacted


@pytest.mark.parametrize(
    "identity",
    [
        "María García",
        "王小明",
        "Mary van Example",
        "Mary Anne van Example",
    ],
)
def test_public_diagnostic_redacts_unicode_and_long_unquoted_identities(
    identity: str,
) -> None:
    redacted = public_diagnostic_text(
        f"Import failed for subject_id={identity}; retry after review."
    )

    assert identity not in redacted
    assert "subject_id=[SUBJECT_REF:" in redacted
    assert "; retry after review." in redacted


def test_public_diagnostic_redacts_multiword_unquoted_identity() -> None:
    redacted = public_diagnostic_text(
        "Import failed for subject_id=Mary Example; retry after review."
    )

    assert "Mary" not in redacted
    assert "Example" not in redacted
    assert "subject_id=[SUBJECT_REF:" in redacted
    assert "; retry after review." in redacted


@pytest.mark.parametrize(
    "identity",
    [
        "alice.smith",
        "García, María",
    ],
)
def test_public_diagnostic_redacts_complete_punctuated_identity(identity: str) -> None:
    redacted = public_diagnostic_text(
        f"Import failed for subject_id={identity}; retry after review."
    )

    assert identity not in redacted
    assert "subject_id=[SUBJECT_REF:" in redacted
    assert "; retry after review." in redacted


@pytest.mark.parametrize(
    "message,private_values,expected_suffix",
    [
        (
            "subject_name=Mary Example failed validation. Choose another file.",
            ("Mary Example",),
            "failed validation. Choose another file.",
        ),
        (
            "participant_code=P001; retry after review.",
            ("P001",),
            "; retry after review.",
        ),
        (
            "subject_ids=P001,P002, retry after review.",
            ("P001", "P002"),
            ", retry after review.",
        ),
        (
            "Subject ID: Mary Example; continue.",
            ("Mary Example",),
            "; continue.",
        ),
        (
            "BIDS participant sub-control failed validation.",
            ("sub-control",),
            "failed validation.",
        ),
    ],
)
def test_public_diagnostic_redacts_extended_text_identity_without_losing_action(
    message: str,
    private_values: tuple[str, ...],
    expected_suffix: str,
) -> None:
    redacted = public_diagnostic_text(message)

    for private_value in private_values:
        assert private_value not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert expected_suffix in redacted


@pytest.mark.parametrize(
    "message, identity, preserved",
    [
        (
            "Subject Jane Doe failed preprocessing. Retry after review.",
            "Jane Doe",
            "failed preprocessing. Retry after review.",
        ),
        (
            "受試者王小明前處理失敗。請檢查資料。",
            "王小明",
            "前處理失敗。請檢查資料。",
        ),
        (
            "受试者张伟预处理失败。请检查数据。",
            "张伟",
            "预处理失败。请检查数据。",
        ),
    ],
)
def test_public_diagnostic_redacts_natural_identity_failure_sentences(
    message: str,
    identity: str,
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(message)

    assert identity not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert preserved in redacted


@pytest.mark.parametrize(
    ("message", "identity", "preserved"),
    (
        (
            "Subject Jos\u00e9 \u00c1lvarez completed preprocessing.",
            "Jos\u00e9 \u00c1lvarez",
            "completed preprocessing.",
        ),
        (
            "Participant Zo\u00eb Fran\u00e7ois was accepted.",
            "Zo\u00eb Fran\u00e7ois",
            "was accepted.",
        ),
        (
            "Patient \u738b\u5c0f\u660e loaded successfully.",
            "\u738b\u5c0f\u660e",
            "loaded successfully.",
        ),
        (
            "\u53c3\u8207\u8005\u9673\u5c0f\u660e\u5df2\u5b8c\u6210\u532f\u5165\u3002",
            "\u9673\u5c0f\u660e",
            "\u5df2\u5b8c\u6210\u532f\u5165\u3002",
        ),
    ),
)
def test_public_diagnostic_redacts_natural_identity_success_sentences(
    message: str,
    identity: str,
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(message)

    assert identity not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert preserved in redacted


def test_public_diagnostic_preserves_non_identity_sub_prefix_terms() -> None:
    message = (
        "Compare sub-band, sub-threshold, sub-sampling, sub-second, sub-sample, "
        "sub-harmonic, sub-Gaussian, sub-Nyquist, and sub-1Hz features with "
        "subject-matched, participant-facing, and patient-reported outcomes."
    )

    assert public_diagnostic_text(message) == message


def test_public_diagnostic_preserves_scientific_digest_language() -> None:
    message = "Compute a SHA-256 digest for the BIDS file before validation."

    assert public_diagnostic_text(message) == message


def test_public_diagnostic_redacts_lowercase_bids_identifier_in_filename() -> None:
    redacted = public_diagnostic_text("Could not read sub-control.edf.")

    assert "sub-control" not in redacted
    assert "sub-[SUBJECT_REF:" in redacted
    assert ".edf" in redacted


def test_public_diagnostic_projection_is_idempotent() -> None:
    raw_text = (
        "subject_id=Alice; could not read /srv/private/sub-P001/session.edf "
        "with password=secret; retry."
    )
    raw_value = {
        "subject_name": "Alice",
        "source_path": "/srv/private/sub-P001/session.edf",
        "token": "secret",
    }

    first_text = public_diagnostic_text(raw_text)
    first_value = public_diagnostic_value(raw_value)

    assert public_diagnostic_text(first_text) == first_text
    assert public_diagnostic_value(first_value) == first_value


@pytest.mark.parametrize(
    ("raw", "private_value"),
    [
        ("AWS_SECRET_ACCESS\u200b_KEY=topsecret; retry.", "topsecret"),
        ("pass\x1b[31mword=topsecret; retry.", "topsecret"),
        ("pass\x00word=topsecret; retry.", "topsecret"),
        ("pass\tword=topsecret; retry.", "topsecret"),
        ("subject_\u200bid=Mary Example; retry.", "Mary Example"),
        ("subject_\x00id=Mary Example; retry.", "Mary Example"),
        (
            'Dige\x00st username="alice", realm="private", response="deadbeef". Retry.',
            "deadbeef",
        ),
        (
            "AWS4-HMAC-\t256 Credential=AKIAIOSFODNN7EXAMPLE/date, "
            "SignedHeaders=host, Signature=deadbeef. Retry.",
            "AKIAIOSFODNN7EXAMPLE",
        ),
    ],
)
def test_public_diagnostic_normalizes_evasive_controls_before_redaction(
    raw: str,
    private_value: str,
) -> None:
    redacted = public_diagnostic_text(raw)

    assert private_value not in redacted
    assert public_diagnostic_text(redacted) == redacted


def test_public_diagnostic_normalizes_structured_keys_before_classification() -> None:
    redacted = public_diagnostic_value(
        {
            "pass\x1b[31mword": "correct horse",
            "pass\x00word": "nul secret",
            "pass\tword": "tab secret",
            "pass\u200bword": "zero-width secret",
            "subject_\u200bid": "Mary Example",
            "subject_\x00id": "Alice Example",
            "subject_\tid": "María García",
            "source\x00_path": "relative/private/Mary Example/session.edf",
        }
    )
    serialized = repr(redacted)

    for private_value in (
        "correct horse",
        "nul secret",
        "tab secret",
        "zero-width secret",
        "Mary Example",
        "Alice Example",
        "María García",
        "relative/private",
    ):
        assert private_value not in serialized
    assert "[REDACTED_SECRET]" in serialized
    assert "[SUBJECT_REF:" in serialized
    assert "[REDACTED_PATH]" in serialized


@pytest.mark.parametrize(
    ("field_name", "private_identity"),
    (
        ("client", "Jane Doe"),
        ("clie\u200bnt", "Mary Example"),
        ("client_identity", "Bob Jones"),
        ("client_\u200bidentity", "王小明"),
        ("client_name", "Jane Doe"),
        ("client_\u200bname", "Mary Example"),
        ("客戶", "Bob Jones"),
        ("客\u200b戶", "王小明"),
        ("客户", "Jane Doe"),
        ("客\u200b户", "Mary Example"),
    ),
)
def test_public_diagnostic_value_redacts_client_identity_key_variants(
    field_name: str,
    private_identity: str,
) -> None:
    projected = public_diagnostic_value({field_name: private_identity})
    serialized = json.dumps(projected, ensure_ascii=False)

    assert private_identity not in serialized
    assert "[SUBJECT_REF:" in serialized


@pytest.mark.parametrize(
    "message",
    [
        'Digest username="alice", realm="private", response="deadbeef". Retry.',
        (
            "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/date, "
            "SignedHeaders=host, Signature=deadbeef. Retry."
        ),
    ],
)
def test_public_diagnostic_redacts_bare_auth_credentials(message: str) -> None:
    redacted = public_diagnostic_text(message)

    for private_value in ("alice", "private", "deadbeef", "AKIAIOSFODNN7EXAMPLE"):
        assert private_value not in redacted
    assert "Retry." in redacted
    assert "]]" not in redacted


@pytest.mark.parametrize(
    ("message", "preserved"),
    [
        (
            "subject_name=Mary Select Example; retry.",
            "; retry.",
        ),
        (
            "subject_id=P001 retry-secret; choose another file.",
            "; choose another file.",
        ),
        (
            "subject_name=Mary Example was rejected. Choose another file.",
            "was rejected. Choose another file.",
        ),
        (
            "subject_id=Alice loaded successfully.",
            "loaded successfully.",
        ),
        (
            "subject_name=王小明。請重新選擇。",
            "。請重新選擇。",
        ),
    ],
)
def test_public_diagnostic_redacts_identity_without_dropping_status_or_instruction(
    message: str,
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(message)

    assert "[SUBJECT_REF:" in redacted
    assert preserved in redacted
    assert "Mary Select Example" not in redacted
    assert "P001 retry-secret" not in redacted
    assert "Mary Example" not in redacted
    assert "Alice loaded" not in redacted
    assert "王小明" not in redacted


@pytest.mark.parametrize(
    "message",
    [
        f"subject_id={'A' * 300}; retry.",
        f'subject_name="{"Mary Example " * 20}"; retry.',
    ],
)
def test_public_diagnostic_redacts_oversized_identity_values(message: str) -> None:
    redacted = public_diagnostic_text(message)

    assert "Mary Example" not in redacted
    assert "A" * 100 not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert "; retry." in redacted


@pytest.mark.parametrize(
    ("message", "private_values", "preserved"),
    [
        (
            'subject_name="Mary O\'Connor"; retry.',
            ("Mary", "O'Connor"),
            "; retry.",
        ),
        (
            'subject_name="Mary \\"M\\" Example"; retry.',
            ("Mary", "Example"),
            "; retry.",
        ),
        (
            "subject_name=Mary A. Smith; retry.",
            ("Mary", "Smith"),
            "; retry.",
        ),
        (
            "participant_name=Dr. María García; choose another.",
            ("María", "García"),
            "; choose another.",
        ),
        (
            "subjects=S01,S02; retry.",
            ("S01", "S02"),
            "; retry.",
        ),
        (
            "participants=P001,P002; retry.",
            ("P001", "P002"),
            "; retry.",
        ),
        (
            "subject_id=Alice. participant_id=Bob; retry.",
            ("Alice", "Bob"),
            "; retry.",
        ),
    ],
)
def test_public_diagnostic_redacts_quoted_initial_honorific_and_plural_identities(
    message: str,
    private_values: tuple[str, ...],
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(message)

    for private_value in private_values:
        assert private_value not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert preserved in redacted


def test_public_diagnostic_preserves_empty_identity_assignment_action() -> None:
    message = "subject_id=. Retry."

    assert public_diagnostic_text(message) == message


@pytest.mark.parametrize(
    ("private_path", "private_fragments"),
    [
        (
            "/home/alice/Clinical Records/Mary Example/config.ini",
            ("/home/alice", "Clinical Records", "Mary Example"),
        ),
        (
            r"C:\Users\Alice\Clinical Records\Mary Example\config.ini",
            (r"C:\Users\Alice", "Clinical Records", "Mary Example"),
        ),
        (
            "relative/private/Mary Example/session.edf",
            ("relative/private", "Mary Example"),
        ),
        (
            "/home/alice/Clinical Records/Mary Example",
            ("/home/alice", "Clinical Records", "Mary Example"),
        ),
        (
            "/home/alice/Clinical Records/Mary.Example",
            ("/home/alice", "Clinical Records", "Mary.Example"),
        ),
    ],
)
def test_public_diagnostic_redacts_private_paths_with_spaces_and_relative_paths(
    private_path: str,
    private_fragments: tuple[str, ...],
) -> None:
    redacted = public_diagnostic_text(
        f"Could not open {private_path}; choose another file."
    )

    for private_fragment in private_fragments:
        assert private_fragment not in redacted
    assert "[REDACTED_PATH]" in redacted
    assert "choose another file." in redacted


@pytest.mark.parametrize(
    "private_path",
    (
        "/home/alice/Clinical Records/Mary Example",
        r"C:\Users\Alice\Patient Records\Mary Example",
        r"\\clinical-nas\EEG Archive\Mary Example",
    ),
)
@pytest.mark.parametrize("line_ending", ("\n", "\r\n"))
def test_public_diagnostic_redacts_spaced_directory_before_line_boundary(
    private_path: str,
    line_ending: str,
) -> None:
    rendered = public_diagnostic_text(
        f"Selected source: {private_path}{line_ending}Review the import preview."
    )

    assert private_path not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert rendered.endswith("\nReview the import preview.")


@pytest.mark.parametrize(
    ("suffix", "preserved"),
    (
        (". Review the import preview.", ". Review the import preview."),
        ("! Retry with a smaller scope.", "! Retry with a smaller scope."),
    ),
)
def test_public_diagnostic_preserves_prose_after_spaced_private_directory(
    suffix: str,
    preserved: str,
) -> None:
    private_path = "/home/alice/Clinical Records/Mary Example"

    rendered = public_diagnostic_text(f"Selected source: {private_path}{suffix}")

    assert private_path not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert rendered.endswith(preserved)


@pytest.mark.parametrize("line_ending", ("", "\n", "\r\n"))
def test_public_diagnostic_preserves_recovery_clause_after_spaced_path(
    line_ending: str,
) -> None:
    private_path = "/home/alice/Clinical Records/Mary Example"

    rendered = public_diagnostic_text(
        f"Path {private_path} because import failed.{line_ending}Retry after review."
    )

    assert private_path not in rendered
    assert "Clinical Records" not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert " because import failed." in rendered
    assert rendered.endswith("Retry after review.")
    assert "\r" not in rendered
    assert ("\n" in rendered) is bool(line_ending)


@pytest.mark.parametrize(
    "message",
    [
        "Retry command with --password topsecret and continue.",
        "AWS_SECRET_ACCESS_KEY topsecret; retry.",
    ],
)
def test_public_diagnostic_redacts_space_separated_cli_and_env_secrets(
    message: str,
) -> None:
    redacted = public_diagnostic_text(message)

    assert "topsecret" not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert "Retry" in redacted or "retry" in redacted


def test_quoted_identity_projection_is_idempotent() -> None:
    first = public_diagnostic_text('subject_name="Mary Example"; retry.')
    second = public_diagnostic_text(first)
    third = public_diagnostic_text(second)

    assert "Mary Example" not in first
    assert first == second == third


@pytest.mark.parametrize(
    "message",
    [
        "Digest alpha=8, beta=13 frequency-band results before review.",
        "Digest value=SHA256(data), then compare the BIDS manifest.",
    ],
)
def test_public_diagnostic_preserves_scientific_digest_parameter_text(
    message: str,
) -> None:
    assert public_diagnostic_text(message) == message


@pytest.mark.parametrize(
    ("message", "private_value", "preserved"),
    [
        (
            "subject_name=王小明\uff0c請重新選擇。",
            "王小明",
            "\uff0c請重新選擇。",
        ),
        (
            "subject_id=Alice is invalid. Choose another file.",
            "Alice",
            "is invalid. Choose another file.",
        ),
        (
            "participant_id=P001 is missing. Retry.",
            "P001",
            "is missing. Retry.",
        ),
    ],
)
def test_public_diagnostic_preserves_cjk_and_status_actions(
    message: str,
    private_value: str,
    preserved: str,
) -> None:
    redacted = public_diagnostic_text(message)

    assert private_value not in redacted
    assert "[SUBJECT_REF:" in redacted
    assert preserved in redacted


def test_public_diagnostic_preserves_lines_but_removes_other_controls() -> None:
    raw = "Import failed\r\nFORGED ERROR\t\x00subject_id=Alice\u202e.gdf"

    redacted = public_diagnostic_text(raw)

    assert "Import failed" in redacted
    assert "FORGED ERROR" in redacted
    assert "Alice" not in redacted
    assert all(character == "\n" or ord(character) >= 32 for character in redacted)
    assert "\u202e" not in redacted
    assert "\t" not in redacted
    assert "\x00" not in redacted
    assert "\n" in redacted
    assert "\r" not in redacted


def test_single_line_diagnostic_layout_blocks_log_injection() -> None:
    redacted = public_diagnostic_text(
        "Import failed\r\nFORGED\tERROR",
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )

    assert redacted == "Import failed FORGED ERROR"


def test_detailed_diagnostics_are_explicit_and_still_log_injection_safe() -> None:
    private = "/srv/private/sub-P001/session.edf subject_id=Alice"

    detailed = public_diagnostic_text(
        f"{private}\r\nFORGED",
        disclosure=DiagnosticDisclosure.DETAILED,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )

    assert private in detailed
    assert "FORGED" in detailed
    assert "\n" not in detailed
    assert "\r" not in detailed


def test_public_diagnostic_preserves_https_urls() -> None:
    public_urls = (
        "https://docs.example.test/product/guide",
        "https://docs.example.test/product/guide.json",
        "https://docs-example.test/product/guide.json",
        "https://docs.example-test/product/guide.json",
    )

    for public_url in public_urls:
        assert public_diagnostic_text(public_url) == public_url


@pytest.mark.parametrize(
    "message",
    [
        "PASSWORD requirements are missing.",
        "TOKEN count is 5.",
    ],
)
def test_public_diagnostic_preserves_uppercase_domain_labels(message: str) -> None:
    assert public_diagnostic_text(message) == message


def test_public_diagnostic_preserves_eeg_domain_language_and_missing_status() -> None:
    message = (
        "Use subject-specific and subject-independent validation. "
        "Compare participant-level and patient-centered summaries. "
        "Ask the subject-matter expert. Subject: Missing. Subject: not set."
    )

    assert public_diagnostic_text(message) == message


@pytest.mark.parametrize(
    "email",
    (
        "josé@exämple.test",
        "δοκιμή@παράδειγμα.δοκιμή",
        "mary@xn--exmple-cua.test",
        "mary@example.xn--p1ai",
    ),
)
def test_public_diagnostic_redacts_unicode_and_punycode_email_identities(
    email: str,
) -> None:
    rendered = public_diagnostic_text(f"Contact {email} after import review.")

    assert email not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert rendered.endswith(" after import review.")


def test_public_diagnostic_redacts_natural_subject_id_rejection() -> None:
    rendered = public_diagnostic_text(
        "Subject ID Mary Example was rejected. Retry after review."
    )

    assert "Mary Example" not in rendered
    assert "Subject ID [SUBJECT_REF:" in rendered
    assert rendered.endswith(" was rejected. Retry after review.")


@pytest.mark.parametrize(
    ("message", "private_identity", "preserved"),
    (
        (
            "Error for patient Mary Example at preprocessing.",
            "Mary Example",
            " at preprocessing.",
        ),
        (
            "Import failed for subject Alice Smith because the header is invalid.",
            "Alice Smith",
            " because the header is invalid.",
        ),
        (
            "Review participant Jane Doe in the validation report.",
            "Jane Doe",
            " in the validation report.",
        ),
        (
            "受試者王小明在前處理時發生錯誤。",
            "王小明",
            "在前處理時發生錯誤。",
        ),
        (
            "患者陳大文因為匯入失敗，請檢查來源。",  # noqa: RUF001
            "陳大文",
            "因為匯入失敗，請檢查來源。",  # noqa: RUF001
        ),
        (
            "參與者林小華於驗證階段被拒絕。",
            "林小華",
            "於驗證階段被拒絕。",
        ),
    ),
)
def test_public_diagnostic_redacts_natural_labeled_identity_context(
    message: str,
    private_identity: str,
    preserved: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert preserved in rendered


@pytest.mark.parametrize(
    ("message", "private_identity", "preserved"),
    (
        (
            "Import failed for subject Jane Doe during validation.",
            "Jane Doe",
            " during validation.",
        ),
        (
            "Import failed for client Mary Example during validation.",
            "Mary Example",
            " during validation.",
        ),
        (
            "Import failed for patient Bob Jones during validation.",
            "Bob Jones",
            " during validation.",
        ),
        (
            "Import failed for subject 王小明 during validation.",
            "王小明",
            " during validation.",
        ),
    ),
)
def test_public_diagnostic_redacts_identity_after_failure_for_prefix(
    message: str,
    private_identity: str,
    preserved: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert preserved in rendered


def test_public_diagnostic_redacts_delimited_labeled_identities() -> None:
    message = (
        "Import failed for subject Jane Doe; client Mary Example; "
        "patient Bob Jones; subject 王小明. Retry."
    )

    rendered = public_diagnostic_text(message)

    for private_identity in ("Jane Doe", "Mary Example", "Bob Jones", "王小明"):
        assert private_identity not in rendered
    assert rendered.count("[SUBJECT_REF:") == 4
    assert rendered.endswith(". Retry.")


@pytest.mark.parametrize(
    ("message", "private_identity"),
    (
        (
            "Failed to read /home/alice/Clinical Records/Jane Doe/session 01/"
            "eeg data.edf for subject Jane Doe",
            "Jane Doe",
        ),
        (
            r"Could not read C:\Users\Mary Example\EEG Studies\session 01"
            r"\recording data.gdf for client Mary Example",
            "Mary Example",
        ),
        (
            r"Could not read \\lab-server\Clinical Share\Bob Jones\session 01"
            r"\events data.tsv for patient Bob Jones",
            "Bob Jones",
        ),
        (
            "Could not read /srv/Clinical Records/王小明/session 01/"
            "events data.tsv for subject 王小明",
            "王小明",
        ),
    ),
)
def test_public_diagnostic_redacts_labeled_identity_at_end_of_text(
    message: str,
    private_identity: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert "[SUBJECT_REF:" in rendered


@pytest.mark.parametrize(
    ("message", "private_identity", "preserved"),
    (
        (
            "Client Jane Doe failed validation. Retry.",
            "Jane Doe",
            " failed validation. Retry.",
        ),
        (
            "Clie\u200bnt Mary Example was rejected. Retry.",
            "Mary Example",
            " was rejected. Retry.",
        ),
        (
            "client_identity=Bob Jones; retry.",
            "Bob Jones",
            "; retry.",
        ),
        (
            "client_\u200bname=Jane Doe; retry.",
            "Jane Doe",
            "; retry.",
        ),
        (
            "客戶王小明從匯入畫面載入成功。",
            "王小明",
            "從匯入畫面載入成功。",
        ),
        (
            "客\u200b戶王小明從\u200b匯入畫面載入成功。",
            "王小明",
            "從匯入畫面載入成功。",
        ),
        (
            "客户王小明从导入画面加载成功。",
            "王小明",
            "从导入画面加载成功。",
        ),
        (
            "客\u200b户王小明从\u200b导入画面加载成功。",
            "王小明",
            "从导入画面加载成功。",
        ),
    ),
)
def test_public_diagnostic_text_redacts_client_identity_variants(
    message: str,
    private_identity: str,
    preserved: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert preserved in rendered


@pytest.mark.parametrize(
    "message",
    (
        "Subject ID mapping was rejected by the schema.",
        "Subject ID confidence was rejected as a feature.",
        "Subject ID mapping was accepted by the schema.",
        "Participant workflow completed validation.",
        "Patient record loaded successfully.",
        "Patient data in the import wizard remains available.",
        "Subject mapping because the schema is strict.",
        "Participant workflow at the validation stage is ready.",
        "\u53c3\u8207\u8005\u8cc7\u6599\u5df2\u5b8c\u6210\u532f\u5165\u3002",
        "患者資料在匯入精靈中仍然可用。",
        "受試者對映因為結構限制而被停用。",
        "EEG label subject-id-independent remains available.",
    ),
)
def test_public_diagnostic_preserves_nonidentity_subject_id_domain_terms(
    message: str,
) -> None:
    assert public_diagnostic_text(message) == message


@pytest.mark.parametrize(
    "message",
    [
        "Use basic alpha-band normalization",
        "Subject: press the left button",
        "/reset",
        "Researcher Jane Doe failed preprocessing.",
    ],
)
def test_public_diagnostic_preserves_nonsecret_nonidentity_workflow_text(
    message: str,
) -> None:
    assert public_diagnostic_text(message) == message


def test_public_diagnostic_sanitizer_is_bounded_near_linear() -> None:
    elapsed: list[float] = []
    for size in (32 * 1024, 128 * 1024):
        adversarial = ("subject:" + ("a." * size))[:size]
        started = perf_counter()
        rendered = public_diagnostic_text(adversarial)
        elapsed.append(perf_counter() - started)
        assert rendered

    assert elapsed[0] < 3.0
    assert elapsed[1] < 12.0
    assert elapsed[1] <= (elapsed[0] * 6) + 1.0


def test_deep_percent_encoding_is_bounded_and_preserves_non_sensitive_text() -> None:
    message = "status%" + ("25" * 60_000) + "5Fcode=ok"

    started = perf_counter()
    rendered = public_diagnostic_text(message)
    elapsed = perf_counter() - started

    assert rendered == message
    assert elapsed < 12.0


def test_public_diagnostic_output_expansion_has_a_global_byte_bound() -> None:
    private_path = "/srv/private/sub-P001/a.edf"
    message = " ".join(private_path for _ in range(4_000))

    rendered = public_diagnostic_text(message)

    assert private_path not in rendered
    assert len(rendered.encode("utf-8")) <= 128 * 1024
    assert "[TRUNCATED]" in rendered
    assert public_diagnostic_text(rendered) == rendered


@pytest.mark.parametrize(
    "private_value",
    (
        "file://research-nas/Clinical Records/Mary Example",
        "Clinical Records/Mary Example",
    ),
)
def test_public_diagnostic_redacts_authority_uri_and_directory_only_paths(
    private_value: str,
) -> None:
    rendered = public_diagnostic_text(
        f"Import failed for {private_value}; choose another source."
    )

    assert private_value not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert "Import failed for" in rendered
    assert "choose another source" in rendered


@pytest.mark.parametrize(
    "private_uri",
    (
        "sftp://research-nas/Clinical Records/Mary Example",
        "smb://research-nas/Clinical Records/Mary Example",
        "ftp://research-nas/Clinical Records/Mary Example",
    ),
)
def test_public_diagnostic_atomically_redacts_private_remote_uris(
    private_uri: str,
) -> None:
    rendered = public_diagnostic_text(
        f"Import failed for {private_uri}; choose another source."
    )

    assert private_uri not in rendered
    assert "research-nas" not in rendered
    assert "Clinical Records" not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert "Import failed for" in rendered
    assert "choose another source" in rendered


@pytest.mark.parametrize(
    "private_path",
    (
        "/srv/Clinical Records/Mary Example's session.edf",
        '/srv/Clinical Records/Mary \\"Example\\"/session.edf',
    ),
)
def test_public_diagnostic_redacts_quoted_paths_with_embedded_quotes(
    private_path: str,
) -> None:
    rendered = public_diagnostic_text(
        f"Could not open '{private_path}' because retry is available."
    )

    assert private_path not in rendered
    assert "/srv" not in rendered
    assert "Clinical Records" not in rendered
    assert "Mary" not in rendered
    assert "Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert "because retry is available" in rendered


@pytest.mark.parametrize(
    ("message", "private_identity", "preserved_action"),
    (
        (
            "Patient maría garcía encountered an import error.",
            "maría garcía",
            "encountered an import error",
        ),
        (
            "患者王小明發生匯入錯誤，請重試。",  # noqa: RUF001
            "王小明",
            "發生匯入錯誤，請重試",  # noqa: RUF001
        ),
    ),
)
def test_public_diagnostic_redacts_multilingual_natural_identities(
    message: str,
    private_identity: str,
    preserved_action: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert preserved_action in rendered


@pytest.mark.parametrize(
    ("message", "private_identity", "preserved_action"),
    (
        (
            "Could not load subject Jane Doe",
            "Jane Doe",
            "Could not load subject",
        ),
        (
            "Failed to import participant Mary Example",
            "Mary Example",
            "Failed to import participant",
        ),
        (
            "Training failed for patient Bob Jones",
            "Bob Jones",
            "Training failed for patient",
        ),
        (
            "無法匯入受試者王小明",
            "王小明",
            "無法匯入受試者",
        ),
        (
            "受試者王小明無法完成前處理",
            "王小明",
            "無法完成前處理",
        ),
    ),
)
def test_public_diagnostic_redacts_identity_in_natural_failure_forms(
    message: str,
    private_identity: str,
    preserved_action: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert preserved_action in rendered


@pytest.mark.parametrize(
    ("message", "private_identity"),
    (
        (
            "Could not load subject Jane Doe from "
            "/home/alice/Clinical Records/Mary Example/A01.edf",
            "Jane Doe",
        ),
        (
            "Failed to import participant Mary Example from "
            "sftp://alice:secret@private.example/Clinical Records/"
            "Mary Example.edf",
            "Mary Example",
        ),
        (
            "載入受試者王小明失敗：C:\\Users\\王小明\\EEG Data\\A01.gdf",  # noqa: RUF001
            "王小明",
        ),
        (
            "訓練病患王小明失敗，來源 "  # noqa: RUF001
            "ftp://user:pass@host/private/王小明.edf",
            "王小明",
        ),
    ),
)
def test_public_diagnostic_redacts_labeled_identity_before_private_source(
    message: str,
    private_identity: str,
) -> None:
    rendered = public_diagnostic_text(message)

    assert private_identity not in rendered
    assert "[SUBJECT_REF:" in rendered
    assert "[REDACTED_PATH]" in rendered


@pytest.mark.parametrize(
    "email",
    (
        '"Mary Example"@example.com',
        "user@[192.168.10.25]",
    ),
)
def test_public_diagnostic_redacts_quoted_and_address_literal_emails(
    email: str,
) -> None:
    rendered = public_diagnostic_text(f"Contact {email} after import review.")

    assert email not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "after import review" in rendered


def test_public_diagnostic_projection_classifies_normalized_sensitive_keys() -> None:
    private_values = {
        "credential": "credential-secret",
        "cookie": "session=private-cookie",
        "refresh": "private-refresh-token",
        "participant": "Mary Example",
        "subject": "subject-private-uuid",
        "filename": "Mary Example.edf",
        "input": "Clinical Records/Mary Example",
        "recipe": "recipes/Mary Example.json",
    }
    projected = public_diagnostic_value(
        {
            "nested": {
                "Cre-den_tial": private_values["credential"],
                "Cookie": private_values["cookie"],
                "refreshToken": private_values["refresh"],
                "participant_identity": private_values["participant"],
                "subject.UUID": private_values["subject"],
                "fileName": private_values["filename"],
                "inputPath": private_values["input"],
                "recipe_path": private_values["recipe"],
            }
        }
    )
    serialized = json.dumps(projected, ensure_ascii=False)

    assert all(value not in serialized for value in private_values.values())
    assert serialized.count("[REDACTED_SECRET]") >= 3
    assert serialized.count("[SUBJECT_REF:") >= 2
    assert serialized.count("[REDACTED_PATH]") >= 3


def test_safe_exception_type_name_does_not_execute_hostile_metaclass() -> None:
    error = _HostileDiagnosticError("/srv/Clinical Records/Mary Example")

    assert diagnostics_module.safe_exception_type_name(error) == "Exception"
    assert (
        diagnostics_module.public_exception_message(error, fallback="safe failure")
        == "safe failure"
    )
    assert public_diagnostic_text(error) == "[UNSUPPORTED_VALUE]"


def test_public_exception_message_sanitizes_exact_builtin_detail() -> None:
    private_path = "/srv/Clinical Records/Mary Example"

    rendered = diagnostics_module.public_exception_message(
        RuntimeError(f"Could not load {private_path}; retry.")
    )

    assert rendered.startswith("Could not load")
    assert private_path not in rendered
    assert "Mary Example" not in rendered
    assert "[REDACTED_PATH]" in rendered
    assert rendered.endswith("retry.")


def test_public_diagnostic_value_bounds_cycles_and_nested_containers() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)
    cyclic_identity: dict[str, object] = {}
    cyclic_identity["patient"] = cyclic_identity
    deeply_nested: object = "subject_id=Deep-Identity"
    for _ in range(64):
        deeply_nested = {"nested": deeply_nested}

    cyclic_projection = public_diagnostic_value(cyclic)
    identity_projection = public_diagnostic_value({"subjects": cyclic_identity})
    nested_projection = public_diagnostic_value(deeply_nested)

    assert cyclic_projection == ["[CYCLE]"]
    assert "[CYCLE]" in repr(identity_projection)
    assert "[TRUNCATED]" in repr(nested_projection)
    assert "Deep-Identity" not in repr(nested_projection)


def test_public_diagnostic_value_bounds_container_cardinality() -> None:
    value = {f"item_{index}": f"subject_id=Private-{index}" for index in range(1_000)}

    projected = public_diagnostic_value(value)
    serialized = repr(projected)

    assert len(projected) <= 257
    assert projected["[TRUNCATED_ITEMS]"] == 744
    assert "Private-999" not in serialized


def test_public_diagnostic_value_rejects_unknown_objects_without_rendering_them() -> (
    None
):
    class PrivateObject:
        def __str__(self) -> str:
            raise AssertionError("Unknown diagnostic objects must not be rendered.")

        def __repr__(self) -> str:
            return "PrivateObject(/srv/clinical/sub-P001/session.edf, topsecret)"

    private_object = PrivateObject()

    projected = public_diagnostic_value({"detail": private_object})

    assert projected == {"detail": "[UNSUPPORTED_VALUE]"}
    assert projected["detail"] is not private_object


def test_public_diagnostic_value_does_not_execute_container_subclass_protocols() -> (
    None
):
    class PrivateDict(dict[str, str]):
        def items(self):
            raise AssertionError("Container subclasses must not be traversed.")

    class PrivateList(list[str]):
        def __iter__(self):
            raise AssertionError("Container subclasses must not be traversed.")

    class PrivateTuple(tuple[str, ...]):
        def __iter__(self):
            raise AssertionError("Container subclasses must not be traversed.")

    class PrivateSet(set[str]):
        def __iter__(self):
            raise AssertionError("Container subclasses must not be traversed.")

    projected = public_diagnostic_value(
        {
            "mapping": PrivateDict({"subject": "Private-17"}),
            "sequence": PrivateList(["subject_id=Private-18"]),
            "tuple": PrivateTuple(("subject_id=Private-19",)),
            "set": PrivateSet({"subject_id=Private-20"}),
        }
    )

    assert projected == {
        "mapping": "[UNSUPPORTED_VALUE]",
        "sequence": "[UNSUPPORTED_VALUE]",
        "tuple": "[UNSUPPORTED_VALUE]",
        "set": "[UNSUPPORTED_VALUE]",
    }


def test_public_diagnostics_do_not_execute_custom_pathlike_protocols() -> None:
    class PrivatePath(os.PathLike[str]):
        def __fspath__(self) -> str:
            raise AssertionError("Custom path protocols must not be executed.")

    value = PrivatePath()

    assert public_diagnostic_text(value) == "[UNSUPPORTED_VALUE]"
    assert public_diagnostic_value({"path": value}) == {"path": "[UNSUPPORTED_VALUE]"}


def test_public_diagnostic_value_rejects_primitive_subclasses_and_huge_ints() -> None:
    class PrivateInt(int):
        def __str__(self) -> str:
            raise AssertionError("Primitive subclasses must not be rendered.")

        def __repr__(self) -> str:
            return "PrivateInt(/srv/clinical/sub-P001/session.edf)"

    private_int = PrivateInt(7)
    huge_int = 1 << (256 * 1024 * 8)

    projected = public_diagnostic_value({"unknown": private_int, "oversized": huge_int})

    assert projected["unknown"] == "[UNSUPPORTED_VALUE]"
    assert projected["unknown"] is not private_int
    assert projected["oversized"] == "[TRUNCATED]"


def test_public_diagnostic_value_bounds_shared_subtrees_globally() -> None:
    shared_leaf = ["subject_id=Private-17"] * 256
    value = [shared_leaf] * 256

    projected = public_diagnostic_value(value)

    assert isinstance(projected, list)
    assert isinstance(projected[0], list)
    assert projected[1:] == ["[SHARED]"] * 255
    assert sum(isinstance(item, list) for item in projected) == 1


def test_public_diagnostic_value_enforces_global_node_and_byte_budgets() -> None:
    value = [
        [f"subject_id=Private-{outer}-{inner}" for inner in range(64)]
        for outer in range(64)
    ]
    byte_heavy = [["x" * 8_192 for _ in range(32)] for _ in range(32)]

    projected = public_diagnostic_value(value)
    byte_projected = public_diagnostic_value(byte_heavy)

    assert _structured_node_count(projected) <= 2_049
    assert "[TRUNCATED]" in repr(projected)
    assert _structured_text_bytes(byte_projected) <= (256 * 1024) + len(b"[TRUNCATED]")
    assert "[TRUNCATED]" in repr(byte_projected)


def test_public_diagnostic_value_bounds_actual_compact_json_bytes_at_exact_cap() -> (
    None
):
    empty_envelope_size = len(
        json.dumps(
            {"a": "", "b": ""},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    text_budget = PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES - empty_envelope_size
    left_size = text_budget // 2
    at_cap = {"a": "x" * left_size, "b": "x" * (text_budget - left_size)}
    over_cap = {"a": at_cap["a"], "b": f"{at_cap['b']}x"}

    projected_at_cap = public_diagnostic_value(at_cap)
    projected_over_cap = public_diagnostic_value(over_cap)
    serialized_at_cap = json.dumps(
        projected_at_cap,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    serialized_over_cap = json.dumps(
        projected_over_cap,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert len(serialized_at_cap) == PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES
    assert len(serialized_over_cap) <= PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES
    assert "[TRUNCATED" in repr(projected_over_cap)


def test_public_diagnostics_reject_hostile_protocol_subclasses_without_execution() -> (
    None
):
    class HostileStr(str):
        def __str__(self) -> str:
            raise AssertionError("str subclass protocol must not execute")

        def __bool__(self) -> bool:
            raise AssertionError("str subclass truth protocol must not execute")

    class HostileEnum(Enum):
        ITEM = "subject_id=Private-Enum"

        @property
        def value(self) -> str:
            raise AssertionError("enum value property must not execute")

    class HostileError(BaseException):
        @property
        def args(self) -> tuple[object, ...]:
            raise AssertionError("exception args property must not execute")

        @property
        def message(self) -> str:
            raise AssertionError("exception message property must not execute")

        def __str__(self) -> str:
            raise AssertionError("exception string protocol must not execute")

    class HostileMapping(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError("mapping lookup must not execute")

        def __iter__(self):
            raise AssertionError("mapping iteration must not execute")

        def __len__(self) -> int:
            raise AssertionError("mapping length must not execute")

    values = (
        HostileStr("/srv/private/sub-P001/session.edf"),
        HostileEnum.ITEM,
        HostileError("subject_id=Private-Error"),
        HostileMapping(),
    )

    for value in values:
        assert public_diagnostic_text(value) == "[UNSUPPORTED_VALUE]"
        assert public_diagnostic_value({"detail": value}) == {
            "detail": "[UNSUPPORTED_VALUE]"
        }


def test_product_code_cannot_install_a_log_handler_outside_central_logger() -> None:
    findings: list[tuple[str, int, str]] = []
    for root in PRODUCT_LOG_ROOTS:
        for path in root.rglob("*.py"):
            if path == LOGGER_MODULE or path.is_relative_to(MODEL_CACHE_ROOT):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in LOG_HANDLER_FACTORIES
                ):
                    findings.append(
                        (
                            path.relative_to(PROJECT_ROOT).as_posix(),
                            node.lineno,
                            node.func.attr,
                        )
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in LOG_METHODS
                    and any(keyword.arg == "extra" for keyword in node.keywords)
                ):
                    findings.append(
                        (
                            path.relative_to(PROJECT_ROOT).as_posix(),
                            node.lineno,
                            "logging extra",
                        )
                    )
                if isinstance(
                    node, (ast.Assign, ast.AnnAssign)
                ) and _is_false_propagate_assignment(node):
                    findings.append(
                        (
                            path.relative_to(PROJECT_ROOT).as_posix(),
                            node.lineno,
                            "propagate=False",
                        )
                    )

    assert findings == []


def test_assistant_redaction_delegates_to_backend_public_diagnostic_boundary() -> None:
    source = (PROJECT_ROOT / "XBrainLab/llm/tools/result_contract.py").read_text(
        encoding="utf-8"
    )

    assert "XBrainLab.backend.utils.public_diagnostics" in source
    assert "_POSIX_PATH_PATTERN" not in source
    assert "_WINDOWS_PATH_PATTERN" not in source


def _path_reference(value: str) -> str:
    marker = "[PATH_REF:"
    start = value.index(marker)
    return value[start : value.index("]", start) + 1]


def _structured_node_count(value: object) -> int:
    if isinstance(value, dict):
        return 1 + sum(1 + _structured_node_count(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return 1 + sum(_structured_node_count(item) for item in value)
    return 1


def _structured_text_bytes(value: object) -> int:
    if isinstance(value, dict):
        return sum(
            len(str(key).encode("utf-8")) + _structured_text_bytes(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return sum(_structured_text_bytes(item) for item in value)
    return len(value.encode("utf-8")) if isinstance(value, str) else 0


def _is_false_propagate_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if not isinstance(value, ast.Constant) or value.value is not False:
        return False
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return any(
        isinstance(target, ast.Attribute) and target.attr == "propagate"
        for target in targets
    )
