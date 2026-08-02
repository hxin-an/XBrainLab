#!/usr/bin/env python3
"""Capture bounded exact-Granite ChatPanel long-session evidence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from scripts.dev.active_checkout import assert_active_checkout_import
from scripts.dev.chatpanel_long_session.cli import cli_main

assert_active_checkout_import(ROOT)


def main() -> int:
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
