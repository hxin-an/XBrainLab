import logging
import os
import shutil
import tempfile
import uuid

import pytest

from XBrainLab.backend.utils.logger import setup_logger


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
