#!/usr/bin/env python3
"""Validate gold_set.json + train/test/val splits.

Performs comprehensive quality checks:

1. **Schema validation** — every example's parameters are checked against
   the actual tool definitions (required/optional/unknown fields).
2. **Structural checks** — duplicate IDs, missing fields, tool coverage.
3. **Split integrity** — no overlap between train/test/val, every gold-set
   item present in exactly one split, content equality.
4. **Manifest verification** — if a ``manifest.json`` exists, verify that
   the current gold-set checksum matches.

Exit code 0 = no errors, 1 = errors found.

Usage:
    python scripts/agent/benchmarks/validate_gold_set.py
    python scripts/agent/benchmarks/validate_gold_set.py --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
GOLD_SET_PATH = PROJECT_ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json"
DATA_DIR = SCRIPT_DIR / "data"

# ── Actual tool parameter schemas (from tool definition files) ──
#
# NOTE on "intent-only" design:
#   The gold-set tests *intent extraction* — it only lists the parameters
#   the user explicitly mentioned.  For tools like ``configure_training``
#   where epoch/batch_size/learning_rate are technically required, the
#   gold-set may omit them when the user didn't specify a value.  This
#   is by design and flagged as WARN, not ERROR.
#
TOOL_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "list_files": {"required": ["directory"], "optional": ["pattern"]},
    "load_data": {"required": ["paths"], "optional": []},
    "attach_labels": {"required": ["mapping"], "optional": ["label_format"]},
    "clear_dataset": {"required": [], "optional": []},
    "get_dataset_info": {"required": [], "optional": []},
    "generate_dataset": {
        "required": ["split_strategy", "training_mode"],
        "optional": ["test_ratio", "val_ratio"],
    },
    "apply_standard_preprocess": {
        "required": [],
        "optional": [
            "l_freq",
            "h_freq",
            "notch_freq",
            "rereference",
            "resample_rate",
            "normalize_method",
        ],
    },
    "apply_bandpass_filter": {"required": ["low_freq", "high_freq"], "optional": []},
    "apply_notch_filter": {"required": ["freq"], "optional": []},
    "resample_data": {"required": ["rate"], "optional": []},
    "normalize_data": {"required": ["method"], "optional": []},
    "set_reference": {"required": ["method"], "optional": []},
    "select_channels": {"required": ["channels"], "optional": []},
    "set_montage": {"required": ["montage_name"], "optional": []},
    "epoch_data": {
        "required": ["t_min", "t_max"],
        "optional": ["event_id", "baseline"],
    },
    "set_model": {"required": ["model_name"], "optional": []},
    "configure_training": {
        "required": ["epoch", "batch_size", "learning_rate"],
        "optional": ["repeat", "device", "optimizer", "save_checkpoints_every"],
    },
    "start_training": {"required": [], "optional": []},
    "switch_panel": {"required": ["panel_name"], "optional": ["view_mode"]},
}

EXPECTED_TOOLS = 19
VALID_CATEGORIES = {"dataset", "preprocess", "training", "ui", "complex"}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def file_md5(path: Path) -> str:
    """Return hex MD5 digest of *path*."""
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324


def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# 1. Schema Validation
# ═══════════════════════════════════════════════════════════════


def validate_schema(data: list[dict], *, strict: bool = False):
    """Validate gold-set entries against tool schemas.

    Returns ``(errors, warnings)``.
    """
    errors: list[str] = []
    warnings: list[str] = []
    id_counter: Counter = Counter()
    tool_coverage: Counter = Counter()
    category_counter: Counter = Counter()

    for item in data:
        # Required top-level fields
        for field in ("id", "category", "input", "expected_tool_calls"):
            if field not in item:
                errors.append(f"[SCHEMA] Item missing '{field}': {item}")
                continue

        item_id = item.get("id", "??")
        category = item.get("category", "unknown")
        id_counter[item_id] += 1
        category_counter[category] += 1

        if category not in VALID_CATEGORIES:
            errors.append(f"[SCHEMA] {item_id}: Unknown category '{category}'")

        if not item.get("input", "").strip():
            errors.append(f"[SCHEMA] {item_id}: Empty input field")

        for tc in item.get("expected_tool_calls", []):
            tool_name = tc.get("tool_name")
            params = tc.get("parameters", {})
            tool_coverage[tool_name] += 1

            if tool_name not in TOOL_SCHEMAS:
                errors.append(f"[SCHEMA] {item_id}: Unknown tool '{tool_name}'")
                continue

            schema = TOOL_SCHEMAS[tool_name]

            # Missing required params
            for req in schema["required"]:
                if req not in params:
                    msg = f"{item_id}: Missing required param '{req}' for {tool_name}"
                    if strict:
                        errors.append(f"[SCHEMA] {msg}")
                    else:
                        warnings.append(f"[INTENT] {msg}")

            # Unknown params
            all_known = set(schema["required"] + schema["optional"])
            for p in params:
                if p not in all_known:
                    errors.append(
                        f"[SCHEMA] {item_id}: Unknown param '{p}' for {tool_name}"
                    )

    # Duplicate IDs
    for k, v in id_counter.items():
        if v > 1:
            errors.append(f"[SCHEMA] Duplicate ID: '{k}' appears {v} times")

    # Tool coverage
    for tool_name in TOOL_SCHEMAS:
        if tool_name not in tool_coverage:
            errors.append(f"[COVERAGE] Tool '{tool_name}' has ZERO examples")

    return errors, warnings, tool_coverage, category_counter


# ═══════════════════════════════════════════════════════════════
# 2. Split Integrity
# ═══════════════════════════════════════════════════════════════


def validate_splits(data: list[dict]):
    """Verify train/test/val splits are consistent with gold_set.

    Returns ``(errors, info_lines)``.
    """
    errors: list[str] = []
    info: list[str] = []

    split_files = {
        "train": DATA_DIR / "train.json",
        "test": DATA_DIR / "test.json",
        "val": DATA_DIR / "val.json",
    }

    # Check files exist
    for name, path in split_files.items():
        if not path.exists():
            errors.append(f"[SPLIT] {name}.json not found at {path}")

    if errors:
        return errors, info

    splits = {name: load_json(path) for name, path in split_files.items()}

    # Sizes
    total = sum(len(s) for s in splits.values())
    info.append(
        f"Split sizes: train={len(splits['train'])} "
        f"test={len(splits['test'])} val={len(splits['val'])} "
        f"(sum={total}, gold={len(data)})"
    )
    if total != len(data):
        errors.append(f"[SPLIT] Sum of splits ({total}) != gold_set size ({len(data)})")

    # ID sets
    id_sets = {name: {x["id"] for x in items} for name, items in splits.items()}
    gold_ids = {x["id"] for x in data}

    # Overlap
    for a, b in [("train", "test"), ("train", "val"), ("test", "val")]:
        overlap = id_sets[a] & id_sets[b]
        if overlap:
            errors.append(f"[SPLIT] Overlap {a}-{b}: {overlap}")

    # Missing / Extra
    all_split_ids = id_sets["train"] | id_sets["test"] | id_sets["val"]
    missing = gold_ids - all_split_ids
    extra = all_split_ids - gold_ids
    if missing:
        errors.append(f"[SPLIT] Missing from splits: {missing}")
    if extra:
        errors.append(f"[SPLIT] Extra in splits (not in gold_set): {extra}")

    # Content equality
    gold_map = {x["id"]: x for x in data}
    mismatches = 0
    for name, items in splits.items():
        for item in items:
            g = gold_map.get(item["id"])
            if g is None:
                continue  # already caught
            if item["input"] != g["input"]:
                errors.append(f"[SPLIT] {item['id']} input differs in {name}")
                mismatches += 1
            elif json.dumps(item["expected_tool_calls"], sort_keys=True) != json.dumps(
                g["expected_tool_calls"], sort_keys=True
            ):
                errors.append(
                    f"[SPLIT] {item['id']} expected_tool_calls differs in {name}"
                )
                mismatches += 1

    info.append(f"Content mismatches: {mismatches}")
    return errors, info


# ═══════════════════════════════════════════════════════════════
# 3. Manifest Verification
# ═══════════════════════════════════════════════════════════════


def validate_manifest():
    """Check if splits are up-to-date with gold_set via manifest.

    Returns ``(errors, info_lines)``.
    """
    errors: list[str] = []
    info: list[str] = []
    manifest_path = DATA_DIR / "manifest.json"

    if not manifest_path.exists():
        info.append("No manifest.json found — cannot verify data freshness")
        return errors, info

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    current_md5 = file_md5(GOLD_SET_PATH)
    expected_md5 = manifest.get("gold_set_md5")

    if current_md5 != expected_md5:
        errors.append(
            f"[MANIFEST] gold_set.json has changed since last split! "
            f"Expected MD5={expected_md5}, got {current_md5}. "
            f"Re-run split_dataset.py."
        )
    else:
        info.append(f"Manifest OK — gold_set MD5={current_md5}")

    return errors, info


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser(description="Validate gold_set + splits")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing required params as errors (default: warnings)",
    )
    args = ap.parse_args()

    if not GOLD_SET_PATH.exists():
        print(f"ERROR: gold_set.json not found at {GOLD_SET_PATH}")
        sys.exit(1)

    data = load_json(GOLD_SET_PATH)
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. Schema
    print("=" * 60)
    print("1. Schema Validation")
    print("=" * 60)
    errs, warns, tool_cov, cat_cov = validate_schema(data, strict=args.strict)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    print(f"Total items: {len(data)}")
    print(f"Categories: {dict(cat_cov)}")
    print(f"\nTool Coverage ({len(tool_cov)}/{EXPECTED_TOOLS}):")
    for t, c in sorted(tool_cov.items()):
        print(f"  {t:30s}: {c}")

    # 2. Split Integrity
    print(f"\n{'=' * 60}")
    print("2. Split Integrity")
    print("=" * 60)
    split_errs, split_info = validate_splits(data)
    all_errors.extend(split_errs)
    for line in split_info:
        print(f"  {line}")

    # 3. Manifest
    print(f"\n{'=' * 60}")
    print("3. Manifest Verification")
    print("=" * 60)
    man_errs, man_info = validate_manifest()
    all_errors.extend(man_errs)
    for line in man_info:
        print(f"  {line}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)

    if all_errors:
        print(f"\n  ERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"    {e}")

    if all_warnings:
        print(f"\n  WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"    {w}")

    if not all_errors and not all_warnings:
        print("  All checks passed!")
    elif not all_errors:
        print(f"\n  Result: PASS ({len(all_warnings)} intent-design warnings)")
    else:
        print(
            f"\n  Result: FAIL ({len(all_errors)} errors, {len(all_warnings)} warnings)"
        )

    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
