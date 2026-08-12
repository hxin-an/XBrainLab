from pathlib import Path

from tomllib import loads

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_rag_uses_maintained_langchain_partner_packages() -> None:
    product_sources = [
        REPO_ROOT / "XBrainLab" / "llm" / "rag" / "indexer.py",
        REPO_ROOT / "XBrainLab" / "llm" / "rag" / "retriever.py",
    ]

    source = "\n".join(path.read_text(encoding="utf-8") for path in product_sources)

    assert "langchain_community" not in source
    assert "langchain.docstore" not in source
    assert "from langchain_huggingface import HuggingFaceEmbeddings" in source
    assert "from langchain_qdrant import Qdrant" in source
    assert "from langchain_core.documents import Document" in source


def test_poetry_lock_pins_numpy2_moabb_and_partner_integrations() -> None:
    pyproject = loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    assert "langchain" not in dependencies
    assert "langchain-community" not in dependencies
    assert dependencies["langchain-core"] == "1.3.3"
    assert dependencies["langchain-huggingface"] == "1.1.0"
    assert dependencies["langchain-qdrant"] == "1.1.0"
    assert dependencies["moabb"] == "1.5.0"

    lock = loads((REPO_ROOT / "poetry.lock").read_text(encoding="utf-8"))
    versions = {package["name"]: package["version"] for package in lock["package"]}
    assert versions["numpy"] == "2.5.2"
    assert versions["moabb"] == "1.5.0"
    assert versions["langchain-core"] == "1.3.3"
    assert versions["langchain-huggingface"] == "1.1.0"
    assert versions["langchain-qdrant"] == "1.1.0"
