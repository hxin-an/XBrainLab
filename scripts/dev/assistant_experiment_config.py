"""Pure bounded experiment identity and schedule; execution stays in the runner."""

from __future__ import annotations

import json
import math
import re
from collections import Counter

CONFIG_SCHEMA = "xbrainlab.assistant_experiment_config.v1"
PROTOCOL = "xbrainlab.assistant_experiment.v1"
MODELS = {
    "granite4": "ibm-granite/granite-4.0-micro",
    "granite33": "ibm-granite/granite-3.3-2b-instruct",
    "phi4": "microsoft/Phi-4-mini-instruct",
    "llama32": "meta-llama/Llama-3.2-3B-Instruct",
    "gemma3": "google/gemma-3-4b-it",
}


def experiment_identity(config: dict) -> dict:
    """Validate the one editable config; derive non-editable research policy."""
    required = {
        "schema",
        "split",
        "purpose",
        "models",
        "embedding_cache",
        "budget_seconds",
        "resource_inventory",
    }
    if (
        not isinstance(config, dict)
        or not required <= config.keys()
        or config.keys() - required - {"case_ids"}
    ):
        raise ValueError("Unknown or missing experiment config fields")
    split, purpose = config["split"], config["purpose"]
    if (
        config["schema"] != CONFIG_SCHEMA
        or split not in {"DEV", "VALID"}
        or purpose not in {"research", "engineering-smoke"}
    ):
        raise ValueError("Unsupported experiment schema, split or purpose")
    if purpose == "engineering-smoke" and split != "DEV":
        raise ValueError("Engineering smoke only permits DEV")
    ids = config.get("case_ids")
    if "case_ids" in config and (
        purpose != "engineering-smoke"
        or not isinstance(ids, list)
        or not ids
        or any(not isinstance(item, str) for item in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError(
            "Explicit unique case_ids are only allowed for DEV engineering smoke"
        )
    if purpose == "engineering-smoke" and ids is None:
        raise ValueError("Engineering smoke requires explicit case_ids")
    budget = config["budget_seconds"]
    if (
        type(budget) not in {int, float}
        or not math.isfinite(budget)
        or not 0 < budget <= (3600 if purpose == "engineering-smoke" else 14400)
    ):
        raise ValueError("Experiment budget exceeds the bounded policy")
    if any(
        not isinstance(config[key], str) or not config[key] or "\x00" in config[key]
        for key in ("embedding_cache", "resource_inventory")
    ):
        raise ValueError(
            "Explicit embedding cache and resource inventory paths are required"
        )
    models = config["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 5:
        raise ValueError("Select one to five approved models")
    seen = set()
    for model in models:
        if not isinstance(model, dict) or set(model) != {
            "alias",
            "candidate_index",
            "source",
            "model_cache",
        }:
            raise ValueError("Invalid selected model configuration")
        alias, candidate, source = (
            model["alias"],
            model["candidate_index"],
            model["source"],
        )
        if (
            not isinstance(alias, str)
            or alias not in MODELS
            or alias in seen
            or type(candidate) is not int
            or not 1 <= candidate <= 5
        ):
            raise ValueError("Unknown/duplicate model or candidate outside 1..5")
        seen.add(alias)
        if (
            not isinstance(source, dict)
            or set(source) != {"root", "head"}
            or not isinstance(source["head"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", source["head"])
        ):
            raise ValueError("Candidate source must have one exact source head/root")
        if any(
            not isinstance(value, str) or not value or "\x00" in value
            for value in (source["root"], model["model_cache"])
        ):
            raise ValueError("Candidate source/cache paths must be explicit")
    return _policy(split, purpose)


def _policy(split: str, purpose: str) -> dict:
    if (split, purpose) not in {
        ("DEV", "research"),
        ("VALID", "research"),
        ("DEV", "engineering-smoke"),
    }:
        raise ValueError("Unsupported experiment stage/purpose")
    return {
        "protocol": PROTOCOL,
        "stage": split,
        "purpose": purpose,
        "repeats": [0, 1, 2] if split == "VALID" else [0],
        "seed": 0,
        "rag_enabled": True,
        "max_candidates": 5,
        "projection_id": "dev-state-card-nuisance-v1",
        "qt_platform": "offscreen",
        "max_format_recovery_attempts": 1,
        "max_invalid_replacements": 1,
    }


def is_experiment_protocol(experiment: object) -> bool:
    """Recognize only an exact derived policy, never a protocol-name-only bypass."""
    if not isinstance(experiment, dict):
        return False
    try:
        return json.dumps(experiment, sort_keys=True, allow_nan=False) == json.dumps(
            _policy(experiment.get("stage"), experiment.get("purpose")),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return False


def build_selection(bank: dict, config: dict) -> dict:
    experiment = experiment_identity(config)
    cases = [case for case in bank["cases"] if case["split"] == experiment["stage"]]
    indexed = {case["case_id"]: case for case in cases}
    requested = config.get("case_ids", sorted(indexed))
    if not indexed or len(indexed) != len(cases) or set(requested) - indexed.keys():
        raise ValueError("Missing, duplicate or wrong-split selected cases")
    identifiers = sorted(requested)
    counts = dict(Counter(indexed[item]["decision"] for item in identifiers))
    if config["purpose"] == "research":
        expected = (
            {"Action": 144, "Clarification": 48, "No-call": 72}
            if config["split"] == "DEV"
            else {"Action": 54, "Clarification": 18, "No-call": 27}
        )
        families = Counter(indexed[item]["family_id"] for item in identifiers)
        if (
            counts != expected
            or len(families) != (66 if config["split"] == "DEV" else 33)
            or set(families.values()) != ({4} if config["split"] == "DEV" else {3})
        ):
            raise ValueError(
                "Research population does not match the frozen split denominator"
            )
    return {
        "schema": "xbrainlab.assistant_experiment_selection.v1",
        "source_sha256": bank["source"]["sha256"],
        "split": experiment["stage"],
        "selection_rule": "Explicit DEV engineering smoke"
        if "case_ids" in config
        else "All cases of the frozen split, case_id ascending",
        "counts": counts,
        "case_ids": identifiers,
        "phase_one_case_ids": identifiers,
        "phase_two_case_ids": [],
    }


def job_condition_identity(job: dict) -> str:
    if "candidate_index" not in job:
        return job["condition"]
    return f"{job['condition']}__candidate-{job['candidate_index']}__{job['split']}__repeat-{job['repeat']}"


def build_jobs(selection: dict, config: dict) -> list[dict]:
    experiment = experiment_identity(config)
    jobs = []
    for model in sorted(
        config["models"], key=lambda item: list(MODELS).index(item["alias"])
    ):
        for repeat in experiment["repeats"]:
            identity = {
                "condition": model["alias"] + "-rag-on",
                "candidate_index": model["candidate_index"],
                "split": config["split"],
                "repeat": repeat,
                "source_head": model["source"]["head"],
                "source_root": model["source"]["root"],
            }
            for case_id in selection["case_ids"]:
                jobs.append(
                    {
                        **identity,
                        "id": job_condition_identity(identity) + "__" + case_id,
                        "case_id": case_id,
                        "phase": 1,
                    }
                )
    return jobs
