"""Bounded working-set estimates for external label/event carriers."""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from typing import Any, BinaryIO

# Returned label payloads remain resident across a batch, while parsers run
# sequentially. Keep those two costs explicit so per-file parser floors are not
# multiplied by large batches.
LABEL_CARRIER_PERSISTENT_MULTIPLIERS = {
    ".csv": 64.0,
    ".tsv": 64.0,
    ".txt": 4.0,
    ".mat": 8.0,
    ".npy": 4.0,
}
LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS = {
    ".csv": 8.0,
    ".tsv": 8.0,
    ".txt": 14.0,
    ".mat": 56.0,
    ".npy": 1.0,
}
LABEL_CARRIER_FILE_SIZE_MULTIPLIERS = {
    suffix: LABEL_CARRIER_PERSISTENT_MULTIPLIERS[suffix]
    + LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS[suffix]
    for suffix in LABEL_CARRIER_PERSISTENT_MULTIPLIERS
}
LABEL_CARRIER_PERSISTENT_FALLBACK_MULTIPLIER = 8.0
LABEL_CARRIER_PARSER_TRANSIENT_FALLBACK_MULTIPLIER = 8.0
LABEL_CARRIER_FILE_SIZE_FALLBACK_MULTIPLIER = (
    LABEL_CARRIER_PERSISTENT_FALLBACK_MULTIPLIER
    + LABEL_CARRIER_PARSER_TRANSIENT_FALLBACK_MULTIPLIER
)
TABULAR_PARSER_WORKING_SET_MULTIPLIER = LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS[
    ".csv"
]
TABULAR_RETURNED_OBJECT_MULTIPLIER = LABEL_CARRIER_PERSISTENT_MULTIPLIERS[".csv"]
TABULAR_MINIMUM_WORKING_SET_BYTES = 8 * 1024 * 1024
MAT_LABEL_UNCOMPRESSED_MEMORY_MULTIPLIER = 4.0
MAT_LABEL_MINIMUM_WORKING_SET_BYTES = 4 * 1024 * 1024
MAT_LABEL_PREFLIGHT_READ_BUDGET_BYTES = 1024 * 1024
SUPPORTED_EXTERNAL_LABEL_EXTENSIONS = frozenset(LABEL_CARRIER_FILE_SIZE_MULTIPLIERS)

_MAT_V5_HEADER_BYTES = 128
_MAT_V5_MI_MATRIX = 14
_MAT_V5_MI_COMPRESSED = 15
_MAT_V5_COMPRESSED_HEADER_READ_LIMIT_BYTES = 64 * 1024
_MAT_V5_MAX_TOP_LEVEL_ELEMENTS = 512


@dataclass
class MatPreflightReadBudget:
    """Count and cap every byte read by MAT header inspection."""

    limit_bytes: int
    bytes_read: int = 0

    @property
    def remaining_bytes(self) -> int:
        return max(self.limit_bytes - self.bytes_read, 0)

    def read(self, handle: BinaryIO, size: int) -> bytes:
        allowed = min(max(int(size), 0), self.remaining_bytes)
        if allowed <= 0:
            return b""
        payload = handle.read(allowed)
        self.bytes_read += len(payload)
        return payload

    @property
    def exhausted(self) -> bool:
        return self.remaining_bytes == 0


def create_mat_preflight_read_budget() -> MatPreflightReadBudget:
    """Create the one aggregate MAT inspection budget for an import check."""
    return MatPreflightReadBudget(MAT_LABEL_PREFLIGHT_READ_BUDGET_BYTES)


def estimate_label_carrier_working_set(
    path: str,
    *,
    suffix: str,
    file_bytes: int,
    mat_read_budget: MatPreflightReadBudget | None = None,
) -> tuple[int, dict[str, Any]]:
    """Estimate one carrier without materializing its rows or arrays."""
    multiplier = LABEL_CARRIER_FILE_SIZE_MULTIPLIERS.get(
        suffix,
        LABEL_CARRIER_FILE_SIZE_FALLBACK_MULTIPLIER,
    )
    persistent_multiplier = LABEL_CARRIER_PERSISTENT_MULTIPLIERS.get(
        suffix,
        LABEL_CARRIER_PERSISTENT_FALLBACK_MULTIPLIER,
    )
    transient_multiplier = LABEL_CARRIER_PARSER_TRANSIENT_MULTIPLIERS.get(
        suffix,
        LABEL_CARRIER_PARSER_TRANSIENT_FALLBACK_MULTIPLIER,
    )
    persistent_bytes = int(file_bytes * persistent_multiplier)
    parser_transient_bytes = int(file_bytes * transient_multiplier)
    file_size_estimate = persistent_bytes + parser_transient_bytes
    details: dict[str, Any] = {
        "estimate_source": "label_file_size_multiplier",
        "format_multiplier": multiplier,
        "persistent_multiplier": persistent_multiplier,
        "parser_transient_multiplier": transient_multiplier,
    }
    if suffix in {".csv", ".tsv"}:
        parser_working_set_bytes = max(
            parser_transient_bytes,
            TABULAR_MINIMUM_WORKING_SET_BYTES,
        )
        returned_object_bytes = persistent_bytes
        details.update(
            {
                "estimate_source": "tabular_parser_plus_returned_objects",
                "parser_working_set_bytes": parser_working_set_bytes,
                "returned_object_bytes": returned_object_bytes,
                "minimum_working_set_bytes": TABULAR_MINIMUM_WORKING_SET_BYTES,
                "persistent_bytes": returned_object_bytes,
                "parser_transient_bytes": parser_working_set_bytes,
            },
        )
        return parser_working_set_bytes + returned_object_bytes, details
    if suffix != ".mat":
        details.update(
            {
                "persistent_bytes": persistent_bytes,
                "parser_transient_bytes": parser_transient_bytes,
            }
        )
        return file_size_estimate, details

    budget = mat_read_budget or create_mat_preflight_read_budget()
    bytes_before = budget.bytes_read
    mat_uncompressed_bytes, _aggregate_bytes_read = _estimate_mat_v5_uncompressed_bytes(
        path, budget=budget
    )
    mat_preflight_bytes_read = budget.bytes_read - bytes_before
    details.update(
        {
            "mat_preflight_bytes_read": mat_preflight_bytes_read,
            "mat_preflight_total_bytes_read": budget.bytes_read,
            "mat_preflight_read_budget_bytes": budget.limit_bytes,
            "mat_preflight_budget_exhausted": budget.exhausted,
        },
    )
    if mat_uncompressed_bytes is None:
        details.update(
            {
                "estimate_source": "mat_file_size_or_minimum_fallback",
                "mat_uncompressed_bytes": None,
                "minimum_working_set_bytes": MAT_LABEL_MINIMUM_WORKING_SET_BYTES,
            }
        )
        parser_transient_bytes = max(
            parser_transient_bytes,
            MAT_LABEL_MINIMUM_WORKING_SET_BYTES,
        )
        details.update(
            {
                "persistent_bytes": persistent_bytes,
                "parser_transient_bytes": parser_transient_bytes,
            }
        )
        return persistent_bytes + parser_transient_bytes, details

    uncompressed_persistent_bytes = int(mat_uncompressed_bytes * 2.0)
    uncompressed_parser_transient_bytes = int(mat_uncompressed_bytes * 2.0)
    persistent_bytes = max(persistent_bytes, uncompressed_persistent_bytes)
    parser_transient_bytes = max(
        parser_transient_bytes,
        uncompressed_parser_transient_bytes,
        MAT_LABEL_MINIMUM_WORKING_SET_BYTES,
    )
    uncompressed_estimate = (
        uncompressed_persistent_bytes + uncompressed_parser_transient_bytes
    )
    details.update(
        {
            "estimate_source": "mat_header_or_file_size_multiplier",
            "mat_uncompressed_bytes": mat_uncompressed_bytes,
            "mat_uncompressed_memory_multiplier": (
                MAT_LABEL_UNCOMPRESSED_MEMORY_MULTIPLIER
            ),
            "minimum_working_set_bytes": MAT_LABEL_MINIMUM_WORKING_SET_BYTES,
            "persistent_bytes": persistent_bytes,
            "parser_transient_bytes": parser_transient_bytes,
        }
    )
    estimate = max(
        file_size_estimate,
        uncompressed_estimate,
        persistent_bytes + parser_transient_bytes,
    )
    return estimate, details


def _estimate_mat_v5_uncompressed_bytes(
    path: str,
    *,
    budget: MatPreflightReadBudget | None = None,
) -> tuple[int | None, int]:
    """Read bounded MAT v5 tags to estimate bytes without calling ``loadmat``."""
    budget = budget or create_mat_preflight_read_budget()
    try:
        file_bytes = max(int(os.path.getsize(path)), 0)
        if file_bytes < _MAT_V5_HEADER_BYTES + 8:
            return None, budget.bytes_read
        with open(path, "rb") as handle:
            header = budget.read(handle, _MAT_V5_HEADER_BYTES)
            endian = _mat_v5_endian(header)
            if endian is None:
                return None, budget.bytes_read
            offset = _MAT_V5_HEADER_BYTES
            total_uncompressed_bytes = 0
            element_count = 0
            while offset + 8 <= file_bytes:
                element_count += 1
                if element_count > _MAT_V5_MAX_TOP_LEVEL_ELEMENTS:
                    return None, budget.bytes_read
                handle.seek(offset)
                tag = budget.read(handle, 8)
                if len(tag) != 8:
                    return None, budget.bytes_read
                data_type, payload_bytes = struct.unpack(f"{endian}II", tag)
                payload_start = offset + 8
                payload_end = payload_start + payload_bytes
                if payload_end > file_bytes:
                    return None, budget.bytes_read

                if data_type == _MAT_V5_MI_MATRIX:
                    total_uncompressed_bytes += 8 + payload_bytes
                elif data_type == _MAT_V5_MI_COMPRESSED:
                    matrix_bytes, _compressed_bytes_read = (
                        _mat_v5_compressed_matrix_bytes(
                            handle,
                            payload_bytes=payload_bytes,
                            endian=endian,
                            read_limit_bytes=min(
                                _MAT_V5_COMPRESSED_HEADER_READ_LIMIT_BYTES,
                                budget.remaining_bytes,
                            ),
                            budget=budget,
                        )
                    )
                    if matrix_bytes is None:
                        return None, budget.bytes_read
                    total_uncompressed_bytes += matrix_bytes
                else:
                    total_uncompressed_bytes += 8 + payload_bytes

                offset = _next_mat_v5_element_offset(
                    handle,
                    payload_end=payload_end,
                    payload_bytes=payload_bytes,
                    data_type=data_type,
                    file_bytes=file_bytes,
                    endian=endian,
                    budget=budget,
                )
            return total_uncompressed_bytes or None, budget.bytes_read
    except (OSError, struct.error, zlib.error, ValueError):
        return None, budget.bytes_read


def _mat_v5_endian(header: bytes) -> str | None:
    indicator = header[126:128]
    if indicator == b"IM":
        return "<"
    if indicator == b"MI":
        return ">"
    return None


def _mat_v5_compressed_matrix_bytes(
    handle: BinaryIO,
    *,
    payload_bytes: int,
    endian: str,
    read_limit_bytes: int,
    budget: MatPreflightReadBudget,
) -> tuple[int | None, int]:
    if read_limit_bytes <= 0:
        return None, 0
    decompressor = zlib.decompressobj()
    prefix = b""
    remaining = payload_bytes
    read_bytes = 0
    while len(prefix) < 8 and remaining > 0 and read_bytes < read_limit_bytes:
        chunk_size = min(remaining, 4096, read_limit_bytes - read_bytes)
        chunk = budget.read(handle, chunk_size)
        if not chunk:
            return None, read_bytes
        remaining -= len(chunk)
        read_bytes += len(chunk)
        prefix += decompressor.decompress(chunk, 8 - len(prefix))
    if len(prefix) != 8:
        return None, read_bytes
    data_type, matrix_payload_bytes = struct.unpack(f"{endian}II", prefix)
    if data_type != _MAT_V5_MI_MATRIX:
        return None, read_bytes
    return 8 + matrix_payload_bytes, read_bytes


def _next_mat_v5_element_offset(
    handle: BinaryIO,
    *,
    payload_end: int,
    payload_bytes: int,
    data_type: int,
    file_bytes: int,
    endian: str,
    budget: MatPreflightReadBudget,
) -> int:
    if data_type != _MAT_V5_MI_COMPRESSED:
        return payload_end + ((-payload_bytes) % 8)
    if payload_end >= file_bytes:
        return file_bytes

    # SciPy omits padding for compressed top-level elements; other writers may
    # include it. Prefer the first plausible next tag without reading payloads.
    padded_end = payload_end + ((-payload_bytes) % 8)
    for candidate in (payload_end, padded_end):
        if _looks_like_mat_v5_tag(
            handle,
            offset=candidate,
            file_bytes=file_bytes,
            endian=endian,
            budget=budget,
        ):
            return candidate
    return payload_end


def _looks_like_mat_v5_tag(
    handle: BinaryIO,
    *,
    offset: int,
    file_bytes: int,
    endian: str,
    budget: MatPreflightReadBudget,
) -> bool:
    if offset + 8 > file_bytes:
        return offset == file_bytes
    handle.seek(offset)
    tag = budget.read(handle, 8)
    if len(tag) != 8:
        return False
    try:
        data_type, payload_bytes = struct.unpack(f"{endian}II", tag)
    except struct.error:
        return False
    return 1 <= data_type <= 18 and offset + 8 + payload_bytes <= file_bytes
