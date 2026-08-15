"""Validate the isolated, user-facing XBrainLab documentation source."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.dev.user_site_evidence import (
    EvidencePublicationError,
    publish_capture_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "mkdocs.user.yml"
DOCS_DIR = ROOT / "user_docs"
CASE_DIR = DOCS_DIR / "case-studies"
MANIFEST_DIR = CASE_DIR / "manifests"
MOABB_SOURCE = (
    ROOT / "scripts" / "dev" / "moabb_user_journeys" / "data" / "moabb-datasets-v1.json"
)
MOABB_SITE_COPY = DOCS_DIR / "assets/manifests/moabb-datasets-v1.json"

MOABB_CASES = {
    "ofner2017-mi-gdf": {
        "case_id": "moabb-ofner2017",
        "page": "case-studies/moabb-ofner2017.md",
        "title": "Ofner2017 Motor Imagery",
    },
    "physionetmi-edf-run-semantics": {
        "case_id": "moabb-physionetmi",
        "page": "case-studies/moabb-physionetmi.md",
        "title": "PhysionetMI Run Semantics",
    },
    "lee2021mobile-erp-brainvision": {
        "case_id": "moabb-lee2021mobile-erp",
        "page": "case-studies/moabb-lee2021mobile-erp.md",
        "title": "Lee2021Mobile ERP",
    },
}

REQUIRED_PAGES = (
    "index.md",
    "getting-started.md",
    "workflow.md",
    "case-studies/index.md",
    "case-studies/graz-2a.md",
    "case-studies/openneuro-ds003061.md",
    "case-studies/moabb-ofner2017.md",
    "case-studies/moabb-physionetmi.md",
    "case-studies/moabb-lee2021mobile-erp.md",
    "faq-limits.md",
)

RUN_HEADINGS = (
    "Source and version",
    "App action",
    "Choices",
    "Expected checkpoint",
    "Stop condition",
    "Next step",
)

CASE_STAGES = (
    ("Source and dataset", "source_and_dataset"),
    ("Import scope", "import_scope"),
    ("Labels and metadata", "labels_and_metadata"),
    ("Preprocess", "preprocess"),
    ("Epoch", "epoch"),
    ("Split", "split"),
    ("Model and training", "model_and_training"),
    ("Evaluation", "evaluation"),
    ("Saliency", "saliency"),
    ("Reproducibility and limitations", "reproducibility_and_limitations"),
)

VALID_EVIDENCE_STATUS = {"observed", "bounded", "unverified"}
IDENTITY_FIELDS = (
    "manifest_id",
    "app_revision",
    "run_id",
    "dataset_revision",
)

FORBIDDEN_USER_TERMS = (
    "focused validation",
    "checked-in",
    "regression",
    "smoke test",
    "training smoke",
    "source guard",
    "pytest",
    "exact-head",
    "handoff gate",
    "2,245",
)

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_ASSET = re.compile(r"<(?:img|script)[^>]+src=[\"']([^\"']+)[\"']", re.I)
FULL_COMMIT = re.compile(r"[0-9a-f]{40}", re.I)
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")


def _fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def _read_yaml(path: Path, failures: list[str]) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _fail(f"cannot read {path.relative_to(ROOT)}: {exc}", failures)
        return {}
    if not isinstance(data, dict):
        _fail(f"{path.relative_to(ROOT)} must contain a mapping", failures)
        return {}
    return data


def _read_json(path: Path, failures: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read {path.relative_to(ROOT)}: {exc}", failures)
        return {}
    if not isinstance(data, dict):
        _fail(f"{path.relative_to(ROOT)} must contain an object", failures)
        return {}
    return data


def _source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _moabb_dataset_map(source: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    datasets = source.get("datasets")
    if not isinstance(datasets, list):
        _fail(f"{MOABB_SOURCE.relative_to(ROOT)} has no datasets array", failures)
        return {}
    by_id = {
        item.get("id"): item
        for item in datasets
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    missing = set(MOABB_CASES) - set(by_id)
    unexpected = set(by_id) - set(MOABB_CASES)
    if missing:
        _fail(f"MOABB source is missing required datasets: {sorted(missing)}", failures)
    if unexpected:
        _fail(f"MOABB source has unreviewed datasets: {sorted(unexpected)}", failures)
    return by_id


def _check_moabb_source(source: dict[str, Any], failures: list[str]) -> None:
    if source.get("schema_version") != "1.0.0":
        _fail("MOABB source must use schema_version 1.0.0", failures)
    if source.get("profile_id") != "moabb-compact-user-journeys-v1":
        _fail("MOABB source has an unexpected profile_id", failures)
    release = source.get("moabb_release")
    if not isinstance(release, dict) or not all(
        isinstance(release.get(field), str) and release[field].strip()
        for field in ("version", "commit", "repository")
    ):
        _fail("MOABB source has an incomplete release identity", failures)
    elif not FULL_COMMIT.fullmatch(release["commit"]):
        _fail("MOABB source release commit must be a full commit SHA", failures)
    _moabb_dataset_map(source, failures)


def _read_markdown(path: Path, failures: list[str]) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        _fail(f"{path.relative_to(ROOT)} must start with YAML front matter", failures)
        return {}, text
    try:
        _, raw_front_matter, body = text.split("---", 2)
        front_matter = yaml.safe_load(raw_front_matter)
    except (ValueError, yaml.YAMLError) as exc:
        _fail(f"invalid front matter in {path.relative_to(ROOT)}: {exc}", failures)
        return {}, text
    if not isinstance(front_matter, dict):
        _fail(f"front matter in {path.relative_to(ROOT)} must be a mapping", failures)
        return {}, body
    return front_matter, body


def _section(text: str, level: int, heading: str) -> str:
    marker = f"{'#' * level} {heading}"
    match = re.search(rf"^{re.escape(marker)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    remaining = text[match.end() :]
    next_heading = re.search(rf"^{'#' * level}\s+", remaining, re.MULTILINE)
    return remaining[: next_heading.start()] if next_heading else remaining


def _ordered_headings(text: str, level: int) -> list[str]:
    prefix = "#" * level
    return [
        line.removeprefix(f"{prefix} ").strip()
        for line in text.splitlines()
        if line.startswith(f"{prefix} ")
    ]


def _check_config(config: dict[str, Any], failures: list[str]) -> None:
    expected = {
        "docs_dir": "user_docs",
        "site_dir": "build/user-site",
        "strict": True,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            _fail(f"mkdocs.user.yml must set {key}: {value!r}", failures)

    excluded = str(config.get("exclude_docs", ""))
    for required in ("case-studies/_template.md", "case-studies/manifests/**"):
        if required not in excluded:
            _fail(f"mkdocs.user.yml must exclude {required}", failures)

    nav_text = str(config.get("nav", ""))
    for metadata in MOABB_CASES.values():
        if metadata["page"] not in nav_text:
            _fail(f"mkdocs.user.yml nav is missing {metadata['page']}", failures)


def _check_required_pages(failures: list[str]) -> None:
    for relative in REQUIRED_PAGES:
        if not (DOCS_DIR / relative).is_file():
            _fail(f"missing required user page: user_docs/{relative}", failures)

    for relative in (
        "case-studies/_template.md",
        "case-studies/manifests/_manifest-template.yml",
    ):
        if not (DOCS_DIR / relative).is_file():
            _fail(f"missing publication template: user_docs/{relative}", failures)


def _identity_complete(identity: Any) -> bool:
    if not isinstance(identity, dict):
        return False
    if not all(
        isinstance(identity.get(field), str) and identity[field].strip()
        for field in IDENTITY_FIELDS
    ):
        return False
    evidence_files = identity.get("evidence_files")
    return bool(
        isinstance(evidence_files, list)
        and evidence_files
        and all(isinstance(item, str) and item.strip() for item in evidence_files)
    )


def _check_evidence_file(
    reference: str, manifest_path: Path, failures: list[str]
) -> None:
    if "latest" in reference.lower():
        _fail(
            f"{manifest_path.relative_to(ROOT)} uses mutable evidence: {reference}",
            failures,
        )
        return
    if reference.startswith(("https://", "http://")):
        return
    target = (DOCS_DIR / reference).resolve()
    if not target.is_relative_to(DOCS_DIR.resolve()) or not target.is_file():
        _fail(
            f"{manifest_path.relative_to(ROOT)} has missing user-site evidence file: {reference}",
            failures,
        )


def _check_manifest_identity(
    manifest: dict[str, Any], manifest_path: Path, failures: list[str]
) -> bool:
    identity = manifest.get("identity")
    complete = _identity_complete(identity)
    status = manifest.get("publication_status")
    if status not in VALID_EVIDENCE_STATUS:
        _fail(
            f"{manifest_path.relative_to(ROOT)} has invalid publication_status",
            failures,
        )
    if status in {"observed", "bounded"} and not complete:
        _fail(
            f"{manifest_path.relative_to(ROOT)} promotes evidence without complete identity",
            failures,
        )
    if not complete:
        return False

    if not isinstance(identity, dict):
        return False
    app_revision = str(identity["app_revision"])
    if not FULL_COMMIT.fullmatch(app_revision):
        _fail(
            f"{manifest_path.relative_to(ROOT)} app_revision must be a full commit SHA",
            failures,
        )
    for field in ("manifest_id", "run_id"):
        if "latest" in str(identity[field]).lower():
            _fail(
                f"{manifest_path.relative_to(ROOT)} {field} must be immutable",
                failures,
            )
    for reference in identity["evidence_files"]:
        _check_evidence_file(reference, manifest_path, failures)
    return True


def _check_case_page(path: Path, failures: list[str]) -> Path | None:
    front_matter, body = _read_markdown(path, failures)
    relative_page = path.relative_to(DOCS_DIR).as_posix()
    case_id = front_matter.get("case_id")
    record_reference = front_matter.get("evidence_record")
    page_status = front_matter.get("publication_status")

    if not isinstance(case_id, str) or not case_id:
        _fail(f"{path.relative_to(ROOT)} has no case_id", failures)
    if not isinstance(record_reference, str) or not record_reference:
        _fail(f"{path.relative_to(ROOT)} has no evidence_record", failures)
        return None
    if page_status not in VALID_EVIDENCE_STATUS:
        _fail(f"{path.relative_to(ROOT)} has invalid publication_status", failures)

    record_path = (DOCS_DIR / record_reference).resolve()
    if (
        not record_path.is_relative_to(MANIFEST_DIR.resolve())
        or not record_path.is_file()
    ):
        _fail(f"{path.relative_to(ROOT)} has an invalid evidence_record", failures)
        return None

    manifest = _read_yaml(record_path, failures)
    if manifest.get("schema_version") != 1:
        _fail(f"{record_path.relative_to(ROOT)} must use schema_version 1", failures)
    if manifest.get("case_id") != case_id:
        _fail(
            f"{path.relative_to(ROOT)} and its evidence record disagree on case_id",
            failures,
        )
    if manifest.get("page") != relative_page:
        _fail(f"{record_path.relative_to(ROOT)} points to the wrong page", failures)
    if manifest.get("publication_status") != page_status:
        _fail(
            f"{path.relative_to(ROOT)} and its evidence record disagree on status",
            failures,
        )

    route = manifest.get("route")
    if not isinstance(route, dict) or not all(
        isinstance(route.get(field), str) and route[field].strip()
        for field in ("source", "source_version", "scope", "followable_through")
    ):
        _fail(
            f"{record_path.relative_to(ROOT)} has an incomplete route contract",
            failures,
        )

    run_section = _section(body, 2, "Run this dataset")
    if not run_section:
        _fail(f"{path.relative_to(ROOT)} has no Run this dataset section", failures)
    else:
        run_headings = _ordered_headings(run_section, 3)
        if run_headings[: len(RUN_HEADINGS)] != list(RUN_HEADINGS):
            _fail(f"{path.relative_to(ROOT)} has an incomplete run contract", failures)

    identity_complete = _check_manifest_identity(manifest, record_path, failures)
    identity_section = _section(body, 2, "Evidence identity")
    if not identity_section:
        _fail(
            f"{path.relative_to(ROOT)} has no user-facing evidence identity", failures
        )
    elif identity_complete:
        identity = manifest["identity"]
        identity_values = [str(identity[field]) for field in IDENTITY_FIELDS]
        identity_values.extend(str(item) for item in identity["evidence_files"])
        for value in identity_values:
            if value not in identity_section:
                _fail(
                    f"{path.relative_to(ROOT)} omits identity value from the page: {value}",
                    failures,
                )
    elif not all(
        marker in identity_section
        for marker in ("Unverified", "Not published", "None published")
    ):
        _fail(f"{path.relative_to(ROOT)} must show its incomplete identity", failures)

    evidence_section = _section(body, 2, "Evidence and limits")
    if not evidence_section:
        _fail(f"{path.relative_to(ROOT)} has no Evidence and limits section", failures)
        return record_path

    stage_headings = _ordered_headings(evidence_section, 3)
    expected_headings = [heading for heading, _ in CASE_STAGES]
    if stage_headings[: len(expected_headings)] != expected_headings:
        _fail(
            f"{path.relative_to(ROOT)} stage sections are missing or out of order",
            failures,
        )

    stages = manifest.get("stages")
    expected_keys = {key for _, key in CASE_STAGES}
    if not isinstance(stages, dict) or set(stages) != expected_keys:
        _fail(
            f"{record_path.relative_to(ROOT)} stage keys do not match the page contract",
            failures,
        )
        return record_path

    global_files = set(manifest.get("identity", {}).get("evidence_files", []))
    for heading, key in CASE_STAGES:
        stage = stages.get(key)
        if not isinstance(stage, dict):
            _fail(f"{record_path.relative_to(ROOT)} has invalid stage {key}", failures)
            continue
        stage_status = stage.get("status")
        stage_files = stage.get("evidence_files")
        if stage_status not in VALID_EVIDENCE_STATUS or not isinstance(
            stage_files, list
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} has invalid stage contract: {key}",
                failures,
            )
            continue
        if stage_status in {"observed", "bounded"}:
            if not identity_complete or not stage_files:
                _fail(
                    f"{record_path.relative_to(ROOT)} promotes {key} without identity and files",
                    failures,
                )
            if not set(stage_files).issubset(global_files):
                _fail(
                    f"{record_path.relative_to(ROOT)} {key} files are absent from identity",
                    failures,
                )
        elif stage_files:
            _fail(
                f"{record_path.relative_to(ROOT)} unverified {key} must have no files",
                failures,
            )

        page_stage = _section(evidence_section, 3, heading)
        expected_badge = f"evidence-badge--{stage_status}"
        if (
            expected_badge not in page_stage
            or str(stage_status).capitalize() not in page_stage
        ):
            _fail(
                f"{path.relative_to(ROOT)} badge disagrees for stage {heading}",
                failures,
            )

    if not identity_complete and any(
        badge in body
        for badge in ("evidence-badge--observed", "evidence-badge--bounded")
    ):
        _fail(f"{path.relative_to(ROOT)} promotes evidence without identity", failures)

    return record_path


def _code(value: Any) -> str:
    return f"`{str(value).replace('`', '')}`"


def _selection_scope(dataset: dict[str, Any]) -> str:
    selection = dataset["selection"]
    subjects = ", ".join(str(value) for value in selection["subjects"])
    sessions = ", ".join(str(value) for value in selection["sessions"])
    runs = ", ".join(str(value) for value in selection["runs"])
    return (
        f"Subject(s) {subjects}; session(s) {sessions}; run(s) {runs}; "
        f"{dataset['source_format']} source"
    )


def _mapping_lines(dataset: dict[str, Any]) -> list[str]:
    mappings = dataset["import"]["choices"]["run_event_mappings"]
    lines = []
    for run_name, mapping in mappings.items():
        pairs = ", ".join(f"{_code(code)} = {label}" for code, label in mapping.items())
        lines.append(f"{_code(run_name)}: {pairs}.")
    return lines


def _workflow_lines(dataset: dict[str, Any]) -> list[str]:
    workflow = dataset["workflow"]
    preprocessing = []
    for operation in workflow["preprocessing"]:
        if operation["operation"] == "bandpass":
            preprocessing.append(
                f"band-pass {_code(operation['low_freq'])} to "
                f"{_code(operation['high_freq'])} Hz"
            )
        else:
            preprocessing.append(str(operation["operation"]))
    epoch = workflow["epoch"]
    split = workflow["split"]
    training = workflow["training_profiles"]["showcase"]
    return [
        f"Preprocess: {', '.join(preprocessing)}.",
        (
            f"Epoch: {_code(epoch['t_min'])} to {_code(epoch['t_max'])} s, "
            f"baseline {_code(epoch['baseline'])}."
        ),
        (
            f"Split: {_code(split['test_ratio'])} test and {_code(split['val_ratio'])} "
            f"validation by {_code(split['split_strategy'])}; "
            f"{_code(split['training_mode'])} training."
        ),
        (
            f"Planned training: {_code(training['name'])} on {_code(training['device'])}, "
            f"up to {_code(training['epochs'])} epochs, batch {_code(training['batch_size'])}, "
            f"learning rate {_code(training['learning_rate'])}, "
            f"checkpoint choice {_code(training['evaluation_option'])}."
        ),
    ]


def _evidence_value(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return _code(value)
    return "Not published"


def _page_reference(reference: str) -> str:
    return f"../{reference}"


def _evidence_links(references: Any, *, from_case_page: bool = False) -> str:
    if not isinstance(references, list) or not references:
        return "None published"
    links = [
        _page_reference(reference) if from_case_page else reference
        for reference in references
    ]
    return "<br>".join(
        f"[{html.escape(reference)}]({link})"
        for reference, link in zip(references, links, strict=True)
    )


def _safe_text(value: Any) -> str:
    return html.escape(re.sub(r"\s+", " ", str(value)).strip())


def _metric_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _render_observed_metrics(record: dict[str, Any]) -> str:
    observations = record.get("observations", {})
    metrics = observations.get("metrics") if isinstance(observations, dict) else None
    if not isinstance(metrics, list) or not metrics:
        return ""
    metric_names: list[str] = []
    for row in metrics:
        if not isinstance(row, dict) or not isinstance(row.get("values"), dict):
            continue
        for name in row["values"]:
            if name not in metric_names:
                metric_names.append(name)
    if not metric_names:
        return ""
    headings = ["Test plan", "Samples", *(_metric_label(name) for name in metric_names)]
    lines = [
        "#### Observed held-out metrics",
        "",
        "These values are bounded to the identified run and its one-time held-out test read.",
        "",
        "| " + " | ".join(headings) + " |",
        "| " + " | ".join("---" for _ in headings) + " |",
    ]
    for fallback_index, row in enumerate(metrics):
        if not isinstance(row, dict):
            continue
        values = row.get("values", {})
        if not isinstance(values, dict):
            continue
        cells = [
            str(int(row.get("plan_index", fallback_index)) + 1),
            str(row.get("sample_count", "")),
            *[
                f"{float(values[name]):.3f}" if name in values else "-"
                for name in metric_names
            ],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _render_stage_screenshots(record: dict[str, Any], stage_key: str) -> str:
    publication = record.get("publication", {})
    artifacts = (
        publication.get("published_artifacts", [])
        if isinstance(publication, dict)
        else []
    )
    expected_kind = f"{stage_key}_screenshot"
    if stage_key == "import_scope":
        expected_kind = "import_review_screenshot"
    screenshots = [
        item.get("reference")
        for item in artifacts
        if isinstance(item, dict) and item.get("kind") == expected_kind
    ]
    if not screenshots:
        return ""
    label = stage_key.replace("_", " ").capitalize()
    return "\n\n".join(
        f"![{label} evidence]({_page_reference(str(reference))})"
        for reference in screenshots
    )


def _render_limitations(record: dict[str, Any]) -> str:
    observations = record.get("observations", {})
    limitations = (
        observations.get("limitations", []) if isinstance(observations, dict) else []
    )
    if not isinstance(limitations, list) or not limitations:
        return ""
    return "#### Limits of this observation\n\n" + "\n".join(
        f"- {_safe_text(item)}" for item in limitations
    )


def _stage_details(
    dataset: dict[str, Any], source_digest: str, record: dict[str, Any]
) -> dict[str, list[str]]:
    import_contract = dataset["import"]
    choices = import_contract["choices"]
    workflow = dataset["workflow"]
    epoch = workflow["epoch"]
    split = workflow["split"]
    training = workflow["training_profiles"]["showcase"]
    quality = workflow["quality_acceptance"]
    saliency = workflow["saliency"]
    source_files = ", ".join(_code(item["relative_path"]) for item in dataset["files"])
    selected_files = ", ".join(
        _code(item) for item in import_contract["selected_eeg_files"]
    )
    labels = ", ".join(_code(item) for item in epoch["event_ids"])
    preprocessing = _workflow_lines(dataset)[0].removeprefix("Preprocess: ")
    acceptance = "; ".join(
        (
            f"{_code(rule['metric'])} {rule['operator']} "
            f"{_code(rule['threshold']['name'])}"
        )
        for rule in quality["rules"]
    )
    boundaries = [str(item) for item in dataset["claim_boundary"]]
    details = {
        "source_and_dataset": [
            f"Planned source files: {source_files}.",
            f"Dataset license in the source contract: {_code(dataset['identity']['license'])}.",
        ],
        "import_scope": [
            f"Open {_code(import_contract['entrypoint'])} using the {_code(import_contract['source_hint'])} route.",
            f"Expected selected EEG files: {selected_files}.",
        ],
        "labels_and_metadata": [
            f"Label carrier: {_code(choices['label_carrier'])}.",
            *_mapping_lines(dataset),
        ],
        "preprocess": [f"Planned setting: {preprocessing}"],
        "epoch": [
            (
                f"Planned window: {_code(epoch['t_min'])} to {_code(epoch['t_max'])} s; "
                f"baseline {_code(epoch['baseline'])}; labels {labels}."
            )
        ],
        "split": [
            (
                f"Planned split: {_code(split['test_ratio'])} test and "
                f"{_code(split['val_ratio'])} validation by "
                f"{_code(split['split_strategy'])}; {_code(split['training_mode'])} mode."
            )
        ],
        "model_and_training": [
            (
                f"Planned profile: {_code(training['name'])}, {_code(training['device'])}, "
                f"up to {_code(training['epochs'])} epochs, batch "
                f"{_code(training['batch_size'])}, learning rate "
                f"{_code(training['learning_rate'])}, {_code(training['optimizer'])}."
            ),
            f"Stopping boundary from the source contract: {training['stopping_budget']}",
        ],
        "evaluation": [
            f"Planned held-out split: {_code(quality['held_out_split'])}.",
            f"Planned acceptance comparisons: {acceptance}.",
            quality["test_access_policy"],
            "No measured value is published on this page.",
        ],
        "saliency": [
            "Planned methods: "
            + ", ".join(_code(item) for item in saliency["methods"])
            + ".",
            "No saliency image is published on this page.",
        ],
        "reproducibility_and_limitations": [
            f"Planned seed: {_code(workflow['seed'])}.",
            f"Source contract SHA-256: {_code(source_digest)}.",
            *boundaries,
        ],
    }
    if record.get("publication_status") == "bounded":
        observed = {
            "source_and_dataset": (
                "Observed source files matched the exact registry inventory, byte sizes, "
                "declared checksums, and recorded SHA-256 values."
            ),
            "import_scope": "Observed import/review state in the identified Qt run.",
            "labels_and_metadata": (
                "Observed route labels matched the predeclared dataset semantics."
            ),
            "preprocess": "Observed successful preprocessing commands in the run trace.",
            "epoch": "Observed successful epoch creation in the run trace.",
            "split": "Observed successful dataset split creation in the run trace.",
            "model_and_training": (
                "Observed completed showcase training with immutable multi-point curve data."
            ),
            "evaluation": (
                "Observed accepted held-out test metrics; values are shown below and apply "
                "only to this identified run."
            ),
            "saliency": (
                "Observed successful ApplicationService saliency output and a decoded Qt "
                "screenshot for this run."
            ),
            "reproducibility_and_limitations": (
                "The run is bound to a clean application source digest, registry digest, "
                "dataset revision, seed, and immutable published files."
            ),
        }
        details["evaluation"] = [
            line
            for line in details["evaluation"]
            if line != "No measured value is published on this page."
        ]
        details["saliency"] = [
            line
            for line in details["saliency"]
            if line != "No saliency image is published on this page."
        ]
        for key, line in observed.items():
            details[key].append(line)
    return details


def _render_moabb_page(
    source: dict[str, Any], dataset: dict[str, Any], record: dict[str, Any]
) -> str:
    metadata = MOABB_CASES[dataset["id"]]
    release = source["moabb_release"]
    identity = dataset["identity"]
    import_contract = dataset["import"]
    choices = import_contract["choices"]
    evidence_identity = record["identity"]
    source_contract = record["generated_from"]
    source_digest = source_contract["source_sha256"]
    status = record["publication_status"]
    status_label = str(status).capitalize()
    source_manifest_link = "../assets/manifests/moabb-datasets-v1.json"
    source_files = []
    for item in dataset["files"]:
        checksum = item["checksum"]
        source_files.append(
            f"- {_code(item['relative_path'])}: {_code(checksum['algorithm'])} "
            f"{_code(checksum['value'])} ([source]({item['url']}))"
        )
    selected_files = ", ".join(
        _code(item) for item in import_contract["selected_eeg_files"]
    )
    event_labels = ", ".join(
        _code(item) for item in dataset["workflow"]["epoch"]["event_ids"]
    )
    stage_details = _stage_details(dataset, source_digest, record)
    stage_sections = []
    for heading, key in CASE_STAGES:
        stage = record["stages"][key]
        stage_status = stage["status"]
        detail_lines = "\n".join(f"- {line}" for line in stage_details[key])
        if stage["evidence_files"]:
            detail_lines += "\n- Published files: " + _evidence_links(
                stage["evidence_files"], from_case_page=True
            )
        else:
            detail_lines += "\n- Published XBrainLab run evidence: None."
        supplements = []
        if key == "evaluation":
            supplements.append(_render_observed_metrics(record))
        screenshots = _render_stage_screenshots(record, key)
        if screenshots:
            supplements.append(screenshots)
        if key == "reproducibility_and_limitations":
            supplements.append(_render_limitations(record))
        supplement = "\n\n".join(item for item in supplements if item)
        supplement_block = f"\n\n{supplement}" if supplement else ""
        stage_sections.append(
            f"### {heading}\n\n"
            f'<span class="evidence-badge evidence-badge--{stage_status}">'
            f"{str(stage_status).capitalize()}</span>\n\n{detail_lines}"
            f"{supplement_block}\n"
        )

    published = status == "bounded"
    execution_label = "Exact identified run" if published else "Execution pending"
    evidence_summary = (
        "This page publishes bounded observations from one exact automated XBrainLab run. "
        "Metrics and screenshots apply only to the identity and limitations below."
        if published
        else (
            "This is a manifest-generated execution guide. It contains no completed "
            "XBrainLab run, metric, or saliency claim."
        )
    )
    expected_status = (
        f"- Status: observed in run {_code(evidence_identity['run_id'])}."
        if published
        else "- Status: pending visual confirmation in an identified XBrainLab run."
    )
    next_step = (
        "Use the immutable files and bounded metrics below when reviewing this run. Start a "
        "new run identity before changing any source, choice, preprocessing, model, or seed."
        if published
        else (
            "After the import checkpoint matches, apply the planned settings one stage at a "
            "time and capture a run ID, app revision, dataset revision, and immutable evidence "
            "files. Until those fields are published below, every stage remains pending and "
            "Unverified."
        )
    )

    return (
        "\n".join(
            [
                "---",
                f"title: {metadata['title']}",
                f"case_id: {record['case_id']}",
                f"evidence_record: case-studies/manifests/{record['case_id']}.yml",
                f"publication_status: {status}",
                "generated_from: moabb-datasets-v1",
                "---",
                "",
                f"# {metadata['title']}",
                "",
                '<div class="case-summary" markdown>',
                f"  <div><span>Paradigm</span><strong>{dataset['paradigm']}</strong></div>",
                (
                    "  <div><span>Route scope</span><strong>"
                    f"{_selection_scope(dataset)}</strong></div>"
                ),
                f"  <div><span>Source format</span><strong>{dataset['source_format']}</strong></div>",
                f"  <div><span>Published evidence</span><strong>{status_label}</strong></div>",
                "</div>",
                "",
                f'<span class="evidence-badge evidence-badge--{status}">{status_label}</span> '
                f'<span class="scope-label">{execution_label}</span>',
                "",
                evidence_summary,
                "",
                "## Run this dataset",
                "",
                "Follow the route only while each checkpoint matches. The values below come "
                "from the linked source contract; they are planned inputs, not observed results.",
                "",
                "### Source and version",
                "",
                f"- Dataset: [{identity['title']}]({identity['repository_url']}).",
                f"- Dataset DOI: [doi:{identity['dataset_doi']}](https://doi.org/{identity['dataset_doi']}).",
                f"- Repository and license: {identity['repository']}, {_code(identity['license'])}.",
                (
                    f"- MOABB adapter: [version {release['version']} at "
                    f"{release['commit'][:12]}]({identity['moabb_adapter_url']}); "
                    f"[dataset reference]({identity['moabb_docs_url']})."
                ),
                (
                    f"- Site source contract: [{source['profile_id']}]({source_manifest_link}), "
                    f"SHA-256 {_code(source_digest)}."
                ),
                "",
                *source_files,
                "",
                "### App action",
                "",
                "1. Obtain only the files listed above and verify every checksum before opening the app.",
                "2. Start the XBrainLab development build and choose **Load Data**.",
                (
                    f"3. Use the **{import_contract['source_hint']}** route and select "
                    f"{_code(import_contract['entrypoint'])}."
                ),
                "4. Keep the import review open until the selected files and labels match this page.",
                "",
                "### Choices",
                "",
                f"- Use {_code(choices['label_carrier'])} as the label carrier.",
                *[f"- {line}" for line in _mapping_lines(dataset)],
                *[f"- {line}" for line in _workflow_lines(dataset)],
                "",
                "### Expected checkpoint",
                "",
                f"- Selected EEG files: {selected_files}.",
                f"- Resolved labels: {event_labels}.",
                expected_status,
                "",
                "### Stop condition",
                "",
                "Stop before preprocessing if a checksum differs, the selected file set changes, "
                "a run-specific label maps differently, or the app does not expose the stated choice. "
                "Do not substitute values or interpret later output as evidence for this route.",
                "",
                "### Next step",
                "",
                next_step,
                "",
                "## Evidence identity",
                "",
                '<div class="evidence-identity" markdown>',
                f"<p><strong>Evidence state</strong><br>{status_label}</p>",
                (
                    f"<p><strong>Source journey</strong><br>"
                    f"[{source['profile_id']}]({source_manifest_link})</p>"
                ),
                f"<p><strong>Source contract SHA-256</strong><br>{_code(source_digest)}</p>",
                (
                    f"<p><strong>MOABB release</strong><br>{_code(release['version'])} at "
                    f"{_code(release['commit'])}</p>"
                ),
                f"<p><strong>Manifest ID</strong><br>{_evidence_value(evidence_identity['manifest_id'])}</p>",
                f"<p><strong>App revision</strong><br>{_evidence_value(evidence_identity['app_revision'])}</p>",
                f"<p><strong>Run ID</strong><br>{_evidence_value(evidence_identity['run_id'])}</p>",
                f"<p><strong>Dataset revision</strong><br>{_evidence_value(evidence_identity['dataset_revision'])}</p>",
                (
                    f"<p><strong>Evidence files</strong><br>"
                    f"{_evidence_links(evidence_identity['evidence_files'], from_case_page=True)}</p>"
                ),
                "</div>",
                "",
                '!!! warning "Claim boundary"',
                "    The linked journey manifest identifies intended inputs and choices. It does not "
                "identify a completed XBrainLab run. Observed or Bounded status requires all identity "
                "fields and evidence files above.",
                "",
                "## Evidence and limits",
                "",
                *stage_sections,
                "",
            ]
        )
    ).rstrip() + "\n"


def _new_moabb_record(
    source: dict[str, Any],
    dataset: dict[str, Any],
    existing: dict[str, Any] | None,
    *,
    published: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = MOABB_CASES[dataset["id"]]
    release = source["moabb_release"]
    identity = {
        "manifest_id": None,
        "app_revision": None,
        "run_id": None,
        "dataset_revision": None,
        "evidence_files": [],
    }
    stages = {
        key: {"status": "unverified", "evidence_files": []} for _, key in CASE_STAGES
    }
    publication_status = "unverified"
    publication = None
    observations = None
    if (
        published is None
        and isinstance(existing, dict)
        and existing.get("publication_status") == "bounded"
        and isinstance(existing.get("publication"), dict)
        and isinstance(existing.get("observations"), dict)
        and isinstance(existing.get("stages"), dict)
        and isinstance(existing.get("identity"), dict)
    ):
        observations_existing = existing["observations"]
        published = {
            "publication_status": "bounded",
            "identity": existing["identity"],
            "publication": existing["publication"],
            "metrics": observations_existing.get("metrics", []),
            "limitations": observations_existing.get("limitations", []),
            "saliency_methods": observations_existing.get("saliency_methods", []),
            "stage_evidence": {
                key: existing["stages"].get(key, {}).get("evidence_files", [])
                for _, key in CASE_STAGES
            },
        }
    if published is not None:
        publication_status = str(published["publication_status"])
        identity = dict(published["identity"])
        stage_evidence = published["stage_evidence"]
        stages = {
            key: {
                "status": publication_status,
                "evidence_files": list(stage_evidence[key]),
            }
            for _, key in CASE_STAGES
        }
        publication = dict(published["publication"])
        observations = {
            "metrics": list(published["metrics"]),
            "limitations": list(published["limitations"]),
            "saliency_methods": list(published["saliency_methods"]),
        }
    record = {
        "schema_version": 1,
        "case_id": metadata["case_id"],
        "page": metadata["page"],
        "publication_status": publication_status,
        "generated_from": {
            "source": ("scripts/dev/moabb_user_journeys/data/moabb-datasets-v1.json"),
            "site_copy": "assets/manifests/moabb-datasets-v1.json",
            "schema_version": source["schema_version"],
            "profile_id": source["profile_id"],
            "source_sha256": _source_digest(MOABB_SOURCE),
            "dataset_id": dataset["id"],
            "moabb_version": release["version"],
            "moabb_commit": release["commit"],
        },
        "identity": identity,
        "route": {
            "source": dataset["identity"]["title"],
            "source_version": (
                f"dataset DOI {dataset['identity']['dataset_doi']}; "
                f"MOABB {release['version']} at {release['commit']}"
            ),
            "scope": _selection_scope(dataset),
            "followable_through": "planned execution guide; recorded checkpoints pending",
        },
        "stages": stages,
    }
    if publication is not None:
        record["publication"] = publication
    if observations is not None:
        record["observations"] = observations
    return record


def _sync_moabb_cases(source: dict[str, Any]) -> None:
    datasets = _moabb_dataset_map(source, [])
    MOABB_SITE_COPY.parent.mkdir(parents=True, exist_ok=True)
    MOABB_SITE_COPY.write_bytes(MOABB_SOURCE.read_bytes())
    for dataset_id, metadata in MOABB_CASES.items():
        dataset = datasets[dataset_id]
        record_path = MANIFEST_DIR / f"{metadata['case_id']}.yml"
        existing = None
        if record_path.is_file():
            loaded = yaml.safe_load(record_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        if existing and existing.get("publication_status") == "bounded":
            publication_failures: list[str] = []
            _check_moabb_publication_record(
                existing,
                record_path,
                dataset_id=dataset_id,
                source_digest=_source_digest(MOABB_SOURCE),
                failures=publication_failures,
            )
            if publication_failures:
                raise EvidencePublicationError("; ".join(publication_failures))
        record = _new_moabb_record(source, dataset, existing)
        record_path.write_text(
            yaml.safe_dump(record, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        page_path = DOCS_DIR / metadata["page"]
        page_path.write_text(
            _render_moabb_page(source, dataset, record),
            encoding="utf-8",
        )


def _check_moabb_publication_record(
    record: dict[str, Any],
    record_path: Path,
    *,
    dataset_id: str,
    source_digest: str,
    failures: list[str],
) -> None:
    status = record.get("publication_status")
    identity = record.get("identity")
    stages = record.get("stages")
    if status == "unverified":
        if (
            record.get("publication") is not None
            or record.get("observations") is not None
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} has unverified publication data",
                failures,
            )
        if isinstance(identity, dict) and (
            any(identity.get(field) is not None for field in IDENTITY_FIELDS)
            or identity.get("evidence_files") != []
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} has manual evidence promotion",
                failures,
            )
        if isinstance(stages, dict) and any(
            not isinstance(stage, dict)
            or stage.get("status") != "unverified"
            or stage.get("evidence_files") != []
            for stage in stages.values()
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} has promoted unverified stages",
                failures,
            )
        return
    if status != "bounded":
        _fail(
            f"{record_path.relative_to(ROOT)} exceeds the MOABB publication ceiling",
            failures,
        )
        return

    publication = record.get("publication")
    observations = record.get("observations")
    if not isinstance(publication, dict) or not isinstance(observations, dict):
        _fail(f"{record_path.relative_to(ROOT)} has no publication receipt", failures)
        return
    if publication.get("schema_version") != "1.0.0":
        _fail(
            f"{record_path.relative_to(ROOT)} has an unsupported publication receipt",
            failures,
        )
    manifest_sha = str(publication.get("input_manifest_sha256") or "")
    if not HEX_SHA256.fullmatch(manifest_sha):
        _fail(
            f"{record_path.relative_to(ROOT)} has an invalid input manifest digest",
            failures,
        )
        return
    if (
        not isinstance(identity, dict)
        or identity.get("manifest_id") != f"sha256:{manifest_sha}"
    ):
        _fail(f"{record_path.relative_to(ROOT)} manifest identity disagrees", failures)
        return
    if publication.get("registry_sha256") != source_digest:
        _fail(
            f"{record_path.relative_to(ROOT)} publication registry is stale", failures
        )
    for field in ("application_source_digest", "execution_sha256"):
        if not HEX_SHA256.fullmatch(str(publication.get(field) or "")):
            _fail(f"{record_path.relative_to(ROOT)} has invalid {field}", failures)

    receipts = publication.get("published_artifacts")
    if not isinstance(receipts, list) or not receipts:
        _fail(
            f"{record_path.relative_to(ROOT)} has no published artifact receipts",
            failures,
        )
        return
    receipt_by_reference: dict[str, dict[str, Any]] = {}
    allowed_kinds = {
        "bounded_metrics",
        "training_curves",
        "import_review_screenshot",
        "evaluation_screenshot",
        "saliency_screenshot",
    }
    for raw_receipt in receipts:
        if not isinstance(raw_receipt, dict):
            _fail(
                f"{record_path.relative_to(ROOT)} has an invalid artifact receipt",
                failures,
            )
            continue
        reference = str(raw_receipt.get("reference") or "")
        digest = str(raw_receipt.get("sha256") or "")
        size = raw_receipt.get("size_bytes")
        kind = raw_receipt.get("kind")
        expected_prefix = (
            f"assets/evidence/moabb/{record.get('case_id')}/"
            f"{identity.get('run_id')}-{manifest_sha}/"
        )
        if (
            not reference.startswith(expected_prefix)
            or "latest" in reference.casefold()
            or not HEX_SHA256.fullmatch(digest)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or kind not in allowed_kinds
            or digest not in Path(reference).name
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} has mutable artifact receipt",
                failures,
            )
            continue
        if reference in receipt_by_reference:
            _fail(
                f"{record_path.relative_to(ROOT)} repeats an artifact receipt", failures
            )
            continue
        candidate = DOCS_DIR / reference
        target = candidate.resolve()
        if (
            not target.is_relative_to(DOCS_DIR.resolve())
            or candidate.is_symlink()
            or not target.is_file()
            or target.stat().st_size != size
            or _source_digest(target) != digest
        ):
            _fail(
                f"{record_path.relative_to(ROOT)} published artifact integrity failed: "
                f"{reference}",
                failures,
            )
            continue
        receipt_by_reference[reference] = raw_receipt

    evidence_files = identity.get("evidence_files")
    if not isinstance(evidence_files, list) or set(evidence_files) != set(
        receipt_by_reference
    ):
        _fail(f"{record_path.relative_to(ROOT)} evidence inventory disagrees", failures)
    observed_kinds = {item.get("kind") for item in receipt_by_reference.values()}
    if not allowed_kinds.issubset(observed_kinds):
        _fail(
            f"{record_path.relative_to(ROOT)} evidence kinds are incomplete", failures
        )
    if not isinstance(stages, dict) or any(
        not isinstance(stage, dict)
        or stage.get("status") != "bounded"
        or not isinstance(stage.get("evidence_files"), list)
        or not stage["evidence_files"]
        or not set(stage["evidence_files"]).issubset(receipt_by_reference)
        for stage in stages.values()
    ):
        _fail(
            f"{record_path.relative_to(ROOT)} published stages are incomplete", failures
        )

    summary_references = [
        reference
        for reference, receipt in receipt_by_reference.items()
        if receipt.get("kind") == "bounded_metrics"
    ]
    if len(summary_references) != 1:
        _fail(
            f"{record_path.relative_to(ROOT)} must have one bounded metrics file",
            failures,
        )
        return
    summary = _read_json(DOCS_DIR / summary_references[0], failures)
    expected_summary = {
        "publication_status": "bounded",
        "manifest_id": identity.get("manifest_id"),
        "run_id": identity.get("run_id"),
        "registry_sha256": source_digest,
        "dataset_id": dataset_id,
        "dataset_revision": identity.get("dataset_revision"),
        "successful_through": "saliency",
        "observed_metrics": observations.get("metrics"),
        "limitations": observations.get("limitations"),
    }
    for field, expected in expected_summary.items():
        if summary.get(field) != expected:
            _fail(
                f"{record_path.relative_to(ROOT)} bounded metrics disagree on {field}",
                failures,
            )
    application = summary.get("application")
    if not isinstance(application, dict) or (
        application.get("commit_sha") != identity.get("app_revision")
        or application.get("source_digest")
        != publication.get("application_source_digest")
    ):
        _fail(
            f"{record_path.relative_to(ROOT)} application identity disagrees", failures
        )


def _check_moabb_generated_cases(source: dict[str, Any], failures: list[str]) -> None:
    if not MOABB_SITE_COPY.is_file():
        _fail("missing user-facing MOABB source contract", failures)
    elif MOABB_SITE_COPY.read_bytes() != MOABB_SOURCE.read_bytes():
        _fail("user-facing MOABB source contract has drifted from its source", failures)

    datasets = _moabb_dataset_map(source, failures)
    source_digest = _source_digest(MOABB_SOURCE)
    for dataset_id, metadata in MOABB_CASES.items():
        dataset = datasets.get(dataset_id)
        if not isinstance(dataset, dict):
            continue
        record_path = MANIFEST_DIR / f"{metadata['case_id']}.yml"
        page_path = DOCS_DIR / metadata["page"]
        if not record_path.is_file() or not page_path.is_file():
            continue
        record = _read_yaml(record_path, failures)
        generated_from = record.get("generated_from")
        expected_source = {
            "source": ("scripts/dev/moabb_user_journeys/data/moabb-datasets-v1.json"),
            "site_copy": "assets/manifests/moabb-datasets-v1.json",
            "schema_version": source["schema_version"],
            "profile_id": source["profile_id"],
            "source_sha256": source_digest,
            "dataset_id": dataset_id,
            "moabb_version": source["moabb_release"]["version"],
            "moabb_commit": source["moabb_release"]["commit"],
        }
        if generated_from != expected_source:
            _fail(
                f"{record_path.relative_to(ROOT)} has stale generator identity",
                failures,
            )
            continue
        _check_moabb_publication_record(
            record,
            record_path,
            dataset_id=dataset_id,
            source_digest=source_digest,
            failures=failures,
        )
        expected_page = _render_moabb_page(source, dataset, record)
        if page_path.read_text(encoding="utf-8") != expected_page:
            _fail(
                f"{page_path.relative_to(ROOT)} has drifted; run --sync-moabb",
                failures,
            )


def _check_case_studies(failures: list[str]) -> None:
    case_paths = sorted(
        path
        for path in CASE_DIR.glob("*.md")
        if path.name not in {"index.md", "_template.md"}
    )
    referenced_records = {
        record
        for path in case_paths
        if (record := _check_case_page(path, failures)) is not None
    }
    published_records = {
        path.resolve()
        for path in MANIFEST_DIR.glob("*.yml")
        if not path.name.startswith("_")
    }
    for orphan in sorted(published_records - referenced_records):
        _fail(f"orphan evidence record: {orphan.relative_to(ROOT)}", failures)

    template = (CASE_DIR / "_template.md").read_text(encoding="utf-8")
    for heading in ("Run this dataset", "Evidence identity", "Evidence and limits"):
        if f"## {heading}" not in template:
            _fail(f"case-study template is missing {heading}", failures)
    for heading in RUN_HEADINGS:
        if f"### {heading}" not in template:
            _fail(f"case-study template is missing run field: {heading}", failures)
    for heading, _ in CASE_STAGES:
        if f"### {heading}" not in template:
            _fail(f"case-study template is missing stage: {heading}", failures)


def _check_user_language(failures: list[str]) -> None:
    for source in DOCS_DIR.rglob("*.md"):
        if source.name.startswith("_"):
            continue
        text = source.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_USER_TERMS:
            if term.lower() in text:
                _fail(
                    f"{source.relative_to(ROOT)} contains developer-facing term: {term}",
                    failures,
                )


def _check_local_links(failures: list[str]) -> None:
    for source in DOCS_DIR.rglob("*.md"):
        text = source.read_text(encoding="utf-8")
        targets = MARKDOWN_LINK.findall(text) + HTML_ASSET.findall(text)
        for raw_target in targets:
            target = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (source.parent / target).resolve()
            if not resolved.is_relative_to(DOCS_DIR.resolve()):
                _fail(
                    f"{source.relative_to(ROOT)} links outside user_docs: {raw_target}",
                    failures,
                )
            elif not resolved.exists():
                _fail(
                    f"{source.relative_to(ROOT)} has missing local target: {raw_target}",
                    failures,
                )


def _check_built_site(built_dir: Path, failures: list[str]) -> None:
    expected = (
        "index.html",
        "getting-started/index.html",
        "workflow/index.html",
        "case-studies/index.html",
        "case-studies/graz-2a/index.html",
        "case-studies/openneuro-ds003061/index.html",
        "case-studies/moabb-ofner2017/index.html",
        "case-studies/moabb-physionetmi/index.html",
        "case-studies/moabb-lee2021mobile-erp/index.html",
        "faq-limits/index.html",
    )
    for relative in expected:
        if not (built_dir / relative).is_file():
            _fail(f"built site is missing {relative}", failures)

    excluded_outputs = (
        "case-studies/_template/index.html",
        "case-studies/manifests/graz-2a/index.html",
        "case-studies/manifests/openneuro-ds003061/index.html",
        "case-studies/manifests/moabb-ofner2017/index.html",
        "case-studies/manifests/moabb-physionetmi/index.html",
        "case-studies/manifests/moabb-lee2021mobile-erp/index.html",
    )
    for relative in excluded_outputs:
        if (built_dir / relative).exists():
            _fail(f"excluded publication source was rendered: {relative}", failures)


MAX_PUBLICATION_RENDER_FILES = 16
MAX_PUBLICATION_RENDER_FILE_BYTES = 4 * 1024 * 1024
MAX_PUBLICATION_RENDER_TOTAL_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class _PublicationFileEntry:
    target: Path
    staged: Path
    backup: Path | None
    existed: bool


class _PublicationFileTransaction:
    """Bounded multi-file replacement with rollback retained through validation."""

    def __init__(
        self,
        *,
        entries: list[_PublicationFileEntry],
        docs_root: Path,
        created_assets: list[Path],
    ) -> None:
        self._entries = entries
        self._docs_root = docs_root
        self._created_assets = created_assets
        self._committed: list[_PublicationFileEntry] = []
        self._state = "prepared"

    @classmethod
    def prepare(
        cls,
        outputs: list[tuple[Path, str]],
        *,
        docs_root: Path,
        created_assets: list[Path],
    ) -> _PublicationFileTransaction:
        root = docs_root.expanduser().resolve()
        if not outputs or len(outputs) > MAX_PUBLICATION_RENDER_FILES:
            raise EvidencePublicationError("publication render file count is invalid")
        prepared: list[tuple[Path, bytes, int | None]] = []
        seen: set[Path] = set()
        total_bytes = 0
        for raw_target, content in outputs:
            target = raw_target.expanduser()
            if not target.is_absolute():
                target = root / target
            if target in seen or target.is_symlink():
                raise EvidencePublicationError(
                    "publication render target is not unique"
                )
            seen.add(target)
            parent = target.parent.resolve()
            if not parent.is_relative_to(root):
                raise EvidencePublicationError(
                    "publication render target escapes user_docs"
                )
            if target.exists() and not target.is_file():
                raise EvidencePublicationError(
                    "publication render target is not a file"
                )
            encoded = content.encode("utf-8")
            if not encoded or len(encoded) > MAX_PUBLICATION_RENDER_FILE_BYTES:
                raise EvidencePublicationError(
                    "publication render file size is invalid"
                )
            total_bytes += len(encoded)
            mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
            prepared.append((target, encoded, mode))
        if total_bytes > MAX_PUBLICATION_RENDER_TOTAL_BYTES:
            raise EvidencePublicationError(
                "publication render output exceeds its budget"
            )

        assets = cls._preflight_created_assets(created_assets, docs_root=root)
        token = uuid.uuid4().hex
        entries: list[_PublicationFileEntry] = []
        try:
            for target, encoded, mode in prepared:
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = target.with_name(f".{target.name}.{token}.publication-part")
                backup = (
                    target.with_name(f".{target.name}.{token}.publication-backup")
                    if target.exists()
                    else None
                )
                entry = _PublicationFileEntry(
                    target=target,
                    staged=staged,
                    backup=backup,
                    existed=target.exists(),
                )
                entries.append(entry)
                _write_bytes_durable(staged, encoded, mode=mode)
                if backup is not None:
                    shutil.copy2(target, backup)
                    _fsync_file(backup)
        except Exception:
            cls._cleanup_paths(
                [entry.staged for entry in entries]
                + [entry.backup for entry in entries if entry.backup is not None]
            )
            cls._remove_created_assets(assets, docs_root=root)
            raise
        return cls(entries=entries, docs_root=root, created_assets=assets)

    def commit(self) -> None:
        if self._state != "prepared":
            raise EvidencePublicationError("publication transaction is not prepared")
        try:
            for entry in self._entries:
                os.replace(entry.staged, entry.target)
                self._committed.append(entry)
            self._state = "committed"
        except Exception as exc:
            try:
                self._restore_committed()
            except Exception as rollback_exc:
                self._state = "rollback_failed"
                raise EvidencePublicationError(
                    f"publication replacement failed and rollback failed: {rollback_exc}"
                ) from exc
            self._state = "rolled_back"
            self._remove_created_assets(
                self._created_assets,
                docs_root=self._docs_root,
            )
            self._cleanup_staging()
            raise

    def rollback(self) -> None:
        if self._state == "rolled_back":
            return
        if self._state != "committed":
            raise EvidencePublicationError("publication transaction cannot roll back")
        self._restore_committed()
        self._state = "rolled_back"
        self._remove_created_assets(
            self._created_assets,
            docs_root=self._docs_root,
        )
        self._cleanup_staging()

    def finish(self) -> None:
        if self._state != "committed":
            raise EvidencePublicationError("publication transaction cannot finish")
        self._cleanup_staging()
        self._state = "finished"

    def _restore_committed(self) -> None:
        for entry in reversed(self._committed):
            if entry.existed:
                if entry.backup is None or not entry.backup.is_file():
                    raise EvidencePublicationError(
                        f"publication backup is missing for {entry.target.name}"
                    )
                os.replace(entry.backup, entry.target)
            else:
                entry.target.unlink(missing_ok=True)
        self._committed.clear()

    def _cleanup_staging(self) -> None:
        self._cleanup_paths(
            [entry.staged for entry in self._entries]
            + [entry.backup for entry in self._entries if entry.backup is not None]
        )

    @staticmethod
    def _preflight_created_assets(paths: list[Path], *, docs_root: Path) -> list[Path]:
        assets: list[Path] = []
        for raw_path in paths:
            if raw_path.is_symlink():
                raise EvidencePublicationError("created publication asset is a symlink")
            path = raw_path.resolve()
            if (
                not path.is_relative_to(docs_root)
                or not path.is_file()
                or path in assets
            ):
                raise EvidencePublicationError("created publication asset is invalid")
            assets.append(path)
        return assets

    @staticmethod
    def _cleanup_paths(paths: list[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    @staticmethod
    def _remove_created_assets(paths: list[Path], *, docs_root: Path) -> None:
        for path in reversed(paths):
            resolved = path.resolve()
            if resolved.is_relative_to(docs_root):
                resolved.unlink(missing_ok=True)
                parent = resolved.parent
                while parent != docs_root:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent


def _write_bytes_durable(path: Path, content: bytes, *, mode: int | None) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        path.chmod(mode)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _publish_moabb_cases(
    source: dict[str, Any], capture_manifest: Path
) -> _PublicationFileTransaction:
    publication = publish_capture_manifest(
        capture_manifest_path=capture_manifest,
        registry_path=MOABB_SOURCE,
        docs_dir=DOCS_DIR,
        case_map=MOABB_CASES,
    )
    datasets = _moabb_dataset_map(source, [])
    outputs: list[tuple[Path, str]] = []
    created_assets = [
        Path(path) for path in publication.pop("_created_asset_paths", [])
    ]
    try:
        for dataset_id, metadata in MOABB_CASES.items():
            record_path = MANIFEST_DIR / f"{metadata['case_id']}.yml"
            existing = None
            if record_path.is_file():
                loaded = yaml.safe_load(record_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            record = _new_moabb_record(
                source,
                datasets[dataset_id],
                existing,
                published=publication["datasets"][dataset_id],
            )
            outputs.append(
                (
                    record_path,
                    yaml.safe_dump(record, sort_keys=False, allow_unicode=False),
                )
            )
            outputs.append(
                (
                    DOCS_DIR / metadata["page"],
                    _render_moabb_page(source, datasets[dataset_id], record),
                )
            )
        transaction = _PublicationFileTransaction.prepare(
            outputs,
            docs_root=DOCS_DIR,
            created_assets=created_assets,
        )
        transaction.commit()
    except Exception:
        _PublicationFileTransaction._remove_created_assets(
            created_assets,
            docs_root=DOCS_DIR.resolve(),
        )
        raise
    else:
        return transaction


def _run_site_checks(
    source: dict[str, Any],
    *,
    built_dir: Path | None,
) -> list[str]:
    failures: list[str] = []
    config = _read_yaml(CONFIG_PATH, failures)
    _check_config(config, failures)
    _check_required_pages(failures)
    _check_case_studies(failures)
    _check_moabb_generated_cases(source, failures)
    _check_user_language(failures)
    _check_local_links(failures)
    if built_dir is not None:
        resolved = built_dir if built_dir.is_absolute() else ROOT / built_dir
        _check_built_site(resolved, failures)
    return failures


def _print_failures(failures: list[str]) -> int:
    print("User site validation failed:")
    for failure in failures:
        print(f"- {failure}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--sync-moabb",
        action="store_true",
        help="Regenerate MOABB evidence records, pages, and the linked source contract.",
    )
    action.add_argument(
        "--publish-run-manifest",
        type=Path,
        metavar="QT_CAPTURE_MANIFEST",
        help=(
            "Validate one exact showcase Qt capture, publish content-addressed evidence, "
            "and render bounded case observations."
        ),
    )
    parser.add_argument(
        "--built-dir",
        type=Path,
        help="Also verify expected HTML beneath an existing MkDocs output directory.",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []
    source = _read_json(MOABB_SOURCE, failures)
    _check_moabb_source(source, failures)
    if failures:
        return _print_failures(failures)

    if args.publish_run_manifest is not None:
        preflight = _run_site_checks(source, built_dir=None)
        if preflight:
            return _print_failures(preflight)
        transaction: _PublicationFileTransaction | None = None
        try:
            transaction = _publish_moabb_cases(source, args.publish_run_manifest)
            post_write_failures = _run_site_checks(
                source,
                built_dir=args.built_dir,
            )
            if post_write_failures:
                transaction.rollback()
                return _print_failures(
                    [
                        *post_write_failures,
                        "evidence publication was rolled back",
                    ]
                )
            transaction.finish()
        except Exception as exc:
            rollback_failure = None
            if transaction is not None:
                try:
                    transaction.rollback()
                except Exception as rollback_exc:
                    rollback_failure = rollback_exc
            detail = f"evidence publication rejected: {exc}"
            if rollback_failure is not None:
                detail += f"; rollback failed: {rollback_failure}"
            return _print_failures([detail])
        print(
            "User site validation passed: IA, run instructions, fail-closed evidence "
            "receipts, bounded observations, user language, and local links are consistent."
        )
        return 0
    elif args.sync_moabb:
        try:
            _sync_moabb_cases(source)
        except (EvidencePublicationError, OSError, KeyError, ValueError) as exc:
            return _print_failures([f"MOABB sync rejected: {exc}"])

    failures = _run_site_checks(source, built_dir=args.built_dir)
    if failures:
        return _print_failures(failures)

    print(
        "User site validation passed: IA, run instructions, fail-closed evidence "
        "receipts, bounded observations, user language, and local links are consistent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
