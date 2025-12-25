import logging
import os
from logging.handlers import RotatingFileHandler
import sys

def setup_logger(name="XBrainLab", log_file="logs/app.log", level=logging.INFO):
    """
    Sets up a logger with both console and file handlers.
    
    Args:
        name (str): Name of the logger.
        log_file (str): Path to the log file.
        level (int): Logging level (default: logging.INFO).
        
    Returns:
        logging.Logger: Configured logger instance.
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times if setup_logger is called repeatedly
    if logger.hasHandlers():
        return logger

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File Handler (Rotating)
    # Max size 5MB, keep 5 backup files
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Create a default logger instance
logger = setup_logger()
