"""Lightweight CLI boundary for exact-Granite long-session evidence."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from argparse import Namespace
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from scripts.dev.chatpanel_long_session.evidence import (
    validate_artifact_directory,
)
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID

DEFAULT_TIMEOUT_SECONDS = 360
MAX_TIMEOUT_SECONDS = 600
MIN_TIMEOUT_SECONDS = 120


def parse_args(argv: Sequence[str] | None = None) -> Namespace:
    """Parse an exact-model capture or post-hoc validation command."""
    parser = argparse.ArgumentParser()
    environment_cache = os.environ.get("XBRAINLAB_MODEL_CACHE_DIR", "").strip()
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Caller-provided directory used for every mutable capture artifact.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        required=not environment_cache,
        default=Path(environment_cache) if environment_cache else None,
        help=(
            "Existing read-only model cache containing the pinned Granite snapshot. "
            "Defaults to the handoff registry's XBRAINLAB_MODEL_CACHE_DIR."
        ),
    )
    parser.add_argument(
        "--model",
        choices=(PRIMARY_LOCAL_MODEL_ID,),
        default=PRIMARY_LOCAL_MODEL_ID,
        help="Exact supported product model; fallback models are rejected.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_bounded_timeout,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Total capture budget, including startup, turns, and provenance sealing.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Revalidate existing evidence against current source and model cache.",
    )
    return parser.parse_args(argv)


def prepare_capture_output(output_dir: Path, *, cache_dir: Path) -> Path:
    """Create one empty output root that cannot overlap the model cache."""
    cache = cache_dir.expanduser().resolve(strict=True)
    if not cache.is_dir():
        raise ValueError("Model cache must be an existing directory.")
    output = output_dir.expanduser().resolve(strict=False)
    if _paths_overlap(output, cache):
        raise ValueError("Output directory and model cache must not overlap.")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Capture output directory must be empty.")
    return output


@contextmanager
def isolated_capture_write_environment(
    output_dir: Path,
    *,
    cache_dir: Path,
) -> Iterator[Path]:
    """Route mutable application and dependency paths below the output root."""
    output = output_dir.expanduser().resolve(strict=True)
    cache = cache_dir.expanduser().resolve(strict=True)
    previous: dict[str, str | None] = {}
    with tempfile.TemporaryDirectory(prefix=".runtime-", dir=output) as raw_root:
        root = Path(raw_root).resolve()
        values = {
            "XBRAINLAB_CONFIG_DIR": root / "config",
            "XBRAINLAB_DATA_DIR": root / "data",
            "XBRAINLAB_CACHE_DIR": root / "cache",
            "XBRAINLAB_LOG_DIR": root / "logs",
            "XBRAINLAB_RAG_CACHE_DIR": root / "rag",
            "XBRAINLAB_MODEL_CACHE_DIR": cache,
            "XDG_CONFIG_HOME": root / "xdg-config",
            "XDG_CACHE_HOME": root / "xdg-cache",
            "XDG_DATA_HOME": root / "xdg-data",
            "XDG_STATE_HOME": root / "xdg-state",
            "MPLCONFIGDIR": root / "matplotlib",
            "HF_HOME": root / "huggingface",
            "HF_DATASETS_CACHE": root / "huggingface" / "datasets",
            "SENTENCE_TRANSFORMERS_HOME": root / "sentence-transformers",
            "TORCH_HOME": root / "torch",
            "PYTORCH_KERNEL_CACHE_PATH": root / "torch-kernels",
            "CUDA_CACHE_PATH": root / "cuda",
            "NUMBA_CACHE_DIR": root / "numba",
            "TMPDIR": root / "tmp",
        }
        flags = {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "MNE_DONTWRITE_HOME": "true",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            for name, path in values.items():
                previous[name] = os.environ.get(name)
                if name != "XBRAINLAB_MODEL_CACHE_DIR":
                    path.mkdir(parents=True, exist_ok=True)
                os.environ[name] = str(path)
            for name, value in flags.items():
                previous[name] = os.environ.get(name)
                os.environ[name] = value
            yield root
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def cli_main(argv: Sequence[str] | None = None) -> int:
    """Run capture lazily, or strictly revalidate an existing artifact bundle."""
    args = parse_args(argv)
    try:
        cache_dir = args.cache_dir.expanduser().resolve(strict=True)
        if args.validate_only:
            output_dir = _existing_output_directory(args.output_dir)
        else:
            output_dir = prepare_capture_output(
                args.output_dir,
                cache_dir=cache_dir,
            )
    except (OSError, ValueError) as exc:
        print(f"Long-session evidence preflight failed: {exc}", file=sys.stderr)
        return 2

    with isolated_capture_write_environment(output_dir, cache_dir=cache_dir):
        if args.validate_only:
            return _validate_existing(output_dir, cache_dir=cache_dir)
        from scripts.dev.chatpanel_long_session.runtime import run_capture

        return run_capture(
            output_dir=output_dir,
            cache_dir=cache_dir,
            requested_model_id=args.model,
            timeout_seconds=args.timeout_seconds,
        )


def _validate_existing(output_dir: Path, *, cache_dir: Path) -> int:
    from scripts.dev.local_assistant_capture_runtime import (
        collect_capture_source_identity,
        collect_model_identity,
    )

    current_source = collect_capture_source_identity(refresh=True)
    current_model = collect_model_identity(
        requested_model_id=PRIMARY_LOCAL_MODEL_ID,
        loaded_model_id=PRIMARY_LOCAL_MODEL_ID,
        cache_dir=str(cache_dir),
    )
    ok, reason = validate_artifact_directory(
        output_dir,
        current_source_identity=current_source,
        current_model_identity=current_model,
    )
    print(f"status={'passed' if ok else 'failed'}")
    if reason:
        print(f"reason={reason}", file=sys.stderr)
    return 0 if ok else 1


def _bounded_timeout(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be an integer") from exc
    if value < MIN_TIMEOUT_SECONDS or value > MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    return value


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _existing_output_directory(output_dir: Path) -> Path:
    resolved = output_dir.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("Validation output must be an existing directory.")
    return resolved
