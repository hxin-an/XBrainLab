#!/usr/bin/env python3
"""Run the XBrainLab ApplicationService MCP server over stdio."""

from __future__ import annotations

import logging

from XBrainLab.mcp import run_stdio


def main() -> int:
    logging.getLogger("XBrainLab").setLevel(logging.WARNING)
    return run_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
