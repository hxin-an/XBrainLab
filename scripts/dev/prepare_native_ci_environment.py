#!/usr/bin/env python3
"""Prepare one isolated mutable-path environment for native CI probes."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.dev.run_native_platform_product_smoke import REQUIRED_ISOLATED_ENV

_RELATIVE_PATHS = {
    "TEMP": "temp",
    "TMP": "temp",
    "XBRAINLAB_CONFIG_DIR": "config",
    "XBRAINLAB_DATA_DIR": "data",
    "XBRAINLAB_CACHE_DIR": "cache",
    "XBRAINLAB_LOG_DIR": "logs",
    "XBRAINLAB_MODEL_CACHE_DIR": "models",
    "HF_HOME": "huggingface cache",
    "MPLCONFIGDIR": "matplotlib cache",
}


def build_isolated_environment(root: str | Path) -> dict[str, str]:
    """Create and return the exact mutable directories below ``root``."""
    resolved_root = Path(root).expanduser().resolve()
    if " " not in resolved_root.name or not any(
        ord(char) > 127 for char in resolved_root.name
    ):
        raise ValueError("The native CI root must contain a space and non-ASCII text.")
    environment: dict[str, str] = {}
    for variable in REQUIRED_ISOLATED_ENV:
        path = resolved_root / _RELATIVE_PATHS[variable]
        path.mkdir(parents=True, exist_ok=True)
        environment[variable] = str(path)
    return environment


def write_github_environment(path: Path, environment: dict[str, str]) -> None:
    """Append simple absolute path values to GitHub's environment file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for name, value in sorted(environment.items()):
            if "\n" in name or "\n" in value or "\r" in name or "\r" in value:
                raise ValueError("GitHub environment values must be single-line text.")
            stream.write(f"{name}={value}\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    environment = build_isolated_environment(args.root)
    environment["XBL_NATIVE_ROOT"] = str(Path(args.root).expanduser().resolve())
    write_github_environment(args.github_env, environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
