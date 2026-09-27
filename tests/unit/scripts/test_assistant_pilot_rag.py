"""Filesystem isolation and identity checks without embedding/model loading."""

import os
from pathlib import Path

import pytest

from scripts.dev.assistant_pilot_rag import prepare_rag_cache, verify_rag_cache
from XBrainLab.llm.rag.config import RAGConfig


@pytest.fixture
def embeddings(tmp_path):
    root = tmp_path / "shared" / "models"
    snapshot = RAGConfig.embedding_snapshot_path(root)
    for relative in (
        *RAGConfig._REQUIRED_SNAPSHOT_FILES,
        "model.safetensors",
        "tokenizer.json",
    ):
        path = snapshot / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture contents " + relative.encode())
    return root


def test_isolated_vectors_share_model_files_without_environment_mutation(
    tmp_path, embeddings
):
    before_env = dict(os.environ)
    result = prepare_rag_cache(tmp_path / "run-rag", embedding_cache=embeddings)
    assert dict(os.environ) == before_env
    assert result["runtime_ready"] is False
    root = Path(result["cache_root"])
    assert (root / "models").samefile(embeddings)
    assert RAGConfig.embedding_cache_ready(root / "models")
    assert (root / "vectors").is_dir()
    assert not (root / "vectors").is_symlink()
    assert not (embeddings.parent / "vectors").exists()
    assert result["environment"] == {RAGConfig.CACHE_DIR_ENV: str(root)}
    assert verify_rag_cache(result) is True


def test_existing_destination_and_missing_source_do_not_write(tmp_path, embeddings):
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        prepare_rag_cache(existing, embedding_cache=embeddings)
    assert (existing / "keep").read_text() == "keep"
    with pytest.raises((FileNotFoundError, ValueError)):
        prepare_rag_cache(tmp_path / "new", embedding_cache=tmp_path / "missing")
    assert not (tmp_path / "new").exists()


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "nt", reason="Windows junction compatibility")
def test_cache_isolation_without_python312_junction_method(
    tmp_path, embeddings, monkeypatch
):
    def unavailable(_path):
        raise AttributeError("Path.is_junction is absent on Python 3.11")

    monkeypatch.setattr(Path, "is_junction", unavailable, raising=False)
    result = prepare_rag_cache(tmp_path / "run", embedding_cache=embeddings)
    assert (Path(result["cache_root"]) / "models").samefile(embeddings)
    assert verify_rag_cache(result) is True
    vectors = Path(result["cache_root"]) / "vectors"
    vectors.rmdir()
    from scripts.dev.assistant_pilot_rag import _link_directory

    _link_directory(embeddings, vectors)
    with pytest.raises(ValueError, match="vectors"):
        verify_rag_cache(result)


def test_source_overlap_and_identity_mismatch_fail_before_writes(tmp_path, embeddings):
    with pytest.raises(ValueError, match="overlap"):
        prepare_rag_cache(embeddings / "run", embedding_cache=embeddings)
    with pytest.raises(ValueError, match="identity"):
        prepare_rag_cache(
            tmp_path / "new",
            embedding_cache=embeddings,
            expected_embedding_sha256="0" * 64,
        )
    assert not (embeddings / "run").exists()
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("new_file", [False, True])
def test_changed_weights_and_new_files_fail_verification(
    tmp_path, embeddings, new_file
):
    result = prepare_rag_cache(tmp_path / "run", embedding_cache=embeddings)
    weight = RAGConfig.embedding_snapshot_path(embeddings) / (
        "new.json" if new_file else "model.safetensors"
    )
    weight.write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity"):
        verify_rag_cache(result)


def test_incomplete_snapshot_fails_before_destination_creation(tmp_path, embeddings):
    (RAGConfig.embedding_snapshot_path(embeddings) / "modules.json").unlink()
    with pytest.raises(ValueError, match="snapshot"):
        prepare_rag_cache(tmp_path / "new", embedding_cache=embeddings)
    assert not (tmp_path / "new").exists()


def test_missing_corpus_integrity_is_not_ready(tmp_path, embeddings, monkeypatch):
    monkeypatch.setattr(RAGConfig, "gold_set_integrity_ok", lambda: False)
    with pytest.raises(ValueError, match="corpus"):
        prepare_rag_cache(tmp_path / "new", embedding_cache=embeddings)
    assert not (tmp_path / "new").exists()


def test_vector_replacement_cannot_point_to_shared_data(tmp_path, embeddings):
    result = prepare_rag_cache(tmp_path / "run", embedding_cache=embeddings)
    vectors = Path(result["cache_root"]) / "vectors"
    vectors.rmdir()
    from scripts.dev.assistant_pilot_rag import _link_directory

    _link_directory(embeddings, vectors)
    with pytest.raises(ValueError, match="vectors"):
        verify_rag_cache(result)


def test_snapshot_directory_link_escape_fails_before_writes(tmp_path, embeddings):
    from scripts.dev.assistant_pilot_rag import _link_directory

    outside = tmp_path / "outside"
    outside.mkdir()
    _link_directory(outside, RAGConfig.embedding_snapshot_path(embeddings) / "extra")
    with pytest.raises(ValueError, match="escapes"):
        prepare_rag_cache(tmp_path / "run", embedding_cache=embeddings)
    assert not (tmp_path / "run").exists()
