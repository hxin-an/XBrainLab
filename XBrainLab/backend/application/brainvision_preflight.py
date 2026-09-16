"""Bounded BrainVision dependency parsing shared by admission and RAM estimation."""

from pathlib import Path, PureWindowsPath

from .bids_dataset_index import current_bids_dataset_index_for_path
from .errors import PreconditionError

BRAINVISION_HEADER_MAX_BYTES = 1_048_576


def brainvision_parser_dependencies(vhdr_file: str) -> list[str]:
    """Resolve BrainVision data/marker references from one bounded text header."""
    path = Path(vhdr_file).expanduser()
    try:
        with path.open("rb") as handle:
            payload = handle.read(BRAINVISION_HEADER_MAX_BYTES + 1)
    except OSError as exc:
        raise PreconditionError(
            f"BrainVision header dependencies could not be inspected: {path}.",
            diagnostics={
                "code": "brainvision_dependency_header_unavailable",
                "path": str(path.resolve(strict=False)),
                "os_error": str(exc),
            },
        ) from exc
    if len(payload) > BRAINVISION_HEADER_MAX_BYTES:
        raise PreconditionError(
            f"BrainVision header exceeds the bounded dependency read limit: {path}.",
            diagnostics={
                "code": "brainvision_dependency_header_too_large",
                "path": str(path.resolve(strict=False)),
                "max_bytes": BRAINVISION_HEADER_MAX_BYTES,
            },
        )
    text = _decode_brainvision_header(payload)
    references = _brainvision_common_info_references(text)
    dependencies: list[str] = []
    for key, expected_suffix in (("datafile", ".eeg"), ("markerfile", ".vmrk")):
        reference = references.get(key)
        if not reference:
            continue
        dependency = _resolve_brainvision_reference(
            header_path=path,
            reference=reference,
            expected_suffix=expected_suffix,
        )
        dependencies.append(str(dependency))
    return dependencies


def _decode_brainvision_header(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload.decode("cp1252", errors="replace")


def _brainvision_common_info_references(text: str) -> dict[str, str]:
    section = ""
    references: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().casefold()
            continue
        if section != "common infos" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().casefold()
        if normalized_key in {"datafile", "markerfile"}:
            references[normalized_key] = value.strip()
    return references


def _resolve_brainvision_reference(
    *,
    header_path: Path,
    reference: str,
    expected_suffix: str,
) -> Path:
    normalized = reference.strip().strip('"').strip("\x00").replace("\\", "/")
    relative = Path(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or windows_path.drive
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency reference must be a safe relative path.",
        )
    if relative.suffix.casefold() != expected_suffix:
        raise _brainvision_dependency_error(
            header_path,
            reference,
            f"The dependency reference must name a {expected_suffix} file.",
        )

    bids_index = current_bids_dataset_index_for_path(header_path)
    if bids_index is not None and bids_index.contains_recording(header_path):
        indexed = bids_index.indexed_file_in_recording_directory(
            header_path,
            relative,
        )
        if indexed is None:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency was not listed in the BIDS dataset index.",
            )
        resolved = Path(indexed)
        if resolved.suffix.casefold() != expected_suffix:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                f"The dependency reference must name a {expected_suffix} file.",
            )
        return resolved
    root = header_path.parent.resolve()
    current = root
    for part in relative.parts:
        exact = current / part
        if exact.exists():
            current = exact
            continue
        try:
            matches = [
                child
                for child in current.iterdir()
                if child.name.casefold() == part.casefold()
            ]
        except OSError as exc:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency directory could not be inspected.",
            ) from exc
        if len(matches) != 1:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency file was not found uniquely.",
            )
        current = matches[0]
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency escapes the BrainVision header folder.",
        ) from exc
    if not resolved.is_file():
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency is not a regular file.",
        )
    return resolved


def _brainvision_dependency_error(
    header_path: Path,
    reference: str,
    reason: str,
) -> PreconditionError:
    return PreconditionError(
        f"BrainVision parser dependency could not be admitted for {header_path.name}: "
        f"{reason}",
        diagnostics={
            "code": "brainvision_dependency_unavailable",
            "path": str(header_path.resolve(strict=False)),
            "reference": reference,
            "reason": reason,
        },
    )
