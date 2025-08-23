"""
File I/O utilities for various compressed and uncompressed formats.
"""

import gzip
import logging
from pathlib import Path
from typing import Optional, Union

from unlzw3 import unlzw

from ..utils.logging import get_logger


def read_gzip_file(
    file_path: Union[str, Path], loglevel: int = logging.WARNING
) -> Optional[bytes]:
    """
    Read and decompress a gzip file.

    Args:
        file_path: Path to the gzip file
        loglevel: Logging level

    Returns:
        File content as bytes, or None if error
    """
    logger = get_logger(__name__, loglevel)

    try:
        with gzip.open(file_path, "rb") as f:
            file_content = f.read()
            logger.info(f"Opened: {file_path}")
            return file_content
    except FileNotFoundError:
        logger.warning(f"File {file_path} not found")
        return None
    except gzip.BadGzipFile:
        logger.error(f"File {file_path} not a proper gzip file")
        return None


def read_zzipped_file(
    file_path: Union[str, Path], loglevel: int = logging.WARNING
) -> Optional[bytes]:
    """
    Read and decompress a Z-compressed file.

    Args:
        file_path: Path to the Z file
        loglevel: Logging level

    Returns:
        File content as bytes, or None if error
    """
    logger = get_logger(__name__, loglevel)

    try:
        with open(file_path, "rb") as f:
            compressed_content = f.read()
            file_content = unlzw(compressed_content)
            logger.info(f"Opened: {file_path}")
            return file_content
    except FileNotFoundError:
        logger.warning(f"File {file_path} not found")
        return None
    except Exception as e:
        logger.error(f"Error decompressing file {file_path}: {e}")
        return None


def read_text_file(
    file_path: Union[str, Path], loglevel: int = logging.WARNING
) -> Optional[str]:
    """
    Read a plain text file.

    Args:
        file_path: Path to the text file
        loglevel: Logging level

    Returns:
        File content as string, or None if error
    """
    logger = get_logger(__name__, loglevel)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            logger.info(f"Opened: {file_path}")
            return content
    except FileNotFoundError:
        logger.warning(f"File {file_path} not found")
        return None
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None
