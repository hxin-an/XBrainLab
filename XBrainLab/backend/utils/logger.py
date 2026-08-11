"""Logging configuration with private-by-default diagnostic handlers."""

from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from contextlib import suppress
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from threading import RLock
from typing import Any, cast

from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticDisclosure,
    DiagnosticTextLayout,
    public_diagnostic_text,
    public_diagnostic_value,
    safe_exception_type_name,
)
from XBrainLab.backend.utils.secure_log_storage import (
    flags_for_log_mode as _flags_for_log_mode,
)
from XBrainLab.backend.utils.secure_log_storage import (
    open_regular_log_descriptor as _open_regular_log_descriptor,
)
from XBrainLab.backend.utils.secure_log_storage import (
    prepare_log_file as _prepare_log_file,
)
from XBrainLab.backend.utils.secure_log_storage import (
    prepare_secure_log_directory as _prepare_secure_log_directory,
)
from XBrainLab.backend.utils.secure_log_storage import (
    remove_excess_numeric_backups as _remove_excess_numeric_backups,
)
from XBrainLab.backend.utils.secure_log_storage import (
    sanitize_legacy_log_family as _migrate_legacy_log_family,
)
from XBrainLab.backend.utils.secure_log_storage import (
    secure_log_family as _secure_log_family,
)
from XBrainLab.backend.utils.secure_log_storage import (
    truncate_log_file_to_bytes as _truncate_log_file_to_bytes,
)
from XBrainLab.platform_paths import user_log_dir

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_MAX_RECORD_BYTES = 64 * 1024
LOG_SANITIZER_INPUT_BYTES = LOG_MAX_RECORD_BYTES
LOG_MAX_TEMPLATE_BYTES = 16 * 1024
LOG_MAX_ARGUMENT_BYTES = 4 * 1024
LOG_MAX_ARGUMENTS = 32
LOG_MAX_FORMAT_CONVERSIONS = 64
LOG_MAX_TRACEBACK_FRAMES = 32
LOG_MAX_METADATA_BYTES = 4 * 1024
_TRUNCATED_RECORD_MARKER = " [TRUNCATED]"
_DIAGNOSTIC_REDACTION_FAILED = "[DIAGNOSTIC_REDACTION_FAILED]"
_PUBLIC_DISCLOSURE_MARKER = object()
_DETAILED_DISCLOSURE_MARKER = object()
_SAFE_PATH_TYPES = (PosixPath, WindowsPath, PurePosixPath, PureWindowsPath)
_FORMAT_SPEC_PATTERN = re.compile(
    r"%(?:\((?P<key>[^)]+)\))?"
    r"(?P<flags>[#0+ \-]*)"
    r"(?P<width>\d+)?"
    r"(?:\.(?P<precision>\d+))?"
    r"[hlL]?"
    r"(?P<conversion>[diouxXeEfFgGcrsa%])"
)
_LOG_RECORD_FACTORY_LOCK = RLock()
_PROTECTED_LOGGER_FILTERS: dict[str, DiagnosticRedactionFilter] = {}
_LOG_RECORD_FACTORY_DELEGATE = [logging.getLogRecordFactory()]
_LOG_RECORD_TEXT_METADATA_FIELDS = (
    "name",
    "pathname",
    "filename",
    "module",
    "funcName",
    "threadName",
    "processName",
    "taskName",
)


class DiagnosticLogger(logging.Logger):
    """Sanitize protected logger arguments and extra fields before publication."""

    def makeRecord(  # noqa: N802 - stdlib API
        self,
        name,
        level,
        fn,
        lno,
        msg,
        args,
        exc_info,
        func=None,
        extra=None,
        sinfo=None,
    ):
        diagnostic_filter = _protected_filter_for_name(name)
        if diagnostic_filter is None:
            return super().makeRecord(
                name,
                level,
                fn,
                lno,
                msg,
                args,
                exc_info,
                func,
                extra,
                sinfo,
            )

        safe_args = _bounded_log_arguments(args)
        record = super().makeRecord(
            name,
            level,
            fn,
            lno,
            msg,
            safe_args,
            exc_info,
            func,
            None,
            sinfo,
        )
        _apply_public_extra(record, extra, diagnostic_filter.disclosure)
        return record


logging.setLoggerClass(DiagnosticLogger)


class DiagnosticRedactionFilter(logging.Filter):
    """Sanitize a complete log record before any configured handler emits it."""

    def __init__(self, disclosure: DiagnosticDisclosure) -> None:
        super().__init__()
        if not isinstance(disclosure, DiagnosticDisclosure):
            raise TypeError("Logger disclosure must be an explicit enum value.")
        self.disclosure = disclosure

    def filter(self, record: logging.LogRecord) -> bool:
        previous = getattr(record, "_xbrainlab_diagnostic_disclosure", None)
        if previous is _PUBLIC_DISCLOSURE_MARKER:
            return True
        if (
            previous is _DETAILED_DISCLOSURE_MARKER
            and self.disclosure is DiagnosticDisclosure.DETAILED
        ):
            return True

        message = _bounded_log_message(record)
        details: list[str] = []
        if record.exc_info is not None:
            details.append(_bounded_traceback_text(record.exc_info))
        if record.stack_info:
            details.append(
                _truncate_text_to_bytes(
                    record.stack_info[:LOG_SANITIZER_INPUT_BYTES],
                    LOG_SANITIZER_INPUT_BYTES,
                    encoding="utf-8",
                )
            )
        if details:
            message = _truncate_text_to_bytes(
                " | ".join((message, *details)),
                LOG_SANITIZER_INPUT_BYTES,
                encoding="utf-8",
            )

        record.msg = _truncate_text_to_bytes(
            public_diagnostic_text(
                message,
                disclosure=self.disclosure,
                layout=DiagnosticTextLayout.SINGLE_LINE,
            ),
            LOG_SANITIZER_INPUT_BYTES,
            encoding="utf-8",
        )
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        _sanitize_log_record_metadata(record, disclosure=self.disclosure)
        record.__dict__["_xbrainlab_diagnostic_disclosure"] = (
            _PUBLIC_DISCLOSURE_MARKER
            if self.disclosure is DiagnosticDisclosure.PUBLIC
            else _DETAILED_DISCLOSURE_MARKER
        )
        return True


def _register_protected_logger(
    name: str,
    disclosure: DiagnosticDisclosure,
) -> DiagnosticRedactionFilter:
    """Protect one logger namespace before any descendant handler can emit.

    Product code is source-guarded against replacing logging factories/classes
    or supplying ``extra`` fields, which the stdlib applies after this factory.
    """
    diagnostic_filter = DiagnosticRedactionFilter(disclosure)
    with _LOG_RECORD_FACTORY_LOCK:
        guard_was_installed = bool(_PROTECTED_LOGGER_FILTERS)
        _PROTECTED_LOGGER_FILTERS[name] = diagnostic_filter
        _promote_existing_logger_namespace(name)
        current_factory = logging.getLogRecordFactory()
        if current_factory is not _protected_log_record_factory:
            # Preserve the pre-existing factory only on first installation.
            # A later replacement may wrap this guard; adopting that wrapper
            # as our delegate would recurse and disable fail-closed handling.
            if not guard_was_installed:
                _LOG_RECORD_FACTORY_DELEGATE[0] = current_factory
            logging.setLogRecordFactory(_protected_log_record_factory)
    return diagnostic_filter


def _promote_existing_logger_namespace(name: str) -> None:
    candidates = [logging.getLogger(name)]
    candidates.extend(
        logger
        for logger_name, logger in logging.Logger.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
        and (logger_name == name or logger_name.startswith(f"{name}."))
    )
    for candidate in candidates:
        if type(candidate) is logging.Logger:
            candidate.__class__ = DiagnosticLogger


def _apply_public_extra(
    record: logging.LogRecord,
    extra: object,
    disclosure: DiagnosticDisclosure,
) -> None:
    if extra is None:
        return
    if type(extra) is not dict:
        return
    for key, value in extra.items():
        if type(key) is not str or key in {"message", "asctime"}:
            continue
        if key in record.__dict__:
            continue
        record.__dict__[key] = public_diagnostic_value(
            value,
            disclosure=disclosure,
        )


def _protected_log_record_factory(*args, **kwargs) -> logging.LogRecord:
    with _LOG_RECORD_FACTORY_LOCK:
        delegate = _LOG_RECORD_FACTORY_DELEGATE[0]
    record = delegate(*args, **kwargs)
    diagnostic_filter = _protected_filter_for_name(record.name)
    if diagnostic_filter is None:
        return record
    try:
        diagnostic_filter.filter(record)
    except Exception:
        _fail_closed_log_record(record)
    finally:
        # Logger.makeRecord applies ``extra`` after the factory returns. Keep
        # that namespace available; configured handlers will mark the record
        # again after their final sanitization pass.
        record.__dict__.pop("_xbrainlab_diagnostic_disclosure", None)
    return record


def _protected_filter_for_name(name: object) -> DiagnosticRedactionFilter | None:
    if not isinstance(name, str) or not name:
        return None
    with _LOG_RECORD_FACTORY_LOCK:
        matches = [
            (prefix, diagnostic_filter)
            for prefix, diagnostic_filter in _PROTECTED_LOGGER_FILTERS.items()
            if name == prefix or name.startswith(f"{prefix}.")
        ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def _fail_closed_log_record(record: logging.LogRecord) -> None:
    record.msg = _DIAGNOSTIC_REDACTION_FAILED
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    for field_name in _LOG_RECORD_TEXT_METADATA_FIELDS:
        if field_name in record.__dict__:
            record.__dict__[field_name] = _DIAGNOSTIC_REDACTION_FAILED
    record.__dict__["_xbrainlab_diagnostic_disclosure"] = _PUBLIC_DISCLOSURE_MARKER


def _sanitize_log_record_metadata(
    record: logging.LogRecord,
    *,
    disclosure: DiagnosticDisclosure,
) -> None:
    for field_name in _LOG_RECORD_TEXT_METADATA_FIELDS:
        if field_name not in record.__dict__:
            continue
        record.__dict__[field_name] = _truncate_text_to_bytes(
            public_diagnostic_text(
                _bounded_log_text(
                    record.__dict__[field_name],
                    LOG_MAX_METADATA_BYTES,
                ),
                disclosure=disclosure,
                layout=DiagnosticTextLayout.SINGLE_LINE,
            ),
            LOG_MAX_METADATA_BYTES,
            encoding="utf-8",
        )


def _bounded_log_message(record: logging.LogRecord) -> str:
    template = _bounded_log_text(record.msg, LOG_MAX_TEMPLATE_BYTES)
    if (type(record.args) is tuple and len(record.args) == 0) or (
        type(record.args) is dict and len(record.args) == 0
    ):
        return _truncate_text_to_bytes(
            template,
            LOG_SANITIZER_INPUT_BYTES,
            encoding="utf-8",
        )

    safe_args = _bounded_log_arguments(record.args)
    if _format_template_is_bounded(template):
        try:
            formatted = template % safe_args
        except (KeyError, TypeError, ValueError):
            formatted = _fallback_log_message(template, safe_args)
    else:
        formatted = _fallback_log_message(template, safe_args)
    return _truncate_text_to_bytes(
        formatted,
        LOG_SANITIZER_INPUT_BYTES,
        encoding="utf-8",
    )


def _bounded_log_arguments(
    value: object,
) -> tuple[object, ...] | dict[str, object]:
    if type(value) is dict:
        return {
            _bounded_log_text(key, 256): _bounded_log_value(item)
            for key, item in list(value.items())[:LOG_MAX_ARGUMENTS]
        }
    if type(value) is tuple:
        return tuple(_bounded_log_value(item) for item in value[:LOG_MAX_ARGUMENTS])
    return (_bounded_log_value(value),)


def _bounded_log_value(value: object) -> object:
    if type(value) is str:
        return _truncate_text_to_bytes(
            value[:LOG_MAX_ARGUMENT_BYTES],
            LOG_MAX_ARGUMENT_BYTES,
            encoding="utf-8",
        )
    if type(value) is bytes:
        return value[:LOG_MAX_ARGUMENT_BYTES].decode("utf-8", errors="replace")
    if type(value) is int and _estimated_int_text_bytes(value) > LOG_MAX_ARGUMENT_BYTES:
        return _TRUNCATED_RECORD_MARKER.strip()
    if value is None or any(
        type(value) is primitive_type for primitive_type in (bool, int, float)
    ):
        return value
    if any(type(value) is path_type for path_type in _SAFE_PATH_TYPES):
        return _bounded_log_value(
            os.fspath(cast(os.PathLike[str] | os.PathLike[bytes], value))
        )
    if isinstance(value, BaseException):
        return _bounded_exception_summary(value)
    return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


def _bounded_log_text(value: object, budget: int) -> str:
    bounded = _bounded_log_value(value)
    if type(bounded) is str:
        return _truncate_text_to_bytes(bounded, budget, encoding="utf-8")
    if bounded is None or any(
        type(bounded) is primitive_type for primitive_type in (bool, int, float)
    ):
        return str(bounded)
    return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


def _format_template_is_bounded(template: str) -> bool:
    position = 0
    conversions = 0
    while True:
        percent = template.find("%", position)
        if percent < 0:
            return True
        match = _FORMAT_SPEC_PATTERN.match(template, percent)
        if match is None:
            return False
        position = match.end()
        if match.group("conversion") == "%":
            continue
        conversions += 1
        if conversions > LOG_MAX_FORMAT_CONVERSIONS:
            return False
        for group_name in ("width", "precision"):
            raw_limit = match.group(group_name)
            if raw_limit is None:
                continue
            if len(raw_limit) > 6 or int(raw_limit) > LOG_MAX_ARGUMENT_BYTES:
                return False


def _fallback_log_message(template: str, safe_args: object) -> str:
    if type(safe_args) is dict:
        items = [
            f"{_bounded_log_text(key, 256)}={_bounded_log_text(value, 1024)}"
            for key, value in list(safe_args.items())[:LOG_MAX_ARGUMENTS]
        ]
    elif type(safe_args) is tuple:
        items = [
            _bounded_log_text(value, 1024) for value in safe_args[:LOG_MAX_ARGUMENTS]
        ]
    else:
        items = [_bounded_log_text(safe_args, 1024)]
    return f"{template} | args=[{', '.join(items)}]"


def _bounded_exception_summary(error: BaseException) -> str:
    args_descriptor = cast(Any, BaseException.__dict__["args"])
    raw_arguments = args_descriptor.__get__(error, type(error))
    arguments_source = raw_arguments if type(raw_arguments) is tuple else ()
    arguments = [
        _bounded_log_text(item, LOG_MAX_ARGUMENT_BYTES)
        for item in arguments_source[:LOG_MAX_ARGUMENTS]
    ]
    detail = ", ".join(arguments)
    exception_type = safe_exception_type_name(error)
    summary = f"{exception_type}: {detail}" if detail else exception_type
    return _truncate_text_to_bytes(
        summary,
        LOG_MAX_ARGUMENT_BYTES * 2,
        encoding="utf-8",
    )


def _bounded_traceback_text(exc_info: tuple) -> str:
    error = exc_info[1] if len(exc_info) > 1 else None
    traceback_value = exc_info[2] if len(exc_info) > 2 else None
    parts = ["Traceback (bounded):"]
    if traceback_value is not None:
        frames = traceback.extract_tb(
            traceback_value,
            limit=LOG_MAX_TRACEBACK_FRAMES,
        )
        parts.extend(
            (
                f'File "{_bounded_log_text(frame.filename, 4096)}", '
                f"line {frame.lineno}, in {_bounded_log_text(frame.name, 1024)}"
            )
            for frame in frames
        )
    if isinstance(error, BaseException):
        parts.append(_bounded_exception_summary(error))
    return _truncate_text_to_bytes(
        " ".join(parts),
        LOG_SANITIZER_INPUT_BYTES,
        encoding="utf-8",
    )


class SafeRotatingFileHandler(RotatingFileHandler):
    """Rotate bounded logs and keep each active file owner-only on POSIX."""

    def __init__(self, *args, **kwargs) -> None:
        self._disabled_after_rollover_failure = False
        filename = args[0] if args else kwargs.get("filename")
        if filename is None:
            raise TypeError("SafeRotatingFileHandler requires a filename.")
        _migrate_legacy_log_family(
            os.fspath(filename),
            sanitizer_input_bytes=LOG_SANITIZER_INPUT_BYTES,
        )
        super().__init__(*args, **kwargs)
        try:
            self._bound_existing_log_family()
        except (PermissionError, OSError):
            self._disable_after_rollover_failure()

    @property
    def disabled_after_rollover_failure(self) -> bool:
        """Return whether bounded file logging failed closed."""
        return self._disabled_after_rollover_failure

    def revalidate_retention(self) -> bool:
        """Re-apply byte/count limits after external or concurrent file changes."""
        if self._disabled_after_rollover_failure:
            return False
        try:
            self._bound_existing_log_family()
        except (PermissionError, OSError):
            self._disable_after_rollover_failure()
        return not self._disabled_after_rollover_failure

    def _open(self) -> TextIOWrapper:
        descriptor = _open_regular_log_descriptor(
            self.baseFilename,
            _flags_for_log_mode(self.mode),
        )
        try:
            return cast(
                TextIOWrapper,
                os.fdopen(
                    descriptor,
                    self.mode,
                    encoding=self.encoding,
                    errors=self.errors,
                    newline="",
                ),
            )
        except Exception:
            os.close(descriptor)
            raise

    def emit(self, record: logging.LogRecord) -> None:
        """Emit only while the configured bounded-retention contract is usable."""
        if self._disabled_after_rollover_failure:
            return
        try:
            bounded_record = self._bounded_record(record)
            if bounded_record is None:
                return
            should_rollover = self.shouldRollover(bounded_record)
            if self._disabled_after_rollover_failure:
                return
            if should_rollover:
                self.doRollover()
                if self._disabled_after_rollover_failure:
                    return
            logging.FileHandler.emit(self, bounded_record)
        except Exception:
            self.handleError(record)

    def doRollover(self) -> None:  # noqa: N802
        try:
            # Fail closed before moving the active file if owner-only hardening
            # is unavailable. A failed rollover must not replace a valid log
            # with a new unprotected file.
            self._bound_existing_log_family()
            _secure_log_family(self.baseFilename, self.backupCount)
            super().doRollover()
            self._bound_existing_log_family()
            _secure_log_family(self.baseFilename, self.backupCount)
        except (PermissionError, OSError):
            self._disable_after_rollover_failure()
            return

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802
        """Use encoded bytes, not Python character counts, for the file cap."""
        if self.maxBytes <= 0:
            return False
        if self.stream is None:
            self.stream = self._open()
        self.stream.flush()
        try:
            current_size = os.path.getsize(self.baseFilename)
        except OSError:
            self._disable_after_rollover_failure()
            return False
        encoding = self.encoding or "utf-8"
        return (
            current_size + self._formatted_size(record, encoding=encoding)
            > self.maxBytes
        )

    def _bounded_record(
        self,
        record: logging.LogRecord,
    ) -> logging.LogRecord | None:
        limit = LOG_MAX_RECORD_BYTES
        if self.maxBytes > 0:
            limit = min(limit, self.maxBytes)
        clone = logging.makeLogRecord(record.__dict__.copy())
        clone.args = ()
        clone.exc_info = None
        clone.exc_text = None
        clone.stack_info = None
        original_message = _bounded_log_message(record)
        encoding = self.encoding or "utf-8"
        clone.msg = original_message
        if self._formatted_size(clone, encoding=encoding) <= limit:
            return clone

        low = 0
        high = len(original_message)
        best: str | None = None
        while low <= high:
            midpoint = (low + high) // 2
            candidate = f"{original_message[:midpoint]}{_TRUNCATED_RECORD_MARKER}"
            clone.msg = candidate
            if self._formatted_size(clone, encoding=encoding) <= limit:
                best = candidate
                low = midpoint + 1
            else:
                high = midpoint - 1
        if best is None:
            clone.msg = ""
            return (
                clone
                if self._formatted_size(clone, encoding=encoding) <= limit
                else None
            )
        clone.msg = best
        return clone

    def _formatted_size(self, record: logging.LogRecord, *, encoding: str) -> int:
        return len(
            f"{self.format(record)}{self.terminator}".encode(
                encoding,
                errors="replace",
            )
        )

    def _bound_existing_log_family(self) -> None:
        """Apply the configured byte cap to active and rotated legacy files."""
        if self.maxBytes <= 0:
            return
        stream_was_open = self.stream is not None
        if self.stream is not None:
            self.stream.flush()
            self.stream.close()
            self.stream = cast(TextIOWrapper, None)
        _remove_excess_numeric_backups(self.baseFilename, self.backupCount)
        for candidate in (
            self.baseFilename,
            *(
                f"{self.baseFilename}.{index}"
                for index in range(1, self.backupCount + 1)
            ),
        ):
            if os.path.lexists(candidate):
                _truncate_log_file_to_bytes(candidate, self.maxBytes)
        _secure_log_family(self.baseFilename, self.backupCount)
        if stream_was_open:
            self.stream = self._open()

    def _disable_after_rollover_failure(self) -> None:
        self._disabled_after_rollover_failure = True
        if self.stream is not None:
            try:
                self.stream.close()
            finally:
                self.stream = cast(TextIOWrapper, None)
        with suppress(OSError):
            sys.stderr.write(
                "XBrainLab file logging disabled because bounded log rotation failed.\n"
            )


def setup_logger(
    name="XBrainLab",
    log_file=None,
    level=logging.INFO,
    *,
    disclosure: DiagnosticDisclosure = DiagnosticDisclosure.PUBLIC,
):
    """Sets up a logger with both console and file handlers.

    Args:
        name (str): Name of the logger.
        log_file (str | Path | None): Path to the log file. The secure default
            is the current user's XBrainLab state directory.
        level (int): Logging level (default: logging.INFO).
        disclosure: Explicit private-detail policy. Public is the secure default.

    Returns:
        logging.Logger: Configured logger instance.

    """
    if not isinstance(disclosure, DiagnosticDisclosure):
        raise TypeError("Logger disclosure must be an explicit enum value.")
    diagnostic_filter = _register_protected_logger(name, disclosure)

    resolved_log_file = os.fspath(
        user_log_dir() / "app.log" if log_file is None else log_file
    )
    log_dir = os.path.dirname(os.path.abspath(resolved_log_file))
    file_sink_available = True
    try:
        _prepare_secure_log_directory(log_dir)
        _prepare_log_file(
            resolved_log_file,
            backup_count=LOG_BACKUP_COUNT,
        )
    except OSError:
        file_sink_available = False
        with suppress(OSError):
            sys.stderr.write(
                "XBrainLab file logging disabled because private log storage "
                "could not be verified.\n"
            )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    absolute_log_file = os.path.abspath(resolved_log_file)
    existing_handlers = list(logger.handlers)
    matching_file_handlers = [
        handler
        for handler in existing_handlers
        if isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == absolute_log_file
    ]
    owned_handlers = [
        handler
        for handler in existing_handlers
        if getattr(handler, "_xbrainlab_owned", False)
    ]
    if file_sink_available and _existing_logger_configuration_is_valid(
        existing_handlers=existing_handlers,
        matching_file_handlers=matching_file_handlers,
        owned_handlers=owned_handlers,
        disclosure=disclosure,
        level=level,
        propagate=logger.propagate,
    ):
        file_handler = matching_file_handlers[0]
        if (
            isinstance(
                file_handler,
                SafeRotatingFileHandler,
            )
            and file_handler.revalidate_retention()
        ):
            return logger
    for handler in existing_handlers:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    console_handler.addFilter(diagnostic_filter)
    console_handler._xbrainlab_owned = True  # type: ignore[attr-defined]

    if file_sink_available:
        try:
            file_handler = SafeRotatingFileHandler(
                resolved_log_file,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        except OSError:
            file_sink_available = False
            with suppress(OSError):
                sys.stderr.write(
                    "XBrainLab file logging disabled because its secure sink "
                    "could not be opened.\n"
                )
        else:
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            file_handler.addFilter(diagnostic_filter)
            file_handler._xbrainlab_owned = True  # type: ignore[attr-defined]
            logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger


def _existing_logger_configuration_is_valid(
    *,
    existing_handlers: list[logging.Handler],
    matching_file_handlers: list[RotatingFileHandler],
    owned_handlers: list[logging.Handler],
    disclosure: DiagnosticDisclosure,
    level: int,
    propagate: bool,
) -> bool:
    if len(existing_handlers) != 2:
        return False
    if propagate:
        return False
    if len(matching_file_handlers) != 1:
        return False
    file_handler = matching_file_handlers[0]
    if not isinstance(file_handler, SafeRotatingFileHandler):
        return False
    if (
        file_handler.maxBytes != LOG_MAX_BYTES
        or file_handler.backupCount != LOG_BACKUP_COUNT
        or file_handler.level != level
        or file_handler.disabled_after_rollover_failure
        or not _handler_uses_disclosure(file_handler, disclosure)
    ):
        return False
    console_handlers = [
        handler
        for handler in owned_handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
    ]
    return bool(
        len(owned_handlers) == 2
        and set(existing_handlers) == set(owned_handlers)
        and len(console_handlers) == 1
        and console_handlers[0].level == level
        and _handler_uses_disclosure(console_handlers[0], disclosure)
    )


def _handler_uses_disclosure(
    handler: logging.Handler,
    disclosure: DiagnosticDisclosure,
) -> bool:
    filters = [
        item for item in handler.filters if isinstance(item, DiagnosticRedactionFilter)
    ]
    return bool(len(filters) == 1 and filters[0].disclosure is disclosure)


def _truncate_text_to_bytes(text: str, budget: int, *, encoding: str) -> str:
    if budget <= 0:
        return ""
    candidate = text if len(text) <= budget else text[:budget]
    encoded = candidate.encode(encoding, errors="replace")
    if candidate is text and len(encoded) <= budget:
        return text
    marker = _TRUNCATED_RECORD_MARKER.encode(encoding)
    if budget <= len(marker):
        return marker[:budget].decode(encoding, errors="ignore")
    prefix = encoded[: budget - len(marker)].decode(encoding, errors="ignore")
    return f"{prefix}{_TRUNCATED_RECORD_MARKER}"


def _estimated_int_text_bytes(value: int) -> int:
    if value == 0:
        return 1
    digits = (abs(value).bit_length() * 30_103) // 100_000 + 1
    return digits + int(value < 0)


logger = setup_logger()
