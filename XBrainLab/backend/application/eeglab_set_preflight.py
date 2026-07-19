"""Bounded EEGLAB ``.set`` signal-header inspection.

The inspector reads MATLAB element metadata and small scalar/string values only.
Numeric EEG payloads are never read. Compressed streams have a hard decoded-byte
budget so a signal hidden behind a large field fails closed instead of forcing
decompression of the recording.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

MAT_FILE_HEADER_BYTES = 128
MAT_COMPRESSED_HEADER_BUDGET_BYTES = 1_048_576
MAT_REFERENCE_MAX_BYTES = 4_096
MAT_STREAM_CHUNK_BYTES = 65_536
EEGLAB_EXTERNAL_DTYPE = "float32"
EEGLAB_EXTERNAL_DTYPE_BYTES = 4

_MI_INT8 = 1
_MI_UINT8 = 2
_MI_INT16 = 3
_MI_UINT16 = 4
_MI_INT32 = 5
_MI_UINT32 = 6
_MI_SINGLE = 7
_MI_DOUBLE = 9
_MI_INT64 = 12
_MI_UINT64 = 13
_MI_MATRIX = 14
_MI_COMPRESSED = 15
_MI_UTF8 = 16
_MI_UTF16 = 17
_MI_UTF32 = 18

_MX_STRUCT = 2
_MX_CHAR = 4
_MAT_ARRAY_FLAG_COMPLEX = 0x0800
_NUMERIC_DTYPES: dict[int, tuple[str, int, str]] = {
    _MI_INT8: ("int8", 1, "b"),
    _MI_UINT8: ("uint8", 1, "B"),
    _MI_INT16: ("int16", 2, "h"),
    _MI_UINT16: ("uint16", 2, "H"),
    _MI_INT32: ("int32", 4, "i"),
    _MI_UINT32: ("uint32", 4, "I"),
    _MI_SINGLE: ("float32", 4, "f"),
    _MI_DOUBLE: ("float64", 8, "d"),
    _MI_INT64: ("int64", 8, "q"),
    _MI_UINT64: ("uint64", 8, "Q"),
}
_TOP_LEVEL_FIELDS = frozenset(
    {"EEG", "data", "datfile", "nbchan", "pnts", "trials", "srate"}
)
_STRUCT_FIELDS = frozenset({"data", "datfile", "nbchan", "pnts", "trials", "srate"})


@dataclass(frozen=True, slots=True)
class EeglabSetHeaderInspection:
    """Signal storage metadata discovered without reading EEG samples."""

    path: str
    bound_known: bool
    storage_mode: str
    reason_code: str
    reason: str
    source_shape: tuple[int, ...] | None = None
    source_dtype: str | None = None
    data_reference: str | None = None
    external_data_file: str | None = None
    external_data_file_bytes: int | None = None
    channels: int | None = None
    time_samples: int | None = None
    trials: int | None = None
    sampling_rate_hz: float | None = None
    mat_format: str = "mat_v5"
    compressed_header: bool = False
    header_bytes_read: int = 0
    decoded_header_bytes: int = 0


@dataclass(frozen=True, slots=True)
class _Tag:
    type_code: int
    nbytes: int
    inline_data: bytes | None = None


@dataclass(frozen=True, slots=True)
class _MatrixValue:
    name: str
    kind: str
    shape: tuple[int, ...]
    dtype: str | None = None
    scalar: float | None = None
    text: str | None = None


@dataclass(slots=True)
class _HeaderAccumulator:
    source_shape: tuple[int, ...] | None = None
    source_dtype: str | None = None
    data_reference: str | None = None
    datfile_reference: str | None = None
    channels: int | None = None
    time_samples: int | None = None
    trials: int | None = None
    sampling_rate_hz: float | None = None

    @property
    def reference(self) -> str | None:
        return self.data_reference or self.datfile_reference

    @property
    def external_shape(self) -> tuple[int, int, int] | None:
        channels = self.channels
        time_samples = self.time_samples
        trials = self.trials
        if (
            isinstance(channels, int)
            and channels > 0
            and isinstance(time_samples, int)
            and time_samples > 0
            and isinstance(trials, int)
            and trials > 0
        ):
            return channels, time_samples, trials
        return None

    @property
    def external_shape_complete(self) -> bool:
        return self.external_shape is not None


class _MatHeaderError(RuntimeError):
    reason_code = "mat_header_invalid"


class _MatHeaderBudgetError(_MatHeaderError):
    reason_code = "mat_header_budget_exceeded"


class _MatHeaderUnsupportedError(_MatHeaderError):
    reason_code = "mat_header_unsupported"


class _FileReader:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.bytes_read = 0

    def tell(self) -> int:
        return int(self.handle.tell())

    def read(self, size: int) -> bytes:
        if size < 0:
            raise _MatHeaderError("Negative MAT read size.")
        data = self.handle.read(size)
        self.bytes_read += len(data)
        if len(data) != size:
            raise _MatHeaderError("Unexpected end of MATLAB file.")
        return data

    def skip(self, size: int) -> None:
        if size < 0:
            raise _MatHeaderError("Negative MAT skip size.")
        self.handle.seek(size, os.SEEK_CUR)

    def seek(self, position: int) -> None:
        self.handle.seek(position, os.SEEK_SET)

    def require_payload_extent(self, size: int) -> None:
        """Verify a declared payload exists without reading its sample bytes."""
        if size < 0:
            raise _MatHeaderError("Negative MAT payload size.")
        current = self.tell()
        self.handle.seek(0, os.SEEK_END)
        end = int(self.handle.tell())
        self.handle.seek(current, os.SEEK_SET)
        if current + size > end:
            raise _MatHeaderError("MATLAB numeric payload is truncated.")


class _ZlibReader:
    def __init__(
        self,
        handle: BinaryIO,
        *,
        compressed_bytes: int,
        decoded_limit: int = MAT_COMPRESSED_HEADER_BUDGET_BYTES,
    ) -> None:
        self.handle = handle
        self.remaining_compressed_bytes = compressed_bytes
        self.total_compressed_bytes = compressed_bytes
        self.decoded_limit = decoded_limit
        self.position = 0
        self.compressed_bytes_read = 0
        self._decompressor = zlib.decompressobj()
        self._pending = b""
        self._buffer = bytearray()

    def tell(self) -> int:
        return self.position

    def read(self, size: int) -> bytes:
        if size < 0:
            raise _MatHeaderError("Negative compressed MAT read size.")
        if self.position + size > self.decoded_limit:
            raise _MatHeaderBudgetError(
                "Compressed EEGLAB header exceeds the bounded decode budget."
            )
        self._fill(size)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        self.position += size
        return data

    def skip(self, size: int) -> None:
        remaining = size
        while remaining:
            chunk = min(remaining, MAT_STREAM_CHUNK_BYTES)
            self.read(chunk)
            remaining -= chunk

    def require_payload_extent(self, size: int) -> None:
        """Fail closed when a compressed numeric payload is not reachable.

        Fully decoding a large embedded EEG array would defeat bounded RAM
        preflight. Peeking one decoded byte proves that the stream did not end at
        the data tag; a conservative DEFLATE lower bound rejects declarations
        that cannot physically encode the advertised payload.
        """
        if size < 0:
            raise _MatHeaderError("Negative compressed MAT payload size.")
        if size == 0:
            return
        self._fill(1)
        minimum_payload_bytes = math.ceil(math.ceil(size / 258) * 2 / 8)
        if self.total_compressed_bytes < minimum_payload_bytes:
            raise _MatHeaderError(
                "Compressed MATLAB element cannot contain its declared numeric payload."
            )

    def _fill(self, target_size: int) -> None:
        while len(self._buffer) < target_size:
            needed = target_size - len(self._buffer)
            if self._pending:
                chunk = self._pending
                self._pending = b""
            elif self.remaining_compressed_bytes:
                read_size = min(
                    MAT_STREAM_CHUNK_BYTES,
                    self.remaining_compressed_bytes,
                )
                chunk = self.handle.read(read_size)
                if len(chunk) != read_size:
                    raise _MatHeaderError("Truncated compressed MATLAB element.")
                self.remaining_compressed_bytes -= read_size
                self.compressed_bytes_read += read_size
            else:
                flushed = self._decompressor.flush(needed)
                if flushed:
                    self._buffer.extend(flushed)
                    continue
                raise _MatHeaderError("Truncated decoded MATLAB element.")

            output = self._decompressor.decompress(chunk, needed)
            self._buffer.extend(output)
            self._pending = self._decompressor.unconsumed_tail
            if not output and not self._pending and not self.remaining_compressed_bytes:
                flushed = self._decompressor.flush(needed)
                if flushed:
                    self._buffer.extend(flushed)
                    continue
                raise _MatHeaderError("Compressed MATLAB element ended early.")


def inspect_eeglab_set_header(path: str | Path) -> EeglabSetHeaderInspection:
    """Inspect one EEGLAB signal header without materializing signal samples."""
    set_path = Path(path).expanduser()
    try:
        with set_path.open("rb") as handle:
            file_reader = _FileReader(handle)
            header = file_reader.read(MAT_FILE_HEADER_BYTES)
            if header.startswith(b"MATLAB 7.3 MAT-file"):
                return _unknown(
                    set_path,
                    reason_code="mat_v73_not_bounded",
                    reason=(
                        "MATLAB 7.3 EEGLAB signal storage is not bounded by the "
                        "MAT v5 header inspector."
                    ),
                    mat_format="mat_v7.3",
                    header_bytes_read=file_reader.bytes_read,
                )
            endian = _mat_v5_endian(header)
            accumulator = _HeaderAccumulator()
            compressed_header = False
            decoded_header_bytes = 0
            while True:
                outer_start = file_reader.tell()
                if outer_start >= set_path.stat().st_size:
                    break
                tag = _read_tag(file_reader, endian)
                if tag.inline_data is not None:
                    raise _MatHeaderUnsupportedError(
                        "Top-level small MATLAB elements are unsupported."
                    )
                payload_start = file_reader.tell()
                payload_end = payload_start + tag.nbytes
                if tag.type_code == _MI_COMPRESSED:
                    compressed_header = True
                    compressed_reader = _ZlibReader(
                        handle,
                        compressed_bytes=tag.nbytes,
                    )
                    inner_tag = _read_tag(compressed_reader, endian)
                    _require_matrix_tag(inner_tag)
                    value = _parse_matrix(
                        compressed_reader,
                        inner_tag.nbytes,
                        endian=endian,
                        accumulator=accumulator,
                        top_level=True,
                    )
                    decoded_header_bytes = max(
                        decoded_header_bytes,
                        compressed_reader.tell(),
                    )
                    file_reader.seek(payload_end + _padding(tag.nbytes))
                elif tag.type_code == _MI_MATRIX:
                    value = _parse_matrix(
                        file_reader,
                        tag.nbytes,
                        endian=endian,
                        accumulator=accumulator,
                        top_level=True,
                    )
                    file_reader.seek(payload_end + _padding(tag.nbytes))
                else:
                    file_reader.seek(payload_end + _padding(tag.nbytes))
                    continue

                _apply_matrix_value(accumulator, value)
                inspection = _inspection_if_complete(
                    set_path,
                    accumulator,
                    compressed_header=compressed_header,
                    header_bytes_read=file_reader.bytes_read,
                    decoded_header_bytes=decoded_header_bytes,
                )
                if inspection is not None:
                    return inspection

            inspection = _inspection_if_complete(
                set_path,
                accumulator,
                compressed_header=compressed_header,
                header_bytes_read=file_reader.bytes_read,
                decoded_header_bytes=decoded_header_bytes,
                final=True,
            )
            if inspection is not None:
                return inspection
            return _unknown(
                set_path,
                reason_code="eeglab_data_header_missing",
                reason="EEGLAB data storage metadata was not found in the MAT header.",
                compressed_header=compressed_header,
                header_bytes_read=file_reader.bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
    except _MatHeaderError as exc:
        return _unknown(
            set_path,
            reason_code=exc.reason_code,
            reason=str(exc),
        )
    except (OSError, OverflowError, ValueError, struct.error, zlib.error) as exc:
        return _unknown(
            set_path,
            reason_code="eeglab_header_unavailable",
            reason=(
                "EEGLAB MAT header could not be inspected safely: "
                f"{type(exc).__name__}."
            ),
        )


def eeglab_external_data_dependency(path: str | Path) -> str | None:
    """Return the exact existing external data path named by a ``.set`` header."""
    inspection = inspect_eeglab_set_header(path)
    return inspection.external_data_file


def _parse_matrix(
    reader: _FileReader | _ZlibReader,
    matrix_bytes: int,
    *,
    endian: str,
    accumulator: _HeaderAccumulator,
    top_level: bool,
    field_name: str | None = None,
) -> _MatrixValue:
    matrix_end = reader.tell() + matrix_bytes
    flags = _read_small_element(reader, endian, maximum=16)
    if len(flags) < 4:
        raise _MatHeaderError("MATLAB array flags are truncated.")
    array_flags = struct.unpack(f"{endian}I", flags[:4])[0]
    class_id = array_flags & 0xFF
    dimensions = _read_dimensions(reader, endian)
    encoded_name = _decode_name(_read_small_element(reader, endian, maximum=1_024))
    name = field_name or encoded_name

    if top_level and encoded_name not in _TOP_LEVEL_FIELDS:
        return _MatrixValue(name=name, kind="ignored", shape=dimensions)
    if class_id == _MX_STRUCT:
        if encoded_name != "EEG":
            return _MatrixValue(name=name, kind="ignored", shape=dimensions)
        return _parse_eeg_struct(
            reader,
            matrix_end=matrix_end,
            dimensions=dimensions,
            endian=endian,
            accumulator=accumulator,
        )
    if array_flags & _MAT_ARRAY_FLAG_COMPLEX:
        raise _MatHeaderUnsupportedError(
            f"Complex MATLAB array {name or 'data'} cannot be bounded safely."
        )

    data_tag = _read_tag(reader, endian)
    if class_id == _MX_CHAR:
        text = _read_char_payload(reader, data_tag, endian=endian)
        _skip_to(reader, matrix_end)
        return _MatrixValue(name=name, kind="text", shape=dimensions, text=text)
    if data_tag.type_code not in _NUMERIC_DTYPES:
        raise _MatHeaderUnsupportedError(
            f"Unsupported MATLAB data type {data_tag.type_code} for {name or 'data'}."
        )
    dtype, dtype_bytes, _format = _NUMERIC_DTYPES[data_tag.type_code]
    expected_bytes = _element_count(dimensions) * dtype_bytes
    if expected_bytes != data_tag.nbytes:
        raise _MatHeaderError(
            f"MATLAB numeric shape does not match payload bytes for {name or 'data'}."
        )
    reader.require_payload_extent(data_tag.nbytes)
    if name == "data":
        return _MatrixValue(
            name=name,
            kind="numeric_data",
            shape=dimensions,
            dtype=dtype,
        )
    if expected_bytes > 8:
        raise _MatHeaderUnsupportedError(f"EEGLAB scalar field {name} is not scalar.")
    payload = _read_payload(reader, data_tag, maximum=8)
    scalar = _numeric_scalar(payload, data_tag.type_code, endian=endian)
    _skip_to(reader, matrix_end)
    return _MatrixValue(
        name=name,
        kind="scalar",
        shape=dimensions,
        dtype=dtype,
        scalar=scalar,
    )


def _parse_eeg_struct(
    reader: _FileReader | _ZlibReader,
    *,
    matrix_end: int,
    dimensions: tuple[int, ...],
    endian: str,
    accumulator: _HeaderAccumulator,
) -> _MatrixValue:
    if _element_count(dimensions) != 1:
        raise _MatHeaderUnsupportedError(
            "Only scalar EEGLAB EEG structs are supported."
        )
    field_length_payload = _read_small_element(reader, endian, maximum=8)
    if len(field_length_payload) < 4:
        raise _MatHeaderError("MATLAB struct field-name length is truncated.")
    field_name_length = int(struct.unpack(f"{endian}i", field_length_payload[:4])[0])
    if field_name_length <= 0 or field_name_length > 256:
        raise _MatHeaderError("MATLAB struct field-name length is invalid.")
    field_payload = _read_small_element(
        reader,
        endian,
        maximum=field_name_length * 4_096,
    )
    if len(field_payload) % field_name_length:
        raise _MatHeaderError("MATLAB struct field-name table is malformed.")
    field_names = [
        _decode_name(field_payload[index : index + field_name_length])
        for index in range(0, len(field_payload), field_name_length)
    ]
    for field_name in field_names:
        field_tag = _read_tag(reader, endian)
        if field_tag.type_code != _MI_MATRIX or field_tag.inline_data is not None:
            raise _MatHeaderError(
                f"EEGLAB struct field {field_name} is not a MATLAB matrix."
            )
        if field_name not in _STRUCT_FIELDS:
            _skip_payload(reader, field_tag)
            continue
        value = _parse_matrix(
            reader,
            field_tag.nbytes,
            endian=endian,
            accumulator=accumulator,
            top_level=False,
            field_name=field_name,
        )
        _apply_matrix_value(accumulator, value)
        if accumulator.source_shape is not None or (
            accumulator.reference and accumulator.external_shape_complete
        ):
            return _MatrixValue(name="EEG", kind="complete", shape=dimensions)
    _skip_to(reader, matrix_end)
    return _MatrixValue(name="EEG", kind="struct", shape=dimensions)


def _apply_matrix_value(
    accumulator: _HeaderAccumulator,
    value: _MatrixValue,
) -> None:
    if value.kind == "numeric_data":
        accumulator.source_shape = value.shape
        accumulator.source_dtype = value.dtype
        return
    if value.kind == "text":
        text = str(value.text or "").strip().strip("\x00")
        if value.name == "data" and text:
            accumulator.data_reference = text
        elif value.name == "datfile" and text:
            accumulator.datfile_reference = text
        return
    if value.kind != "scalar" or value.scalar is None:
        return
    if value.name == "srate":
        if math.isfinite(value.scalar) and value.scalar > 0:
            accumulator.sampling_rate_hz = float(value.scalar)
        return
    normalized = _positive_integral_scalar(value.scalar)
    if value.name == "nbchan":
        accumulator.channels = normalized
    elif value.name == "pnts":
        accumulator.time_samples = normalized
    elif value.name == "trials":
        accumulator.trials = normalized


def _inspection_if_complete(
    set_path: Path,
    accumulator: _HeaderAccumulator,
    *,
    compressed_header: bool,
    header_bytes_read: int,
    decoded_header_bytes: int,
    final: bool = False,
) -> EeglabSetHeaderInspection | None:
    if accumulator.source_shape is not None:
        shape = accumulator.source_shape
        if not shape or any(dimension <= 0 for dimension in shape):
            return _unknown(
                set_path,
                reason_code="eeglab_embedded_shape_invalid",
                reason="Embedded EEGLAB signal shape is missing or invalid.",
                compressed_header=compressed_header,
                header_bytes_read=header_bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
        channels = shape[0] if shape else None
        time_samples = shape[1] if len(shape) >= 2 else None
        trials = math.prod(shape[2:]) if len(shape) >= 3 else 1
        return EeglabSetHeaderInspection(
            path=str(set_path),
            bound_known=True,
            storage_mode="embedded",
            reason_code="eeglab_embedded_header_bounded",
            reason=(
                "Embedded EEGLAB signal shape and dtype were read from MAT metadata."
            ),
            source_shape=shape,
            source_dtype=accumulator.source_dtype,
            channels=channels,
            time_samples=time_samples,
            trials=trials,
            sampling_rate_hz=accumulator.sampling_rate_hz,
            compressed_header=compressed_header,
            header_bytes_read=header_bytes_read,
            decoded_header_bytes=decoded_header_bytes,
        )

    reference = accumulator.reference
    if reference and (accumulator.external_shape_complete or final):
        external_path, path_reason = _resolve_external_reference(set_path, reference)
        shape: tuple[int, ...] | None = accumulator.external_shape
        if external_path is None:
            return _unknown(
                set_path,
                reason_code="eeglab_external_reference_unsafe",
                reason=path_reason,
                storage_mode="external",
                source_shape=shape,
                source_dtype=EEGLAB_EXTERNAL_DTYPE,
                data_reference=reference,
                channels=accumulator.channels,
                time_samples=accumulator.time_samples,
                trials=accumulator.trials,
                sampling_rate_hz=accumulator.sampling_rate_hz,
                compressed_header=compressed_header,
                header_bytes_read=header_bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
        try:
            external_bytes = int(external_path.stat().st_size)
        except OSError:
            external_bytes = -1
        if external_bytes < 0:
            return _unknown(
                set_path,
                reason_code="eeglab_external_data_unavailable",
                reason="The external EEGLAB data file could not be inspected.",
                storage_mode="external",
                source_shape=shape,
                source_dtype=EEGLAB_EXTERNAL_DTYPE,
                data_reference=reference,
                external_data_file=str(external_path),
                channels=accumulator.channels,
                time_samples=accumulator.time_samples,
                trials=accumulator.trials,
                sampling_rate_hz=accumulator.sampling_rate_hz,
                compressed_header=compressed_header,
                header_bytes_read=header_bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
        expected_bytes = (
            _element_count(shape) * EEGLAB_EXTERNAL_DTYPE_BYTES
            if shape is not None
            else None
        )
        if expected_bytes is not None and external_bytes != expected_bytes:
            return _unknown(
                set_path,
                reason_code="eeglab_external_shape_size_mismatch",
                reason=(
                    "The referenced EEGLAB data file size does not match the "
                    "nbchan/pnts/trials header shape."
                ),
                storage_mode="external",
                source_shape=shape,
                source_dtype=EEGLAB_EXTERNAL_DTYPE,
                data_reference=reference,
                external_data_file=str(external_path),
                external_data_file_bytes=external_bytes,
                channels=accumulator.channels,
                time_samples=accumulator.time_samples,
                trials=accumulator.trials,
                sampling_rate_hz=accumulator.sampling_rate_hz,
                compressed_header=compressed_header,
                header_bytes_read=header_bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
        if expected_bytes is None and external_bytes % EEGLAB_EXTERNAL_DTYPE_BYTES:
            return _unknown(
                set_path,
                reason_code="eeglab_external_size_invalid",
                reason=(
                    "The referenced EEGLAB data file size is not aligned to "
                    "float32 samples."
                ),
                storage_mode="external",
                source_dtype=EEGLAB_EXTERNAL_DTYPE,
                data_reference=reference,
                external_data_file=str(external_path),
                external_data_file_bytes=external_bytes,
                compressed_header=compressed_header,
                header_bytes_read=header_bytes_read,
                decoded_header_bytes=decoded_header_bytes,
            )
        return EeglabSetHeaderInspection(
            path=str(set_path),
            bound_known=True,
            storage_mode="external",
            reason_code="eeglab_external_header_bounded",
            reason=(
                "External EEGLAB signal reference, dtype, and shape/size were "
                "bounded from MAT metadata and the referenced data file."
            ),
            source_shape=shape,
            source_dtype=EEGLAB_EXTERNAL_DTYPE,
            data_reference=reference,
            external_data_file=str(external_path),
            external_data_file_bytes=external_bytes,
            channels=accumulator.channels,
            time_samples=accumulator.time_samples,
            trials=accumulator.trials,
            sampling_rate_hz=accumulator.sampling_rate_hz,
            compressed_header=compressed_header,
            header_bytes_read=header_bytes_read,
            decoded_header_bytes=decoded_header_bytes,
        )
    return None


def _resolve_external_reference(
    set_path: Path,
    reference: str,
) -> tuple[Path | None, str]:
    normalized = reference.strip().strip("\x00").replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    relative = Path(normalized)
    if not normalized or windows_path.drive or relative.is_absolute():
        return None, "The external EEGLAB data reference must be a relative path."
    if relative.suffix.casefold() != ".fdt":
        return None, "The external EEGLAB data reference is not an .fdt file."
    if any(part in {"", ".", ".."} for part in relative.parts):
        return None, "The external EEGLAB data reference contains an unsafe path."

    root = set_path.parent.resolve()
    current = root
    for part in relative.parts:
        try:
            entries = list(current.iterdir())
        except OSError:
            return None, "The external EEGLAB data reference could not be resolved."
        exact_matches = [child for child in entries if child.name == part]
        if len(exact_matches) == 1:
            current = exact_matches[0]
            continue
        matches = [
            child for child in entries if child.name.casefold() == part.casefold()
        ]
        if len(matches) != 1:
            return None, "The external EEGLAB data reference was not found uniquely."
        current = matches[0]
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "The external EEGLAB data reference escapes the SET folder."
    if current.is_symlink() or not resolved.is_file():
        return None, "The external EEGLAB data reference is not a regular file."
    return resolved, ""


def _mat_v5_endian(header: bytes) -> str:
    if len(header) != MAT_FILE_HEADER_BYTES:
        raise _MatHeaderError("MATLAB file header is truncated.")
    marker = header[126:128]
    if marker == b"IM":
        return "<"
    if marker == b"MI":
        return ">"
    raise _MatHeaderUnsupportedError("The EEGLAB file is not a supported MAT v5 file.")


def _read_tag(reader: _FileReader | _ZlibReader, endian: str) -> _Tag:
    raw = reader.read(8)
    small_type, small_nbytes = struct.unpack(f"{endian}HH", raw[:4])
    if small_nbytes:
        if small_nbytes > 4:
            raise _MatHeaderError("Invalid MATLAB small-data element size.")
        return _Tag(
            type_code=int(small_type),
            nbytes=int(small_nbytes),
            inline_data=raw[4 : 4 + small_nbytes],
        )
    type_code, nbytes = struct.unpack(f"{endian}II", raw)
    if type_code <= 0 or nbytes < 0:
        raise _MatHeaderError("Invalid MATLAB element tag.")
    return _Tag(type_code=int(type_code), nbytes=int(nbytes))


def _require_matrix_tag(tag: _Tag) -> None:
    if tag.type_code != _MI_MATRIX or tag.inline_data is not None:
        raise _MatHeaderError("Compressed MATLAB element does not contain a matrix.")


def _read_small_element(
    reader: _FileReader | _ZlibReader,
    endian: str,
    *,
    maximum: int,
) -> bytes:
    tag = _read_tag(reader, endian)
    return _read_payload(reader, tag, maximum=maximum)


def _read_payload(
    reader: _FileReader | _ZlibReader,
    tag: _Tag,
    *,
    maximum: int,
) -> bytes:
    if tag.nbytes > maximum:
        raise _MatHeaderBudgetError(
            f"MATLAB header value exceeds the {maximum}-byte read limit."
        )
    if tag.inline_data is not None:
        return tag.inline_data
    payload = reader.read(tag.nbytes)
    reader.skip(_padding(tag.nbytes))
    return payload


def _skip_payload(reader: _FileReader | _ZlibReader, tag: _Tag) -> None:
    if tag.inline_data is None:
        reader.skip(tag.nbytes + _padding(tag.nbytes))


def _read_dimensions(
    reader: _FileReader | _ZlibReader,
    endian: str,
) -> tuple[int, ...]:
    payload = _read_small_element(reader, endian, maximum=128)
    if not payload or len(payload) % 4:
        raise _MatHeaderError("MATLAB dimensions are malformed.")
    values = struct.unpack(f"{endian}{len(payload) // 4}i", payload)
    if any(value < 0 for value in values):
        raise _MatHeaderError("MATLAB dimensions contain a negative size.")
    return tuple(int(value) for value in values)


def _read_char_payload(
    reader: _FileReader | _ZlibReader,
    tag: _Tag,
    *,
    endian: str,
) -> str:
    payload = _read_payload(reader, tag, maximum=MAT_REFERENCE_MAX_BYTES)
    if tag.type_code in {_MI_INT8, _MI_UINT8, _MI_UTF8}:
        return payload.decode("utf-8", errors="strict")
    if tag.type_code in {_MI_INT16, _MI_UINT16, _MI_UTF16}:
        encoding = "utf-16-le" if endian == "<" else "utf-16-be"
        return payload.decode(encoding, errors="strict")
    if tag.type_code in {_MI_INT32, _MI_UINT32, _MI_UTF32}:
        encoding = "utf-32-le" if endian == "<" else "utf-32-be"
        return payload.decode(encoding, errors="strict")
    raise _MatHeaderUnsupportedError(
        f"Unsupported MATLAB character encoding type {tag.type_code}."
    )


def _numeric_scalar(payload: bytes, type_code: int, *, endian: str) -> float:
    _name, width, format_code = _NUMERIC_DTYPES[type_code]
    if len(payload) != width:
        raise _MatHeaderError("MATLAB scalar payload size is invalid.")
    return float(struct.unpack(f"{endian}{format_code}", payload)[0])


def _positive_integral_scalar(value: float) -> int | None:
    if not math.isfinite(value) or value <= 0 or not value.is_integer():
        return None
    return int(value)


def _element_count(shape: tuple[int, ...] | None) -> int:
    if not shape:
        return 0
    return int(math.prod(shape))


def _decode_name(payload: bytes) -> str:
    return payload.split(b"\x00", 1)[0].decode("latin1", errors="strict").strip()


def _skip_to(reader: _FileReader | _ZlibReader, end: int) -> None:
    remaining = end - reader.tell()
    if remaining < 0:
        raise _MatHeaderError("MATLAB matrix parser exceeded its declared size.")
    reader.skip(remaining)


def _padding(nbytes: int) -> int:
    return (-nbytes) % 8


def _unknown(
    path: Path,
    *,
    reason_code: str,
    reason: str,
    storage_mode: str = "unknown",
    source_shape: tuple[int, ...] | None = None,
    source_dtype: str | None = None,
    data_reference: str | None = None,
    external_data_file: str | None = None,
    external_data_file_bytes: int | None = None,
    channels: int | None = None,
    time_samples: int | None = None,
    trials: int | None = None,
    sampling_rate_hz: float | None = None,
    mat_format: str = "mat_v5",
    compressed_header: bool = False,
    header_bytes_read: int = 0,
    decoded_header_bytes: int = 0,
) -> EeglabSetHeaderInspection:
    return EeglabSetHeaderInspection(
        path=str(path),
        bound_known=False,
        storage_mode=storage_mode,
        reason_code=reason_code,
        reason=reason,
        source_shape=source_shape,
        source_dtype=source_dtype,
        data_reference=data_reference,
        external_data_file=external_data_file,
        external_data_file_bytes=external_data_file_bytes,
        channels=channels,
        time_samples=time_samples,
        trials=trials,
        sampling_rate_hz=sampling_rate_hz,
        mat_format=mat_format,
        compressed_header=compressed_header,
        header_bytes_read=header_bytes_read,
        decoded_header_bytes=decoded_header_bytes,
    )
