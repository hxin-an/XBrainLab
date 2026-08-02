#!/usr/bin/env python3
"""Start a Windows gate command only after its parent establishes containment."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from typing import BinaryIO

HANDSHAKE_TOKEN = b"1"
HANDSHAKE_FAILURE_EXIT_CODE = 125


def run_after_handshake(argv: Sequence[str], handshake: BinaryIO) -> int:
    """Run an exact argv only after the parent releases the one-byte barrier."""
    command = [str(part) for part in argv]
    if not command or handshake.read(1) != HANDSHAKE_TOKEN:
        return HANDSHAKE_FAILURE_EXIT_CODE
    completed = subprocess.run(command, check=False)  # noqa: S603
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the separator and inherit target stdio from this bootstrap."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--"]:
        args = args[1:]
    return run_after_handshake(args, sys.stdin.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
