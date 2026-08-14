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


def test_poetry_dependencies_pin_numpy2_and_partner_integrations() -> None:
    pyproject = loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    assert "langchain" not in dependencies
    assert "langchain-community" not in dependencies
    assert "moabb" not in dependencies
    assert dependencies["numpy"] == ">=2.0,<3"
    assert dependencies["langchain-core"] == "1.3.3"
    assert dependencies["langchain-huggingface"] == "1.1.0"
    assert dependencies["langchain-qdrant"] == "1.1.0"

    lock = loads((REPO_ROOT / "poetry.lock").read_text(encoding="utf-8"))
    versions = {package["name"]: package["version"] for package in lock["package"]}
    assert versions["langchain-core"] == "1.3.3"
    assert versions["langchain-huggingface"] == "1.1.0"
    assert versions["langchain-qdrant"] == "1.1.0"


def test_product_foundation_excludes_campaign_runtime_dependencies() -> None:
    pyproject = loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    dev_dependencies = pyproject["tool"]["poetry"]["group"]["dev"]["dependencies"]
    campaign_packages = {
        "bids-validator-deno",
        "edfio",
        "edflib-python",
        "eeglabio",
        "mne-bids",
        "moabb",
        "pybv",
        "pyxdf",
    }

    assert campaign_packages.isdisjoint(dependencies)
    assert campaign_packages.isdisjoint(dev_dependencies)

    registry_source = (
        REPO_ROOT / "scripts" / "dev" / "handoff_gate_spec.py"
    ).read_text(encoding="utf-8")
    assert "moabb-15-delivery-validation" not in registry_source
