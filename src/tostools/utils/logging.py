"""
Logging utilities for tostools.
"""

import logging


def get_logger(name: str = __name__, level: int = logging.WARNING) -> logging.Logger:
    """
    Create and configure a logger for tostools modules.

    Args:
        name: Name for the logger (typically __name__)
        level: Logging level

    Returns:
        Configured logger instance
    """
    # Create log handler
    log_handler = logging.StreamHandler()

    # Set handler format
    log_format = logging.Formatter("[%(levelname)s] %(funcName)s: %(message)s")
    log_handler.setFormatter(log_format)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Add handler to logger
    logger.addHandler(log_handler)

    # Stop propagating to root logger
    logger.propagate = False

    return logger
