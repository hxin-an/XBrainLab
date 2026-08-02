"""Contract tests for the real offline RAG verification command."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from unittest.mock import patch

from scripts.dev import verify_rag
from XBrainLab.llm.agent.context_encoding import (
    UntrustedContextItem,
    UntrustedContextSource,
    encode_untrusted_context,
)


def _encoded_tool_context(tool_name: str) -> str:
    return encode_untrusted_context(
        [
            UntrustedContextItem(
                item_type="rag_example",
                source=UntrustedContextSource(
                    kind="xbrainlab_bundled_gold_set",
                    id="case-1",
                    category="test",
                ),
                data={
                    "input": "test prompt",
                    "expected_action": {
                        "tool_name": tool_name,
                        "parameters": {},
                    },
                },
            )
        ],
        max_chars=4_096,
        max_items=1,
        max_string_chars=768,
    )


def test_evaluate_context_result_requires_expected_tool() -> None:
    result = verify_rag.evaluate_context_result(
        _encoded_tool_context("get_dataset_info"),
        expected_tool="get_dataset_info",
    )

    assert result == {
        "ok": True,
        "expected_tool": "get_dataset_info",
        "observed_tool": "get_dataset_info",
        "item_count": 1,
    }


def test_evaluate_context_result_rejects_empty_or_wrong_context() -> None:
    assert (
        verify_rag.evaluate_context_result(
            "",
            expected_tool="start_training",
        )["ok"]
        is False
    )
    assert (
        verify_rag.evaluate_context_result(
            _encoded_tool_context("get_dataset_info"),
            expected_tool="start_training",
        )["ok"]
        is False
    )


def test_strict_main_returns_failure_for_failed_report(capsys) -> None:
    failed = {
        "ok": False,
        "checks": [{"name": "embedding_cache", "ok": False}],
    }

    with patch.object(verify_rag, "run_verification", return_value=failed):
        exit_code = verify_rag.main(["--format", "json", "--strict"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_main_writes_the_same_json_artifact(tmp_path: Path, capsys) -> None:
    passed = {
        "ok": True,
        "checks": [{"name": "embedding_cache", "ok": True}],
    }
    artifact_path = tmp_path / "rag-verification.json"

    with patch.object(verify_rag, "run_verification", return_value=passed):
        exit_code = verify_rag.main(
            [
                "--format",
                "json",
                "--strict",
                "--write-artifact",
                "--artifact-path",
                str(artifact_path),
            ]
        )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == passed
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == passed


def test_json_output_is_not_polluted_by_rag_runtime_logs(capsys) -> None:
    passed = {
        "ok": True,
        "checks": [{"name": "retriever_initialized", "ok": True}],
    }

    child_logger = logging.getLogger("XBrainLab.llm.rag.retriever")
    child_logger.setLevel(logging.NOTSET)
    emitted = io.StringIO()
    handler = logging.StreamHandler(emitted)
    child_logger.addHandler(handler)

    def run_with_error_log():
        child_logger.error("synthetic runtime diagnostic")
        return passed

    try:
        with patch.object(
            verify_rag,
            "run_verification",
            side_effect=run_with_error_log,
        ):
            assert verify_rag.main(["--format", "json", "--strict"]) == 0
    finally:
        child_logger.removeHandler(handler)
        handler.close()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == passed
    assert "synthetic runtime diagnostic" not in captured.out
    assert emitted.getvalue() == ""
