"""Developer prompt-export contract tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.dev.export_assistant_prompt import export_prompt_dossier


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
    ):
        dossier = export_prompt_dossier("missing_bandpass_en", output)

    rendered = output.read_text(encoding="utf-8")
    assert load_tokenizer.call_count == 1
    load_model.assert_not_called()
    assert dossier["case_id"] == "missing_bandpass_en"
    assert dossier["model"]["id"] == "ibm-granite/granite-4.0-micro"
    assert dossier["final_prompt"]["token_count"] == 3
    assert "## Raw messages" in rendered
    assert "## Processed messages" in rendered
    assert "## Final rendered prompt" in rendered
    assert "<rendered>system|user|assistant|user" in rendered
