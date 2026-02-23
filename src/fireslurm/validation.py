from pathlib import Path
import os
import logging


logger = logging.getLogger(__name__)


def path_is_readable_dir(dir: Path) -> bool:
    """
    Return True if DIR exists, is a directory, and readable.

    NOTE: This implementation has a TOCTOU "vulnerability". Be careful with
    multiple processes/threads accessing/working with these files!
    """
    logger.debug(f"Validating that {dir=!s} is a readable directory!")
    return all(
        [
            dir.exists(),
            dir.is_dir(),
            os.access(dir, os.R_OK),
        ]
    )


def path_is_writable_dir(dir: Path) -> bool:
    """
    Return True if DIR exists, is a directory, and writable.

    NOTE: A directory being writable does NOT NECESSARILY mean that it is
    readable or executable (`ls`-able)!

    NOTE: This implementation has a TOCTOU "vulnerability". Be careful with
    multiple processes/threads accessing/working with these files!
    """
    logger.debug(f"Validating that {dir=!s} is a writable directory!")
    return all(
        [
            dir.exists(),
            dir.is_dir(),
            os.access(dir, os.W_OK),
        ]
    )


def path_is_readable_file(f: Path) -> bool:
    """
    Return True if DIR exists, is a regular file, and readable.

    NOTE: This implementation has a TOCTOU "vulnerability". Be careful with
    multiple processes/threads accessing/working with these files!
    """
    logger.debug(f"Validating that {f=!s} is a readable file!")
    return all(
        [
            f.exists(),
            f.is_file(),
            os.access(f, os.R_OK),
        ]
    )


def path_is_executable_file(f: Path) -> bool:
    """
    Return True if F exists, is a regular file, is readable, and executable.

    NOTE: This implementation has a TOCTOU "vulnerability". Be careful with
    multiple processes/threads accessing/working with these files!
    """
    logger.debug(f"Validating that {f=!s} is an executable file!")
    return all(
        [
            f.exists(),
            f.is_file(),
            os.access(f, os.R_OK) and os.access(f, os.X_OK),
        ]
    )
