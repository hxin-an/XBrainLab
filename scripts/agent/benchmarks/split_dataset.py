#!/usr/bin/env python3
"""Split gold_set.json into train / test / val sets.

Performs stratified splitting by category so every category is
represented proportionally in each partition.

Default split ratios: 60% train, 20% test, 20% val.

Generates a ``manifest.json`` alongside the splits so that
``validate_gold_set.py`` can detect stale splits.

Usage:
    python scripts/agent/benchmarks/split_dataset.py
    python scripts/agent/benchmarks/split_dataset.py --train 0.6 --test 0.2 --val 0.2
"""

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
GOLD_SET_PATH = PROJECT_ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json"
OUTPUT_DIR = SCRIPT_DIR / "data"


def load_gold_set(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def stratified_split(
    data: list[dict],
    train_ratio: float = 0.6,
    test_ratio: float = 0.2,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split *data* into train/test/val, stratified by ``category``."""
    if abs(train_ratio + test_ratio + val_ratio - 1.0) >= 1e-6:
        msg = "Ratios must sum to 1.0"
        raise ValueError(msg)

    rng = random.Random(seed)  # noqa: S311

    # Group by category
    by_category: dict[str, list[dict]] = defaultdict(list)
    for item in data:
        by_category[item.get("category", "unknown")].append(item)

    train, test, val = [], [], []
    for _cat, items in sorted(by_category.items()):
        rng.shuffle(items)
        n = len(items)
        n_test = max(1, round(n * test_ratio))
        n_val = max(1, round(n * val_ratio))
        n_train = n - n_test - n_val
        if n_train < 1:
            # Very small category - at least 1 train sample
            n_train = 1
            remaining = n - n_train
            n_test = remaining // 2
            n_val = remaining - n_test

        train.extend(items[:n_train])
        test.extend(items[n_train : n_train + n_test])
        val.extend(items[n_train + n_test :])

    return train, test, val


def save_json(data: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"  Saved {len(data):>3} samples → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split gold_set into train/test/val")
    parser.add_argument("--train", type=float, default=0.6, help="Train ratio")
    parser.add_argument("--test", type=float, default=0.2, help="Test ratio")
    parser.add_argument("--val", type=float, default=0.2, help="Val ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print(f"Loading gold set from: {GOLD_SET_PATH}")
    data = load_gold_set(GOLD_SET_PATH)
    print(f"Total samples: {len(data)}")

    # Count per category
    cat_counts = Counter(item.get("category", "unknown") for item in data)
    print("\nCategory distribution:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"  {cat:>12}: {cnt}")

    train, test, val = stratified_split(
        data,
        train_ratio=args.train,
        test_ratio=args.test,
        val_ratio=args.val,
        seed=args.seed,
    )

    print(f"\nSplit result (seed={args.seed}):")
    print(f"  Train: {len(train)}")
    print(f"  Test:  {len(test)}")
    print(f"  Val:   {len(val)}")

    # Per-category breakdown
    for label, subset in [("train", train), ("test", test), ("val", val)]:
        cats = Counter(item.get("category", "unknown") for item in subset)
        details = ", ".join(f"{c}={n}" for c, n in sorted(cats.items()))
        print(f"  {label:>5} categories: {details}")

    save_json(train, OUTPUT_DIR / "train.json")
    save_json(test, OUTPUT_DIR / "test.json")
    save_json(val, OUTPUT_DIR / "val.json")

    # Generate manifest for integrity verification
    gold_md5 = hashlib.md5(GOLD_SET_PATH.read_bytes()).hexdigest()  # noqa: S324
    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "gold_set_path": str(GOLD_SET_PATH),
        "gold_set_md5": gold_md5,
        "gold_set_count": len(data),
        "seed": args.seed,
        "ratios": {"train": args.train, "test": args.test, "val": args.val},
        "split_counts": {
            "train": len(train),
            "test": len(test),
            "val": len(val),
        },
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  Manifest → {manifest_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
