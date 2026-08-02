import io
import logging
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path

import pytest

from XBrainLab.backend.utils import logger as logger_module
from XBrainLab.backend.utils import secure_log_storage
from XBrainLab.backend.utils.logger import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    LOG_SANITIZER_INPUT_BYTES,
    DiagnosticRedactionFilter,
    SafeRotatingFileHandler,
    setup_logger,
)
from XBrainLab.backend.utils.public_diagnostics import DiagnosticDisclosure


@pytest.fixture
def temp_log_dir():
    # Create a temporary directory for logs
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir)


def test_setup_logger(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "test.log")
    # Use unique name to ensure fresh logger
    logger_name = f"TestLogger_{uuid.uuid4()}"

    # Setup logger
    logger = setup_logger(name=logger_name, log_file=log_file, level=logging.DEBUG)

    # Check if logger is created correctly
    assert isinstance(logger, logging.Logger)
    assert logger.name == logger_name
    assert logger.level == logging.DEBUG

    # Check handlers (File + Console)
    # Note: pytest might add its own handlers, so we check if OUR handlers are present

    has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers
    )

    assert has_file_handler, "FileHandler not found"
    assert has_stream_handler, "StreamHandler not found"

    for handler in logger.handlers:
        handler.close()


def test_setup_logger_default_uses_per_user_state_directory(
    temp_log_dir,
    monkeypatch,
) -> None:
    expected_directory = Path(temp_log_dir) / "user-state" / "logs"
    monkeypatch.setattr(
        logger_module,
        "user_log_dir",
        lambda: expected_directory,
    )
    configured = setup_logger(name=f"DefaultPathLogger_{uuid.uuid4()}")

    try:
        file_handlers = [
            handler
            for handler in configured.handlers
            if isinstance(handler, logging.FileHandler)
        ]
        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename) == expected_directory / "app.log"
    finally:
        for handler in configured.handlers:
            handler.close()


def test_setup_logger_disables_file_sink_when_owner_only_access_cannot_be_verified(
    temp_log_dir,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logger_module,
        "_prepare_secure_log_directory",
        lambda _directory: (_ for _ in ()).throw(
            OSError("owner-only access unavailable")
        ),
    )

    configured = setup_logger(
        name=f"UnavailableFileSinkLogger_{uuid.uuid4()}",
        log_file=os.path.join(temp_log_dir, "unavailable.log"),
    )

    try:
        assert not any(
            isinstance(handler, logging.FileHandler) for handler in configured.handlers
        )
        configured.warning("Console logging remains available")
    finally:
        for handler in configured.handlers:
            handler.close()


def test_logger_file_creation(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "test_write.log")
    logger_name = f"WriteLogger_{uuid.uuid4()}"
    logger = setup_logger(name=logger_name, log_file=log_file)

    # Write a log message
    test_message = "This is a test log message."
    logger.info(test_message)

    # Close handlers to flush to file
    for handler in logger.handlers:
        handler.close()

    # Check if file exists and contains the message
    assert os.path.exists(log_file), f"Log file {log_file} does not exist"
    with open(log_file) as f:
        content = f.read()
        assert test_message in content


def test_logger_singleton_behavior(temp_log_dir):
    # setup_logger should return the same logger instance if called with same name
    # and not add duplicate handlers
    log_file = os.path.join(temp_log_dir, "test_singleton.log")
    name = f"SingletonLogger_{uuid.uuid4()}"

    logger1 = setup_logger(name=name, log_file=log_file)
    initial_handlers = len(logger1.handlers)

    logger2 = setup_logger(name=name, log_file=log_file)

    assert logger1 is logger2
    assert len(logger2.handlers) == initial_handlers  # Should not increase

    for handler in logger1.handlers:
        handler.close()


def test_default_logger_redacts_private_exception_path_subject_and_controls(
    temp_log_dir,
):
    log_file = os.path.join(temp_log_dir, "private-default.log")
    logger_name = f"XBrainLab.SecurityDefault.{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=log_file)
    child = logging.getLogger(f"{logger_name}.import")
    private_path = "/srv/private/subject-17/sub-P001_events.tsv"

    try:
        _raise_private_os_error(private_path)
    except OSError:
        child.exception("Data import failed for %s", private_path)

    for handler in configured.handlers:
        handler.flush()
    content = Path(log_file).read_text(encoding="utf-8")

    assert private_path not in content
    assert "/srv/private" not in content
    assert "subject-17" not in content
    assert "sub-P001" not in content
    assert "Alice" not in content
    assert "events.tsv" not in content
    assert ".tsv" in content
    assert "[REDACTED_PATH]" in content
    assert "[PATH_REF:" in content
    assert "[SUBJECT_REF:" in content
    assert "OSError" in content
    assert "FORGED" in content
    assert content.count("\n") == 1

    for handler in configured.handlers:
        handler.close()


def test_public_child_record_cannot_bypass_owned_handlers_via_root(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "child-propagation.log")
    logger_name = f"XBrainLab.ChildBoundary.{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=log_file)
    root = logging.getLogger()
    root_stream = io.StringIO()
    root_handler = logging.StreamHandler(root_stream)
    root_handler.setLevel(logging.DEBUG)
    root.addHandler(root_handler)
    child_stream = io.StringIO()
    child_handler = logging.StreamHandler(child_stream)
    child_handler.setFormatter(
        logging.Formatter("%(pathname)s | %(name)s | %(message)s")
    )
    child_handler.setLevel(logging.DEBUG)
    child = logging.getLogger(f"{logger_name}.subject_id=Mary Example")
    child.setLevel(logging.DEBUG)
    child.addHandler(child_handler)
    private_path = "/srv/clinical/sub-P001/events.tsv"

    try:
        child.debug("Private debug path %s", private_path)
    finally:
        child.removeHandler(child_handler)
        child_handler.close()
        root.removeHandler(root_handler)
        root_handler.close()

    assert configured.propagate is False
    assert root_stream.getvalue() == ""
    assert private_path not in child_stream.getvalue()
    assert "sub-P001" not in child_stream.getvalue()
    assert str(Path(__file__).resolve()) not in child_stream.getvalue()
    assert "Mary Example" not in child_stream.getvalue()
    assert "[REDACTED_PATH]" in child_stream.getvalue()
    for handler in configured.handlers:
        handler.close()


def test_setup_logger_reinstalls_descendant_factory_guard(temp_log_dir) -> None:
    previous_factory = logging.getLogRecordFactory()
    log_file = os.path.join(temp_log_dir, "factory-guard.log")
    logger_name = f"XBrainLab.FactoryGuard.{uuid.uuid4()}"
    child_stream = io.StringIO()
    child_handler = logging.StreamHandler(child_stream)

    def wrapping_replacement(*args, **kwargs):
        return previous_factory(*args, **kwargs)

    logging.setLogRecordFactory(wrapping_replacement)

    try:
        configured = setup_logger(name=logger_name, log_file=log_file)
        child = logging.getLogger(f"{logger_name}.child")
        child.addHandler(child_handler)
        private_path = "/srv/clinical/sub-P001/events.tsv"

        child.error("Could not read %s", private_path)

        assert (
            logging.getLogRecordFactory() is logger_module._protected_log_record_factory
        )
        assert private_path not in child_stream.getvalue()
        assert "sub-P001" not in child_stream.getvalue()
        assert "[REDACTED_PATH]" in child_stream.getvalue()
    finally:
        child_handler.close()
        if "child" in locals():
            child.removeHandler(child_handler)
        if "configured" in locals():
            for handler in configured.handlers:
                handler.close()
        logging.setLogRecordFactory(previous_factory)


def test_descendant_extra_metadata_is_sanitized_before_custom_handler_formats_it(
    temp_log_dir,
) -> None:
    log_file = os.path.join(temp_log_dir, "descendant-extra.log")
    logger_name = f"XBrainLab.DescendantExtra.{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=log_file)
    child = logging.getLogger(f"{logger_name}.child")
    child.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(private_context)s | %(message)s"))
    child.addHandler(handler)
    private_path = "/srv/clinical/sub-P001/events.tsv"

    try:
        child.error(
            "Import failed",
            extra={"private_context": {"path": private_path}},
        )
    finally:
        child.removeHandler(handler)
        handler.close()
        child.propagate = True
        for configured_handler in configured.handlers:
            configured_handler.close()

    rendered = stream.getvalue()
    assert private_path not in rendered
    assert "sub-P001" not in rendered
    assert "[REDACTED_PATH]" in rendered or "[UNSUPPORTED_VALUE]" in rendered


def test_logger_does_not_execute_hostile_argument_protocols(temp_log_dir) -> None:
    class HostileMapping(Mapping):
        def __iter__(self):
            raise AssertionError("hostile Mapping.__iter__ executed")

        def __len__(self):
            raise AssertionError("hostile Mapping.__len__ executed")

        def __getitem__(self, _key):
            raise AssertionError("hostile Mapping.__getitem__ executed")

        def items(self):
            raise AssertionError("hostile Mapping.items executed")

    class HostilePath:
        def __fspath__(self):
            raise AssertionError("hostile PathLike.__fspath__ executed")

    class HostileError(RuntimeError):
        @property
        def args(self):
            raise AssertionError("hostile exception args executed")

    log_file = os.path.join(temp_log_dir, "hostile-arguments.log")
    configured = setup_logger(
        name=f"XBrainLab.HostileArguments.{uuid.uuid4()}",
        log_file=log_file,
    )

    try:
        configured.error("mapping=%s", HostileMapping())
        configured.error("path=%s", HostilePath())
        configured.exception("error", exc_info=HostileError())
        for handler in configured.handlers:
            handler.flush()
    finally:
        for handler in configured.handlers:
            handler.close()

    content = Path(log_file).read_text(encoding="utf-8")
    assert content.count("[UNSUPPORTED_VALUE]") >= 2


def test_logger_does_not_execute_hostile_exception_metaclass(temp_log_dir) -> None:
    class HostileMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                raise AssertionError("hostile exception metaclass name access executed")
            return super().__getattribute__(name)

    class HostileError(Exception, metaclass=HostileMeta):
        def __str__(self) -> str:
            raise AssertionError("hostile exception string protocol executed")

    log_file = os.path.join(temp_log_dir, "hostile-metaclass.log")
    configured = setup_logger(
        name=f"XBrainLab.HostileMetaclass.{uuid.uuid4()}",
        log_file=log_file,
    )

    try:
        configured.error(
            "Unexpected boundary failure: %s",
            HostileError("/srv/Clinical Records/Mary Example"),
        )
        for handler in configured.handlers:
            handler.flush()
    finally:
        for handler in configured.handlers:
            handler.close()

    content = Path(log_file).read_text(encoding="utf-8")
    assert "Mary Example" not in content
    assert "Exception" in content


def test_descendant_factory_failure_clears_message_and_metadata(
    temp_log_dir,
    monkeypatch,
) -> None:
    log_file = os.path.join(temp_log_dir, "factory-failure.log")
    logger_name = f"XBrainLab.FactoryFailure.{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=log_file)
    child = logging.getLogger(f"{logger_name}.subject_id=Mary Example")
    child.propagate = False
    child_stream = io.StringIO()
    child_handler = logging.StreamHandler(child_stream)
    child_handler.setFormatter(
        logging.Formatter("%(pathname)s | %(name)s | %(message)s")
    )
    child.addHandler(child_handler)
    private_path = "/srv/clinical/sub-P001/events.tsv"
    monkeypatch.setattr(
        logger_module,
        "public_diagnostic_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("sanitizer unavailable")
        ),
    )

    try:
        child.error("Could not read %s", private_path)
    finally:
        child.removeHandler(child_handler)
        child_handler.close()
        child.propagate = True
        for handler in configured.handlers:
            handler.close()

    rendered = child_stream.getvalue()
    assert private_path not in rendered
    assert "Mary Example" not in rendered
    assert str(Path(__file__).resolve()) not in rendered
    assert "[DIAGNOSTIC_REDACTION_FAILED]" in rendered


def test_detailed_logger_requires_explicit_disclosure_and_strips_controls(
    temp_log_dir,
):
    log_file = os.path.join(temp_log_dir, "private-detailed.log")
    logger_name = f"DetailedLogger_{uuid.uuid4()}"
    configured = setup_logger(
        name=logger_name,
        log_file=log_file,
        disclosure=DiagnosticDisclosure.DETAILED,
    )
    private_path = "/srv/private/sub-P001/session.edf"

    assert configured.propagate is False
    configured.error(
        "Detailed failure for %s subject_id=Alice\r\nFORGED",
        private_path,
    )
    for handler in configured.handlers:
        handler.flush()
    content = Path(log_file).read_text(encoding="utf-8")

    assert private_path in content
    assert "subject_id=Alice" in content
    assert "FORGED" in content
    assert content.count("\n") == 1

    for handler in configured.handlers:
        handler.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_logger_files_are_owner_only_by_default(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "private-mode.log")
    logger_name = f"PrivateModeLogger_{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=log_file)

    mode = stat.S_IMODE(os.stat(log_file).st_mode)

    assert mode == 0o600
    for handler in configured.handlers:
        handler.close()


def test_default_log_retention_is_bounded():
    assert LOG_MAX_BYTES == 5 * 1024 * 1024
    assert LOG_BACKUP_COUNT == 5
    assert LOG_SANITIZER_INPUT_BYTES <= 128 * 1024


def test_logger_prebounds_record_before_public_sanitizer(monkeypatch) -> None:
    sanitized_inputs: list[str] = []

    def capture_input(value, **_kwargs):
        sanitized_inputs.append(value)
        return value

    monkeypatch.setattr(logger_module, "public_diagnostic_text", capture_input)
    diagnostic_filter = DiagnosticRedactionFilter(DiagnosticDisclosure.PUBLIC)
    record = logging.LogRecord(
        name="PreboundLogger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="subject_id=%s",
        args=("A" * (1024 * 1024),),
        exc_info=None,
    )

    assert diagnostic_filter.filter(record) is True
    assert sanitized_inputs
    assert any(value.startswith("subject_id=") for value in sanitized_inputs)
    assert all(
        len(value.encode("utf-8", errors="replace")) <= LOG_SANITIZER_INPUT_BYTES
        for value in sanitized_inputs
    )


def test_logger_postbounds_redaction_marker_expansion() -> None:
    private_path = '"/"'
    record = logging.LogRecord(
        name="ExpansionLogger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=" ".join(private_path for _ in range(3_000)),
        args=(),
        exc_info=None,
    )

    assert DiagnosticRedactionFilter(DiagnosticDisclosure.PUBLIC).filter(record)
    assert private_path not in str(record.msg)
    assert len(str(record.msg).encode("utf-8")) <= LOG_SANITIZER_INPUT_BYTES
    assert "[TRUNCATED]" in str(record.msg)


def test_logger_does_not_materialize_untrusted_record_objects() -> None:
    class UntrustedValue:
        def __str__(self) -> str:
            raise AssertionError("Untrusted log values must not be stringified.")

        def __repr__(self) -> str:
            raise AssertionError("Untrusted log values must not be repr-rendered.")

    class UntrustedInt(int):
        def __str__(self) -> str:
            raise AssertionError("Primitive subclasses must not be stringified.")

        def __repr__(self) -> str:
            raise AssertionError("Primitive subclasses must not be repr-rendered.")

    diagnostic_filter = DiagnosticRedactionFilter(DiagnosticDisclosure.PUBLIC)
    for value in (UntrustedValue(), UntrustedInt(7)):
        record = logging.LogRecord(
            name="BoundedObjectLogger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Unexpected value: %s",
            args=(value,),
            exc_info=None,
        )
        record.getMessage = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
            AssertionError("Diagnostic filter must not call LogRecord.getMessage().")
        )

        assert diagnostic_filter.filter(record) is True
        assert "[UNSUPPORTED_VALUE]" in str(record.msg)


def test_single_oversized_record_cannot_exceed_handler_file_bound(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "oversized-record.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"OversizedRecordLogger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info("x" * 1000)
    handler.flush()

    assert Path(log_file).stat().st_size <= 80
    backup = Path(f"{log_file}.1")
    assert not backup.exists() or backup.stat().st_size <= 80

    handler.close()
    logger.removeHandler(handler)


@pytest.mark.parametrize(
    "formatter,message",
    [
        (logging.Formatter("%(message)s | %(message)s"), "é" * 100),
        (logging.Formatter("[%(levelname)s] %(message)s"), "🧠" * 100),
    ],
)
def test_bounded_handler_honors_utf8_limit_with_real_formatter(
    temp_log_dir,
    formatter,
    message,
):
    log_file = os.path.join(temp_log_dir, f"utf8-{uuid.uuid4()}.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger(f"Utf8BoundedLogger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info(message)
    handler.flush()

    assert Path(log_file).stat().st_size <= 80
    backup = Path(f"{log_file}.1")
    assert not backup.exists() or backup.stat().st_size <= 80

    handler.close()
    logger.removeHandler(handler)


def test_bounded_handler_uses_encoded_size_across_multiple_records(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "multi-record-utf8.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"MultiRecordUtf8Logger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info("a" * 68)
    logger.info("🧠" * 3)
    handler.flush()

    assert Path(log_file).stat().st_size <= 80
    backup = Path(f"{log_file}.1")
    assert backup.exists()
    assert backup.stat().st_size <= 80

    handler.close()
    logger.removeHandler(handler)


def test_setup_logger_replaces_a_handler_with_the_wrong_disclosure(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "reconfigured.log")
    logger_name = f"ReconfiguredLogger_{uuid.uuid4()}"
    configured = setup_logger(
        name=logger_name,
        log_file=log_file,
        disclosure=DiagnosticDisclosure.DETAILED,
    )

    reconfigured = setup_logger(
        name=logger_name,
        log_file=log_file,
        disclosure=DiagnosticDisclosure.PUBLIC,
    )
    private_path = "/srv/private/sub-P001/session.edf"
    reconfigured.error("Could not read %s", private_path)
    for handler in reconfigured.handlers:
        handler.flush()

    content = Path(log_file).read_text(encoding="utf-8")
    matching_handlers = [
        handler
        for handler in reconfigured.handlers
        if isinstance(handler, SafeRotatingFileHandler)
        and handler.baseFilename == os.path.abspath(log_file)
    ]

    assert reconfigured is configured
    assert len(matching_handlers) == 1
    filters = [
        item
        for item in matching_handlers[0].filters
        if isinstance(item, DiagnosticRedactionFilter)
    ]
    assert len(filters) == 1
    assert filters[0].disclosure is DiagnosticDisclosure.PUBLIC
    assert private_path not in content
    assert "[REDACTED_PATH]" in content

    for handler in reconfigured.handlers:
        handler.close()


def test_setup_logger_removes_uncontrolled_handler_before_private_record(
    temp_log_dir,
):
    protected_log = os.path.join(temp_log_dir, "protected.log")
    uncontrolled_log = os.path.join(temp_log_dir, "uncontrolled.log")
    logger_name = f"UncontrolledHandlerLogger_{uuid.uuid4()}"
    configured = logging.getLogger(logger_name)
    uncontrolled_handler = logging.FileHandler(uncontrolled_log, encoding="utf-8")
    configured.addHandler(uncontrolled_handler)

    secured = setup_logger(name=logger_name, log_file=protected_log)
    private_path = "/srv/clinical/sub-P001/session.edf"
    secured.error("Could not read %s", private_path)
    for handler in secured.handlers:
        handler.flush()

    assert uncontrolled_handler not in secured.handlers
    assert Path(uncontrolled_log).read_text(encoding="utf-8") == ""
    protected = Path(protected_log).read_text(encoding="utf-8")
    assert private_path not in protected
    assert "[REDACTED_PATH]" in protected

    for handler in secured.handlers:
        handler.close()


def test_rollover_failure_disables_file_logging_instead_of_growing_unbounded(
    temp_log_dir,
    monkeypatch,
):
    log_file = os.path.join(temp_log_dir, "rollover-failure.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"RolloverFailureLogger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    monkeypatch.setattr(
        handler,
        "rotate",
        lambda _source, _destination: (_ for _ in ()).throw(
            PermissionError("rotation denied")
        ),
    )
    logger.info("x" * 100)
    size_after_failure = os.path.getsize(log_file)
    logger.info("y" * 100)

    assert handler.disabled_after_rollover_failure is True
    assert os.path.getsize(log_file) == size_after_failure

    handler.close()
    logger.removeHandler(handler)


def test_rollover_permission_hardening_failure_disables_file_logging(
    temp_log_dir,
    monkeypatch,
):
    from XBrainLab.backend.utils import logger as logger_module

    log_file = os.path.join(temp_log_dir, "rollover-permission.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"RolloverPermissionLogger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    monkeypatch.setattr(
        logger_module,
        "_secure_log_family",
        lambda _path, _count: (_ for _ in ()).throw(PermissionError("chmod denied")),
    )
    logger.info("x" * 100)
    size_after_failure = os.path.getsize(log_file)
    logger.info("y" * 100)

    assert handler.disabled_after_rollover_failure is True
    assert os.path.getsize(log_file) == size_after_failure

    handler.close()
    logger.removeHandler(handler)


def test_log_size_probe_failure_disables_file_logging(
    temp_log_dir,
    monkeypatch,
) -> None:
    log_file = os.path.join(temp_log_dir, "size-probe-failure.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    configured = logging.getLogger(f"SizeProbeFailureLogger_{uuid.uuid4()}")
    configured.setLevel(logging.INFO)
    configured.propagate = False
    configured.addHandler(handler)

    monkeypatch.setattr(
        os.path,
        "getsize",
        lambda _path: (_ for _ in ()).throw(PermissionError("stat denied")),
    )
    for _ in range(10):
        configured.info("x" * 30)
    handler.flush()

    assert handler.disabled_after_rollover_failure is True
    assert Path(log_file).stat().st_size <= 80

    handler.close()
    configured.removeHandler(handler)


def test_existing_log_family_is_bounded_when_handler_opens(temp_log_dir) -> None:
    log_file = Path(temp_log_dir) / "legacy.log"
    log_file.write_bytes(b"a" * 200)
    Path(f"{log_file}.1").write_bytes(b"b" * 250)
    Path(f"{log_file}.2").write_bytes(b"c" * 300)
    Path(f"{log_file}.3").write_bytes(b"d" * 350)
    Path(f"{log_file}.99").write_bytes(b"e" * 400)

    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    assert log_file.stat().st_size <= 80
    assert Path(f"{log_file}.1").stat().st_size <= 80
    assert Path(f"{log_file}.2").stat().st_size <= 80
    assert not Path(f"{log_file}.3").exists()
    assert not Path(f"{log_file}.99").exists()
    if os.name != "nt":
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in (log_file, Path(f"{log_file}.1"), Path(f"{log_file}.2"))
        )

    handler.close()


def test_idempotent_setup_rebounds_externally_oversized_active_and_backup(
    temp_log_dir,
    monkeypatch,
) -> None:
    monkeypatch.setattr(logger_module, "LOG_MAX_BYTES", 128)
    monkeypatch.setattr(logger_module, "LOG_BACKUP_COUNT", 2)
    log_file = Path(temp_log_dir) / "rebound.log"
    backup = Path(f"{log_file}.1")
    logger_name = f"ReboundLogger_{uuid.uuid4()}"
    configured = setup_logger(name=logger_name, log_file=str(log_file))

    log_file.write_bytes(b"a" * 300)
    backup.write_bytes(b"b" * 300)

    same = setup_logger(name=logger_name, log_file=str(log_file))

    assert same is configured
    assert log_file.stat().st_size <= 128
    assert backup.stat().st_size <= 128

    log_file.write_bytes(b"c" * 300)
    same.info("trigger bounded rollover")
    for handler in same.handlers:
        handler.flush()

    assert log_file.stat().st_size <= 128
    assert Path(f"{log_file}.1").stat().st_size <= 128
    for handler in same.handlers:
        handler.close()


def test_existing_legacy_log_family_is_purged_before_new_public_records(
    temp_log_dir,
) -> None:
    log_file = Path(temp_log_dir) / "legacy-private.log"
    backup = Path(f"{log_file}.1")
    private_values = (
        "/srv/clinical/sub-P001/events.tsv",
        "subject_id=Mary Example",
    )
    log_file.write_text(private_values[0], encoding="utf-8")
    backup.write_text(private_values[1], encoding="utf-8")

    configured = setup_logger(
        name=f"LegacyPrivacyMigrationLogger_{uuid.uuid4()}",
        log_file=str(log_file),
    )
    configured.info("Current import failed for %s", private_values[0])
    for handler in configured.handlers:
        handler.flush()

    family_content = "\n".join(
        path.read_text(encoding="utf-8") for path in (log_file, backup) if path.exists()
    )
    assert all(private_value not in family_content for private_value in private_values)
    assert "[REDACTED_PATH]" in family_content

    for handler in configured.handlers:
        handler.close()


def test_forged_privacy_marker_cannot_preserve_legacy_private_logs(
    temp_log_dir,
) -> None:
    log_file = Path(temp_log_dir) / "forged-marker.log"
    marker = log_file.with_name(f".{log_file.name}.privacy-v1")
    private_path = "/srv/clinical/sub-P001/events.tsv"
    log_file.write_text(private_path, encoding="utf-8")
    marker.write_bytes(b"forged" * 100)

    configured = setup_logger(
        name=f"ForgedPrivacyMarkerLogger_{uuid.uuid4()}",
        log_file=str(log_file),
    )
    for handler in configured.handlers:
        handler.flush()

    assert private_path not in log_file.read_text(encoding="utf-8")
    assert marker.read_bytes() == b"xbrainlab-public-diagnostics-v1\n"
    for handler in configured.handlers:
        handler.close()


def test_public_marker_cannot_preserve_unsanitized_legacy_private_logs(
    temp_log_dir,
) -> None:
    log_file = Path(temp_log_dir) / "known-marker.log"
    marker = log_file.with_name(f".{log_file.name}.privacy-v1")
    private_path = "/srv/clinical/sub-P001/events.tsv"
    log_file.write_text(private_path, encoding="utf-8")
    marker.write_bytes(b"xbrainlab-public-diagnostics-v1\n")

    configured = setup_logger(
        name=f"KnownMarkerLogger_{uuid.uuid4()}",
        log_file=str(log_file),
    )
    for handler in configured.handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert private_path not in content
    assert "sub-P001" not in content
    assert "[REDACTED_PATH]" in content
    for handler in configured.handlers:
        handler.close()


def test_existing_log_family_removes_noncanonical_and_excess_numeric_backups(
    temp_log_dir,
) -> None:
    log_file = Path(temp_log_dir) / "legacy-numeric.log"
    log_file.write_bytes(b"a" * 200)
    Path(f"{log_file}.1").write_bytes(b"b" * 200)
    Path(f"{log_file}.01").write_bytes(b"c" * 200)
    Path(f"{log_file}.0002").write_bytes(b"d" * 200)
    Path(f"{log_file}.3").write_bytes(b"e" * 200)
    huge_suffix = "9" * 200
    huge_backup = Path(f"{log_file}.{huge_suffix}")
    huge_backup.write_bytes(b"f" * 200)

    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=2,
        encoding="utf-8",
    )

    retained = [log_file, Path(f"{log_file}.1"), Path(f"{log_file}.2")]
    assert not Path(f"{log_file}.01").exists()
    assert not Path(f"{log_file}.0002").exists()
    assert not Path(f"{log_file}.3").exists()
    assert not huge_backup.exists()
    assert sum(path.stat().st_size for path in retained if path.exists()) <= 240

    handler.close()


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX no-follow semantics")
def test_active_log_symlink_fails_closed_without_touching_target(temp_log_dir) -> None:
    target = Path(temp_log_dir) / "outside.log"
    target.write_bytes(b"private" * 50)
    original = target.read_bytes()
    log_file = Path(temp_log_dir) / "active.log"
    log_file.symlink_to(target)

    with pytest.raises(OSError):
        SafeRotatingFileHandler(
            log_file,
            maxBytes=80,
            backupCount=1,
            encoding="utf-8",
        )

    assert log_file.is_symlink()
    assert target.read_bytes() == original


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX hard-link semantics")
def test_active_log_hard_link_fails_closed_without_touching_target(
    temp_log_dir,
) -> None:
    target = Path(temp_log_dir) / "outside-hard-link.log"
    target.write_bytes(b"private" * 50)
    target.chmod(0o640)
    original = target.read_bytes()
    original_mode = target.stat().st_mode
    log_file = Path(temp_log_dir) / "active-hard-link.log"
    os.link(target, log_file)

    with pytest.raises(OSError, match=r"regular file without links"):
        SafeRotatingFileHandler(
            log_file,
            maxBytes=80,
            backupCount=1,
            encoding="utf-8",
        )

    assert target.read_bytes() == original
    assert target.stat().st_mode == original_mode
    assert target.stat().st_nlink == 2


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX no-follow semantics")
def test_symlinked_parent_log_directory_fails_closed(temp_log_dir) -> None:
    target = Path(temp_log_dir) / "real-directory"
    target.mkdir()
    linked_directory = Path(temp_log_dir) / "linked-directory"
    linked_directory.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError, match=r"directory.*links|symlink"):
        SafeRotatingFileHandler(
            linked_directory / "app.log",
            maxBytes=80,
            backupCount=1,
            encoding="utf-8",
        )

    assert not (target / "app.log").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_log_descriptor_rejects_ineffective_owner_only_mode(
    temp_log_dir,
    monkeypatch,
) -> None:
    log_file = Path(temp_log_dir) / "mode-not-enforced.log"
    log_file.write_text("", encoding="utf-8")
    log_file.chmod(0o666)
    monkeypatch.setattr(secure_log_storage.os, "fchmod", lambda *_args: None)

    with pytest.raises(OSError, match="owner-only"):
        logger_module._open_regular_log_descriptor(
            str(log_file),
            os.O_APPEND | os.O_WRONLY,
        )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX no-follow semantics")
def test_backup_log_symlink_disables_handler_without_touching_target(
    temp_log_dir,
) -> None:
    target = Path(temp_log_dir) / "outside-backup.log"
    target.write_bytes(b"private" * 50)
    original = target.read_bytes()
    log_file = Path(temp_log_dir) / "active-backup.log"
    log_file.write_bytes(b"active")
    Path(f"{log_file}.1").symlink_to(target)

    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=80,
        backupCount=1,
        encoding="utf-8",
    )

    assert handler.disabled_after_rollover_failure is True
    assert Path(f"{log_file}.1").is_symlink()
    assert target.read_bytes() == original
    handler.close()


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX hard-link semantics")
def test_backup_log_hard_link_fails_closed_without_touching_target(
    temp_log_dir,
) -> None:
    target = Path(temp_log_dir) / "outside-backup-hard-link.log"
    target.write_bytes(b"private" * 50)
    target.chmod(0o640)
    original = target.read_bytes()
    original_mode = target.stat().st_mode
    log_file = Path(temp_log_dir) / "active-backup-hard-link.log"
    log_file.write_bytes(b"active")
    os.link(target, Path(f"{log_file}.1"))

    with pytest.raises(OSError, match=r"regular file without links"):
        SafeRotatingFileHandler(
            log_file,
            maxBytes=80,
            backupCount=1,
            encoding="utf-8",
        )

    assert target.read_bytes() == original
    assert target.stat().st_mode == original_mode
    assert target.stat().st_nlink == 2


@pytest.mark.parametrize(
    "disclosure",
    [DiagnosticDisclosure.PUBLIC, DiagnosticDisclosure.DETAILED],
)
def test_logger_redacts_control_obfuscated_secret_in_all_disclosure_modes(
    temp_log_dir,
    disclosure,
) -> None:
    log_file = os.path.join(temp_log_dir, f"obfuscated-{disclosure.value}.log")
    configured = setup_logger(
        name=f"ObfuscatedSecretLogger_{uuid.uuid4()}",
        log_file=log_file,
        disclosure=disclosure,
    )

    configured.error("pass\x1b[31mword=topsecret; retry.")
    for handler in configured.handlers:
        handler.flush()
    content = Path(log_file).read_text(encoding="utf-8")

    assert "topsecret" not in content
    assert "[REDACTED_SECRET]" in content
    for handler in configured.handlers:
        handler.close()


@pytest.mark.parametrize(
    "disclosure",
    [DiagnosticDisclosure.PUBLIC, DiagnosticDisclosure.DETAILED],
)
def test_logger_redacts_nul_and_tab_obfuscated_secrets_in_all_modes(
    temp_log_dir,
    disclosure,
) -> None:
    log_file = os.path.join(
        temp_log_dir,
        f"control-obfuscated-{disclosure.value}.log",
    )
    configured = setup_logger(
        name=f"ControlObfuscatedSecretLogger_{uuid.uuid4()}",
        log_file=log_file,
        disclosure=disclosure,
    )

    configured.error(
        "pass\x00word=nul-secret; pass\tword=tab-secret; "
        'Dige\x00st username="alice", response="deadbeef". Retry.'
    )
    for handler in configured.handlers:
        handler.flush()
    content = Path(log_file).read_text(encoding="utf-8")

    for private_value in ("nul-secret", "tab-secret", "alice", "deadbeef"):
        assert private_value not in content
    assert "[REDACTED_SECRET]" in content
    for handler in configured.handlers:
        handler.close()


def test_forged_log_record_disclosure_marker_cannot_skip_redaction(
    temp_log_dir,
) -> None:
    log_file = os.path.join(temp_log_dir, "forged-disclosure-marker.log")
    configured = setup_logger(
        name=f"ForgedDisclosureMarkerLogger_{uuid.uuid4()}",
        log_file=log_file,
    )
    private_path = "/srv/private/sub-P001/events.tsv"

    configured.error(
        "password=forged-secret; subject_id=Forged Subject; %s",
        private_path,
        extra={"_xbrainlab_diagnostic_disclosure": "public"},
    )
    for handler in configured.handlers:
        handler.flush()
    content = Path(log_file).read_text(encoding="utf-8")

    for private_value in ("forged-secret", "Forged Subject", private_path, "sub-P001"):
        assert private_value not in content
    assert "[REDACTED_SECRET]" in content
    assert "[REDACTED_PATH]" in content
    assert "[SUBJECT_REF:" in content
    for handler in configured.handlers:
        handler.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_rotated_log_files_are_owner_only(temp_log_dir):
    log_file = os.path.join(temp_log_dir, "rotated-mode.log")
    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=40,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"RotatedModeLogger_{uuid.uuid4()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info("a" * 30)
    logger.info("b" * 30)
    logger.info("c" * 30)
    handler.flush()

    paths = [Path(log_file), Path(f"{log_file}.1"), Path(f"{log_file}.2")]
    assert all(path.exists() for path in paths)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths)

    handler.close()
    logger.removeHandler(handler)


def _raise_private_os_error(private_path: str) -> None:
    raise OSError(f"Could not open {private_path}\r\nFORGED subject_id=Alice")
