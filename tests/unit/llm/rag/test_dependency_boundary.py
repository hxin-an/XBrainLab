from pathlib import Path
from tomllib import loads

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[4]


def _main_dependency_names(pyproject: dict[str, object]) -> set[str]:
    project = pyproject["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)
    return {Requirement(raw).name for raw in dependencies}


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
    dependency_names = _main_dependency_names(pyproject)
    dependencies = set(pyproject["project"]["dependencies"])
    assert "langchain" not in dependency_names
    assert "langchain-community" not in dependency_names
    assert "moabb" not in dependency_names
    assert "numpy (>=2.0,<3)" in dependencies
    assert "langchain-core (==1.3.3)" in dependencies
    assert "langchain-huggingface (==1.1.0)" in dependencies
    assert "langchain-qdrant (==1.1.0)" in dependencies

    lock = loads((REPO_ROOT / "poetry.lock").read_text(encoding="utf-8"))
    versions = {package["name"]: package["version"] for package in lock["package"]}
    assert versions["langchain-core"] == "1.3.3"
    assert versions["langchain-huggingface"] == "1.1.0"
    assert versions["langchain-qdrant"] == "1.1.0"


def test_windows_pytorch_variants_use_mutually_exclusive_explicit_sources() -> None:
    pyproject = loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    base_versions = {
        "torch": "2.11.0",
        "torchvision": "0.26.0",
        "torchaudio": "2.11.0",
    }

    assert project["requires-python"] == ">=3.11,<3.13"
    assert "dynamic" not in project
    assert pyproject["tool"]["poetry"]["requires-poetry"] == ">=2.3,<3"
    for name, version in base_versions.items():
        assert f"{name} (=={version})" in project["dependencies"]
    assert project["optional-dependencies"]["cpu"] == [
        f"{name} (=={version}+cpu) ; sys_platform == 'win32'"
        for name, version in base_versions.items()
    ]
    assert project["optional-dependencies"]["cuda"] == [
        f"{name} (=={version}+cu130) ; sys_platform == 'win32'"
        for name, version in base_versions.items()
    ]
    assert pyproject["tool"]["poetry"]["source"] == [
        {
            "name": "pytorch-cpu",
            "url": "https://download.pytorch.org/whl/cpu",
            "priority": "explicit",
        },
        {
            "name": "pytorch-cu130",
            "url": "https://download.pytorch.org/whl/cu130",
            "priority": "explicit",
        },
    ]

    for name in base_versions:
        non_windows, windows_cpu, windows_cuda = dependencies[name]
        assert non_windows == {
            "markers": "sys_platform != 'win32'",
        }
        assert windows_cpu == {
            "markers": (
                "sys_platform == 'win32' and extra == 'cpu' and extra != 'cuda'"
            ),
            "source": "pytorch-cpu",
        }
        assert windows_cuda == {
            "markers": (
                "sys_platform == 'win32' and extra == 'cuda' and extra != 'cpu'"
            ),
            "source": "pytorch-cu130",
        }

    lock = loads((REPO_ROOT / "poetry.lock").read_text(encoding="utf-8"))
    locked_variants: dict[str, set[tuple[str, str | None]]] = {
        name: set() for name in base_versions
    }
    for package in lock["package"]:
        name = package["name"]
        if name not in locked_variants:
            continue
        source = package.get("source")
        source_reference = source.get("reference") if source else None
        locked_variants[name].add((package["version"], source_reference))

    for name, base_version in base_versions.items():
        assert locked_variants[name] == {
            (base_version, None),
            (f"{base_version}+cpu", "pytorch-cpu"),
            (f"{base_version}+cu130", "pytorch-cu130"),
        }

    ci_source = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert 'POETRY_INSTALLER_RE_RESOLVE: "true"' in ci_source
    sync_lines = [
        line.strip()
        for line in ci_source.splitlines()
        if "run: poetry sync --no-interaction" in line
    ]
    assert sync_lines
    assert all(line.endswith("-E cpu") for line in sync_lines)

    pre_commit_source = (REPO_ROOT / ".pre-commit-config.yaml").read_text(
        encoding="utf-8"
    )
    assert "https://github.com/python-poetry/poetry" in pre_commit_source
    assert "rev: 2.3.4" in pre_commit_source


def test_product_foundation_excludes_campaign_runtime_dependencies() -> None:
    pyproject = loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = _main_dependency_names(pyproject)
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
