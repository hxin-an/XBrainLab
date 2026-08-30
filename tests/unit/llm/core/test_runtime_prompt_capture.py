"""Developer-only exact prompt capture at the local generation boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.generation import ResolvedGenerationOptions
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID, local_model_spec


class _Inputs(dict):
    def to(self, _device: str):
        return self


class _Tokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        prompt = "".join(f"<{item['role']}>{item['content']}" for item in messages)
        if add_generation_prompt:
            prompt += "<assistant>"
        return list(range(len(prompt))) if tokenize else prompt

    def __call__(self, prompt, *, return_tensors, add_special_tokens):
        assert return_tensors == "pt"
        assert add_special_tokens is False
        return _Inputs(input_ids=prompt.encode("utf-8"))


class _Streamer:
    def __iter__(self):
        return iter(("raw ", "output"))

    def end(self):
        return None


class _ImmediateThread:
    def __init__(self, target, **_kwargs):
        self._target = target

    def start(self):
        self._target()

    def join(self):
        return None


def _backend() -> LocalBackend:
    backend = LocalBackend(
        SimpleNamespace(model_name=PRIMARY_LOCAL_MODEL_ID, device="cpu")
    )
    model = MagicMock()
    model.device = "cpu"
    backend.is_loaded = True
    backend.model = model
    backend.tokenizer = _Tokenizer()
    return backend


def test_enabled_capture_persists_exact_fitted_prompt_raw_output_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture_dir = tmp_path / "assistant-runtime-prompts"
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(capture_dir))
    backend = _backend()
    options = ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)

    with (
        patch.dict(
            "sys.modules",
            {
                "transformers": MagicMock(
                    TextIteratorStreamer=MagicMock(return_value=_Streamer())
                )
            },
        ),
        patch("XBrainLab.llm.core.backends.local.Thread", _ImmediateThread),
    ):
        assert list(
            backend.generate_stream(
                [{"role": "user", "content": "hello"}], options=options
            )
        ) == ["raw ", "output"]

    captures = list(capture_dir.glob("*/*"))
    assert len(captures) == 1
    artifact_dir = captures[0]
    prompt = "<user>hello<assistant>"
    raw_output = "raw output"
    assert (artifact_dir / "prompt.txt").read_text(encoding="utf-8") == prompt
    assert (artifact_dir / "raw-output.txt").read_text(encoding="utf-8") == raw_output
    metadata = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    spec = local_model_spec(PRIMARY_LOCAL_MODEL_ID)
    assert spec is not None
    assert metadata == {
        "model": {"id": spec.repo_id, "revision": spec.revision},
        "options": {
            "do_sample": False,
            "max_new_tokens": 128,
            "temperature": None,
            "top_p": None,
        },
        "prompt_bytes": len(prompt.encode("utf-8")),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "raw_output_bytes": len(raw_output.encode("utf-8")),
        "raw_output_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        "sequence": 1,
        "session_id": metadata["session_id"],
        "status": "completed",
    }


def _generate(backend: LocalBackend, options: ResolvedGenerationOptions) -> list[str]:
    with (
        patch.dict(
            "sys.modules",
            {
                "transformers": MagicMock(
                    TextIteratorStreamer=MagicMock(return_value=_Streamer())
                )
            },
        ),
        patch("XBrainLab.llm.core.backends.local.Thread", _ImmediateThread),
    ):
        return list(
            backend.generate_stream(
                [{"role": "user", "content": "hello"}], options=options
            )
        )


def test_disabled_capture_performs_no_capture_filesystem_work(monkeypatch) -> None:
    monkeypatch.delenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", raising=False)
    backend = _backend()
    with patch(
        "XBrainLab.llm.core.backends.local.Path.mkdir", side_effect=AssertionError
    ):
        assert _generate(
            backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
        ) == ["raw ", "output"]


def test_capture_uses_one_child_session_and_monotonic_sequence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    options = ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
    assert _generate(backend, options) == ["raw ", "output"]
    assert _generate(backend, options) == ["raw ", "output"]
    captures = sorted(tmp_path.glob("*/*"), key=lambda path: int(path.name))
    assert [
        json.loads((item / "metadata.json").read_text())["sequence"]
        for item in captures
    ] == [1, 2]
    assert len({item.parent.name for item in captures}) == 1


def test_capture_writes_prepared_metadata_before_model_generation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    observed_statuses: list[str] = []

    def _observe_prepared(**_kwargs) -> None:
        artifact = next(tmp_path.glob("*/*"))
        observed_statuses.append(
            json.loads((artifact / "metadata.json").read_text())["status"]
        )

    backend.model.generate.side_effect = _observe_prepared
    assert _generate(
        backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
    ) == ["raw ", "output"]
    assert observed_statuses == ["prepared"]


def test_capture_marks_consumer_close_cancelled_and_keeps_yielded_raw_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    with (
        patch.dict(
            "sys.modules",
            {
                "transformers": MagicMock(
                    TextIteratorStreamer=MagicMock(return_value=_Streamer())
                )
            },
        ),
        patch("XBrainLab.llm.core.backends.local.Thread", _ImmediateThread),
    ):
        stream = backend.generate_stream(
            [{"role": "user", "content": "hello"}],
            options=ResolvedGenerationOptions(max_new_tokens=128, do_sample=False),
        )
        assert next(stream) == "raw "
        stream.close()
    artifact = next(tmp_path.glob("*/*"))
    assert (artifact / "raw-output.txt").read_text() == "raw "
    assert json.loads((artifact / "metadata.json").read_text())["status"] == "cancelled"


def test_capture_marks_model_failure_without_swallowing_inference_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    backend.model.generate.side_effect = ValueError("private failure")
    with pytest.raises(RuntimeError, match="Local generation failed"):
        _generate(
            backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
        )
    artifact = next(tmp_path.glob("*/*"))
    assert json.loads((artifact / "metadata.json").read_text())["status"] == "failed"


def test_capture_finalizes_failed_when_tokenization_fails_after_preparation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    tokenizer = MagicMock(wraps=backend.tokenizer)
    tokenizer.side_effect = OSError("private tokenizer path")
    backend.tokenizer = tokenizer
    with pytest.raises(OSError, match="private tokenizer path"):
        _generate(
            backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
        )
    artifact = next(tmp_path.glob("*/*"))
    assert json.loads((artifact / "metadata.json").read_text())["status"] == "failed"


def test_capture_finalizes_cancelled_before_generation_thread_starts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path))
    backend = _backend()
    original_start = backend._start_prompt_capture

    def _capture_then_cancel(*args, **kwargs):
        result = original_start(*args, **kwargs)
        assert backend._active_generation is not None
        backend._active_generation.cancel_event.set()
        return result

    with patch.object(
        backend, "_start_prompt_capture", side_effect=_capture_then_cancel
    ):
        assert (
            _generate(
                backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
            )
            == []
        )
    artifact = next(tmp_path.glob("*/*"))
    assert json.loads((artifact / "metadata.json").read_text())["status"] == "cancelled"


def test_invalid_or_writer_failure_capture_is_nonblocking_and_redacted(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    backend = _backend()
    options = ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
    monkeypatch.setenv(
        "XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", "relative/private/path"
    )
    assert _generate(backend, options) == ["raw ", "output"]
    monkeypatch.setenv(
        "XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(tmp_path / "private")
    )
    with patch.object(
        backend, "_write_capture_file", side_effect=OSError("secret path")
    ):
        assert _generate(backend, options) == ["raw ", "output"]
    assert "relative/private/path" not in caplog.text
    assert "secret path" not in caplog.text


def test_capture_finalization_writer_failure_is_nonblocking_and_redacted(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    capture_dir = tmp_path / "private-capture-root"
    monkeypatch.setenv("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", str(capture_dir))
    backend = _backend()
    original_writer = backend._write_capture_file
    written_paths: list[Path] = []

    def _fail_only_after_prepared(path: Path, content: str) -> None:
        if len(written_paths) >= 3:
            raise OSError("/private/finalize-path should not leak")
        written_paths.append(path)
        original_writer(path, content)

    with patch.object(
        backend, "_write_capture_file", side_effect=_fail_only_after_prepared
    ):
        assert _generate(
            backend, ResolvedGenerationOptions(max_new_tokens=128, do_sample=False)
        ) == ["raw ", "output"]

    assert [path.name for path in written_paths] == [
        "prompt.txt",
        "raw-output.txt",
        "metadata.json",
    ]
    artifact = next(capture_dir.glob("*/*"))
    assert (artifact / "prompt.txt").read_text(encoding="utf-8") == (
        "<user>hello<assistant>"
    )
    assert (artifact / "raw-output.txt").read_text(encoding="utf-8") == ""
    assert (
        json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))["status"]
        == "prepared"
    )
    assert "/private/finalize-path" not in caplog.text
    assert "hello" not in caplog.text
    assert "raw output" not in caplog.text
