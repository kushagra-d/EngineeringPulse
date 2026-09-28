"""
EngineeringPulse Logger
=======================
Provides a consistent logging format across all project scripts.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Starting extraction...")
    logger.error("API call failed")
"""

import logging
import sys
from datetime import datetime


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create and return a configured logger.

    What this does:
        - Creates a logger with a consistent format showing timestamp, 
          module name, log level, and message.
        - Outputs to console (stdout) so you can see what's happening.
        - Each module gets its own named logger so you can tell which 
          part of the pipeline is speaking.

    Args:
        name:  Usually __name__ (the module's name, like 'ingestion.extract')
        level: How detailed the logs should be.
               INFO  = normal operation messages
               DEBUG = very detailed messages (for debugging)
               ERROR = only errors

    Returns:
        A configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Console handler — prints to terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Format: [2026-03-15 14:30:22] [ingestion.extract] [INFO] Starting extraction...
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
