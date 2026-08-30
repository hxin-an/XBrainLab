"""Developer prompt-export contract tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.dev.export_assistant_prompt import _source_identity, export_prompt_dossier
from XBrainLab.llm.core.backends.local import LocalBackend


def test_exporter_writes_exact_processed_and_rendered_prompt_without_model_load(
    tmp_path: Path,
) -> None:
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.side_effect = (
        lambda messages, *, tokenize, add_generation_prompt: (
            [101, 102, 103]
            if tokenize
            else "<rendered>" + "|".join(item["role"] for item in messages)
        )
    )
    tokenizer.encode.return_value = [101, 102, 103]
    output = tmp_path / "missing-bandpass.md"

    with (
        patch(
            "scripts.dev.export_assistant_prompt._load_pinned_tokenizer",
            return_value=tokenizer,
        ) as load_tokenizer,
        patch(
            "XBrainLab.llm.core.backends.local.LocalBackend.load",
            autospec=True,
        ) as load_model,
        patch.object(
            LocalBackend,
            "_fit_prompt_to_runtime_context",
            autospec=True,
            return_value="<fitted>system|user|assistant|user",
        ) as fit_prompt,
    ):
        dossier = export_prompt_dossier("missing_bandpass_en", output)

    rendered = output.read_text(encoding="utf-8")
    assert load_tokenizer.call_count == 1
    load_model.assert_not_called()
    assert dossier["case_id"] == "missing_bandpass_en"
    assert dossier["model"]["id"] == "ibm-granite/granite-4.0-micro"
    assert dossier["final_prompt"]["token_count"] == 3
    assert dossier["final_prompt"]["content"] == "<fitted>system|user|assistant|user"
    assert fit_prompt.call_args.kwargs["max_input_tokens"] == 7_680
    assert "## Raw messages" in rendered
    assert "## Processed messages" in rendered
    assert "## Final rendered prompt" in rendered
    assert "<fitted>system|user|assistant|user" in rendered


def test_source_identity_marks_uncommitted_prompt_changes_as_dirty() -> None:
    with (
        patch(
            "scripts.dev.export_assistant_prompt.shutil.which",
            return_value="/usr/bin/git",
        ),
        patch(
            "scripts.dev.export_assistant_prompt.subprocess.check_output",
            side_effect=["abc123\n", " M scripts/dev/export_assistant_prompt.py\n"],
        ),
    ):
        identity = _source_identity()

    assert identity == {
        "head_sha": "abc123",
        "clean_except_protected_settings": False,
        "changes_excluding_protected_settings": [
            " M scripts/dev/export_assistant_prompt.py"
        ],
    }
