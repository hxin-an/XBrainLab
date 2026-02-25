"""Parse slipcover JSON coverage output and print sorted missing-line report."""

import json
import re
import sys

OMIT_PATTERNS = [
    r"llm[\\/]core[\\/]models[\\/]",
    r"__pycache__",
    r"saliency_3d_engine\.py",
    r"plot_3d_head\.py",
    r"plot_3d_view\.py",
]

if len(sys.argv) > 1:
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
else:
    d = json.load(sys.stdin)
items = []
for f, v in d["files"].items():
    # Skip omitted patterns
    if any(re.search(p, f) for p in OMIT_PATTERNS):
        continue
    miss = v.get("missing_lines", [])
    covered = v.get("summary", {}).get("covered_lines", 0)
    total = covered + len(miss)
    pct = round(covered / total * 100) if total else 100
    if miss:
        items.append((f, len(miss), pct, miss))

items.sort(key=lambda x: -x[1])
total_miss = sum(x[1] for x in items)
total_stmts = 0
for f, v in d["files"].items():
    if any(re.search(p, f) for p in OMIT_PATTERNS):
        continue
    covered = v.get("summary", {}).get("covered_lines", 0)
    miss_len = len(v.get("missing_lines", []))
    total_stmts += covered + miss_len
total_covered = total_stmts - total_miss
pct_all = round(total_covered / total_stmts * 100) if total_stmts else 100
print(f"TOTAL: {total_stmts} stmts, {total_miss} miss, {pct_all}%")
target_miss = int(total_stmts * 0.1)
print(
    f"Target 90%: max {target_miss} miss allowed, need to cover {total_miss - target_miss} more lines"
)
print()
for f, miss_count, pct, _lines in items:
    print(f"{f}: {miss_count} miss ({pct}%)")
