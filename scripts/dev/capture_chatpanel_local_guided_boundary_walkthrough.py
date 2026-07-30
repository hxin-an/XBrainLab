#!/usr/bin/env python3
"""Capture a real Granite adaptive-workflow UI-handoff boundary proof."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from scripts.dev.active_checkout import assert_active_checkout_import
from scripts.dev.chatpanel_guided_boundary.runtime import cli_main

assert_active_checkout_import(ROOT)


def main() -> int:
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
