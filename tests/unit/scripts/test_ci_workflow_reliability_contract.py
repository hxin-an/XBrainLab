from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCS_WORKFLOW = ROOT / ".github" / "workflows" / "docs-pages.yml"

ACTION_PINS = {
    # Public GitHub Action commit pins, not credentials.
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",  # pragma: allowlist secret
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",  # pragma: allowlist secret
    "actions/cache": "0057852bfaa89a56745cba8c7296529d2fc39830",  # pragma: allowlist secret
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",  # pragma: allowlist secret
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",  # pragma: allowlist secret
    "actions/configure-pages": "983d7736d9b0ae728b81ab479565c72886d7745b",  # pragma: allowlist secret
    "actions/upload-pages-artifact": "56afc609e74202658d3ffba0e8f6dda462b719fa",  # pragma: allowlist secret
    "actions/deploy-pages": "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",  # pragma: allowlist secret
}


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", ())]


def test_all_official_actions_are_pinned_to_reviewed_immutable_shas() -> None:
    observed: set[str] = set()
    for path in (CI_WORKFLOW, DOCS_WORKFLOW):
        for step in _steps(_workflow(path)):
            reference = step.get("uses")
            if not isinstance(reference, str) or not reference.startswith("actions/"):
                continue
            owner, sha = reference.split("@", 1)
            assert sha == ACTION_PINS[owner]
            observed.add(owner)

    assert observed == set(ACTION_PINS)


def test_ci_poetry_bootstrap_and_venv_cache_are_lock_exact() -> None:
    workflow = _workflow(CI_WORKFLOW)
    assert workflow["env"] == {
        "POETRY_VERSION": "2.3.4",
        "CI_PYTHON_VERSION": "3.11",
    }
    steps = _steps(workflow)
    poetry_installers = [step for step in steps if step.get("name") == "Install Poetry"]
    dependency_installers = [
        step
        for step in steps
        if step.get("name") == "Install dependencies"
        and str(step.get("run", "")).startswith("poetry ")
    ]
    assert len(poetry_installers) == 8
    assert all(
        'python -m pip install "poetry==${POETRY_VERSION}"' in step["run"]
        for step in poetry_installers
    )
    assert len(dependency_installers) == 8
    windows_cpu_sync = (
        "poetry sync --no-interaction ${{ runner.os == 'Windows' && '-E cpu' || '' }}"
    )
    platform_resolver = "${{ runner.os == 'Windows' && 'true' || 'false' }}"
    assert all(step["run"] == windows_cpu_sync for step in dependency_installers)
    assert all(
        step.get("env") == {"POETRY_INSTALLER_RE_RESOLVE": platform_resolver}
        for step in dependency_installers
    )

    venv_cache_steps = [
        step for step in steps if str(step.get("with", {}).get("path", "")) == ".venv"
    ]
    assert len(venv_cache_steps) == 8
    for step in venv_cache_steps:
        cache = step["with"]
        assert "restore-keys" not in cache
        key = cache["key"]
        assert "${{ runner.os }}-${{ runner.arch }}" in key
        assert (
            "py${{ env.CI_PYTHON_VERSION }}" in key or "py${{ matrix.python }}" in key
        )
        assert "poetry-${{ env.POETRY_VERSION }}" in key
        assert "${{ hashFiles('poetry.lock') }}" in key

    for job_key, job in workflow["jobs"].items():
        job_steps = job.get("steps", ())
        if not any(step in venv_cache_steps for step in job_steps):
            continue
        setup_python = next(
            step
            for step in job_steps
            if str(step.get("uses", "")).startswith("actions/setup-python@")
        )
        expected_python = (
            "${{ matrix.python }}"
            if job_key == "native-platform-source"
            else "${{ env.CI_PYTHON_VERSION }}"
        )
        assert setup_python["with"]["python-version"] == expected_python
        cache_step = next(step for step in job_steps if step in venv_cache_steps)
        assert f"py{expected_python}" in cache_step["with"]["key"]

    workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert 'pip install "coverage>=7,<8" pytest' not in workflow_text
    assert "poetry run -- coverage combine test-results" in workflow_text


def test_public_fixture_cache_does_not_restore_a_stale_manifest() -> None:
    steps = _steps(_workflow(CI_WORKFLOW))
    fixture_cache = next(
        step for step in steps if step.get("name") == "Cache pinned public EEG fixtures"
    )
    assert "restore-keys" not in fixture_cache["with"]


def test_native_platform_source_matrix_is_finite_native_and_required() -> None:
    workflow = _workflow(CI_WORKFLOW)
    job = workflow["jobs"]["native-platform-source"]
    assert "QT_QPA_PLATFORM" not in job.get("env", {})
    assert job["strategy"]["matrix"]["include"] == [
        {
            "key": "windows-product-py311",
            "os": "windows-latest",
            "python": "3.11",
            "mode": "product",
            "artifact_type": "xbrainlab.native_platform_product_smoke",
            "qt_platform": "windows",
            "runner_os": "Windows",
            "panel_timeout_ms": 20_000,
        },
        {
            "key": "windows-startup-py312",
            "os": "windows-latest",
            "python": "3.12",
            "mode": "startup",
            "artifact_type": "xbrainlab.startup_smoke",
            "qt_platform": "windows",
            "runner_os": "Windows",
        },
        {
            "key": "macos-product-py311",
            "os": "macos-latest",
            "python": "3.11",
            "mode": "product",
            "artifact_type": "xbrainlab.native_platform_product_smoke",
            "qt_platform": "cocoa",
            "runner_os": "macOS",
            "panel_timeout_ms": 45_000,
        },
    ]

    steps = job["steps"]
    assert any(step.get("name") == "Prepare isolated native paths" for step in steps)
    verification = next(
        step for step in steps if step.get("name") == "Verify required native evidence"
    )
    assert "verify_native_ci_evidence.py" in verification["run"]
    assert "--expected-job-key ${{ matrix.key }}" in verification["run"]
    assert "--expected-runner-os ${{ matrix.runner_os }}" in verification["run"]
    assert "--expected-artifact-type ${{ matrix.artifact_type }}" in verification["run"]
    assert "--expected-platform ${{ matrix.qt_platform }}" in verification["run"]
    assert '--expected-isolated-root "${XBL_NATIVE_ROOT}"' in verification["run"]
    assert verification["if"] == "always()"
    upload = next(
        step for step in steps if step.get("name") == "Upload required native evidence"
    )
    assert upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "native-platform-smoke.json" in upload["with"]["path"]
    assert "ci-source-provenance.json" in upload["with"]["path"]

    product_probe = next(
        step
        for step in steps
        if step.get("name") == "Run native MainWindow product lifecycle"
    )
    assert "--panel-timeout-ms ${{ matrix.panel_timeout_ms }}" in product_probe["run"]


def test_native_source_probes_require_platform_and_isolated_root() -> None:
    steps = _workflow(CI_WORKFLOW)["jobs"]["native-platform-source"]["steps"]
    probes = [
        step
        for step in steps
        if step.get("name")
        in {
            "Run native MainWindow product lifecycle",
            "Run native entrypoint startup lifecycle",
        }
    ]
    assert len(probes) == 2
    for probe in probes:
        assert "--expected-platform ${{ matrix.qt_platform }}" in probe["run"]
        assert '--expected-isolated-root "${XBL_NATIVE_ROOT}"' in probe["run"]
        assert "QT_QPA_PLATFORM" not in probe.get("env", {})


def test_authoritative_ci_artifacts_fail_closed_and_include_provenance() -> None:
    workflow = _workflow(CI_WORKFLOW)
    required_uploads = {
        "linux-shard": (
            "Upload shard evidence",
            "Upload source provenance sidecar",
        ),
        "linux-test": ("Upload aggregate Linux evidence",),
        "human-like-product": ("Upload human-like product evidence",),
        "platform-test": ("Upload test results",),
        "native-platform-source": ("Upload required native evidence",),
        "ui-default-visual": ("Upload default-scale UI evidence",),
        "ui-windows-dpi": ("Upload Windows DPI evidence",),
        "public-dataset-gate": ("Upload public dataset gate reports",),
    }
    for job_key, upload_names in required_uploads.items():
        steps = workflow["jobs"][job_key]["steps"]
        for name in upload_names:
            upload = next(step for step in steps if step.get("name") == name)
            assert upload["with"]["if-no-files-found"] == "error"

    provenance_jobs = {
        "linux-shard",
        "linux-test",
        "human-like-product",
        "platform-test",
        "native-platform-source",
        "ui-default-visual",
        "ui-windows-dpi",
        "public-dataset-gate",
    }
    for job_key in provenance_jobs:
        steps = workflow["jobs"][job_key]["steps"]
        recorders = [
            step
            for step in steps
            if step.get("name")
            in {
                "Record exact source provenance",
                "Record aggregate checkout provenance",
            }
        ]
        assert recorders, job_key
        assert all("ci_source_provenance.py" in step["run"] for step in recorders)

    assert (
        "test-results/ci-source-provenance.json"
        in next(
            step
            for step in workflow["jobs"]["platform-test"]["steps"]
            if step.get("name") == "Upload test results"
        )["with"]["path"]
    )


def test_multifile_authoritative_jobs_verify_every_primary_result_before_upload() -> (
    None
):
    jobs = _workflow(CI_WORKFLOW)["jobs"]
    expected = {
        "human-like-product": (
            "Verify required human-like evidence",
            (("human-like", "human-like-walkthrough.json"),),
        ),
        "platform-test": (
            "Verify required platform evidence",
            (("sharded-pytest", "test-results/${{ matrix.command }}.json"),),
        ),
        "ui-default-visual": (
            "Verify required default-scale UI evidence",
            (("ui-baseline", "ui-baseline-evidence.json"),),
        ),
        "ui-windows-dpi": (
            "Verify required Windows DPI evidence",
            (("windows-dpi", "dpi-gate.json"),),
        ),
        "public-dataset-gate": (
            "Verify required public dataset evidence",
            (
                ("dataset-validation", "dataset-validation-matrix.json"),
                (
                    "data-interpretation-format",
                    "data-interpretation-format-matrix.json",
                ),
                ("public-cross-source", "public-cross-source-smoke.json"),
                ("required-pytest", "public-bids-visible-ui.json"),
                ("required-pytest", "required-public-io.json"),
            ),
        ),
    }
    for job_key, (step_name, required_artifacts) in expected.items():
        step = next(
            item for item in jobs[job_key]["steps"] if item.get("name") == step_name
        )
        assert "verify_required_ci_artifacts.py" in step["run"]
        assert "--provenance" in step["run"]
        assert "--expected-job-key" in step["run"]
        assert "--expected-github-job" in step["run"]
        assert "--expected-runner-os" in step["run"]
        for contract, path in required_artifacts:
            assert "--required-artifact" in step["run"]
            assert f"--required-artifact {contract}=" in step["run"]
            assert path in step["run"]
    assert (
        "test-results/ci-source-provenance.json"
        in next(
            step
            for step in jobs["public-dataset-gate"]["steps"]
            if step.get("name") == "Upload public dataset gate reports"
        )["with"]["path"]
    )
